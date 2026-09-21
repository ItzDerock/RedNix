{ lib, ... }:
{
  networking.useNetworkd = true;

  systemd.network = {
    enable = true;
    wait-online.enable = false;

    # The launcher decides the NIC at start time via ./qemu-extra-args, so the
    # guest identifies the active profile by the MAC the launcher assigns.
    networks."40-rednix-nat" = {
      matchConfig.PermanentMACAddress = "02:00:00:00:00:01";
      networkConfig.DHCP = "yes";
      linkConfig.RequiredForOnline = "no";
    };

    networks."40-rednix-routed" = {
      matchConfig.PermanentMACAddress = "02:00:00:00:00:02";
      address = [ "10.7.0.2/24" ];
      gateway = [ "10.7.0.1" ];
      networkConfig = {
        IPv6AcceptRA = false;
        LinkLocalAddressing = "no";
      };
      linkConfig.RequiredForOnline = "no";
    };
  };

  # Scope enforcement lives in host nftables (rednix net up), not in the guest,
  # so guest root cannot lift it. See docs/networking.md.
  networking.firewall.enable = false;
}
