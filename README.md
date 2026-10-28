# Power

Power Saver, Balanced, and Performance for Linux laptops. It also sets an 80% or 100% charge limit when the laptop supports one, raises the fan curve when the CPU gets hot, and keeps the mode you chose across reboot. The charger does not switch modes.

On Cinnamon, the choices sit in the battery icon on the panel. Every desktop also gets a **Power** app in the menu, with battery, fan, temperature, and unplugged-power graphs.

## Install

One command. It downloads Power, asks for your password once, and installs it:

```bash
curl -fsSL https://raw.githubusercontent.com/kishava/power/main/install.sh | bash
```

Or download this repository, open a terminal in the folder, and run:

```bash
./install.sh
```

You need Linux with systemd, and Python 3 with GTK 3. Linux Mint and Ubuntu already include that. If the window fails to open, install the missing piece:

```bash
sudo apt install python3-gi gir1.2-gtk-3.0
```

### After it installs

On Cinnamon, open the battery icon on the panel:

- Power Saver, Balanced, and Performance
- Charge to 80% and Charge to 100%, when the laptop has that control
- Open Power window

On another desktop, open **Power** from the application menu. The battery-menu items are added only on Cinnamon.

On an ASUS laptop, Fn+F cycles Silent, Standard, and Performance the way MyASUS does. A notification names the mode. Other laptops use the menu or the Power window.

## What the modes do

| Mode | Fan and platform | Processor |
|---|---|---|
| Power Saver | Quietest profile the laptop offers | Lowest energy preference |
| Balanced | Balanced profile | Middle energy preference |
| Performance | Performance profile | Full performance preference |

If a laptop has no platform profiles, only the processor preference changes. Graphics power saving is used in Power Saver when the Intel graphics driver exposes it.

Fans speed up from the CPU temperature, and they will not drop quieter than the mode you chose:

| CPU temperature | Fan curve |
|---|---|
| Under 58 °C | Quiet |
| 58 °C and up | Standard |
| 75 °C and up | Strong |

The curve steps back down only after the CPU has cooled a few degrees, so the fans do not pulse. On many ASUS laptops the firmware owns the fan speed, so this selects the firmware curve rather than a manual speed.

80% stops the charge early and is easier on the cells. 100% fills the battery for the longest time unplugged.

## Remove

From the downloaded folder:

```bash
./uninstall.sh
```

That removes the program and the battery-menu items. It does not change a charge limit already stored in the laptop.
