# Tulip: attack/defense traffic analysis

[Tulip](https://github.com/OpenAttackDefenseTools/tulip) is built for attack/defense CTFs:
search TCP/UDP flows and flags, compare traffic, and generate Python replay snippets.
Capture on **your defended service box**, then send completed PCAPs into RedNix.
Encrypted traffic needs separate decryption.

## Prepare before the event

Build the guest with network access, then boot your event:

```sh
rednix build EVENT --pin
rednix start EVENT
rednix shell EVENT
```

Inside the **guest**, initialize and edit the event configuration:

```sh
tulip init
cd /var/lib/rednix/tulip
$EDITOR tulip.env
$EDITOR services.json
```

`tulip.env` uses systemd EnvironmentFile syntax, not a shell script. Set the event's
UTC start time, tick duration **in milliseconds**, and flag regular expression:

```ini
TICK_START=2026-10-01T12:00:00Z
TICK_LENGTH=180000
FLAG_REGEX="[A-Z0-9]{31}="
```

Replace these examples with your event values. In `services.json`, use the defended
box's IP **as it appears in the capture**, service ports, and names:

```json
[
  {"ip": "10.60.4.1", "port": 8080, "name": "Shop"},
  {"ip": "10.60.4.1", "port": 5555, "name": "Notes"}
]
```

Start the stack:

```sh
tulip start
```

Open `http://127.0.0.1:3000` in a guest browser (`rednix gui --event EVENT firefox`
from the host), or tunnel the UI to your **host browser**:

```sh
# On the host; use your state root if it differs from the default.
ssh -F ~/.local/state/rednix/ssh_config -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:3000:127.0.0.1:3000 rednix-EVENT
```

Leave the tunnel running and visit `http://127.0.0.1:3000` on the host. Change the
local port if busy. The UI and API bind only to guest loopback.

Rehearse startup and sample import with internet unavailable. All dependencies are
baked into the guest; startup performs no downloads or Nix evaluation.

## Capture remotely

On the **defended box**, choose the service interface (`ip -br addr`) and run this
in a persistent shell/service. The hook renames only completed captures:

```sh
sudo install -d -m 0700 /var/tmp/tulip-pcaps
sudo tee /usr/local/bin/tulip-pcap-complete >/dev/null <<'SH'
#!/bin/sh
mv -- "$1" "${1%.part}"
SH
sudo chmod 0755 /usr/local/bin/tulip-pcap-complete
sudo tcpdump -i eth0 -nn -s 0 -U -Z root -G 30 \
  -w '/var/tmp/tulip-pcaps/traffic-%Y%m%dT%H%M%S.pcap.part' \
  -z /usr/local/bin/tulip-pcap-complete \
  'tcp and (port 8080 or port 5555)'
```

Adjust interface, ports, and protocol (`tcp or udp` if needed). `-s 0` keeps full
payloads; filtering service ports excludes the SSH transfer. `-Z root` lets the
hook rename files in the root-owned directory. The active file stays `.part`.

## Pull completed captures into RedNix

Inside the **guest**, put a dedicated event SSH key at `~/.ssh/ctf_box` (mode 0600)
and verify the defended box's SSH host key on the first connection. RedNix does
not forward your host agent. The defended box also needs `rsync` installed.
Pull completed files continuously, or run the `rsync` command once:

```sh
while true; do
  rsync -rt --ignore-existing --include='*.pcap' --exclude='*' \
    -e 'ssh -i /home/rednix/.ssh/ctf_box -o BatchMode=yes -o ConnectTimeout=5' \
    root@DEFENDED_BOX:/var/tmp/tulip-pcaps/ /var/lib/rednix/tulip/pcaps/ \
    || echo 'PCAP transfer failed; retrying' >&2
  sleep 5
done
```

Use a capture-readable account in place of root when available. Default rsync
publishes files by rename; **do not use `--inplace`, `--append`, or `--partial`** in
Tulip's watched directory. Never overwrite imported filenames. Rename tcpdump's
last `.part` manually only after the process exits. Allow time for rotation and
indexing; `tulip logs` shows ingestion progress.

For an existing PCAP, stage it outside the watched directory, then rename it in:

```sh
cp /work/capture.pcap /var/lib/rednix/tulip/capture.part
mv /var/lib/rednix/tulip/capture.part /var/lib/rednix/tulip/pcaps/capture.pcap
```

Guest NAT can reach the box through the host's event VPN. In routed mode, allow
its IP and SSH port in the [scope rules](networking.md). No inbound callback is needed.

## Use the traffic during a round

1. Select the service and time window around a suspected attack or flag loss.
2. Search flags, URLs or suspicious payloads; compare with normal checker traffic.
3. Inspect HTTP/raw data, star useful flows, and compare similar requests.
4. Generate and review HTTP/pwntools replay snippets. Reproduce on an authorized
   test service, patch your box, and verify both the fix and service health.

For running a reviewed exploit across the opponent list and submitting flags,
continue with [ExploitFarm](exploitfarm.md).

## Operations and limits

Use `tulip status`, `tulip logs`, and `tulip stop`. After configuration edits,
stop/start to reload. Tulip starts on demand after each guest boot.

Configuration/captures live in `/var/lib/rednix/tulip`; database `tulip` lives in
the persistent PostgreSQL cluster. Snapshots preserve both. Copy captures/notes to
`/work` before `rednix destroy EVENT`, which deletes Tulip's guest data.

Check `df -h /var/lib/rednix`: the event disk is 64 GiB and traffic grows quickly.
Prune remote files only after successful transfer. Deleting local PCAPs retains
indexed data but breaks raw-capture downloads.

The UI, API and file ingestor are included. Optional external converters, flag-ID
scraping and Suricata enrichment are not configured. Built-in HTTP decoding works;
checksum checking is skipped for offloaded captures. Tulip analyzes traffic; it
does not patch services or schedule attacks.

## Integration decisions

Source is pinned in `pkgs/tulip/default.nix`; this is distinct from nixpkgs' unrelated
graph-visualization package named `tulip`. Native Nix builds avoid Docker registry
access at runtime. `modules/tools/tulip.nix` adds an on-demand systemd target and
TimescaleDB (Apache build), pg_hint_plan and Tulip's custom extension to the existing PostgreSQL
cluster. Schema initialization runs transactionally once; normal database
durability settings remain enabled. PostgreSQL uses local peer authentication as
the guest `rednix` user, without a stored database password.

Verification: `nix build .#checks.x86_64-linux.tulip` boots a test VM and checks
offline startup, completed-PCAP ingestion, flag tagging, replay generation,
workspace DB access and persistence across restart/reboot.
