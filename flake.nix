{
  description = "RedNix — a disposable per-CTF NixOS MicroVM pentesting workbench";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    microvm = {
      url = "github:microvm-nix/microvm.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    # Placeholder so the flake evaluates standalone. `rednix build` injects the
    # user's real guest public key with --override-input guestKey, which implies
    # --no-write-lock-file, so this lock entry never changes.
    guestKey = {
      url = "path:keys/rednix.pub";
      flake = false;
    };
  };

  outputs = {
    self,
    nixpkgs,
    microvm,
    guestKey,
  }: let
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};

    # UID/GID translation for the /work virtiofs share. Defaults match
    # derock's host (uid 1000, gid 100); `rednix doctor` compares the actual
    # host ids and tells you to change these when they differ.
    guestUid = 1000;
    guestGid = 1000;
    hostUid = 1000;
    hostGid = 100;

    specialArgs = {
      inherit guestUid guestGid hostUid hostGid;
      guestSshPubKey = builtins.readFile guestKey;
    };
  in {
    nixosConfigurations.rednix = nixpkgs.lib.nixosSystem {
      inherit system specialArgs;
      modules = [
        microvm.nixosModules.microvm
        ./modules/guest
      ];
    };

    packages.${system} = {
      guestRunner = self.nixosConfigurations.rednix.config.microvm.runner.qemu;

      rednix = pkgs.python3Packages.buildPythonApplication {
        pname = "rednix";
        version = "0.1.0";
        src = ./src;
        pyproject = true;
        build-system = [ pkgs.python3Packages.setuptools ];
        meta = {
          mainProgram = "rednix";
          description = "Launcher for RedNix per-event MicroVMs";
          license = pkgs.lib.licenses.mit;
        };
      };

      default = self.packages.${system}.rednix;
    };

    apps.${system}.rednix = {
      type = "app";
      program = "${self.packages.${system}.rednix}/bin/rednix";
    };

    # `nix develop` puts the launcher and every host-side dependency it execs
    # (ssh/scp/ssh-keygen, waypipe, vncviewer, nix, nft, ip) on PATH.
    devShells.${system}.default = pkgs.mkShell {
      packages = [
        self.packages.${system}.rednix
        pkgs.openssh
        pkgs.waypipe
        pkgs.tigervnc
        pkgs.nix
        pkgs.nftables
        pkgs.iproute2
        (pkgs.python3.withPackages (ps: [ ps.pytest ]))
      ];
    };
  };
}
