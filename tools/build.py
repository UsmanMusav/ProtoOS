#!/usr/bin/env python3
"""Build the ProtoOS Live UEFI ISO without external ISO/bootloader utilities."""
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
LIMINE_SHA256 = "51ca2b20ed14bbc678a396cdfb0c1d941acbc155cabebc9bfafabe4cdae1be73"
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


def obtain_kernel() -> Path:
    """Fetch one pinned Linux EFI-stub binary and verify it before use."""
    source = BUILD / "vendor" / "micro-linux"
    kernel = source / "bzImage"
    if not kernel.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            shutil.rmtree(source)
        # A shallow checkout at a full commit makes the input deterministic.
        run(["git", "clone", "--depth", "1", KERNEL_REPOSITORY, str(source)])
        run(["git", "fetch", "--depth", "1", "origin", KERNEL_COMMIT], cwd=source)
        run(["git", "checkout", "--detach", KERNEL_COMMIT], cwd=source)
    actual = sha256(kernel)
    if actual != KERNEL_SHA256:
        fail(
            "The fetched Linux kernel checksum does not match the pinned value. "
            f"Expected {KERNEL_SHA256}, got {actual}. Remove build/vendor/micro-linux and retry."
        )
    return kernel


def obtain_limine() -> Path:
    """Fetch a pinned, upstream Limine UEFI loader and verify it before use."""
    source = BUILD / "vendor" / "limine"
    loader = source / "BOOTX64.EFI"
    if not loader.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            shutil.rmtree(source)
        run(["git", "clone", "--depth", "1", "--branch", "v8.x-binary", LIMINE_REPOSITORY, str(source)])
        run(["git", "fetch", "--depth", "1", "origin", LIMINE_COMMIT], cwd=source)
        run(["git", "checkout", "--detach", LIMINE_COMMIT], cwd=source)
    actual = sha256(loader)
    if actual != LIMINE_SHA256:
        fail(
            "The fetched Limine loader checksum does not match the pinned value. "
            f"Expected {LIMINE_SHA256}, got {actual}. Remove build/vendor/limine and retry."
        )
    return loader


def limine_config() -> bytes:
    """Describe the Linux kernel and initramfs to the UEFI boot manager."""
    return b"""timeout: 0
default_entry: 1
verbose: yes

/ProtoOS Live 0.1.1
    protocol: linux
    path: boot():/EFI/BOOT/KERNEL.EFI
    module_path: boot():/EFI/BOOT/INITRD.IMG
    cmdline: console=tty0
"""


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
echo '             ProtoOS Live 0.1.1'
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
  echo 'ProtoOS Live 0.1.1'
  uname -a
  echo
  echo 'Memory:'
  grep -E 'MemTotal|MemFree' /proc/meminfo
}
export PS1='ProtoOS# '
"""
    os_release = b"""NAME=ProtoOS
VERSION=0.1.1
ID=protoos
PRETTY_NAME=\"ProtoOS Live 0.1.1\"
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


def short_name(name: str) -> bytes:
    """Return a strict 8.3 uppercase FAT directory name."""
    if "." in name:
        base, extension = name.rsplit(".", 1)
    else:
        base, extension = name, ""
    encoded = (base.upper().encode("ascii")[:8].ljust(8, b" ") +
               extension.upper().encode("ascii")[:3].ljust(3, b" "))
    if any(byte < 32 for byte in encoded):
        fail(f"Invalid FAT name: {name}")
    return encoded


def fat_dir_entry(name: str, attributes: int, first_cluster: int, size: int = 0) -> bytes:
    entry = bytearray(32)
    if name == ".":
        entry[0] = 0x2E
        entry[1:11] = b" " * 10
    elif name == "..":
        entry[0:2] = b".."
        entry[2:11] = b" " * 9
    else:
        entry[:11] = short_name(name)
    entry[11] = attributes
    struct.pack_into("<H", entry, 20, (first_cluster >> 16) & 0xFFFF)
    struct.pack_into("<H", entry, 26, first_cluster & 0xFFFF)
    struct.pack_into("<I", entry, 28, size)
    return bytes(entry)


