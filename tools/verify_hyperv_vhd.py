#!/usr/bin/env python3
"""Validate the fixed VHD and its UEFI boot files before Hyper-V testing."""
from __future__ import annotations

import argparse
import binascii
import struct
import sys
from pathlib import Path

SECTOR = 512


def fail(message: str) -> None:
    raise RuntimeError(message)


def read_fat16(image: bytes) -> dict[str, bytes]:
    if image[54:62] != b"FAT16   " or image[510:512] != b"\x55\xaa":
        fail("EFI System Partition is not FAT16.")
    bytes_per_sector = struct.unpack_from("<H", image, 11)[0]
    sectors_per_cluster = image[13]
    reserved = struct.unpack_from("<H", image, 14)[0]
    fats = image[16]
    root_entries = struct.unpack_from("<H", image, 17)[0]
    fat_sectors = struct.unpack_from("<H", image, 22)[0]
    if bytes_per_sector != SECTOR or sectors_per_cluster == 0 or fats != 2:
        fail("Unexpected FAT16 geometry.")
    root_offset = (reserved + fats * fat_sectors) * SECTOR
    root_size = root_entries * 32
    data_offset = root_offset + root_size
    cluster_size = sectors_per_cluster * SECTOR
    fat_offset = reserved * SECTOR

    def next_cluster(cluster: int) -> int:
        return struct.unpack_from("<H", image, fat_offset + cluster * 2)[0]

    def chain(cluster: int, size: int) -> bytes:
        result = bytearray()
        visited: set[int] = set()
        while 2 <= cluster < 0xFFF8:
            if cluster in visited:
                fail("A FAT cluster chain loops.")
            visited.add(cluster)
            offset = data_offset + (cluster - 2) * cluster_size
            result.extend(image[offset:offset + cluster_size])
            cluster = next_cluster(cluster)
        return bytes(result[:size])

    def long_name(entry: bytes) -> str:
        units = [struct.unpack_from("<H", entry, position)[0]
                 for position in (1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30)]
        return "".join(chr(unit) for unit in units if unit not in (0, 0xFFFF))

    def directory(cluster: int, size: int | None) -> dict[str, tuple[int, int, int]]:
        raw = image[root_offset:root_offset + root_size] if cluster == 0 else chain(cluster, size or cluster_size)
        result: dict[str, tuple[int, int, int]] = {}
        pending_long_name: str | None = None
        for offset in range(0, len(raw), 32):
            entry = raw[offset:offset + 32]
            if entry[0] == 0:
                break
            if entry[0] == 0xE5:
                pending_long_name = None
                continue
            if entry[11] == 0x0F:
                pending_long_name = long_name(entry)
                continue
            if entry[0] == 0x2E:
                pending_long_name = None
                continue
            base = entry[:8].decode("ascii").rstrip()
            extension = entry[8:11].decode("ascii").rstrip()
            name = pending_long_name or (base if not extension else f"{base}.{extension}")
            pending_long_name = None
            attributes = entry[11]
            first = struct.unpack_from("<H", entry, 26)[0] | (struct.unpack_from("<H", entry, 20)[0] << 16)
            file_size = struct.unpack_from("<I", entry, 28)[0]
            result[name.upper()] = (attributes, first, file_size)
        return result

    root = directory(0, None)
    if "EFI" not in root:
        fail("ESP root is missing EFI.")
    efi = directory(root["EFI"][1], root["EFI"][2])
    if "BOOT" not in efi:
        fail("ESP EFI directory is missing BOOT.")
    boot = directory(efi["BOOT"][1], efi["BOOT"][2])
    result: dict[str, bytes] = {}
    for filename in ("BOOTX64.EFI", "LIMINE.CONF", "KERNEL.EFI", "INITRD.IMG"):
        if filename not in boot:
            fail(f"ESP boot directory is missing {filename}.")
        _, cluster, size = boot[filename]
        result[filename] = chain(cluster, size)
    return result


def verify(path: Path) -> None:
    content = path.read_bytes()
    if len(content) < SECTOR * 2:
        fail("File is too small to be a fixed VHD.")
    footer = content[-SECTOR:]
    if footer[:8] != b"conectix" or struct.unpack_from(">I", footer, 60)[0] != 2:
        fail("VHD footer is missing or disk type is not fixed.")
    expected_checksum = struct.unpack_from(">I", footer, 64)[0]
    checksum_data = bytearray(footer)
    struct.pack_into(">I", checksum_data, 64, 0)
    if (~sum(checksum_data) & 0xFFFFFFFF) != expected_checksum:
        fail("VHD footer checksum is invalid.")
    virtual_size = struct.unpack_from(">Q", footer, 48)[0]
    if len(content) != virtual_size + SECTOR:
        fail("VHD physical length does not match fixed virtual disk size.")
    raw = content[:virtual_size]
    if raw[510:512] != b"\x55\xaa" or raw[450] != 0xEE:
        fail("Virtual disk lacks a protective GPT MBR.")
    header = raw[SECTOR:2 * SECTOR]
    if header[:8] != b"EFI PART" or struct.unpack_from("<I", header, 12)[0] != 92:
        fail("Virtual disk has no valid primary GPT header.")
    header_crc = struct.unpack_from("<I", header, 16)[0]
    crc_data = bytearray(header[:92])
    struct.pack_into("<I", crc_data, 16, 0)
    if binascii.crc32(crc_data) & 0xFFFFFFFF != header_crc:
        fail("Primary GPT header CRC is invalid.")
    entries_lba = struct.unpack_from("<Q", header, 72)[0]
    entries = raw[entries_lba * SECTOR:(entries_lba + 32) * SECTOR]
    if binascii.crc32(entries) & 0xFFFFFFFF != struct.unpack_from("<I", header, 88)[0]:
        fail("Primary GPT entries CRC is invalid.")
    esp_guid = bytes.fromhex("28732ac11ff8d211ba4b00a0c93ec93b")
    if entries[:16] != esp_guid:
        fail("First GPT partition is not an EFI System Partition.")
    first_lba = struct.unpack_from("<Q", entries, 32)[0]
    last_lba = struct.unpack_from("<Q", entries, 40)[0]
    if last_lba < first_lba:
        fail("EFI System Partition geometry is invalid.")
    esp = raw[first_lba * SECTOR:(last_lba + 1) * SECTOR]
    files = read_fat16(esp)
    if not files["BOOTX64.EFI"].startswith(b"MZ"):
        fail("BOOTX64.EFI is not an EFI application.")
    if b"protocol: linux" not in files["LIMINE.CONF"]:
        fail("LIMINE.CONF does not define a Linux boot entry.")
    if not files["KERNEL.EFI"].startswith(b"MZ"):
        fail("KERNEL.EFI is not an EFI-stub Linux kernel.")
    if not files["INITRD.IMG"].startswith(b"\x1f\x8b"):
        fail("INITRD.IMG is not gzip-compressed.")
    print(f"OK: {path}")
    print(f"  fixed VHD virtual size: {virtual_size // 1024 // 1024} MiB")
    print(f"  GPT ESP: LBA {first_lba}–{last_lba} ({len(esp) // 1024 // 1024} MiB)")
    for name, value in files.items():
        print(f"  {name}: {len(value):,} bytes")


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
