#!/usr/bin/env python3
"""Structural checks for a ProtoOS UEFI ISO built by tools/build.py."""
from __future__ import annotations

import argparse
import binascii
import struct
import sys
from pathlib import Path

SECTOR = 2048


def fail(message: str) -> None:
    raise RuntimeError(message)


def read_sector(image: bytes, number: int) -> bytes:
    begin = number * SECTOR
    sector = image[begin:begin + SECTOR]
    if len(sector) != SECTOR:
        fail(f"Missing ISO sector {number}.")
    return sector


def read_extent(image: bytes, extent: int, size: int) -> bytes:
    begin = extent * SECTOR
    data = image[begin:begin + size]
    if len(data) != size:
        fail(f"Truncated ISO extent at sector {extent}.")
    return data


def check_gpt(image: bytes) -> tuple[int, int]:
    """Validate the GPT ESP map used by Hyper-V UEFI and return its extent."""
    if image[510:512] != b"\x55\xaa" or image[446 + 4] != 0xEE:
        fail("ISO system area does not contain a protective MBR.")
    header = image[512:1024]
    if header[:8] != b"EFI PART" or struct.unpack_from("<I", header, 12)[0] != 92:
        fail("ISO system area does not contain a valid primary GPT header.")
    expected_crc = struct.unpack_from("<I", header, 16)[0]
    crc_data = bytearray(header[:92])
    struct.pack_into("<I", crc_data, 16, 0)
    if binascii.crc32(crc_data) & 0xFFFFFFFF != expected_crc:
        fail("Primary GPT header CRC is invalid.")
    entries_lba = struct.unpack_from("<Q", header, 72)[0]
    entry_count = struct.unpack_from("<I", header, 80)[0]
    entry_size = struct.unpack_from("<I", header, 84)[0]
    if entries_lba != 2 or entry_count != 128 or entry_size != 128:
        fail("Unexpected primary GPT entry geometry.")
    entries_size = entry_count * entry_size
    entries = image[entries_lba * 512:entries_lba * 512 + entries_size]
    if len(entries) != entries_size:
        fail("Primary GPT partition entries are truncated.")
    if binascii.crc32(entries) & 0xFFFFFFFF != struct.unpack_from("<I", header, 88)[0]:
        fail("Primary GPT entry CRC is invalid.")
    # EFI System Partition GUID, in GPT's mixed-endian byte order.
    esp_guid = bytes.fromhex("28732ac11ff8d211ba4b00a0c93ec93b")
    if entries[:16] != esp_guid:
        fail("First GPT entry is not an EFI System Partition.")
    first_lba = struct.unpack_from("<Q", entries, 32)[0]
    last_lba = struct.unpack_from("<Q", entries, 40)[0]
    if first_lba % 4 or last_lba < first_lba:
        fail("EFI System Partition has an invalid ISO extent.")
    return first_lba // 4, (last_lba - first_lba + 1) // 4


def parse_directory(image: bytes, extent: int, size: int) -> dict[str, tuple[int, int, int]]:
    raw = read_extent(image, extent, size)
    entries: dict[str, tuple[int, int, int]] = {}
    offset = 0
    while offset < len(raw):
        length = raw[offset]
        if length == 0:
            # This ISO uses one sector per directory, so the rest is padding.
            break
        if offset + length > len(raw) or length < 34:
            fail(f"Invalid ISO directory record at sector {extent}, offset {offset}.")
        record = raw[offset:offset + length]
        file_extent = struct.unpack_from("<I", record, 2)[0]
        file_size = struct.unpack_from("<I", record, 10)[0]
        flags = record[25]
        name_size = record[32]
        name = record[33:33 + name_size]
        if len(name) != name_size:
            fail("Truncated ISO file identifier.")
        if name == b"\0":
            label = "."
        elif name == b"\1":
            label = ".."
        else:
            label = name.decode("ascii")
            if ";" in label:
                label = label.split(";", 1)[0]
        entries[label] = (flags, file_extent, file_size)
        offset += length
    return entries


