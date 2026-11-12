#!/usr/bin/env bash
# Build a Debian KDE Plasma Live-style dynamic VHD for Hyper-V Generation 2.
# This script is intended for a privileged Debian/Ubuntu runner with apt access.
set -Eeuo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
EDITION="$ROOT/kde-edition"
OUT=${PROTOOS_OUT_DIR:-"$ROOT/out"}
WORK=${PROTOOS_WORK_DIR:-"$ROOT/build/kde-vhd"}
RELEASE=${PROTOOS_DEBIAN_RELEASE:-trixie}
VIRTUAL_SIZE=${PROTOOS_VIRTUAL_SIZE:-12G}
VHD="$OUT/ProtoOS-KDE-0.4.0-HyperV.vhd"
RAW="$WORK/protoos-kde.raw"
ROOTFS="$WORK/rootfs"
LOOP_DEVICE=

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "Run as root (for loop devices and mounts)." >&2
        exit 1
    fi
}

cleanup() {
    set +e
    # Chroot package configuration and GRUB need real kernel pseudo-filesystems.
    # Unmount nested bind mounts before the root filesystem and loop device.
    for fs in run sys proc dev/pts dev; do
        mountpoint -q "$ROOTFS/$fs" && umount "$ROOTFS/$fs"
    done
    mountpoint -q "$ROOTFS/boot/efi" && umount "$ROOTFS/boot/efi"
    mountpoint -q "$ROOTFS" && umount "$ROOTFS"
    [ -n "${LOOP_DEVICE:-}" ] && losetup -d "$LOOP_DEVICE"
}
trap cleanup EXIT

require_root
mkdir -p "$OUT" "$WORK"
rm -rf "$ROOTFS" "$RAW" "$VHD"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
    debootstrap dosfstools e2fsprogs gdisk parted qemu-utils rsync ca-certificates

# A dynamic VHD keeps download size reasonable while exposing a 12 GiB virtual
# disk to Hyper-V. The first partition is a normal ESP, the second is Debian.
truncate -s "$VIRTUAL_SIZE" "$RAW"
parted --script "$RAW" \
    mklabel gpt \
    mkpart ESP fat32 1MiB 513MiB set 1 esp on \
    mkpart ProtoOS ext4 513MiB 100%
LOOP_DEVICE=$(losetup --find --show --partscan "$RAW")
mkfs.vfat -F 32 -n PROTOOS_EFI "${LOOP_DEVICE}p1"
mkfs.ext4 -F -L protoos-root "${LOOP_DEVICE}p2"
mkdir -p "$ROOTFS"
mount "${LOOP_DEVICE}p2" "$ROOTFS"
mkdir -p "$ROOTFS/boot/efi"
mount "${LOOP_DEVICE}p1" "$ROOTFS/boot/efi"

debootstrap --arch=amd64 --variant=minbase "$RELEASE" "$ROOTFS" https://deb.debian.org/debian

# Package maintainer scripts, initramfs generation and EFI setup must see the
# normal kernel pseudo-filesystems. Binding them now also avoids a half-set-up
# systemd database during the first chrooted apt transaction.
for fs in dev dev/pts proc sys run; do
    mount --bind "/$fs" "$ROOTFS/$fs"
done

# Install the packages that turn the rootfs into a bootable Plasma desktop.
cat > "$ROOTFS/tmp/protoos-base-packages.txt" <<'PACKAGES'
linux-image-amd64
initramfs-tools
grub-efi-amd64
grub-efi-amd64-bin
efibootmgr
sudo
live-config
PACKAGES
chroot "$ROOTFS" /bin/sh -eu -c '
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    xargs apt-get install -y --no-install-recommends < /tmp/protoos-base-packages.txt
    rm -f /tmp/protoos-base-packages.txt
'

# `provision-rootfs.sh` installs KDE Plasma, the branding, the default user and
# SDDM auto-login. Its package manifest is versioned next to the design assets.
"$EDITION/scripts/provision-rootfs.sh" "$ROOTFS"

cat > "$ROOTFS/etc/default/grub" <<'GRUB'
GRUB_DEFAULT=0
GRUB_TIMEOUT=3
GRUB_DISTRIBUTOR="ProtoOS KDE Edition"
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"
GRUB_CMDLINE_LINUX=""
GRUB_GFXMODE=1280x720,1024x768,auto
GRUB_GFXPAYLOAD_LINUX=keep
GRUB

# A regular user's files live on tmpfs. The rest of the root disk is present to
# boot Debian normally, while ordinary Live-session changes disappear on reboot.
install -d "$ROOTFS/usr/local/lib"
cat > "$ROOTFS/usr/local/lib/protoos-live-home" <<'HOME_SETUP'
#!/bin/sh
set -eu
/bin/mount -t tmpfs -o mode=0755,size=1536M tmpfs /home/protoos
/bin/cp -a /etc/skel/. /home/protoos/
/bin/chown -R protoos:protoos /home/protoos
HOME_SETUP
chmod 0755 "$ROOTFS/usr/local/lib/protoos-live-home"
cat > "$ROOTFS/etc/systemd/system/protoos-live-home.service" <<'SERVICE'
[Unit]
Description=Prepare the ephemeral ProtoOS Live home directory
DefaultDependencies=no
After=local-fs.target
Before=display-manager.service

[Service]
Type=oneshot
ExecStart=/usr/local/lib/protoos-live-home
RemainAfterExit=yes

[Install]
RequiredBy=display-manager.service
SERVICE

cat > "$ROOTFS/etc/os-release" <<'OS_RELEASE'
PRETTY_NAME="ProtoOS KDE Edition 0.4.0"
NAME="ProtoOS KDE Edition"
VERSION_ID="0.4.0"
VERSION="0.4.0 (Debian KDE Plasma Live)"
ID=protoos
ID_LIKE=debian
HOME_URL="https://github.com/UsmanMusav/ProtoOS"
SUPPORT_URL="https://github.com/UsmanMusav/ProtoOS/issues"
OS_RELEASE

chroot "$ROOTFS" /bin/sh -eu -c '
    systemctl enable protoos-live-home.service
    systemctl set-default graphical.target
    grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=ProtoOS --removable --no-nvram
    update-initramfs -u -k all
    update-grub
    apt-get clean
    rm -rf /var/lib/apt/lists/* /tmp/*
'

# qemu-img writes a standards-compliant dynamic VHD that Hyper-V can attach to
# a SCSI controller. No sparse files are committed to Git; CI publishes it.
qemu-img convert -p -f raw -O vpc -o subformat=dynamic "$RAW" "$VHD"
qemu-img info "$VHD"
sha256sum "$VHD" | tee "$VHD.sha256"
echo "Built $VHD"
