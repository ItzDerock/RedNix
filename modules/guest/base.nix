{ lib, guestUid, guestGid, ... }:
{
  networking.hostName = "rednix";
  time.timeZone = "UTC";

  system.stateVersion = "25.11";

  users.groups.rednix.gid = guestGid;

  users.users.rednix = {
    isNormalUser = true;
    uid = guestUid;
    group = "rednix";
    extraGroups = [ "wheel" "docker" ];
    initialPassword = "rednix";
    description = "RedNix guest user";
  };

  # The guest root is untrusted by design (see docs/threat-model.md); the
  # disposable reset story matters more than in-guest hardening.
  security.sudo.enable = true;
}
