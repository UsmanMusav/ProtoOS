#!/bin/sh
# Configure a prepared Debian amd64 rootfs as ProtoOS KDE Edition.
# Run this script as root on the host: ./provision-rootfs.sh /path/to/rootfs
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: $0 ROOTFS" >&2
    exit 2
fi

rootfs=$1
project=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
packages="$project/manifest/packages.txt"

if [ ! -d "$rootfs/etc" ]; then
    echo "Not a Debian rootfs: $rootfs" >&2
    exit 1
fi

# Package download is intentionally explicit. It must run against a configured
# Debian mirror in the rootfs; this repository never claims a desktop exists
# until these packages were installed successfully.
if [ "${PROTOOS_SKIP_APT:-0}" != 1 ]; then
    cp "$packages" "$rootfs/tmp/protoos-kde-packages.txt"
    chroot "$rootfs" /bin/sh -eu -c '
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        grep -Ev "^[[:space:]]*(#|$)" /tmp/protoos-kde-packages.txt | xargs apt-get install -y --no-install-recommends
        rm -f /tmp/protoos-kde-packages.txt
        apt-get clean
    '
fi

install -d "$rootfs/etc/sddm.conf.d" "$rootfs/usr/share/color-schemes" \
    "$rootfs/usr/share/plasma/look-and-feel" "$rootfs/etc/skel/.local/share/wallpapers" \
    "$rootfs/usr/local/share/applications"
cp "$project/rootfs/etc/sddm.conf.d/10-protoos-autologin.conf" "$rootfs/etc/sddm.conf.d/"
cp "$project/branding/colors/"*.colors "$rootfs/usr/share/color-schemes/"
cp -a "$project/branding/look-and-feel/org.protoos.desktop" "$rootfs/usr/share/plasma/look-and-feel/"
cp -a "$project/branding/wallpapers/ProtoOS" "$rootfs/etc/skel/.local/share/wallpapers/"
cp -a "$project/rootfs/etc/skel/." "$rootfs/etc/skel/"
# /usr/local takes precedence over package desktop entries. Keep the package
# binaries while presenting the concise ProtoOS roles in the application menu.
cp -a "$project/rootfs/usr/local/share/applications/." "$rootfs/usr/local/share/applications/"

# Keep the selected Aurora Motion profile testable: the installed rootfs must
# carry its settings before a VHD is published, not merely document them.
test -s "$rootfs/etc/skel/.config/kwinrc"
test -s "$rootfs/etc/skel/.config/baloofilerc"
test -s "$rootfs/etc/skel/.config/plasma-org.kde.plasma.desktop-appletsrc"
grep -Fqx 'Enabled=true' "$rootfs/etc/skel/.config/kwinrc"
grep -Fqx 'fadeEnabled=true' "$rootfs/etc/skel/.config/kwinrc"
grep -Fqx 'Indexing-Enabled=false' "$rootfs/etc/skel/.config/baloofilerc"
for launcher in org.kde.dolphin org.kde.konsole org.kde.kate org.kde.okular systemsettings; do
    test -s "$rootfs/usr/local/share/applications/$launcher.desktop"
done

if ! chroot "$rootfs" id protoos >/dev/null 2>&1; then
    chroot "$rootfs" useradd --create-home --shell /bin/bash --groups sudo,video,audio,input protoos
fi
chroot "$rootfs" /bin/sh -eu -c 'cp -a /etc/skel/. /home/protoos/; chown -R protoos:protoos /home/protoos'

# Live image service selection. A real rootfs build should enable graphical
# boot only after sddm was successfully installed by apt above.
chroot "$rootfs" systemctl set-default graphical.target
chroot "$rootfs" systemctl enable sddm.service

echo "ProtoOS KDE Edition configured in $rootfs"
