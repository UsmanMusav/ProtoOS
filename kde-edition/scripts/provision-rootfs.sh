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
proton_deb=${PROTOOS_PROTON_DEB:-}
proton_required=${PROTOOS_REQUIRE_PROTON:-0}

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

# Proton is a user-requested, closed-source browser distributed through its
# author's public GitHub release. The builder supplies a version- and
# SHA-pinned .deb; do not substitute an unverified local file here.
if [ "$proton_required" = 1 ] && [ -z "$proton_deb" ]; then
    echo "PROTOOS_REQUIRE_PROTON=1 requires PROTOOS_PROTON_DEB" >&2
    exit 1
fi
if [ -n "$proton_deb" ]; then
    test -f "$proton_deb"
    proton_package=$(dpkg-deb -f "$proton_deb" Package)
    proton_architecture=$(dpkg-deb -f "$proton_deb" Architecture)
    if [ "$proton_architecture" != amd64 ]; then
        echo "Proton package is not amd64: $proton_architecture" >&2
        exit 1
    fi
    cp "$proton_deb" "$rootfs/tmp/proton-browser.deb"
    chroot "$rootfs" /bin/sh -eu -c '
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        apt-get install -y --no-install-recommends /tmp/proton-browser.deb
        rm -f /tmp/proton-browser.deb
        apt-get clean
    '
    chroot "$rootfs" dpkg-query -W -f '${Status} ${Version}\n' "$proton_package"
    chroot "$rootfs" /bin/sh -eu -c 'command -v proton'
fi

install -d "$rootfs/etc/sddm.conf.d" "$rootfs/usr/share/color-schemes" \
    "$rootfs/usr/share/plasma/look-and-feel" "$rootfs/etc/skel/.local/share/wallpapers" \
    "$rootfs/usr/share/icons" "$rootfs/usr/local/bin" "$rootfs/usr/local/share/applications"
cp "$project/rootfs/etc/sddm.conf.d/10-protoos-autologin.conf" "$rootfs/etc/sddm.conf.d/"
cp "$project/branding/colors/"*.colors "$rootfs/usr/share/color-schemes/"
cp -a "$project/branding/look-and-feel/org.protoos.desktop" "$rootfs/usr/share/plasma/look-and-feel/"
cp -a "$project/branding/wallpapers/ProtoOS" "$rootfs/etc/skel/.local/share/wallpapers/"
cp -a "$project/branding/icons/ProtoOS-Aurora" "$rootfs/usr/share/icons/"
cp -a "$project/rootfs/etc/skel/." "$rootfs/etc/skel/"
# /usr/local takes precedence over package desktop entries. Keep the package
# binaries while presenting the concise ProtoOS roles in the application menu.
cp -a "$project/rootfs/usr/local/share/applications/." "$rootfs/usr/local/share/applications/"
cp -a "$project/rootfs/usr/local/bin/." "$rootfs/usr/local/bin/"
chmod 0755 "$rootfs/usr/local/bin/protoos-welcome" "$rootfs/usr/local/bin/protoos-settings"
# The Live-home service copies /etc/skel on every boot, so create visible,
# predictable folders there rather than only in the builder's temporary user.
install -d "$rootfs/etc/skel/Desktop" "$rootfs/etc/skel/Documents" \
    "$rootfs/etc/skel/Downloads" "$rootfs/etc/skel/Pictures" \
    "$rootfs/etc/skel/Music" "$rootfs/etc/skel/Videos" "$rootfs/etc/skel/Public" \
    "$rootfs/etc/skel/Templates"

# Keep the selected Aurora Motion profile testable: the installed rootfs must
# carry its settings before a VHD is published, not merely document them.
test -s "$rootfs/etc/skel/.config/kwinrc"
test -s "$rootfs/etc/skel/.config/baloofilerc"
test -s "$rootfs/etc/skel/.config/plasma-org.kde.plasma.desktop-appletsrc"
grep -Fqx 'Enabled=true' "$rootfs/etc/skel/.config/kwinrc"
grep -Fqx 'fadeEnabled=true' "$rootfs/etc/skel/.config/kwinrc"
grep -Fqx 'Indexing-Enabled=false' "$rootfs/etc/skel/.config/baloofilerc"
grep -Fqx 'ColorScheme=ProtoOS Proton Dark' "$rootfs/etc/skel/.config/kdeglobals"
grep -Fqx 'icon=protoos-home' "$rootfs/etc/skel/.config/plasma-org.kde.plasma.desktop-appletsrc"
grep -Fqx 'menuLabel=Home' "$rootfs/etc/skel/.config/plasma-org.kde.plasma.desktop-appletsrc"
grep -Fqx 'Name=ProtoOS Proton Dark' "$rootfs/usr/share/color-schemes/ProtoOS Aurora Dark.colors"
grep -Fqx 'Name=ProtoOS Proton Light' "$rootfs/usr/share/color-schemes/ProtoOS Aurora Light.colors"
for launcher in org.protoos.welcome org.protoos.proton org.protoos.computer \
    org.protoos.recyclebin org.protoos.monitor org.kde.dolphin org.kde.konsole \
    org.kde.kate org.kde.okular org.kde.gwenview org.kde.ark org.kde.kcalc \
    systemsettings; do
    test -s "$rootfs/usr/local/share/applications/$launcher.desktop"
done
test -x "$rootfs/usr/local/bin/protoos-welcome"
test -x "$rootfs/usr/local/bin/protoos-settings"
test -s "$rootfs/etc/skel/.config/user-dirs.dirs"
for folder in Desktop Documents Downloads Pictures Music Videos Public Templates; do
    test -d "$rootfs/etc/skel/$folder"
done
test -s "$rootfs/usr/share/icons/ProtoOS-Aurora/index.theme"
grep -Fqx 'Inherits=breeze-dark,breeze,hicolor' "$rootfs/usr/share/icons/ProtoOS-Aurora/index.theme"
test -s "$rootfs/usr/share/icons/breeze-dark/index.theme"
test -s "$rootfs/usr/share/icons/breeze/index.theme"
test -s "$rootfs/usr/share/icons/hicolor/index.theme"
for icon in protoos-home protoos-proton protoos-welcome protoos-images protoos-archive \
    protoos-calculator protoos-computer protoos-monitor protoos-recycle; do
    test -s "$rootfs/usr/share/icons/ProtoOS-Aurora/scalable/apps/$icon.svg"
done
for command in kdialog gwenview ark kcalc plasma-systemmonitor; do
    chroot "$rootfs" /bin/sh -eu -c "command -v $command"
done
if [ "$proton_required" = 1 ]; then
    chroot "$rootfs" /bin/sh -eu -c 'command -v proton'
fi

if ! chroot "$rootfs" id protoos >/dev/null 2>&1; then
    chroot "$rootfs" useradd --create-home --shell /bin/bash --groups sudo,video,audio,input protoos
fi
chroot "$rootfs" /bin/sh -eu -c 'cp -a /etc/skel/. /home/protoos/; chown -R protoos:protoos /home/protoos'

# Live image service selection. A real rootfs build should enable graphical
# boot only after sddm was successfully installed by apt above.
chroot "$rootfs" systemctl set-default graphical.target
chroot "$rootfs" systemctl enable sddm.service

echo "ProtoOS KDE Edition configured in $rootfs"
