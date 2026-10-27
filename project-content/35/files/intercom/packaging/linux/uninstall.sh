#!/bin/sh
# Removes what install.sh put in place, and the start-at-login entry.
# Your settings (~/.config/intercom) are kept; delete that folder to remove them too.
set -e
PREFIX=${PREFIX:-$HOME/.local}
rm -f "$PREFIX/bin/intercom" "$PREFIX/share/applications/intercom.desktop"
for size in 16 24 32 48 64 128 256 512; do
    rm -f "$PREFIX/share/icons/hicolor/${size}x$size/apps/intercom.png"
done
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/intercom.desktop"
update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
gtk-update-icon-cache -q "$PREFIX/share/icons/hicolor" 2>/dev/null || true
echo "Intercom removed. Settings kept in ${XDG_CONFIG_HOME:-$HOME/.config}/intercom."
