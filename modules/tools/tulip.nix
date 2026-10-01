# Tulip's dependencies are built into the guest; starting it never fetches code.
{ config, pkgs, lib, guestUid, guestGid, ... }:
let
  tulip = import ../../pkgs/tulip { inherit pkgs; postgresql = config.services.postgresql.package; };
  stateDir = "/var/lib/rednix/tulip";
  units = map (name: "rednix-tulip-${name}.service") [ "api" "assembler" "web" ];
  schema = pkgs.writeText "tulip-schema.sql" (''
    CREATE EXTENSION timescaledb;
    CREATE EXTENSION pgcrypto;
    CREATE EXTENSION intarray;
    CREATE EXTENSION "uuid-ossp";
    CREATE EXTENSION pg_trgm;
    CREATE EXTENSION btree_gin;
    CREATE EXTENSION btree_gist;
  '' + builtins.readFile "${tulip.src}/services/schema/functions.sql"
    + builtins.readFile "${tulip.src}/services/schema/schema.sql" + ''
    GRANT ALL ON ALL TABLES IN SCHEMA public TO rednix;
    GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO rednix;
  '');
  webConfig = pkgs.writeText "tulip-nginx.conf" ''
    daemon off;
    pid /run/rednix-tulip-web/nginx.pid;
    error_log stderr;
    events {}
    http {
      include ${pkgs.nginx}/conf/mime.types;
      access_log off;
      client_body_temp_path /run/rednix-tulip-web/client;
      proxy_temp_path /run/rednix-tulip-web/proxy;
      fastcgi_temp_path /run/rednix-tulip-web/fastcgi;
      uwsgi_temp_path /run/rednix-tulip-web/uwsgi;
      scgi_temp_path /run/rednix-tulip-web/scgi;
      server {
        listen 127.0.0.1:3000;
        root ${tulip.frontend};
        location / { try_files $uri $uri/ /index.html; }
        location /api/ {
          proxy_pass http://127.0.0.1:5000/;
          proxy_read_timeout 60s;
        }
      }
    }
  '';
  common = {
    requires = [ "rednix-tulip-init.service" ];
    after = [ "rednix-tulip-init.service" ];
    partOf = [ "rednix-tulip.target" ];
    environment = {
      TIMESCALE = "postgresql://rednix@/tulip?host=/run/postgresql";
      TULIP_TRAFFIC_DIR = "${stateDir}/pcaps";
      TULIP_SERVICES_FILE = "${stateDir}/services.json";
    };
    serviceConfig = {
      User = "rednix";
      Group = "rednix";
      EnvironmentFile = "${stateDir}/tulip.env";
      Restart = "on-failure";
      RestartSec = 2;
    };
  };
in {
  environment.systemPackages = [ pkgs.rsync (pkgs.writeShellApplication {
    name = "tulip";
    runtimeInputs = [ pkgs.systemd pkgs.curl pkgs.coreutils ];
    text = ''
      case "''${1:-help}" in
        # Use NixOS's setuid wrapper, rather than the raw store sudo binary.
        init) /run/wrappers/bin/sudo systemctl start rednix-tulip-init.service ;;
        start)
          /run/wrappers/bin/sudo systemctl start rednix-tulip.target
          for _ in $(seq 1 60); do
            if curl --fail --silent --max-time 2 http://127.0.0.1:3000/api/tags >/dev/null; then
              echo "Tulip: http://127.0.0.1:3000 (guest localhost)"
              exit 0
            fi
            sleep 1
          done
          /run/wrappers/bin/sudo journalctl -n 40 --no-pager -u 'rednix-tulip-*'
          echo "Tulip did not become ready; inspect tulip logs." >&2
          exit 1
          ;;
        stop) /run/wrappers/bin/sudo systemctl stop rednix-tulip.target ;;
        status) systemctl status ${lib.concatStringsSep " " units} ;;
        logs) /run/wrappers/bin/sudo journalctl -f -u 'rednix-tulip-*' ;;
        *) echo "Usage: tulip {init|start|stop|status|logs}" ;;
      esac
    '';
  }) ];

  # Reuse the persistent PostgreSQL cluster already used by Metasploit.
  services.postgresql = {
    extensions = ps: [ ps.timescaledb-apache ps.pg_hint_plan tulip.extension ];
    settings = {
      shared_preload_libraries = "timescaledb,pg_hint_plan";
      "timescaledb.telemetry_level" = "off";
    };
    ensureDatabases = [ "tulip" ];
  };

  systemd.targets.rednix-tulip = {
    description = "Tulip attack/defense traffic analysis";
    requires = units;
    after = units;
  };

  systemd.services.rednix-tulip-init = {
    description = "Initialize event-local Tulip configuration and database";
    requires = [ "postgresql.target" ];
    after = [ "postgresql.target" ];
    unitConfig.RequiresMountsFor = [ "/var/lib/rednix" ];
    path = [ config.services.postgresql.package pkgs.util-linux ];
    serviceConfig = { Type = "oneshot"; RemainAfterExit = true; };
    script = ''
      install -d -m 0755 -o ${toString guestUid} -g ${toString guestGid} ${stateDir} ${stateDir}/pcaps
      if [ ! -e ${stateDir}/tulip.env ]; then
        cat > ${stateDir}/tulip.env <<EOF
      TICK_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
      TICK_LENGTH=180000
      FLAG_REGEX="[A-Z0-9]{31}="
      EOF
        chown ${toString guestUid}:${toString guestGid} ${stateDir}/tulip.env
        chmod 0600 ${stateDir}/tulip.env
      fi
      if [ ! -e ${stateDir}/services.json ]; then
        echo '[]' > ${stateDir}/services.json
        chown ${toString guestUid}:${toString guestGid} ${stateDir}/services.json
      fi
      # All schema DDL is transactional: a failed init can be retried safely.
      if [ "$(runuser -u postgres -- psql -d tulip -Atc "SELECT to_regclass('public.flow') IS NOT NULL")" != t ]; then
        runuser -u postgres -- psql -d tulip -v ON_ERROR_STOP=1 --single-transaction -f ${schema}
      fi
    '';
  };
  systemd.services.rednix-tulip-api = lib.recursiveUpdate common {
    description = "Tulip API";
    serviceConfig.ExecStart = "${tulip.api}/bin/tulip-api -w 3 -t 60 -b 127.0.0.1:5000";
  };
  systemd.services.rednix-tulip-assembler = lib.recursiveUpdate common {
    description = "Tulip PCAP flow assembler";
    serviceConfig = {
      ExecStart = "${tulip.importer}/bin/assembler -http-session-tracking -skipchecksum -disable-converters -dir ${stateDir}/pcaps";
      KillSignal = "SIGINT";
    };
  };
  systemd.services.rednix-tulip-web = lib.recursiveUpdate common {
    description = "Tulip local web UI";
    serviceConfig = {
      ExecStart = "${pkgs.nginx}/bin/nginx -e stderr -c ${webConfig} -p /run/rednix-tulip-web";
      RuntimeDirectory = "rednix-tulip-web";
    };
  };
  environment.etc."rednix/tulip.md".source = ../../docs/tulip.md;
}