def write_fat16(files: dict[str, bytes]) -> bytes:
    """Make a small FAT16 image suitable for an El Torito UEFI boot entry."""
    bytes_per_sector = 512
    sectors_per_cluster = 4
    reserved_sectors = 1
    fat_count = 2
    root_entries = 512
    root_sectors = (root_entries * 32 + bytes_per_sector - 1) // bytes_per_sector
    total_sectors = 32768  # 16 MiB

    fat_sectors = 1
    while True:
        data_sectors = total_sectors - reserved_sectors - fat_count * fat_sectors - root_sectors
        clusters = data_sectors // sectors_per_cluster
        needed = ((clusters + 2) * 2 + bytes_per_sector - 1) // bytes_per_sector
        if needed == fat_sectors:
            break
        fat_sectors = needed
    if not 4085 <= clusters < 65525:
        fail("FAT image geometry did not result in FAT16.")

    image = bytearray(total_sectors * bytes_per_sector)
    boot = memoryview(image)[:bytes_per_sector]
    boot[:3] = b"\xeb\x3c\x90"
    boot[3:11] = b"PROTOOS "
    struct.pack_into("<H", boot, 11, bytes_per_sector)
    boot[13] = sectors_per_cluster
    struct.pack_into("<H", boot, 14, reserved_sectors)
    boot[16] = fat_count
    struct.pack_into("<H", boot, 17, root_entries)
    struct.pack_into("<H", boot, 19, total_sectors)
    boot[21] = 0xF8
    struct.pack_into("<H", boot, 22, fat_sectors)
    struct.pack_into("<H", boot, 24, 32)
    struct.pack_into("<H", boot, 26, 64)
    struct.pack_into("<I", boot, 28, 0)
    struct.pack_into("<I", boot, 32, 0)
    boot[36] = 0x80
    boot[38] = 0x29
    struct.pack_into("<I", boot, 39, 0x50524F54)
    boot[43:54] = b"PROTOOS EFI"
    boot[54:62] = b"FAT16   "
    boot[510:512] = b"\x55\xaa"

    fat_offset = reserved_sectors * bytes_per_sector
    root_offset = (reserved_sectors + fat_count * fat_sectors) * bytes_per_sector
    data_offset = (reserved_sectors + fat_count * fat_sectors + root_sectors) * bytes_per_sector
    cluster_bytes = sectors_per_cluster * bytes_per_sector
    fat = bytearray(fat_sectors * bytes_per_sector)
    struct.pack_into("<H", fat, 0, 0xFFF8)
    struct.pack_into("<H", fat, 2, 0xFFFF)
    next_cluster = 2

    def allocate(data: bytes) -> int:
        nonlocal next_cluster
        count = max(1, (len(data) + cluster_bytes - 1) // cluster_bytes)
        start = next_cluster
        if start + count > clusters + 2:
            fail("The EFI boot image is too large.")
        for index in range(count):
            current = start + index
            following = 0xFFFF if index + 1 == count else current + 1
            struct.pack_into("<H", fat, current * 2, following)
            begin = data_offset + (current - 2) * cluster_bytes
            piece = data[index * cluster_bytes:(index + 1) * cluster_bytes]
            image[begin:begin + len(piece)] = piece
        next_cluster += count
        return start

    efi_cluster = allocate(b"\0" * cluster_bytes)
    boot_cluster = allocate(b"\0" * cluster_bytes)
    file_clusters: dict[str, int] = {}
    for path, content in files.items():
        file_clusters[path] = allocate(content)

    image[root_offset:root_offset + 32] = fat_dir_entry("EFI", 0x10, efi_cluster)

    efi_directory = bytearray(cluster_bytes)
    efi_directory[0:32] = fat_dir_entry(".", 0x10, efi_cluster)
    efi_directory[32:64] = fat_dir_entry("..", 0x10, 0)
    efi_directory[64:96] = fat_dir_entry("BOOT", 0x10, boot_cluster)
    efi_start = data_offset + (efi_cluster - 2) * cluster_bytes
    image[efi_start:efi_start + cluster_bytes] = efi_directory

    boot_directory = bytearray(cluster_bytes)
    boot_directory[0:32] = fat_dir_entry(".", 0x10, boot_cluster)
    boot_directory[32:64] = fat_dir_entry("..", 0x10, efi_cluster)
    offset = 64
    for path, content in files.items():
        filename = path.rsplit("/", 1)[-1]
        boot_directory[offset:offset + 32] = fat_dir_entry(filename, 0x20, file_clusters[path], len(content))
        offset += 32
    boot_start = data_offset + (boot_cluster - 2) * cluster_bytes
    image[boot_start:boot_start + cluster_bytes] = boot_directory

    for copy in range(fat_count):
        start = fat_offset + copy * len(fat)
        image[start:start + len(fat)] = fat
    return bytes(image)


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
    return bytes((length, 0)) + both32(extent) + both32(size) + iso_record_datetime() + bytes((flags, 0, 0)) + both16(1) + bytes((len(identifier),)) + identifier + padding


def boot_catalog(efi_lba: int) -> bytes:
    """Create a single-platform UEFI El Torito catalog.

    Hyper-V's firmware reads the UEFI platform identifier from the validation
    entry and boots the initial entry.  Keeping this as a single EFI catalog,
    instead of a legacy default followed by an EFI extension section, avoids a
    firmware-specific ambiguity observed in the first ProtoOS test image.
    """
    catalog = bytearray(SECTOR)
    catalog[0] = 1  # validation entry
    catalog[1] = 0xEF  # EFI platform identifier
    catalog[4:4 + len(b"ProtoOS UEFI Live")] = b"ProtoOS UEFI Live"
    # The validation entry's 16-bit little-endian word sum must be zero.
    catalog[30] = 0x55
    catalog[31] = 0xAA
    checksum = sum(struct.unpack("<16H", catalog[:32])) & 0xFFFF
    struct.pack_into("<H", catalog, 28, (-checksum) & 0xFFFF)

    catalog[32] = 0x88  # bootable initial/default entry
    catalog[33] = 0x00  # no emulation
    struct.pack_into("<H", catalog, 38, 4)  # UEFI mounts the complete FAT image
    struct.pack_into("<I", catalog, 40, efi_lba)
    return bytes(catalog)


def build_iso(efi_image: bytes, destination: Path) -> None:
    root_lba = 19
    catalog_lba = 20
    path_le_lba = 21
    path_be_lba = 22
    efi_lba = 23
    efi_sectors = len(efi_image) // SECTOR
    if len(efi_image) % SECTOR:
        fail("EFI image must be ISO-sector aligned.")
    readme_lba = efi_lba + efi_sectors
    volume_sectors = readme_lba + 1

    pvd = bytearray(SECTOR)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[6] = 1
    pvd[8:40] = b"PROTOOS".ljust(32, b" ")
    pvd[40:72] = b"PROTOOS_LIVE_0_1_1".ljust(32, b" ")
    pvd[80:88] = both32(volume_sectors)
    pvd[120:124] = both16(1)
    pvd[124:128] = both16(1)
    pvd[128:132] = both16(SECTOR)
    pvd[132:140] = both32(10)
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
    records = [
        iso_directory_record(b"\0", root_lba, SECTOR, 2),
        iso_directory_record(b"\1", root_lba, SECTOR, 2),
        iso_directory_record(b"README.TXT;1", readme_lba, SECTOR, 0),
    ]
    cursor = 0
    for record in records:
        root_directory[cursor:cursor + len(record)] = record
        cursor += len(record)

    path_le = bytearray(SECTOR)
    path_le[:10] = bytes((1, 0)) + struct.pack("<I", root_lba) + struct.pack("<H", 1) + b"\0" + b"\0"
    path_be = bytearray(SECTOR)
    path_be[:10] = bytes((1, 0)) + struct.pack(">I", root_lba) + struct.pack(">H", 1) + b"\0" + b"\0"
    readme = ("ProtoOS Live 0.1.1\r\n"
              "UEFI x86_64 Linux live image.\r\n"
              "Secure Boot must be disabled for this development build.\r\n").encode("ascii")

    for label, buffer in (("PVD", pvd), ("boot record", boot_record), ("terminator", terminator),
                          ("root directory", root_directory), ("path table LE", path_le),
                          ("path table BE", path_be)):
        if len(buffer) != SECTOR:
            fail(f"Internal {label} length is {len(buffer)}, expected {SECTOR}.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as iso:
        iso.write(b"\0" * (16 * SECTOR))
        iso.write(pvd)
        iso.write(boot_record)
        iso.write(terminator)
        iso.write(root_directory)
        iso.write(boot_catalog(efi_lba))
        iso.write(path_le)
        iso.write(path_be)
        iso.write(efi_image)
        iso.write(readme.ljust(SECTOR, b"\0"))
    if destination.stat().st_size != volume_sectors * SECTOR:
        fail("Internal ISO size check failed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "ProtoOS-0.1.1-x86_64.iso")
    args = parser.parse_args()
    try:
        kernel = obtain_kernel()
        limine = obtain_limine()
        initramfs = build_initramfs()
        efi = write_fat16({
            "EFI/BOOT/BOOTX64.EFI": limine.read_bytes(),
            "EFI/BOOT/LIMINE.CFG": limine_config(),
            "EFI/BOOT/KERNEL.EFI": kernel.read_bytes(),
            "EFI/BOOT/INITRD.IMG": initramfs.read_bytes(),
        })
        build_iso(efi, args.output)
        print(f"Built {args.output} ({args.output.stat().st_size / 1024 / 1024:.1f} MiB)")
        print(f"SHA256 {sha256(args.output)}")
    except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
