#!/bin/bash
# Install Power. Run this as your normal user. It asks for your password once.
#
# From a downloaded copy:
#   ./install.sh
#
# One command, from anywhere:
#   curl -fsSL https://raw.githubusercontent.com/kishava/power/main/install.sh | bash
set -euo pipefail

REPO_URL="https://github.com/kishava/power"
ARCHIVE_URL="https://github.com/kishava/power/archive/refs/heads/main.tar.gz"

if [ "$(id -u)" -eq 0 ]; then
    echo "Run this as your normal user, not as root."
    exit 1
fi

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [ ! -f "$here/power-mode" ] || [ ! -f "$here/install-system.sh" ]; then
    tmp=$(mktemp -d)
    echo "Downloading Power..."
    if command -v git >/dev/null 2>&1; then
        git clone --depth 1 "$REPO_URL" "$tmp/power"
        exec bash "$tmp/power/install.sh"
    fi
    if ! command -v curl >/dev/null 2>&1; then
        echo "git or curl is required to download Power."
        exit 1
    fi
    curl -fsSL "$ARCHIVE_URL" | tar -xz -C "$tmp"
    exec bash "$tmp/power-main/install.sh"
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required."
    exit 1
fi
if ! python3 -c 'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk' >/dev/null 2>&1; then
    echo "Python 3 with GTK 3 is required."
    echo "On Linux Mint or Ubuntu: sudo apt install python3-gi gir1.2-gtk-3.0"
    exit 1
fi
if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemd is required."
    exit 1
fi

if [ -n "${SUDO_ASKPASS:-}" ]; then
    sudo -A bash "$here/install-system.sh" "$USER" "$here"
else
    sudo bash "$here/install-system.sh" "$USER" "$here"
fi
rm -f "$HOME/.local/share/applications/power-desk.desktop"
rm -rf "$HOME/.local/share/power-desk"
python3 "$here/patch_cinnamon_battery.py"

if [ -S "/run/user/$(id -u)/bus" ]; then
    export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"
    dbus-send --session --dest=org.Cinnamon --type=method_call /org/Cinnamon \
        org.Cinnamon.ReloadXlet string:power@cinnamon.org string:APPLET || true
fi

echo
echo "Installed. On Cinnamon, open the battery icon on the panel."
echo "Power Saver, Balanced, Performance, and the charge limit are in that menu."
echo "On an ASUS laptop, Fn+F cycles Silent, Standard, and Performance, including the fan curve."
echo "Open Power window shows the graphs. The same window is in the application menu as Power."
