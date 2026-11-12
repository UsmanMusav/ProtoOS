#!/usr/bin/env python3
"""Build the ProtoOS Live UEFI ISO without external ISO authoring tools."""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import shutil
import stat
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
KERNEL_REPOSITORY = "https://github.com/RedMoonnn/MicroLinux.git"
KERNEL_COMMIT = "00a515d49c59f31c9c5e258928ac368012ac1ea6"
KERNEL_SHA256 = "dca8ba50d3ac9867073b54b7d694d019c9e048560102ddd4f9b2563df00686fd"
LIMINE_REPOSITORY = "https://github.com/limine-bootloader/limine.git"
LIMINE_COMMIT = "aad3edd370955449717a334f0289dee10e2c5f01"  # Limine 8.7.0 binary release
LIMINE_UEFI_CD_SHA256 = "0ea0aa408c464014a306840acc843dc564e54f602b2077852ceb34178488bd03"
EPOCH = 1794528000  # 2026-11-12 00:00:00 UTC, a stable ProtoOS build timestamp.
SECTOR = 2048


def fail(message: str) -> None:
    raise RuntimeError(message)


def run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def obtain_pinned_file(repository: str, branch: str, commit: str, filename: str, expected_sha256: str, cache_name: str) -> Path:
    """Clone one fixed upstream revision and validate the file used in the ISO."""
    source = BUILD / "vendor" / cache_name
    result = source / filename
    if not result.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            shutil.rmtree(source)
        run(["git", "clone", "--depth", "1", "--branch", branch, repository, str(source)])
        run(["git", "fetch", "--depth", "1", "origin", commit], cwd=source)
        run(["git", "checkout", "--detach", commit], cwd=source)
    actual = sha256(result)
    if actual != expected_sha256:
        fail(
            f"The checksum of {filename} does not match its pinned value. "
            f"Expected {expected_sha256}, got {actual}. Remove {source} and retry."
        )
    return result


def obtain_kernel() -> Path:
    return obtain_pinned_file(
        KERNEL_REPOSITORY, "main", KERNEL_COMMIT, "bzImage", KERNEL_SHA256, "micro-linux"
    )


def obtain_limine_uefi_cd() -> Path:
    return obtain_pinned_file(
        LIMINE_REPOSITORY, "v8.x-binary", LIMINE_COMMIT, "limine-uefi-cd.bin",
        LIMINE_UEFI_CD_SHA256, "limine"
    )


def pad4(buffer: bytearray) -> None:
    buffer.extend(b"\0" * ((-len(buffer)) % 4))


def cpio_entry(
    archive: bytearray,
    name: str,
    mode: int,
    data: bytes = b"",
    *,
    inode: int,
    nlink: int = 1,
    rdev_major: int = 0,
    rdev_minor: int = 0,
) -> None:
    raw_name = name.encode("utf-8") + b"\0"
    fields = [inode, mode, 0, 0, nlink, EPOCH, len(data), 0, 0, rdev_major, rdev_minor, len(raw_name), 0]
    header = b"070701" + b"".join(f"{field:08x}".encode("ascii") for field in fields)
    if len(header) != 110:
        fail("Internal error while writing a newc header.")
    archive.extend(header)
    archive.extend(raw_name)
    pad4(archive)
    archive.extend(data)
    pad4(archive)