def verify(path: Path) -> None:
    image = path.read_bytes()
    if len(image) % SECTOR:
        fail("ISO is not a whole number of 2048-byte sectors.")
    gpt_efi_lba, gpt_efi_sectors = check_gpt(image)
    pvd = read_sector(image, 16)
    if pvd[:7] != b"\x01CD001\x01":
        fail("Primary Volume Descriptor is invalid.")
    boot_record = read_sector(image, 17)
    if boot_record[:7] != b"\x00CD001\x01" or boot_record[7:30] != b"EL TORITO SPECIFICATION":
        fail("El Torito boot record is invalid.")
    catalog_lba = struct.unpack_from("<I", boot_record, 71)[0]
    catalog = read_sector(image, catalog_lba)
    if sum(struct.unpack("<16H", catalog[:32])) & 0xFFFF:
        fail("El Torito validation checksum is invalid.")
    if catalog[1] != 0xEF or catalog[32] != 0x88 or catalog[33] != 0:
        fail("No bootable UEFI initial El Torito entry was found.")
    if catalog[64] != 0x91 or catalog[65] != 0xEF or catalog[96] != 0x88:
        fail("No bootable UEFI El Torito section entry was found.")
    initial_lba = struct.unpack_from("<I", catalog, 40)[0]
    section_lba = struct.unpack_from("<I", catalog, 104)[0]
    if initial_lba != section_lba:
        fail("UEFI El Torito entries point to different boot images.")
    if initial_lba != gpt_efi_lba or gpt_efi_sectors * SECTOR < 2 * 1024 * 1024:
        fail("GPT EFI System Partition does not map the El Torito UEFI CD image.")
    boot_image = read_extent(image, initial_lba, 64)
    if boot_image[:3] != b"\xeb\x3c\x90" or boot_image[54:62] != b"FAT12   ":
        fail("El Torito boot image is not Limine's FAT12 UEFI CD image.")

    root_extent = struct.unpack_from("<I", pvd, 158)[0]
    root_size = struct.unpack_from("<I", pvd, 166)[0]
    root = parse_directory(image, root_extent, root_size)
    expected_root = ("BOOT", "LIMINE.CONF", "KERNEL.EFI", "INITRD.IMG", "README.TXT")
    for name in expected_root:
        if name not in root:
            fail(f"ISO root is missing {name}.")
    boot = parse_directory(image, root["BOOT"][1], root["BOOT"][2])
    if "LIMINE-UEFI-CD.BIN" not in boot:
        fail("ISO BOOT directory is missing Limine's UEFI CD image.")
    _, boot_file_extent, boot_file_size = boot["LIMINE-UEFI-CD.BIN"]
    if boot_file_extent != initial_lba or boot_file_size < 2 * 1024 * 1024:
        fail("El Torito entry does not point to the ISO Limine CD file.")

    config = read_extent(image, root["LIMINE.CONF"][1], root["LIMINE.CONF"][2])
    kernel = read_extent(image, root["KERNEL.EFI"][1], root["KERNEL.EFI"][2])
    initrd = read_extent(image, root["INITRD.IMG"][1], root["INITRD.IMG"][2])
    if b"protocol: linux" not in config:
        fail("LIMINE.CONF does not declare a Linux boot entry.")
    if not kernel.startswith(b"MZ"):
        fail("KERNEL.EFI is not an EFI-stub Linux kernel.")
    if not initrd.startswith(b"\x1f\x8b"):
        fail("INITRD.IMG is not gzip-compressed.")
    print(f"OK: {path}")
    print(f"  size: {len(image) // 1024 // 1024} MiB")
    print(f"  boot catalog: sector {catalog_lba}; UEFI CD image/GPT ESP: sector {initial_lba}")
    print(f"  LIMINE.CONF: {len(config):,} bytes")
    print(f"  KERNEL.EFI: {len(kernel):,} bytes")
    print(f"  INITRD.IMG: {len(initrd):,} bytes")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    try:
        verify(args.image)
    except (OSError, RuntimeError) as error:
        print(f"verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
