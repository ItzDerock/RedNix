{
  config,
  lib,
  pkgs,
  guestUid,
  guestGid,
  hostUid,
  hostGid,
  ...
}:
let
  stateRoot = "/var/lib/rednix";
  bindMounts = {
    "/home/rednix" = "${stateRoot}/home";
    "/var/lib/postgresql" = "${stateRoot}/postgres";
    "/root" = "${stateRoot}/root";
  };
  mountUnitName = path:
    lib.removePrefix "-" (builtins.replaceStrings [ "/" ] [ "-" ] path);

  workShare = builtins.head (builtins.filter (s: s.tag == "work") config.microvm.shares);
in
{
  # The guest root filesystem is tmpfs; everything below survives reboots
  # because it lives on this volume. The runner auto-creates and formats the
  # sparse image on first start.
  fileSystems = builtins.mapAttrs (mountPoint: device: {
    inherit device;
    fsType = "none";
    options = [ "bind" ];
    depends = [ stateRoot ];
  }) bindMounts // {
    "${stateRoot}".neededForBoot = true;
  };

  microvm.volumes = [
    {
      image = "state.img";
      mountPoint = stateRoot;
      size = 65536;
      fsType = "ext4";
    }
  ];

  # Exactly one host folder is shared (R2). The relative source resolves
  # against the event state directory (the launcher symlinks ./work), and
  # posixAcl is disabled because --posix-acl is mutually exclusive with
  # the --translate-uid/--translate-gid mapping.
  microvm.shares = [
    {
      proto = "virtiofs";
      tag = "work";
      source = "work";
      socket = "rednix-virtiofs-work.sock";
      mountPoint = "/work";
      posixAcl = false;
      extraArgs = [
        "--translate-uid" "guest:${toString guestUid}:${toString hostUid}:1"
        "--translate-gid" "guest:${toString guestGid}:${toString hostGid}:1"
      ];
    }
  ];

  # microvm.nix's own virtiofsd-run wraps virtiofsd in supervisord configured
  # with user = "root", which cannot start as an unprivileged user. The
  # launcher therefore uses this direct script instead. virtiofsd's sandbox
  # bind-mounts the shared dir, which fails with EINVAL when given the ./work
  # symlink, so it is dereferenced at runtime against the event's cwd.
  # inode-file-handles needs CAP_DAC_READ_SEARCH and is disabled accordingly.
  microvm.binScripts.rednix-virtiofsd-work = ''
    exec ${lib.getExe config.microvm.virtiofsd.package} \
      --socket-path=${lib.escapeShellArg workShare.socket} \
      --shared-dir="$(readlink -f ${lib.escapeShellArg workShare.source})" \
      --thread-pool-size ${toString config.microvm.virtiofsd.threadPoolSize} \
      ${lib.concatStringsSep " " workShare.extraArgs}
  '';

  microvm.virtiofsd.inodeFileHandles = "never";

  # Bind-mount sources must exist inside the volume before the bind mounts run;
  # tmpfiles has no ordering guarantee against mount units, so a oneshot sits
  # explicitly between the volume mount and every bind mount. Default
  # dependencies are dropped because a service default (After=basic.target)
  # would form an ordering cycle through local-fs.target (volume mount → prep
  # → bind mounts → local-fs.target → sysinit.target → basic.target); the
  # service is activated as part of the local-fs transaction instead.
  systemd.services.rednix-state-prep = {
    description = "Create RedNix state directories on the persistent volume";
    unitConfig.DefaultDependencies = false;
    after = [ "var-lib-rednix.mount" ];
    before = map (mp: "${mountUnitName mp}.mount") (builtins.attrNames bindMounts);
    wantedBy = [ "local-fs.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    script = ''
      mkdir -p ${stateRoot}/home ${stateRoot}/postgres ${stateRoot}/root ${stateRoot}/ssh
      chmod 0755 ${stateRoot}/ssh
      chown ${toString guestUid}:${toString guestGid} ${stateRoot}/home
      chmod 0700 ${stateRoot}/home ${stateRoot}/root
      if id postgres >/dev/null 2>&1; then
        chown postgres:postgres ${stateRoot}/postgres
        chmod 0700 ${stateRoot}/postgres
      fi
    '';
  };

  # Guest-local PostgreSQL backing Metasploit's workspace DB; the data directory
  # lives on the persistent volume so msfdb init survives reboots. The role can
  # create its own database because `msfdb init` runs as the guest user.
  services.postgresql = {
    enable = true;
    dataDir = "${stateRoot}/postgres";
    ensureUsers = [
      {
        name = "rednix";
        ensureClauses = {
          createdb = true;
        };
      }
    ];
  };
}