def build_initramfs() -> Path:
    output = BUILD / "initramfs" / "INITRD.IMG"
    output.parent.mkdir(parents=True, exist_ok=True)
    busybox = Path("/usr/bin/busybox")
    if not busybox.exists():
        fail("A static BusyBox binary is required at /usr/bin/busybox.")

    init = b"""#!/bin/busybox sh
export PATH=/bin
/bin/busybox --install -s /bin
/bin/mount -t proc proc /proc
/bin/mount -t sysfs sysfs /sys
/bin/clear
echo '================================================'
echo '             ProtoOS Live 0.1.2'
echo '       Minimal Linux environment is ready'
echo '================================================'
echo ''
echo 'Useful commands: help, sysinfo, ls, uname -a, poweroff'
echo ''
. /etc/profile
exec /bin/sh
"""
    profile = b"""help() {
  echo 'ProtoOS Live commands:'
  echo '  sysinfo      Show kernel and memory information'
  echo '  uname -a     Show Linux kernel version'
  echo '  poweroff     Shut down the virtual machine'
}
sysinfo() {
  echo 'ProtoOS Live 0.1.2'
  uname -a
  echo
  echo 'Memory:'
  grep -E 'MemTotal|MemFree' /proc/meminfo
}
export PS1='ProtoOS# '
"""
    os_release = b"""NAME=ProtoOS
VERSION=0.1.2
ID=protoos
PRETTY_NAME=\"ProtoOS Live 0.1.2\"
HOME_URL=\"https://github.com/UsmanMusav/ProtoOS\"
"""
    archive = bytearray()
    inode = 1
    for directory in ("bin", "dev", "proc", "sys", "tmp", "etc"):
        cpio_entry(archive, directory, stat.S_IFDIR | 0o755, inode=inode, nlink=2)
        inode += 1
    cpio_entry(archive, "bin/busybox", stat.S_IFREG | 0o755, busybox.read_bytes(), inode=inode)
    inode += 1
    cpio_entry(archive, "init", stat.S_IFREG | 0o755, init, inode=inode)
    inode += 1
    cpio_entry(archive, "etc/profile", stat.S_IFREG | 0o644, profile, inode=inode)
    inode += 1
    cpio_entry(archive, "etc/os-release", stat.S_IFREG | 0o644, os_release, inode=inode)
    inode += 1
    for name, major, minor in (
        ("console", 5, 1), ("tty", 5, 0), ("null", 1, 3), ("zero", 1, 5),
        ("random", 1, 8), ("urandom", 1, 9),
    ):
        cpio_entry(archive, f"dev/{name}", stat.S_IFCHR | 0o600, inode=inode,
                   rdev_major=major, rdev_minor=minor)
        inode += 1
    cpio_entry(archive, "TRAILER!!!", 0, inode=inode, nlink=1)
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=EPOCH) as compressed:
            compressed.write(archive)
    return output


def limine_config() -> bytes:
    """Describe the root ISO-9660 files to Limine's Linux protocol implementation."""
    return b"""timeout: 0
default_entry: 1
verbose: yes

/ProtoOS Live 0.1.2
    protocol: linux
    path: boot():/KERNEL.EFI
    module_path: boot():/INITRD.IMG
    cmdline: console=tty0
"""


def both16(value: int) -> bytes:
    return struct.pack("<H", value) + struct.pack(">H", value)


def both32(value: int) -> bytes:
    return struct.pack("<I", value) + struct.pack(">I", value)


def iso_datetime() -> bytes:
    moment = dt.datetime.fromtimestamp(EPOCH, tz=dt.timezone.utc)
    # ISO-9660 uses 16 ASCII digits followed by one signed GMT offset byte.
    return moment.strftime("%Y%m%d%H%M%S00").encode("ascii") + b"\0"


def iso_record_datetime() -> bytes:
    moment = dt.datetime.fromtimestamp(EPOCH, tz=dt.timezone.utc)
    return bytes((moment.year - 1900, moment.month, moment.day, moment.hour, moment.minute, moment.second, 0))


def iso_directory_record(identifier: bytes, extent: int, size: int, flags: int) -> bytes:
    padding = b"\0" if len(identifier) % 2 == 0 else b""
    length = 33 + len(identifier) + len(padding)
    return (
        bytes((length, 0)) + both32(extent) + both32(size) + iso_record_datetime()
        + bytes((flags, 0, 0)) + both16(1) + bytes((len(identifier),)) + identifier + padding
    )


def sector_count(content: bytes) -> int:
    return (len(content) + SECTOR - 1) // SECTOR


