#!/bin/bash
# Remove Power. Run this as your normal user. It asks for your password once.
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
    echo "Run this as your normal user, not as root."
    exit 1
fi

sudo systemctl disable --now power-hotkey.service power-fan.service power-mode-restore.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/power-hotkey.service \
    /etc/systemd/system/power-fan.service \
    /etc/systemd/system/power-mode-restore.service \
    /usr/local/sbin/power-fan \
    /usr/local/sbin/power-hotkey \
    /etc/sudoers.d/power-mode \
    /etc/modprobe.d/audio-powersave.conf \
    /usr/local/sbin/power-mode \
    /usr/local/share/applications/power-desk.desktop
sudo rm -rf /usr/local/share/power-desk
sudo systemctl daemon-reload

rm -rf "$HOME/.local/share/cinnamon/applets/power@cinnamon.org"
rm -f "$HOME/.local/share/applications/power-desk.desktop"
rm -rf "$HOME/.local/share/power-desk"

if [ -S "/run/user/$(id -u)/bus" ]; then
    export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"
    dbus-send --session --dest=org.Cinnamon --type=method_call /org/Cinnamon \
        org.Cinnamon.ReloadXlet string:power@cinnamon.org string:APPLET || true
fi

echo "Removed. The laptop is back to the system battery menu."
echo "A charge limit already stored in the laptop is left as it is."
