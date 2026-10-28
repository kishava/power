#!/usr/bin/env python3
"""Power modes, charge limit, and a live view of the laptop."""

import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

HELPER = "/usr/local/sbin/power-mode"
HWMON = Path("/sys/class/hwmon")
CPU = Path("/sys/devices/system/cpu")
SUPPLY = Path("/sys/class/power_supply")
UPOWER = Path("/var/lib/upower")


def read_text(path, default=""):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def battery_dir():
    for folder in sorted(SUPPLY.glob("BAT*")):
        if (folder / "capacity").exists():
            return folder
    return None


def charge_limit_file():
    folder = battery_dir()
    if folder is None:
        return None
    path = folder / "charge_control_end_threshold"
    return path if path.exists() else None


def hwmon(name):
    for folder in HWMON.glob("hwmon*"):
        if read_text(folder / "name") == name:
            return folder
    return None


def battery():
    folder = battery_dir()
    if folder is None:
        return None
    volts = int(read_text(folder / "voltage_now", "0") or 0) / 1e6
    amps = int(read_text(folder / "current_now", "0") or 0) / 1e6
    charge_uah = int(read_text(folder / "charge_now", "0") or 0)
    full = int(read_text(folder / "charge_full", "0") or 0)
    design = int(read_text(folder / "charge_full_design", "0") or 0)
    status = read_text(folder / "status", "Unknown")
    percent = read_text(folder / "capacity", "?")
    watts = volts * amps
    hours = None
    if watts > 0.2 and charge_uah > 0 and volts > 0:
        hours = (charge_uah / 1e6 * volts) / watts
        if hours > 48:
            hours = None
    health = None
    if full > 0 and design > 0:
        health = 100 * full / design
    limit = read_text(folder / "charge_control_end_threshold")
    return {
        "percent": percent,
        "status": status,
        "watts": watts,
        "hours": hours,
        "health": health,
        "limit": limit,
    }


def cpu_mhz():
    values = []
    for folder in CPU.glob("cpu[0-9]*"):
        text = read_text(folder / "cpufreq/scaling_cur_freq")
        if text.isdigit():
            values.append(int(text) / 1000)
    if not values:
        return None
    return sum(values) / len(values), min(values), max(values)


def package_temp():
    folder = hwmon("coretemp")
    if folder is None:
        for candidate in HWMON.glob("hwmon*"):
            if read_text(candidate / "name") in ("k10temp", "zenpower", "nvme"):
                continue
            if (candidate / "temp1_input").exists() and read_text(candidate / "name") not in ("iwlwifi_1",):
                raw = read_text(candidate / "temp1_input")
                if raw.isdigit() and int(raw) > 1000:
                    return int(raw) / 1000
        return None
    for label in folder.glob("temp*_label"):
        if "Package" in read_text(label):
            raw = read_text(label.with_name(label.name.replace("label", "input")))
            if raw.isdigit():
                return int(raw) / 1000
    raw = read_text(folder / "temp1_input")
    return int(raw) / 1000 if raw.isdigit() else None


def fans():
    found = []
    for folder in HWMON.glob("hwmon*"):
        labels = sorted(folder.glob("fan*_label"))
        if not labels:
            continue
        for label in labels:
            raw = read_text(label.with_name(label.name.replace("label", "input")))
            if raw.isdigit():
                found.append((read_text(label).replace("_", " "), int(raw)))
    return found


def keyboard_light():
    for path in Path("/sys/class/leds").glob("*kbd_backlight"):
        level = read_text(path / "brightness")
        maximum = read_text(path / "max_brightness")
        if level.isdigit() and maximum.isdigit():
            return int(level), int(maximum)
    return None


def discharge_history(limit=90):
    files = sorted(UPOWER.glob("history-rate-*.dat"), key=lambda item: item.stat().st_size)
    if not files:
        return []
    points = []
    for line in files[-1].read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[2] != "discharging":
            continue
        try:
            points.append(float(parts[1]))
        except ValueError:
            continue
    return points[-limit:]


def current_mode():
    saved = read_text("/var/lib/power-mode/current")
    profile = read_text("/sys/firmware/acpi/platform_profile")
    epp = read_text(CPU / "cpu0/cpufreq/energy_performance_preference")
    if saved in ("saver", "balanced", "performance"):
        return saved, profile, epp
    if profile == "performance" or epp == "performance":
        return "performance", profile, epp
    if profile in ("quiet", "low-power") or epp == "power":
        return "saver", profile, epp
    return "balanced", profile, epp


