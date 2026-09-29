{ pkgs, ... }:
{
  imports = [
    ./base.nix
    ./ssh.nix
    ./state.nix
    ./networking.nix
    ./wayland.nix
    ./desktop.nix
    ./fhs.nix
    ./containers.nix
    ../tools/core.nix
    ../tools/net.nix
    ../tools/exploit.nix
    ../tools/rev.nix
    ../tools/forensics.nix
    ../tools/crypto.nix
    ../tools/field-guide.nix
  ];

  # Metasploit and a few other pentest tools are marked unfree in nixpkgs;
  # the closure is guest-only either way.
  nixpkgs.config.allowUnfree = true;

  # Mirror the journal to the serial console: the QEMU console log doubles as
  # the guest's diagnosable record during competitions.
  services.journald.settings.Journal = {
    ForwardToConsole = true;
    TTYPath = "/dev/ttyS0";
  };

  microvm = {
    hypervisor = "qemu";
    mem = 16384;
    vcpu = 8;
    storeOnDisk = true;

    # QMP socket relative to the event state directory (the cwd microvm-run
    # is invoked with), so identical names in different event directories
    # never collide and one runner serves every event.
    socket = "rednix.sock";

    # Per-event QEMU arguments (SSH hostfwd port, NAT vs TAP NIC) are written
    # by the launcher to ./qemu-extra-args in the event directory and read at
    # exec time, keeping a single runner build valid for all events.
    extraArgsScript = ''
      cat ./qemu-extra-args 2>/dev/null || true
    '';
  };
}
