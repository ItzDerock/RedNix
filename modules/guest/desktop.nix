{ pkgs, ... }:
let
  xkbRoot = "${pkgs.xkeyboard-config}/share/X11/xkb";

  waybarConfig = pkgs.writeText "rednix-waybar-config" ''
    {
      "layer": "top",
      "height": 28,
      "modules-left": ["custom/launcher", "custom/terminal", "wlr/taskbar"],
      "modules-right": ["clock"],
      "custom/launcher": {
        "format": " Apps ",
        "on-click": "${pkgs.fuzzel}/bin/fuzzel"
      },
      "custom/terminal": {
        "format": " Term ",
        "on-click": "${pkgs.foot}/bin/foot"
      },
      "wlr/taskbar": {
        "format": "{icon}",
        "tooltip": false,
        "on-click": "activate"
      },
      "clock": {
        "format": "{:%H:%M}"
      }
    }
  '';

  waybarStyle = pkgs.writeText "rednix-waybar-style" ''
    * { font-family: sans-serif; font-size: 14px; }
  '';

  rcXml = pkgs.writeText "rednix-labwc-rc" ''
    <?xml version="1.0" encoding="UTF-8"?>
    <openbox_config>
      <theme>
        <cornerradius>8</cornerradius>
        <titleLayout>NLIMC</titleLayout>
        <font place="ActiveWindowLabel"><name>Sans</name><size>10</size></font>
        <font place="InactiveWindowLabel"><name>Sans</name><size>10</size></font>
        <font place="MenuItem"><name>Sans</name><size>10</size></font>
        <font place="Osd"><name>Sans</name><size>10</size></font>
      </theme>
      <keyboard>
        <default/>
        <keybind key="W-d"><action name="Execute" command="${pkgs.fuzzel}/bin/fuzzel"/></keybind>
        <keybind key="W-Return"><action name="Execute" command="${pkgs.foot}/bin/foot"/></keybind>
        <keybind key="W-e"><action name="Execute" command="${pkgs.thunar}/bin/thunar"/></keybind>
        <keybind key="A-F4"><action name="Close"/></keybind>
        <keybind key="W-Up"><action name="ToggleMaximize"/></keybind>
      </keyboard>
    </openbox_config>
  '';

  menuXml = pkgs.writeText "rednix-labwc-menu" ''
    <?xml version="1.0" encoding="UTF-8"?>
    <openbox_menu>
      <menu id="root-menu">
        <item label="Applications (fuzzel)">
          <action name="Execute" command="${pkgs.fuzzel}/bin/fuzzel"/>
        </item>
        <item label="Terminal">
          <action name="Execute" command="${pkgs.foot}/bin/foot"/>
        </item>
        <item label="Files">
          <action name="Execute" command="${pkgs.thunar}/bin/thunar"/>
        </item>
        <separator/>
        <item label="Reconfigure"><action name="Reconfigure"/></item>
        <item label="Exit"><action name="Exit"/></item>
      </menu>
    </openbox_menu>
  '';

  labwcConfigDir = pkgs.runCommand "rednix-labwc-config" { preferLocalBuild = true; } ''
    mkdir -p $out
    cp ${rcXml} $out/rc.xml
    cp ${menuXml} $out/menu.xml
  '';

  desktopStart = pkgs.writeShellScript "rednix-desktop-start" ''
    # Headless wlroots: no DRM seat or input devices exist in the VM, software
    # rendering only; VNC input arrives through wayvnc's virtual input.
    export WLR_BACKENDS=headless
    export WLR_LIBINPUT_NO_DEVICES=1
    export WLR_RENDERER=pixman
    export XKB_CONFIG_ROOT=${xkbRoot}
    # The unit's PATH is intentionally minimal; the system profile must come
    # first so .desktop Exec entries (fuzzel spawns bare names like `ghidra`)
    # and anything else the desktop spawns resolve.
    export PATH="/run/current-system/sw/bin:$PATH"
    # fuzzel's launcher reads .desktop entries from XDG_DATA_DIRS; without this
    # the system profile's applications are invisible and the list is empty.
    export XDG_DATA_DIRS="/run/current-system/sw/share:''${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
    # X11 tools (Ghidra) launched inside the session need a display; wlroots
    # spawns Xwayland on :0 the first time a client connects.
    export DISPLAY=:0
    ${pkgs.labwc}/bin/labwc -C ${labwcConfigDir} &
    labwc_pid=$!
    for _ in $(seq 1 50); do
      ls "$XDG_RUNTIME_DIR"/wayland-* >/dev/null 2>&1 && break
      sleep 0.2
    done
    export WAYLAND_DISPLAY=$(ls "$XDG_RUNTIME_DIR" | grep -E "^wayland-[0-9]+$" | head -1)
    ${pkgs.wlr-randr}/bin/wlr-randr --output HEADLESS-1 --custom-mode 2560x1600
    export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
    [ -S "$XDG_RUNTIME_DIR/bus" ] || \
      ${pkgs.dbus}/bin/dbus-daemon --session --address="$DBUS_SESSION_BUS_ADDRESS" --fork
    ${pkgs.wayvnc}/bin/wayvnc 127.0.0.1 5901 &
    ${pkgs.waybar}/bin/waybar -c ${waybarConfig} -s ${waybarStyle} &
    wait $labwc_pid
  '';
