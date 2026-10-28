#!/bin/bash
# Called by install.sh through sudo. Arguments: username, source directory.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "install-system.sh must run as root."
    exit 1
fi

TARGET_USER=${1:?username}
HERE=${2:?source directory}

install -d /usr/local/sbin /usr/local/share/power-desk /usr/local/share/applications /etc/modprobe.d
install -o root -g root -m 0755 "$HERE/power-mode" /usr/local/sbin/power-mode
install -o root -g root -m 0755 "$HERE/power-fan" /usr/local/sbin/power-fan
install -o root -g root -m 0755 "$HERE/power-hotkey" /usr/local/sbin/power-hotkey
install -o root -g root -m 0755 "$HERE/power_desk.py" /usr/local/share/power-desk/power_desk.py

cat > /usr/local/share/applications/power-desk.desktop << 'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=Power
GenericName=Power mode
Comment=Power modes, charge limit, battery, fans, and CPU
Exec=python3 /usr/local/share/power-desk/power_desk.py
Icon=preferences-system-power
StartupWMClass=power-desk
Terminal=false
Categories=System;Settings;Utility;
StartupNotify=true
EOF
chmod 644 /usr/local/share/applications/power-desk.desktop

cat > /etc/sudoers.d/power-mode << EOF
$TARGET_USER ALL=(root) NOPASSWD: /usr/local/sbin/power-mode
EOF
chmod 440 /etc/sudoers.d/power-mode
if [ -x /usr/sbin/visudo ]; then
    /usr/sbin/visudo -cf /etc/sudoers.d/power-mode
fi

cat > /etc/modprobe.d/audio-powersave.conf << 'EOF'
options snd_hda_intel power_save=1 power_save_controller=Y
EOF

cat > /etc/systemd/system/power-mode-restore.service << 'EOF'
[Unit]
Description=Restore the power mode and charge limit last chosen by the user
After=sysinit.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/power-mode apply-saved
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/power-fan.service << 'EOF'
[Unit]
Description=Adjust the laptop fan curve from CPU temperature
After=power-mode-restore.service

[Service]
Type=simple
ExecStart=/usr/local/sbin/power-fan
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/power-hotkey.service << 'EOF'
[Unit]
Description=Cycle power mode and fan curve with Fn+F
After=power-mode-restore.service

[Service]
Type=simple
ExecStart=/usr/local/sbin/power-hotkey
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable power-mode-restore.service
systemctl enable power-fan.service
systemctl enable power-hotkey.service
systemctl restart power-fan.service
systemctl restart power-hotkey.service
# Keep the mode already chosen. apply-saved reads it, or starts in Power Saver.
if [ ! -f /var/lib/power-mode/current ]; then
    /usr/local/sbin/power-mode saver
else
    /usr/local/sbin/power-mode apply-saved
fi
for f in /sys/class/power_supply/BAT*/charge_control_end_threshold; do
    [ -e "$f" ] || continue
    value=$(cat "$f")
    case "$value" in
        80|100) /usr/local/sbin/power-mode charge "$value" ;;
    esac
    break
done
echo "System files installed for $TARGET_USER"
