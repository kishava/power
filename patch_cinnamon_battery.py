#!/usr/bin/env python3
"""Put Power controls into the Cinnamon battery menu on the panel."""

import shutil
import sys
from pathlib import Path

SRC = Path("/usr/share/cinnamon/applets/power@cinnamon.org")
DST = Path.home() / ".local/share/cinnamon/applets/power@cinnamon.org"
MARKER = "power-desk-hook"

IMPORTS = "const ByteArray = imports.byteArray;\nconst GLib = imports.gi.GLib;\n"

INIT_ANCHOR = "        this.menu.addMenuItem(this.keyboard);\n"
INIT_INSERT = """        this.menu.addMenuItem(this.keyboard);

        // power-desk-hook
        this._powerDeskSection = new PopupMenu.PopupMenuSection();
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this.menu.addMenuItem(this._powerDeskSection);
        this._buildPowerDesk();
        this.menu.connect("open-state-changed", Lang.bind(this, function (menu, isOpen) {
            if (isOpen)
                this._buildPowerDesk();
        }));
"""

METHOD_ANCHOR = """    _changeProfile(newProfile) {
        this._profilesProxy.ActiveProfile = newProfile;
        this.ActiveProfile = this._profilesProxy.ActiveProfile;
    }
"""

METHODS = r'''
    // power-desk-hook methods
    _powerDeskRead(path) {
        try {
            let [ok, contents] = GLib.file_get_contents(path);
            if (!ok)
                return "";
            return ByteArray.toString(contents).trim();
        } catch (e) {
            return "";
        }
    }

    _buildPowerDesk() {
        try {
            this._buildPowerDeskItems();
        } catch (e) {
            global.logError("power-desk menu: " + e);
        }
    }

    _buildPowerDeskItems() {
        if (!this._powerDeskSection)
            return;
        this._powerDeskSection.removeAll();
        if (!Gio.File.new_for_path("/usr/local/sbin/power-mode").query_exists(null))
            return;

        let mode = this._powerDeskRead("/var/lib/power-mode/current");
        let modes = [
            ["saver", _("Power Saver")],
            ["balanced", _("Balanced")],
            ["performance", _("Performance")]
        ];
        for (let i = 0; i < modes.length; i++) {
            let modeId = modes[i][0];
            let label = modes[i][1];
            let item;
            if (mode === modeId) {
                item = new PopupMenu.PopupMenuItem(label, { reactive: false });
                item.setShowDot(true);
            } else {
                item = new PopupMenu.PopupMenuItem(label);
                item.connect("activate", () => {
                    this._powerDeskRun([modeId]);
                    this.menu.toggle();
                });
            }
            this._powerDeskSection.addMenuItem(item);
        }

        let fanCurve = "";
        let fanFile = this._powerDeskRead("/var/lib/power-mode/fan").split("\n");
        for (let i = 0; i < fanFile.length; i++) {
            if (fanFile[i].indexOf("curve=") === 0)
                fanCurve = fanFile[i].substring(6);
        }
        let fanNames = { quiet: "quiet", balanced: "standard", performance: "strong" };
        let fanLabel = _("Fn+F cycles modes · fans follow heat");
        if (fanNames[fanCurve])
            fanLabel = fanLabel + " · " + fanNames[fanCurve];
        this._powerDeskSection.addMenuItem(new PopupMenu.PopupMenuItem(fanLabel, { reactive: false }));

        let threshold = "";
        try {
            threshold = this._powerDeskThreshold();
        } catch (e) {
            threshold = "";
        }
        if (threshold) {
            let current = this._powerDeskRead(threshold);
            this._powerDeskSection.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
            let limits = [["80", _("Charge to 80%")], ["100", _("Charge to 100%")]];
            for (let i = 0; i < limits.length; i++) {
                let limit = limits[i][0];
                let label = limits[i][1];
                let item;
                if (current === limit) {
                    item = new PopupMenu.PopupMenuItem(label, { reactive: false });
                    item.setShowDot(true);
                } else {
                    item = new PopupMenu.PopupMenuItem(label);
                    item.connect("activate", () => {
                        this._powerDeskRun(["charge", limit]);
                        this.menu.toggle();
                    });
                }
                this._powerDeskSection.addMenuItem(item);
            }
        }

        let openItem = new PopupMenu.PopupIconMenuItem(_("Open Power window"), "preferences-system-power", St.IconType.FULLCOLOR);
        openItem.connect("activate", () => {
            try {
                Gio.Subprocess.new(["python3", "/usr/local/share/power-desk/power_desk.py"], Gio.SubprocessFlags.NONE);
            } catch (e) {
                global.logError("power-desk window: " + e);
            }
            this.menu.toggle();
        });
        this._powerDeskSection.addMenuItem(openItem);
    }

    _powerDeskThreshold() {
        let root = Gio.File.new_for_path("/sys/class/power_supply");
        let children = root.enumerate_children("standard::name", Gio.FileQueryInfoFlags.NONE, null);
        let info;
        let found = "";
        while ((info = children.next_file(null))) {
            let name = info.get_name();
            if (name.indexOf("BAT") !== 0)
                continue;
            let candidate = "/sys/class/power_supply/" + name + "/charge_control_end_threshold";
            if (Gio.File.new_for_path(candidate).query_exists(null)) {
                found = candidate;
                break;
            }
        }
        children.close(null);
        return found;
    }

    _powerDeskRun(args) {
        try {
            Gio.Subprocess.new(["sudo", "-n", "/usr/local/sbin/power-mode"].concat(args), Gio.SubprocessFlags.NONE);
        } catch (e) {
            global.logError("power-desk: " + e);
        }
    }
'''


def main():
    if not SRC.is_dir():
        print("Cinnamon battery applet not found; skipping panel menu.")
        return 0
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)
    applet = DST / "applet.js"
    text = applet.read_text()
    if "const Gio = imports.gi.Gio;\n" not in text:
        print("Could not patch the battery menu: unexpected applet header.", file=sys.stderr)
        return 1
    text = text.replace("const Gio = imports.gi.Gio;\n", "const Gio = imports.gi.Gio;\n" + IMPORTS, 1)
    if INIT_ANCHOR not in text or METHOD_ANCHOR not in text:
        print("Could not patch the battery menu: this Cinnamon version looks different.", file=sys.stderr)
        return 1
    text = text.replace(INIT_ANCHOR, INIT_INSERT, 1)
    text = text.replace(METHOD_ANCHOR, METHOD_ANCHOR + "\n" + METHODS, 1)
    if text.count(MARKER) < 2:
        print("Patch did not apply cleanly.", file=sys.stderr)
        return 1
    applet.write_text(text)
    print(f"Battery menu updated: {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
