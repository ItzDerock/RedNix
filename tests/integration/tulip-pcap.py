"""Make a small Ethernet/IPv4/TCP HTTP capture for the real Tulip ingestor."""

import socket
import struct
import sys
import time
from pathlib import Path


def packet(src, dst, sport, dport, seq, ack, flags, payload=b""):
    tcp = struct.pack("!HHIIBBHHH", sport, dport, seq, ack, 5 << 4, flags, 65535, 0, 0)
    ip = struct.pack(
        "!BBHHHBBH4s4s", 0x45, 0, 20 + len(tcp) + len(payload), 1, 0, 64, 6, 0,
        socket.inet_aton(src), socket.inet_aton(dst),
    )
    # The ingestor skips TCP checksum validation, as for offloaded captures.
    return bytes.fromhex("0200000000020200000000010800") + ip + tcp + payload


client, server = "10.60.2.7", "10.60.4.1"
request = b"GET /tulip-smoke HTTP/1.1\r\nHost: shop\r\n\r\n"
flag = b"A" * 31 + b"="
response = b"HTTP/1.1 200 OK\r\nContent-Length: 32\r\n\r\n" + flag
frames = [
    packet(client, server, 45000, 8080, 100, 0, 0x02),
    packet(server, client, 8080, 45000, 500, 101, 0x12),
    packet(client, server, 45000, 8080, 101, 501, 0x10),
    packet(client, server, 45000, 8080, 101, 501, 0x18, request),
    packet(server, client, 8080, 45000, 501, 101 + len(request), 0x18, response),
    packet(client, server, 45000, 8080, 101 + len(request), 501 + len(response), 0x11),
    packet(server, client, 8080, 45000, 501 + len(response), 102 + len(request), 0x11),
    packet(client, server, 45000, 8080, 102 + len(request), 502 + len(response), 0x10),
]
with Path(sys.argv[1]).open("wb") as capture:
    capture.write(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
    timestamp = int(time.time())
    for index, frame in enumerate(frames):
        capture.write(struct.pack("<IIII", timestamp, index * 1000, len(frame), len(frame)))
        capture.write(frame)
