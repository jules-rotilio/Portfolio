#!/bin/sh
# Builds Intercom and installs it for the current user only (no sudo):
#   ~/.local/bin/intercom                    the program
#   ~/.local/share/applications/...desktop   the menu entry
#   ~/.local/share/icons/hicolor/...         the icon, in every size
# Run from anywhere:  sh packaging/linux/install.sh
# PREFIX=/some/folder installs there instead of ~/.local (for testing).
set -e
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PREFIX=${PREFIX:-$HOME/.local}

if [ -z "$SKIP_BUILD" ]; then
    cargo build --release --manifest-path "$ROOT/Cargo.toml"
fi
# Cargo builds into CARGO_TARGET_DIR when it is set, not target/.
install -Dm755 "${CARGO_TARGET_DIR:-$ROOT/target}/release/intercom" "$PREFIX/bin/intercom"
install -Dm644 "$ROOT/packaging/linux/intercom.desktop" "$PREFIX/share/applications/intercom.desktop"
for size in 16 24 32 48 64 128 256 512; do
    install -Dm644 "$ROOT/assets/icons/$size.png" \
        "$PREFIX/share/icons/hicolor/${size}x$size/apps/intercom.png"
done
# Let the menus notice the new entry and icon (harmless if the tools are missing).
update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
gtk-update-icon-cache -q "$PREFIX/share/icons/hicolor" 2>/dev/null || true

echo "Installed: $PREFIX/bin/intercom (and Intercom in the app menu)."
case ":$PATH:" in
    *":$PREFIX/bin:"*) ;;
    *) echo "Note: $PREFIX/bin is not in your PATH; start Intercom from the app menu." ;;
esac
command -v pactl >/dev/null || echo "Note: install pactl for the virtual mic (Debian/Ubuntu: sudo apt install pulseaudio-utils)."
if ! id -nG | grep -qw input; then
    echo "Note: for the global hotkeys, run: sudo usermod -aG input \$USER   then log out and back in."
fi
if [ ! -w /dev/uinput ]; then
    echo "Note: for auto-click and drift, Intercom needs /dev/uinput; Settings › Auto-click & drift shows the fix."
fi
