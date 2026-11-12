#!/usr/bin/env python3
"""Structural checks for a ProtoOS UEFI ISO built by tools/build.py."""
from __future__ import annotations

import argparse
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


def parse_fat16(image: bytes) -> dict[str, bytes]:
    if image[54:62] != b"FAT16   " or image[510:512] != b"\x55\xaa":
        fail("El Torito image is not a FAT16 volume.")
    sector_size = struct.unpack_from("<H", image, 11)[0]
    sectors_per_cluster = image[13]
    reserved = struct.unpack_from("<H", image, 14)[0]
    fats = image[16]
    root_entries = struct.unpack_from("<H", image, 17)[0]
    fat_sectors = struct.unpack_from("<H", image, 22)[0]
    if sector_size != 512 or not sectors_per_cluster or fats != 2:
        fail("Unexpected FAT16 geometry.")
    root_offset = (reserved + fats * fat_sectors) * sector_size
    root_size = root_entries * 32
    data_offset = root_offset + root_size
    cluster_size = sector_size * sectors_per_cluster
    fat_offset = reserved * sector_size

    def next_cluster(cluster: int) -> int:
        return struct.unpack_from("<H", image, fat_offset + cluster * 2)[0]

    def read_cluster_chain(cluster: int, size: int) -> bytes:
        result = bytearray()
        seen: set[int] = set()
        while 2 <= cluster < 0xFFF8:
            if cluster in seen:
                fail("A FAT chain loops.")
            seen.add(cluster)
            begin = data_offset + (cluster - 2) * cluster_size
            result.extend(image[begin:begin + cluster_size])
            cluster = next_cluster(cluster)
        return bytes(result[:size])

    def directory(cluster: int, size: int | None) -> dict[str, tuple[int, int, int]]:
        raw = image[root_offset:root_offset + root_size] if cluster == 0 else read_cluster_chain(cluster, size or cluster_size)
        entries: dict[str, tuple[int, int, int]] = {}
        for position in range(0, len(raw), 32):
            entry = raw[position:position + 32]
            if not entry or entry[0] == 0:
                break
            if entry[0] == 0xE5 or entry[11] == 0x0F:
                continue
            name = entry[:8].decode("ascii").rstrip()
            extension = entry[8:11].decode("ascii").rstrip()
            label = name if not extension else f"{name}.{extension}"
            attributes = entry[11]
            first = struct.unpack_from("<H", entry, 26)[0] | (struct.unpack_from("<H", entry, 20)[0] << 16)
            file_size = struct.unpack_from("<I", entry, 28)[0]
            entries[label] = (attributes, first, file_size)
        return entries

    root = directory(0, None)
    if "EFI" not in root:
        fail("FAT root does not contain EFI.")
    efi = directory(root["EFI"][1], None)
    if "BOOT" not in efi:
        fail("FAT EFI directory does not contain BOOT.")
    boot = directory(efi["BOOT"][1], None)
    result: dict[str, bytes] = {}
    for name in ("BOOTX64.EFI", "LIMINE.CFG", "KERNEL.EFI", "INITRD.IMG"):
        if name not in boot:
            fail(f"FAT boot directory is missing {name}.")
        _, cluster, size = boot[name]
        result[name] = read_cluster_chain(cluster, size)
    return result


def verify(path: Path) -> None:
    image = path.read_bytes()
    if len(image) % SECTOR:
        fail("ISO is not a whole number of 2048-byte sectors.")
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
        fail("No bootable x86_64 UEFI El Torito entry was found.")
    efi_lba = struct.unpack_from("<I", catalog, 40)[0]
    efi_size = 16 * 1024 * 1024
    efi_image = image[efi_lba * SECTOR:efi_lba * SECTOR + efi_size]
    if len(efi_image) != efi_size:
        fail("EFI boot image is truncated.")
    files = parse_fat16(efi_image)
    if not files["BOOTX64.EFI"].startswith(b"MZ"):
        fail("BOOTX64.EFI is not a PE image.")
    if b"protocol: linux" not in files["LIMINE.CFG"]:
        fail("LIMINE.CFG does not declare a Linux boot entry.")
    if not files["KERNEL.EFI"].startswith(b"MZ"):
        fail("KERNEL.EFI is not an EFI-stub Linux kernel.")
    if not files["INITRD.IMG"].startswith(b"\x1f\x8b"):
        fail("INITRD.IMG is not gzip-compressed.")
    print(f"OK: {path}")
    print(f"  size: {len(image) // 1024 // 1024} MiB")
    print(f"  boot catalog: sector {catalog_lba}; EFI image: sector {efi_lba}")
    for name, data in files.items():
        print(f"  {name}: {len(data):,} bytes")


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
