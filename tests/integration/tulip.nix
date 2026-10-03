{ pkgs }:
pkgs.testers.runNixOSTest {
  name = "rednix-tulip";
  nodes.machine = { ... }: {
    imports = [ ../../modules/tools/tulip.nix ];
    _module.args = { guestUid = 1000; guestGid = 1000; };
    virtualisation.memorySize = 3072;
    users.groups.rednix.gid = 1000;
    users.users.rednix = {
      isNormalUser = true;
      uid = 1000;
      group = "rednix";
      extraGroups = [ "wheel" ];
    };
    security.sudo.wheelNeedsPassword = true;
    networking.useDHCP = false;
    services.postgresql = {
      enable = true;
      dataDir = "/var/lib/rednix/postgres";
      ensureUsers = [ { name = "rednix"; ensureClauses.createdb = true; } ];
    };
    systemd.tmpfiles.rules = [
      "d /var/lib/rednix 0755 root root -"
      "d /var/lib/rednix/postgres 0700 postgres postgres -"
    ];
    environment.systemPackages = [ pkgs.curl pkgs.python3 ];
    environment.etc."tulip-pcap.py".source = ./tulip-pcap.py;
  };
  testScript = ''
    import json
    from datetime import timedelta

    start_all()
    machine.wait_for_unit("postgresql.service")
    machine.succeed("ip link set eth0 down")
    machine.fail("systemctl is-active rednix-tulip.target")
    machine.fail("su - rednix -c 'sudo -n true'")
    machine.succeed("su - rednix -c 'tulip init'")
    machine.succeed("""echo '[{"ip":"10.60.4.1","port":8080,"name":"Shop"}]' > /var/lib/rednix/tulip/services.json""")
    machine.succeed("su - rednix -c 'tulip start'")
    machine.succeed("curl -f http://127.0.0.1:3000/ | grep '<html'")
    services = json.loads(machine.succeed("curl -sf http://127.0.0.1:3000/api/services"))
    assert services[0]["name"] == "Shop", services
    machine.succeed("ss -lnt | grep '127.0.0.1:3000'")
    machine.fail("ss -lnt | grep -E '(0.0.0.0|\\*|\\[::\\]):(3000|5000) '")

    # Stage a complete file, then publish it into the watched directory.
    machine.succeed("mkdir /tmp/remote-pcaps; python3 /etc/tulip-pcap.py /tmp/remote-pcaps/sample.pcap")
    machine.succeed("touch /tmp/remote-pcaps/incomplete.pcap.part")
    machine.succeed("su - rednix -c \"rsync -rt --ignore-existing --include='*.pcap' --exclude='*' /tmp/remote-pcaps/ /var/lib/rednix/tulip/pcaps/\"")
    machine.fail("test -e /var/lib/rednix/tulip/pcaps/incomplete.pcap.part")
    query = "curl -sf -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:3000/api/query"
    machine.wait_until_succeeds(query + " | grep 'flag-out'", timeout=timedelta(seconds=60))
    flows = json.loads(machine.succeed(query))
    assert len(flows) == 1, flows
    flow_id = flows[0]["id"]
    machine.succeed(f"curl -sf http://127.0.0.1:3000/api/to_pwn/{flow_id} | grep 'tulip-smoke'")
    machine.succeed(f"curl -sf http://127.0.0.1:3000/api/flow/{flow_id}")

    # Existing workspace database access still works via peer authentication.
    machine.succeed("su - rednix -c 'createdb msf_test'")
    machine.succeed("su - rednix -c 'psql msf_test -c \"SELECT 1\"'")
    machine.succeed("su - rednix -c 'tulip stop'")
    machine.fail("curl -sf http://127.0.0.1:3000/")
    machine.succeed("su - rednix -c 'tulip start'")
    assert json.loads(machine.succeed(query))[0]["id"] == flow_id

    machine.shutdown()
    machine.start()
    machine.wait_for_unit("postgresql.service")
    machine.succeed("ip link set eth0 down")
    machine.fail("systemctl is-active rednix-tulip.target")
    machine.succeed("su - rednix -c 'tulip start'")
    assert json.loads(machine.succeed(query))[0]["id"] == flow_id
  '';
}