class PowerDesk(Gtk.Window):
    def __init__(self):
        super().__init__(title="Power")
        self.set_icon_name("preferences-system-power")
        self.set_default_size(580, 760)
        self.set_border_width(16)
        self._updating = False
        self._light_hold = False
        self._light_timer = None

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(root)

        title = Gtk.Label()
        title.set_markup("<span size='xx-large' weight='bold'>Power</span>")
        title.set_halign(Gtk.Align.START)
        root.pack_start(title, False, False, 0)

        self.mode_label = Gtk.Label(xalign=0)
        root.pack_start(self.mode_label, False, False, 0)

        note = Gtk.Label(
            label="Fn+F cycles Silent, Standard, and Performance, including the fan curve. Fans still rise further if the CPU gets hot. The charger does not change the mode.",
            xalign=0,
        )
        note.set_line_wrap(True)
        note.get_style_context().add_class("dim-label")
        root.pack_start(note, False, False, 0)

        buttons = Gtk.Box(spacing=8)
        self.mode_buttons = {}
        for mode, label in (
            ("saver", "Power Saver"),
            ("balanced", "Balanced"),
            ("performance", "Performance"),
        ):
            button = Gtk.Button(label=label)
            button.connect("clicked", lambda _button, chosen=mode: self.set_mode(chosen))
            buttons.pack_start(button, True, True, 0)
            self.mode_buttons[mode] = button
        root.pack_start(buttons, False, False, 0)

        self.charge_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        charge_label = Gtk.Label(label="Charge limit", xalign=0)
        self.charge_box.pack_start(charge_label, False, False, 0)
        charge_buttons = Gtk.Box(spacing=8)
        self.charge_80 = Gtk.Button(label="Charge to 80%")
        self.charge_100 = Gtk.Button(label="Charge to 100%")
        self.charge_80.connect("clicked", lambda *_: self.set_charge("80"))
        self.charge_100.connect("clicked", lambda *_: self.set_charge("100"))
        charge_buttons.pack_start(self.charge_80, True, True, 0)
        charge_buttons.pack_start(self.charge_100, True, True, 0)
        self.charge_box.pack_start(charge_buttons, False, False, 0)
        charge_note = Gtk.Label(
            label="80% is easier on the battery. 100% stores a full charge for the longest time away from the plug.",
            xalign=0,
        )
        charge_note.set_line_wrap(True)
        charge_note.get_style_context().add_class("dim-label")
        self.charge_box.pack_start(charge_note, False, False, 0)
        root.pack_start(self.charge_box, False, False, 0)

        self.light_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.light_box.pack_start(Gtk.Label(label="Keyboard light", xalign=0), False, False, 0)
        self.light_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 3, 1)
        self.light_scale.set_digits(0)
        self.light_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.light_scale.connect("value-changed", self.on_light_changed)
        self.light_scale.connect("button-press-event", self.on_light_press)
        self.light_scale.connect("button-release-event", self.on_light_release)
        self.light_box.pack_start(self.light_scale, False, False, 0)
        root.pack_start(self.light_box, False, False, 0)

        self.stats = Gtk.Label(xalign=0)
        self.stats.set_line_wrap(True)
        self.stats.set_selectable(True)
        root.pack_start(self.stats, False, False, 0)

        root.pack_start(Gtk.Label(label="Unplugged power draw", xalign=0), False, False, 0)
        self.graph = Gtk.DrawingArea()
        self.graph.set_size_request(-1, 180)
        self.graph.connect("draw", self.draw_graph)
        frame = Gtk.Frame()
        frame.add(self.graph)
        root.pack_start(frame, True, True, 0)

        self.history = []
        self.refresh()
        GLib.timeout_add_seconds(2, self.refresh)

    def run_helper(self, args):
        try:
            result = subprocess.run(
                ["sudo", "-n", HELPER, *args],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.error("The power switch did not answer.")
            return False
        if result.returncode != 0:
            self.error((result.stderr or result.stdout or "The power switch was refused.").strip())
            return False
        return True

    def error(self, detail):
        dialog = Gtk.MessageDialog(
            parent=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.CLOSE,
            text="Could not change that setting",
        )
        dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()

    def set_mode(self, mode):
        if self.run_helper([mode]):
            self.refresh()

    def set_charge(self, limit):
        if self.run_helper(["charge", limit]):
            self.refresh()

    def on_light_press(self, *_args):
        self._light_hold = True
        return False

    def on_light_release(self, *_args):
        self._light_hold = False
        self.commit_light()
        return False

    def on_light_changed(self, _scale):
        if self._updating or not self._light_hold:
            return
        if self._light_timer:
            GLib.source_remove(self._light_timer)
        self._light_timer = GLib.timeout_add(250, self.commit_light)

    def commit_light(self):
        self._light_timer = None
        level = int(self.light_scale.get_value())
        self.run_helper(["backlight", str(level)])
        return False

    def mark(self, button, active):
        style = button.get_style_context()
        if active:
            style.add_class("suggested-action")
        else:
            style.remove_class("suggested-action")

    def refresh(self):
        mode, profile, epp = current_mode()
        names = {"saver": "Power Saver", "balanced": "Balanced", "performance": "Performance"}
        self.mode_label.set_markup(f"<span size='large'>{names.get(mode, mode)} is on</span>")
        for key, button in self.mode_buttons.items():
            self.mark(button, key == mode)

        info = battery()
        limit_file = charge_limit_file()
        self.charge_box.set_visible(limit_file is not None)
        if info and info["limit"] in ("80", "100"):
            self.mark(self.charge_80, info["limit"] == "80")
            self.mark(self.charge_100, info["limit"] == "100")

        light = keyboard_light()
        self.light_box.set_visible(light is not None)
        if light and not self._light_hold:
            level, maximum = light
            self._updating = True
            self.light_scale.set_range(0, maximum)
            self.light_scale.set_value(level)
            self._updating = False

        if info is None:
            rate = "No battery found"
        elif info["status"] == "Discharging":
            rate = f"Using {info['watts']:.1f} W from the battery"
        elif info["status"] == "Charging":
            rate = f"Plugged in, charging at {info['watts']:.1f} W"
        elif info["status"] == "Full":
            rate = "Plugged in, battery at the charge limit"
        else:
            rate = f"{info['status']}, {info['watts']:.1f} W"
        if info and info["hours"] and info["status"] == "Discharging":
            rate += f"  ·  about {info['hours']:.1f} h left"
        elif info and info["hours"] and info["status"] == "Charging":
            rate += f"  ·  about {info['hours']:.1f} h until the limit"

        clocks = cpu_mhz()
        if clocks:
            avg, low, high = clocks
            clocks_text = f"{avg:.0f} MHz average  ({low:.0f}–{high:.0f})"
        else:
            clocks_text = "unavailable"
        temp = package_temp()
        temp_text = f"{temp:.0f} °C" if temp is not None else "unavailable"
        fan_rows = fans()
        fan_text = ", ".join(f"{name} {rpm} rpm" for name, rpm in fan_rows) or "unavailable"
        fan_state = {}
        for line in read_text("/var/lib/power-mode/fan").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                fan_state[key] = value
        curve_names = {"quiet": "quiet", "balanced": "standard", "performance": "strong"}
        if fan_state.get("curve"):
            curve = curve_names.get(fan_state["curve"], fan_state["curve"])
            fan_text += f"    automatic {curve} curve"
            if fan_state.get("temp"):
                fan_text += f" at {fan_state['temp']} °C"
        health = "unavailable"
        if info and info["health"] is not None:
            health = f"{info['health']:.0f}% of original capacity"
        limit_text = f"{info['limit']}%" if info and info["limit"] else "not supported"

        self.stats.set_text(
            "\n".join(
                [
                    f"Battery          {info['percent'] if info else '?'}%    {rate}",
                    f"Charge limit     {limit_text}    health {health}",
                    f"Processor        {clocks_text}    {temp_text}",
                    f"Fans             {fan_text}",
                    f"Laptop profile   {profile or 'unknown'}    CPU preference {epp or 'unknown'}",
                ]
            )
        )
        self.history = discharge_history()
        self.graph.queue_draw()
        return True

    def draw_graph(self, _widget, cr):
        width = self.graph.get_allocated_width()
        height = self.graph.get_allocated_height()
        cr.set_source_rgb(0.12, 0.12, 0.12)
        cr.paint()
        values = self.history
        if len(values) < 2:
            cr.set_source_rgb(0.75, 0.75, 0.75)
            cr.move_to(16, height / 2)
            cr.show_text("No unplugged history yet")
            return False

        peak = max(max(values), 8)
        left, right, top, bottom = 44, 12, 12, 22
        plot_w = max(width - left - right, 1)
        plot_h = max(height - top - bottom, 1)
        cr.set_source_rgb(0.35, 0.35, 0.35)
        cr.set_line_width(1)
        for mark in (0, peak / 2, peak):
            y = top + plot_h * (1 - mark / peak)
            cr.move_to(left, y)
            cr.line_to(width - right, y)
            cr.stroke()
            cr.move_to(4, max(y - 4, 10))
            cr.show_text(f"{mark:.0f} W")

        cr.set_source_rgb(0.35, 0.75, 0.45)
        cr.set_line_width(2)
        for index, value in enumerate(values):
            x = left + plot_w * index / (len(values) - 1)
            y = top + plot_h * (1 - min(value, peak) / peak)
            if index == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()
        return False


def main():
    GLib.set_prgname("power-desk")
    GLib.set_application_name("Power")
    Gtk.Window.set_default_icon_name("preferences-system-power")
    win = PowerDesk()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
