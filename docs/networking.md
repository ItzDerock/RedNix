# Networking

## Compliance caveat — read this first

**The CTF rules forbid *bridging* the CTF network and do not say whether local VM NAT is acceptable. This plan does
not resolve that ambiguity.**

- Ship `nat` as the default — it is not a bridge and adds no host state.
- Do **not** treat the `routed` profile as pre-approved.
- **Have the captain confirm with `support@gam3z-inc.com` before relying on either profile on the event network.**

A strict interpretation of the rules carries a disqualification risk. The compliance question must be answered in
writing before the event (M3 exit criterion).

## Profiles

`microvm.optimize.enable` is `true` by default, which pulls in `systemd-networkd`. Configure it explicitly.

The two profiles:

- **`nat` (default)** — QEMU SLiRP user networking. Needs zero host firewall state.
- **`routed` (opt-in)** — TAP plus routed NAT/DNAT, applied by host nftables. Exists because reverse shells cannot
  reach a SLiRP guest.

Select the profile at start: `rednix start <event> --network nat|routed`.

## `nat` profile (SLiRP, default)

```nix
microvm.interfaces = [{ type = "user"; id = "usernet"; mac = "02:00:00:00:00:01"; }];
```

- Guest gets DHCP `10.0.2.15/24`, gateway `10.0.2.2`, DNS `10.0.2.3`.
- **Outbound only.** The guest is unreachable from the LAN.
- QEMU SLiRP supplies the guest's DHCP address, DNS forwarding, and outbound IPv4 NAT automatically; no host
  TAP device, IP forwarding, or nftables setup is needed. Check it after boot with
  `rednix exec <event> -- ip route` and `rednix exec <event> -- curl -I https://example.com` (or use a known
  event target if internet access is restricted). A successful SSH readiness check alone does not prove guest
  outbound access.
- `forwardPorts` binds SSH to `127.0.0.1` on the host:
  `microvm.forwardPorts = [{ from = "host"; host.address = "127.0.0.1"; host.port = 2222; guest.port = 22; }]`.
- **Reverse shells into the guest do not work** in this profile — SLiRP has no inbound path beyond declared
  `hostfwd` entries. This is a genuine capability gap, and the reason the `routed` profile exists.

For callbacks from the competition network, the `routed` profile requires host setup before VM start:
`sudo rednix net up <event> --iface <ctf-interface>`, then
`rednix start <event> --network routed`. It creates the event TAP device, enables IPv4 forwarding, and applies
scoped nftables NAT/DNAT rules. Use `rednix net down <event>` after the event. Confirm with organizers that local
VM NAT/routing is permitted before connecting it to their network.

SSH port allocation is per-event: the launcher allocates a free port (default base 2222) and passes it as
`-o hostfwd=tcp:127.0.0.1:<port>-:22` via `microvm.qemu.extraArgs`, so two events can run side-by-side with one
built runner and ports decided at start time.

## `routed` profile (opt-in)

```nix
microvm.interfaces = [{ type = "tap"; id = "rednix-<event>"; mac = "02:…"; tap.vhost = true; }];
```

- Guest static `10.7.0.2/24`, default route `10.7.0.1` (the host TAP address).
- SSH is reached directly over the TAP address (no port forward needed).

### Host-side nftables (applied by `rednix net up <event>`, torn down by `rednix net down`)

Kept in a dedicated `inet rednix` table so nothing else on the host is touched. The exact rule set:

- `net.ipv4.ip_forward=1` (host-wide; unavoidable, and why `routed` is opt-in).
- `inet rednix` table, **forward chain**: allow `iifname rednix-<event> oifname <ctf-iface>` and the reverse;
  `policy drop` otherwise.
- `masquerade` on egress for `10.7.0.0/24`.
- **Scope enforcement lives outside the guest**, so guest root cannot lift it:
  - drop `iifname rednix-<event>` traffic to loopback, RFC1918 non-event ranges, link-local, and host addresses;
  - drop guest IPv6 entirely (or apply mirrored rules) — the log called this out and it is easy to forget;
  - `dnat` only the explicitly configured callback ports to the guest;
  - keep an explicit allow-list of event destinations when the organizers hand out fixed target IPs.

### Interface rule: designated Ethernet only

**The TAP device must be created on the designated Ethernet interface only. Never create a bridge, never use
`macvtap` on the competition link.**

Note that `microvm.nix`'s own "simple network setup" documentation example bridges the physical NIC onto `br0` and
is therefore explicitly **not** the pattern to copy.

## `rednix net` subcommands

- `rednix net up` / `rednix net down` — apply/tear down the routed-profile host NAT/DNAT state.
- `rednix net show` — print the effective ruleset in plain language so it can be read aloud to a teammate.
- `rednix net allow <cidr:port>` — manage the destination allow-list.
- `rednix net callback <port>` — manage the DNAT callback ports.

`rednix net` requires root; it prints the exact command if not.

## Docker and systemd-networkd

Note the Docker/networkd interaction from the `microvm.nix` docs: with a bridged setup Docker's `veth*` interfaces
must be left unmanaged by `systemd-networkd` or container networking breaks. This is only relevant to the `routed`
profile; add the `19-docker` unmanaged rule preemptively.

## Acceptance tests

| # | Test | Assertion |
|---|---|---|
| A2 | Blocked host service | Run a listener on `127.0.0.1:<port>` on the host. From the guest, connect must fail in both profiles. |
| A3 | Scope enforcement | In `routed`, guest traffic to a non-allow-listed destination is dropped; guest root cannot flush the `rednix` nftables table into a working state after `rednix net up`. |
| A4 | Callback forwarding | A mock listener on the host receives a connection from the guest via `rednix net callback <port>`, proving reverse shells work in `routed`. |
