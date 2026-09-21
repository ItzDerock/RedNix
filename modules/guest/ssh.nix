{
  lib,
  guestSshPubKey,
  ...
}: let
  # `rednix build` injects the user's public key here via a flake input
  # override. The committed placeholder holds only comment lines, so filtering
  # them out means a standalone `nix build` produces a guest with no usable
  # authorized key until it is built through the launcher.
  keyLines = lib.filter (
    line: line != "" && !lib.hasPrefix "#" line
  ) (lib.splitString "\n" guestSshPubKey);
in {
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "no";
    };
  };

  users.users.rednix.openssh.authorizedKeys.keys = keyLines;
}
