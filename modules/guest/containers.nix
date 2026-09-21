{
  pkgs,
  lib,
  ...
}:
let
  # Images are baked at build time so the guest needs no registry access on
  # competition day. Manifest digests and tarball hashes are pinned below.
  ubuntu2204 = pkgs.dockerTools.pullImage {
    imageName = "ubuntu";
    imageDigest = "sha256:b8b6ee6aa931ecd9d0d952abc34dc0e5f7c6a30c6bb71b079fe399fde0329c02";
    finalImageTag = "22.04";
    sha256 = "sha256-/hxCtWP5lLygO/5V+sJHFUohQ/+ATmvvZZ/YP553J7I=";
  };

  ubuntu2404 = pkgs.dockerTools.pullImage {
    imageName = "ubuntu";
    imageDigest = "sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3";
    finalImageTag = "24.04";
    sha256 = "sha256-JH369uSSA9smCqIXhMXn3A8jwYeJ4EOqQ3WfpHqwMMg=";
  };

  images = [
    (ubuntu2204 // { tag = "22.04"; })
    (ubuntu2404 // { tag = "24.04"; })
  ];

  loadScript = lib.concatMapStrings (img: ''
    docker image inspect ubuntu:${img.tag} >/dev/null 2>&1 || docker load -i ${img}
  '') images;
in
{
  virtualisation.docker = {
    enable = true;
    daemon.settings = {
      data-root = "/var/lib/rednix/docker";
    };
  };

  # With the routed TAP profile, networkd must not manage Docker's veth
  # interfaces or container networking breaks (microvm.nix docs note).
  environment.etc."systemd/network/19-docker.network".text = ''
    [Match]
    Name=veth*

    [Link]
    Unmanaged=yes
  '';

  systemd.services.docker-load = {
    description = "Load prebuilt offline Ubuntu images into Docker";
    after = [ "docker.service" ];
    requires = [ "docker.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    script = loadScript;
  };
}
