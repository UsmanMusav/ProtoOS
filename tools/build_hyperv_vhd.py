#!/usr/bin/env python3
"""Build a fixed VHD with a GPT EFI System Partition for Hyper-V Generation 2."""
from __future__ import annotations

import argparse
import binascii
import datetime as dt
import hashlib
import struct
import sys
from pathlib import Path

from build import BUILD, EPOCH, obtain_kernel, obtain_pinned_file, build_initramfs, fail

ROOT = Path(__file__).resolve().parents[1]
LIMINE_REPOSITORY = "https://github.com/limine-bootloader/limine.git"
LIMINE_COMMIT = "aad3edd370955449717a334f0289dee10e2c5f01"
LIMINE_BOOTX64_SHA256 = "51ca2b20ed14bbc678a396cdfb0c1d941acbc155cabebc9bfafabe4cdae1be73"
SECTOR = 512
VIRTUAL_SIZE = 32 * 1024 * 1024
ESP_FIRST_LBA = 2048
ESP_SECTORS = 32768  # 16 MiB


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def obtain_limine_bootx64() -> Path:
    return obtain_pinned_file(
        LIMINE_REPOSITORY, "v8.x-binary", LIMINE_COMMIT, "BOOTX64.EFI",
        LIMINE_BOOTX64_SHA256, "limine"
    )


def limine_config() -> bytes:
    return b"""timeout: 0
default_entry: 1
verbose: yes

/ProtoOS Hyper-V Live 0.2.1
    protocol: linux
    path: boot():/EFI/BOOT/KERNEL.EFI
    module_path: boot():/EFI/BOOT/INITRD.IMG
    cmdline: console=tty0
"""


def short_name(name: str) -> bytes:
    if "." in name:
        base, extension = name.rsplit(".", 1)
    else:
        base, extension = name, ""
    if len(base) > 8 or len(extension) > 3:
        fail(f"FAT 8.3 name is too long: {name}")
    return base.upper().encode("ascii").ljust(8, b" ") + extension.upper().encode("ascii").ljust(3, b" ")


def fat_entry(name: str, attributes: int, cluster: int, size: int = 0) -> bytes:
    entry = bytearray(32)
    if name == ".":
        entry[0] = 0x2E
        entry[1:11] = b" " * 10
    elif name == "..":
        entry[:2] = b".."
        entry[2:11] = b" " * 9
    else:
        entry[:11] = short_name(name)
    entry[11] = attributes
    struct.pack_into("<H", entry, 20, cluster >> 16)
    struct.pack_into("<H", entry, 26, cluster & 0xFFFF)
    struct.pack_into("<I", entry, 28, size)
    return bytes(entry)


def fat_lfn_checksum(short: bytes) -> int:
    """Return the VFAT checksum associated with an 11-byte short name."""
    checksum = 0
    for value in short:
        checksum = (((checksum & 1) << 7) + (checksum >> 1) + value) & 0xFF
    return checksum


def fat_lfn_entry(name: str, short: bytes) -> bytes:
    """Write the one VFAT long-name entry needed for limine.conf."""
    units = list(name.encode("utf-16le"))
    if len(units) % 2:
        fail("Invalid UTF-16 FAT long filename.")
    characters = [units[index] | (units[index + 1] << 8) for index in range(0, len(units), 2)]
    characters.append(0)
    if len(characters) > 13:
        fail(f"FAT long filename is too long: {name}")
    characters.extend([0xFFFF] * (13 - len(characters)))
    entry = bytearray(32)
    entry[0] = 0x41  # final entry + ordinal 1
    entry[11] = 0x0F
    entry[12] = 0
    entry[13] = fat_lfn_checksum(short)
    struct.pack_into("<H", entry, 26, 0)
    for offset, character in zip((1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30), characters):
        struct.pack_into("<H", entry, offset, character)
    return bytes(entry)