def write_extent(stream, content: bytes) -> None:
    stream.write(content)
    stream.write(b"\0" * ((-len(content)) % SECTOR))


def boot_catalog(efi_lba: int) -> bytes:
    """Create a UEFI El Torito catalog accepted by Hyper-V firmware.

    The initial entry is a UEFI entry and is mirrored in an EFI section entry.
    This supports both firmware implementations that use the validation/initial
    pair and implementations that scan the extension sections.
    """
    catalog = bytearray(SECTOR)
    catalog[0] = 1  # validation entry
    catalog[1] = 0xEF  # EFI platform identifier
    catalog[4:4 + len(b"ProtoOS UEFI Live")] = b"ProtoOS UEFI Live"
    catalog[30] = 0x55
    catalog[31] = 0xAA
    checksum = sum(struct.unpack("<16H", catalog[:32])) & 0xFFFF
    struct.pack_into("<H", catalog, 28, (-checksum) & 0xFFFF)

    catalog[32] = 0x88  # bootable initial/default entry
    catalog[33] = 0x00  # no emulation
    struct.pack_into("<H", catalog, 38, 4)
    struct.pack_into("<I", catalog, 40, efi_lba)

    catalog[64] = 0x91  # final section header
    catalog[65] = 0xEF  # EFI platform identifier
    struct.pack_into("<H", catalog, 66, 1)
    catalog[68:68 + len(b"UEFI x86_64")] = b"UEFI x86_64"
    catalog[96] = 0x88  # bootable section entry
    catalog[97] = 0x00  # no emulation
    struct.pack_into("<H", catalog, 102, 4)
    struct.pack_into("<I", catalog, 104, efi_lba)
    return bytes(catalog)