in
{
  # The guest user never logs in interactively (everything runs through ssh or
  # systemd services), so the XDG base directories are never created. fuzzel
  # aborts without $HOME/.cache ("failed to open: No such file or directory"),
  # which makes the waybar Apps button appear dead.
  systemd.tmpfiles.rules = [
    "d /home/rednix/.cache 0755 rednix rednix -"
    "d /home/rednix/.config 0755 rednix rednix -"
    "d /home/rednix/.local 0755 rednix rednix -"
    "d /home/rednix/.local/share 0755 rednix rednix -"
  ];

  # Foot's default `monospace` resolves through fontconfig; without these the
  # guest falls back to a non-monospace/bitmap font (foot warns at startup and
  # the terminal renders with broken glyphs). DejaVu is the only font pack the
  # guest needs.
  fonts.fontconfig.enable = true;
  fonts.packages = with pkgs; [ dejavu_fonts ];
  fonts.fontconfig.defaultFonts = {
    monospace = [ "DejaVu Sans Mono" ];
    sansSerif = [ "DejaVu Sans" ];
    serif = [ "DejaVu Serif" ];
  };

  environment.systemPackages = with pkgs; [
    labwc
    wayvnc
    foot
    fuzzel
    waybar
    xwayland
    wlr-randr
    wl-clipboard
    xterm
    thunar
  ];

  services.dbus.enable = true;

  # Wayland-native fallback desktop: labwc (Openbox-style floating WM) gives
  # every window real title bars with iconify/maximize/close buttons plus a
  # right-click root menu; waybar provides the App/Terminal buttons and a
  # taskbar, fuzzel the launcher, Thunar the file manager. It runs headless
  # (no DRM seat or input devices exist in the VM, software rendering only);
  # wayvnc serves it as plain VNC/RFB on 127.0.0.1:5901 (guest-local only),
  # reached through the SSH tunnel by the same `rednix desktop` flow — no auth
  # because the only listener path is guest-local (see docs/threat-model.md).
  # If clicks stop doing anything in the VNC, restart the session:
  # `rednix desktop --stop && rednix desktop`.
  systemd.services.rednix-desktop = {
    description = "RedNix fallback desktop (headless labwc + wayvnc)";
    # The service PATH must include `sh`: sway/labwc-family `exec` (the
    # Mod4+d / Mod4+Return bindings) resolves `sh` via execlp(3). The
    # fuzzel/foot entries keep any bare-name spawns working; the waybar, labwc
    # and menu configs use absolute store paths so they do not depend on PATH.
    path = with pkgs; [ dbus bashInteractive fuzzel foot ];
    serviceConfig = {
      Type = "simple";
      User = "rednix";
      RuntimeDirectory = "rednix-desktop";
      # labwc + wayvnc + waybar + XWayland clients together exceed the systemd
      # default soft descriptor limit.
      LimitNOFILE = 524288;
      ExecStart = desktopStart;
      Restart = "no";
    };
    environment.XKB_CONFIG_ROOT = xkbRoot;
    environment.XDG_RUNTIME_DIR = "/run/rednix-desktop";
  };

  # The guest user must be able to raise/lower the desktop on demand without a
  # root shell; tool service modules grant their own service operations separately.
  security.sudo.extraRules = [
    {
      users = [ "rednix" ];
      commands = [
        {
          command = "/run/current-system/sw/bin/systemctl start rednix-desktop.service";
          options = [ "NOPASSWD" ];
        }
        {
          command = "/run/current-system/sw/bin/systemctl stop rednix-desktop.service";
          options = [ "NOPASSWD" ];
        }
      ];
    }
  ];
}