def fat16_esp(files: dict[str, bytes]) -> bytes:
    """Make a simple FAT16 ESP containing /EFI/BOOT and its boot payload."""
    bytes_per_sector = SECTOR
    sectors_per_cluster = 4
    reserved = 1
    fat_count = 2
    root_entries = 512
    root_sectors = root_entries * 32 // bytes_per_sector
    total_sectors = ESP_SECTORS
    fat_sectors = 1
    while True:
        data_sectors = total_sectors - reserved - fat_count * fat_sectors - root_sectors
        clusters = data_sectors // sectors_per_cluster
        required = ((clusters + 2) * 2 + bytes_per_sector - 1) // bytes_per_sector
        if required == fat_sectors:
            break
        fat_sectors = required
    if not 4085 <= clusters < 65525:
        fail("ESP geometry is not FAT16.")

    image = bytearray(total_sectors * bytes_per_sector)
    boot = memoryview(image)[:bytes_per_sector]
    boot[:3] = b"\xeb\x3c\x90"
    boot[3:11] = b"PROTOOS "
    struct.pack_into("<H", boot, 11, bytes_per_sector)
    boot[13] = sectors_per_cluster
    struct.pack_into("<H", boot, 14, reserved)
    boot[16] = fat_count
    struct.pack_into("<H", boot, 17, root_entries)
    struct.pack_into("<H", boot, 19, total_sectors)
    boot[21] = 0xF8
    struct.pack_into("<H", boot, 22, fat_sectors)
    struct.pack_into("<H", boot, 24, 63)
    struct.pack_into("<H", boot, 26, 16)
    struct.pack_into("<I", boot, 28, ESP_FIRST_LBA)
    boot[36] = 0x80
    boot[38] = 0x29
    struct.pack_into("<I", boot, 39, 0x50524F54)
    boot[43:54] = b"PROTOOS EFI"
    boot[54:62] = b"FAT16   "
    boot[510:512] = b"\x55\xaa"

    fat_offset = reserved * bytes_per_sector
    root_offset = (reserved + fat_count * fat_sectors) * bytes_per_sector
    data_offset = (reserved + fat_count * fat_sectors + root_sectors) * bytes_per_sector
    cluster_bytes = sectors_per_cluster * bytes_per_sector
    fat = bytearray(fat_sectors * bytes_per_sector)
    struct.pack_into("<H", fat, 0, 0xFFF8)
    struct.pack_into("<H", fat, 2, 0xFFFF)
    next_cluster = 2

    def allocate(content: bytes) -> int:
        nonlocal next_cluster
        count = max(1, (len(content) + cluster_bytes - 1) // cluster_bytes)
        if next_cluster + count > clusters + 2:
            fail("The ProtoOS boot payload does not fit in the EFI partition.")
        first = next_cluster
        for index in range(count):
            cluster = first + index
            struct.pack_into("<H", fat, cluster * 2, 0xFFFF if index + 1 == count else cluster + 1)
            offset = data_offset + (cluster - 2) * cluster_bytes
            chunk = content[index * cluster_bytes:(index + 1) * cluster_bytes]
            image[offset:offset + len(chunk)] = chunk
        next_cluster += count
        return first

    efi_cluster = allocate(b"\0" * cluster_bytes)
    boot_cluster = allocate(b"\0" * cluster_bytes)
    file_clusters = {path: allocate(content) for path, content in files.items()}
    image[root_offset:root_offset + 32] = fat_entry("EFI", 0x10, efi_cluster)

    efi_directory = bytearray(cluster_bytes)
    efi_directory[0:32] = fat_entry(".", 0x10, efi_cluster)
    efi_directory[32:64] = fat_entry("..", 0x10, 0)
    efi_directory[64:96] = fat_entry("BOOT", 0x10, boot_cluster)
    efi_offset = data_offset + (efi_cluster - 2) * cluster_bytes
    image[efi_offset:efi_offset + cluster_bytes] = efi_directory

    boot_directory = bytearray(cluster_bytes)
    boot_directory[0:32] = fat_entry(".", 0x10, boot_cluster)
    boot_directory[32:64] = fat_entry("..", 0x10, efi_cluster)
    offset = 64
    for path, content in files.items():
        filename = path.rsplit("/", 1)[-1]
        # Limine 8 uses its new configuration syntax only for limine.conf.
        # FAT 8.3 cannot express the four-letter extension, so expose it with
        # a VFAT long name and a conventional short-name alias.
        short_filename = "LIMINE~1.CON" if filename == "LIMINE.CONF" else filename
        short = short_name(short_filename)
        if filename != short_filename:
            boot_directory[offset:offset + 32] = fat_lfn_entry(filename, short)
            offset += 32
        boot_directory[offset:offset + 32] = fat_entry(short_filename, 0x20, file_clusters[path], len(content))
        offset += 32
    boot_offset = data_offset + (boot_cluster - 2) * cluster_bytes
    image[boot_offset:boot_offset + cluster_bytes] = boot_directory
    for copy in range(fat_count):
        offset = fat_offset + copy * len(fat)
        image[offset:offset + len(fat)] = fat
    return bytes(image)


def guid_le(data1: int, data2: int, data3: int, tail: bytes) -> bytes:
    return struct.pack("<IHH", data1, data2, data3) + tail


def gpt_header(current: int, backup: int, first_usable: int, last_usable: int,
               disk_guid: bytes, entries_lba: int, entries: bytes) -> bytes:
    header = bytearray(SECTOR)
    header[:8] = b"EFI PART"
    struct.pack_into("<I", header, 8, 0x00010000)
    struct.pack_into("<I", header, 12, 92)
    struct.pack_into("<Q", header, 24, current)
    struct.pack_into("<Q", header, 32, backup)
    struct.pack_into("<Q", header, 40, first_usable)
    struct.pack_into("<Q", header, 48, last_usable)
    header[56:72] = disk_guid
    struct.pack_into("<Q", header, 72, entries_lba)
    struct.pack_into("<I", header, 80, 128)
    struct.pack_into("<I", header, 84, 128)
    struct.pack_into("<I", header, 88, binascii.crc32(entries) & 0xFFFFFFFF)
    struct.pack_into("<I", header, 16, binascii.crc32(header[:92]) & 0xFFFFFFFF)
    return bytes(header)


def fixed_vhd_footer(virtual_size: int) -> bytes:
    footer = bytearray(512)
    footer[:8] = b"conectix"
    struct.pack_into(">I", footer, 8, 0x00000002)
    struct.pack_into(">I", footer, 12, 0x00010000)
    struct.pack_into(">Q", footer, 16, 0xFFFFFFFFFFFFFFFF)
    timestamp = int(EPOCH - dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    struct.pack_into(">I", footer, 24, timestamp)
    footer[28:32] = b"Ptos"
    struct.pack_into(">I", footer, 32, 0x00010000)
    footer[36:40] = b"Wi2k"
    struct.pack_into(">Q", footer, 40, virtual_size)
    struct.pack_into(">Q", footer, 48, virtual_size)
    total_sectors = virtual_size // SECTOR
    cylinders = min(total_sectors // (16 * 63), 65535)
    footer[56:60] = struct.pack(">HBB", cylinders, 16, 63)
    struct.pack_into(">I", footer, 60, 2)  # fixed disk
    footer[68:84] = guid_le(0x50524F54, 0x5648, 0x0200, b"\x00\x00\x00\x00\x00\x00\x00\x01")
    footer[84] = 0
    struct.pack_into(">I", footer, 64, (~sum(footer) & 0xFFFFFFFF))
    return bytes(footer)


def build_vhd(destination: Path) -> None:
    kernel = obtain_kernel().read_bytes()
    limine = obtain_limine_bootx64().read_bytes()
    initrd = build_initramfs().read_bytes()
    esp = fat16_esp({
        "EFI/BOOT/BOOTX64.EFI": limine,
        "EFI/BOOT/LIMINE.CONF": limine_config(),
        "EFI/BOOT/KERNEL.EFI": kernel,
        "EFI/BOOT/INITRD.IMG": initrd,
    })
    if len(esp) != ESP_SECTORS * SECTOR:
        fail("EFI System Partition has an unexpected size.")
    total_lba = VIRTUAL_SIZE // SECTOR
    entry_count, entry_size = 128, 128
    entries_sectors = entry_count * entry_size // SECTOR
    backup_entries_lba = total_lba - 1 - entries_sectors
    first_usable, last_usable = 2 + entries_sectors, backup_entries_lba - 1
    esp_last = ESP_FIRST_LBA + ESP_SECTORS - 1
    if esp_last > last_usable:
        fail("ESP does not fit in virtual disk.")
    esp_type = guid_le(0xC12A7328, 0xF81F, 0x11D2, b"\xBA\x4B\x00\xA0\xC9\x3E\xC9\x3B")
    disk_guid = guid_le(0x50524F54, 0x5648, 0x0200, b"\x00\x00\x00\x00\x00\x00\x00\x02")
    partition_guid = guid_le(0x50524F54, 0x4553, 0x0200, b"\x00\x00\x00\x00\x00\x00\x00\x02")
    entries = bytearray(entry_count * entry_size)
    entries[:16] = esp_type
    entries[16:32] = partition_guid
    struct.pack_into("<Q", entries, 32, ESP_FIRST_LBA)
    struct.pack_into("<Q", entries, 40, esp_last)
    entries[56:56 + len("ProtoOS EFI".encode("utf-16le"))] = "ProtoOS EFI".encode("utf-16le")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as disk:
        disk.truncate(VIRTUAL_SIZE)
        mbr = bytearray(SECTOR)
        mbr[446 + 4] = 0xEE
        struct.pack_into("<I", mbr, 446 + 8, 1)
        struct.pack_into("<I", mbr, 446 + 12, total_lba - 1)
        mbr[510:512] = b"\x55\xAA"
        disk.seek(0)
        disk.write(mbr)
        disk.seek(SECTOR)
        disk.write(gpt_header(1, total_lba - 1, first_usable, last_usable, disk_guid, 2, entries))
        disk.seek(2 * SECTOR)
        disk.write(entries)
        disk.seek(ESP_FIRST_LBA * SECTOR)
        disk.write(esp)
        disk.seek(backup_entries_lba * SECTOR)
        disk.write(entries)
        disk.seek((total_lba - 1) * SECTOR)
        disk.write(gpt_header(total_lba - 1, 1, first_usable, last_usable, disk_guid, backup_entries_lba, entries))
        disk.seek(VIRTUAL_SIZE)
        disk.write(fixed_vhd_footer(VIRTUAL_SIZE))
    print(f"Built {destination} ({destination.stat().st_size / 1024 / 1024:.1f} MiB)")
    print(f"SHA256 {sha256(destination)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "ProtoOS-HyperV-0.2.1.vhd")
    args = parser.parse_args()
    try:
        build_vhd(args.output)
    except (OSError, RuntimeError) as error:
        print(f"build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