def build_iso(limine_cd: bytes, config: bytes, kernel: bytes, initramfs: bytes, destination: Path) -> None:
    """Write a UEFI ISO-9660 image with Limine's official FAT12 CD boot image."""
    root_lba = 19
    catalog_lba = 20
    path_le_lba = 21
    path_be_lba = 22
    boot_directory_lba = 23
    limine_cd_lba = 24
    config_lba = limine_cd_lba + sector_count(limine_cd)
    kernel_lba = config_lba + sector_count(config)
    initramfs_lba = kernel_lba + sector_count(kernel)
    readme_lba = initramfs_lba + sector_count(initramfs)
    volume_sectors = readme_lba + 1

    # Two ISO path-table records: root (10 bytes) and BOOT (12 bytes).
    path_table_size = 22
    pvd = bytearray(SECTOR)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[6] = 1
    pvd[8:40] = b"PROTOOS".ljust(32, b" ")
    pvd[40:72] = b"PROTOOS_LIVE_0_1_2".ljust(32, b" ")
    pvd[80:88] = both32(volume_sectors)
    pvd[120:124] = both16(1)
    pvd[124:128] = both16(1)
    pvd[128:132] = both16(SECTOR)
    pvd[132:140] = both32(path_table_size)
    struct.pack_into("<I", pvd, 140, path_le_lba)
    struct.pack_into("<I", pvd, 144, 0)
    struct.pack_into(">I", pvd, 148, path_be_lba)
    struct.pack_into(">I", pvd, 152, 0)
    pvd[156:190] = iso_directory_record(b"\0", root_lba, SECTOR, 2)
    pvd[190:318] = b"ProtoOS".ljust(128, b" ")
    pvd[318:446] = b"ProtoOS Live".ljust(128, b" ")
    pvd[446:574] = b"ProtoOS".ljust(128, b" ")
    pvd[574:702] = b"ProtoOS".ljust(128, b" ")
    pvd[813:830] = iso_datetime()
    pvd[830:847] = iso_datetime()
    pvd[847:864] = b"0" * 16 + b"\0"
    pvd[864:881] = iso_datetime()
    pvd[881] = 1

    boot_record = bytearray(SECTOR)
    boot_record[0] = 0
    boot_record[1:6] = b"CD001"
    boot_record[6] = 1
    boot_record[7:39] = b"EL TORITO SPECIFICATION".ljust(32, b" ")
    struct.pack_into("<I", boot_record, 71, catalog_lba)

    terminator = bytearray(SECTOR)
    terminator[0] = 255
    terminator[1:6] = b"CD001"
    terminator[6] = 1

    root_directory = bytearray(SECTOR)
    root_records = (
        iso_directory_record(b"\0", root_lba, SECTOR, 2),
        iso_directory_record(b"\1", root_lba, SECTOR, 2),
        iso_directory_record(b"BOOT", boot_directory_lba, SECTOR, 2),
        iso_directory_record(b"LIMINE.CONF;1", config_lba, len(config), 0),
        iso_directory_record(b"KERNEL.EFI;1", kernel_lba, len(kernel), 0),
        iso_directory_record(b"INITRD.IMG;1", initramfs_lba, len(initramfs), 0),
        iso_directory_record(b"README.TXT;1", readme_lba, SECTOR, 0),
    )
    cursor = 0
    for record in root_records:
        root_directory[cursor:cursor + len(record)] = record
        cursor += len(record)

    boot_directory = bytearray(SECTOR)
    boot_records = (
        iso_directory_record(b"\0", boot_directory_lba, SECTOR, 2),
        iso_directory_record(b"\1", root_lba, SECTOR, 2),
        iso_directory_record(b"LIMINE-UEFI-CD.BIN;1", limine_cd_lba, len(limine_cd), 0),
    )
    cursor = 0
    for record in boot_records:
        boot_directory[cursor:cursor + len(record)] = record
        cursor += len(record)

    path_le = bytearray(SECTOR)
    path_le[0:10] = bytes((1, 0)) + struct.pack("<I", root_lba) + struct.pack("<H", 1) + b"\0\0"
    path_le[10:22] = bytes((4, 0)) + struct.pack("<I", boot_directory_lba) + struct.pack("<H", 1) + b"BOOT"
    path_be = bytearray(SECTOR)
    path_be[0:10] = bytes((1, 0)) + struct.pack(">I", root_lba) + struct.pack(">H", 1) + b"\0\0"
    path_be[10:22] = bytes((4, 0)) + struct.pack(">I", boot_directory_lba) + struct.pack(">H", 1) + b"BOOT"

    readme = (
        "ProtoOS Live 0.1.2\r\n"
        "UEFI x86_64 Linux live image.\r\n"
        "Secure Boot must be disabled for this development build.\r\n"
    ).encode("ascii")
    for label, buffer in (("PVD", pvd), ("boot record", boot_record), ("terminator", terminator),
                          ("root directory", root_directory), ("boot directory", boot_directory),
                          ("path table LE", path_le), ("path table BE", path_be)):
        if len(buffer) != SECTOR:
            fail(f"Internal {label} length is {len(buffer)}, expected {SECTOR}.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as iso:
        iso.write(b"\0" * (16 * SECTOR))
        iso.write(pvd)
        iso.write(boot_record)
        iso.write(terminator)
        iso.write(root_directory)
        iso.write(boot_catalog(limine_cd_lba))
        iso.write(path_le)
        iso.write(path_be)
        iso.write(boot_directory)
        write_extent(iso, limine_cd)
        write_extent(iso, config)
        write_extent(iso, kernel)
        write_extent(iso, initramfs)
        write_extent(iso, readme)
    if destination.stat().st_size != volume_sectors * SECTOR:
        fail("Internal ISO size check failed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "ProtoOS-0.1.2-x86_64.iso")
    args = parser.parse_args()
    try:
        kernel = obtain_kernel()
        limine_cd = obtain_limine_uefi_cd()
        initramfs = build_initramfs()
        build_iso(limine_cd.read_bytes(), limine_config(), kernel.read_bytes(), initramfs.read_bytes(), args.output)
        print(f"Built {args.output} ({args.output.stat().st_size / 1024 / 1024:.1f} MiB)")
        print(f"SHA256 {sha256(args.output)}")
    except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
