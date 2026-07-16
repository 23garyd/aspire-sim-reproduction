#!/usr/bin/env python3
"""
link_probe.py -- 50 Hz link probe for the ASPIRE / SOW WiFi-vs-NearLink rig.

Purpose
-------
A small, stdlib-only tool that characterizes a network link using traffic
shaped like a robot-control command stream (small, fixed-cadence UDP
datagrams). It exists to answer one question ahead of the later
WiFi-vs-NearLink benchmark: "how long can this link starve a 50 Hz
robot-arm command stream?" -- a real servo watchdog on the A2 rig faults
at ~1s without a fresh command, so the tail behaviour of the link (not
just its average loss/RTT) is the metric that matters.

Two roles, one file
--------------------
* ``echo``  -- runs on the far end (e.g. the robot-side node / simhost box).
  Binds a UDP socket and echoes every datagram back to its sender
  verbatim. Runs until killed.

      python3 scripts/link_probe.py --role echo --port 4700

* ``probe`` -- runs on the near end (e.g. the Mac or an SBC sitting next
  to the operator). Sends ``hz * duration`` datagrams at a fixed cadence
  (next_send = start + i/hz, with sleep-until rather than accumulating
  drift), each carrying a sequence number and a monotonic send
  timestamp. A background thread collects echoes and records RTTs.
  After the run (plus a short drain window) it reports loss, RTT
  distribution, jitter, and the deadman-relevant ``max_gap_ms``.

      python3 scripts/link_probe.py --role probe \\
          --target 10.0.0.5:4700 --hz 50 --duration 10 --payload 64 --json

Future WiFi vs NearLink rig example
------------------------------------
  # on the simhost box (far end, wired):
  python3 scripts/link_probe.py --role echo --port 4700

  # on the Mac/SBC over WiFi:
  python3 scripts/link_probe.py --role probe --target <simhost-ip>:4700 \\
      --hz 50 --duration 60 --json > wifi_run.json

  # same Mac/SBC over NearLink:
  python3 scripts/link_probe.py --role probe --target <simhost-ip>:4700 \\
      --hz 50 --duration 60 --json > nearlink_run.json

  # compare max_gap_ms and gap_over_1000ms_count between the two runs.

The deadman interpretation of max_gap_ms
-----------------------------------------
Average loss percentage can look fine (a few percent) while still
hiding a single multi-hundred-millisecond outage buried in the middle
of the run -- exactly the kind of event that trips a robot's servo
watchdog even though "average loss" looks acceptable. ``max_gap_ms`` is
the longest span of wall-clock time in the run during which NOT ONE
packet was successfully echoed, measured across the whole run
(including the lead-in before the first echo and the tail after the
last send). ``gap_over_1000ms_count`` counts how many of those blackout
windows exceeded 1000 ms -- the A2 watchdog's fault threshold. A link
can have low average loss and still be catastrophic for a control loop
if it produces even one such gap.

Computation is factored into pure, socket-free functions
(``compute_stats``, ``percentile``, ``max_gap_ms``) so the statistics
can be unit tested without any networking.
"""
from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
import threading
import time

# 8-byte big-endian sequence number + 8-byte big-endian send timestamp
# (time.monotonic_ns, fits unsigned 64-bit).
HEADER_FMT = ">QQ"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

DRAIN_SECONDS = 0.5
RECV_BUF = 65535


# --------------------------------------------------------------------------
# Pure, socket-free statistics
# --------------------------------------------------------------------------

def percentile(sorted_vals: list[float], p: float) -> float:
    """Linear-interpolation percentile over an already-sorted list."""
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    k = (p / 100.0) * (n - 1)
    f = int(k)
    c = min(f + 1, n - 1)
    if f == c:
        return sorted_vals[f]
    frac = k - f
    return sorted_vals[f] * (1 - frac) + sorted_vals[c] * frac


def max_gap_ms(send_times_ns: list[int], recv_events: list[tuple[int, int]]) -> tuple[float, int]:
    """Longest silence in the receive timeline, plus count of gaps > 1000ms.

    Builds the timeline from the leading edge (first send time), every
    successfully-echoed packet's receive time, and the trailing edge
    (last send time), then returns the largest consecutive gap and how
    many consecutive gaps exceeded 1000 ms.
    """
    if not send_times_ns:
        return 0.0, 0
    recv_times = sorted(t for _, t in recv_events)
    timeline = sorted([send_times_ns[0]] + recv_times + [send_times_ns[-1]])
    gaps_ms = [(timeline[i + 1] - timeline[i]) / 1e6 for i in range(len(timeline) - 1)]
    if not gaps_ms:
        return 0.0, 0
    over_1000 = sum(1 for g in gaps_ms if g > 1000.0)
    return max(gaps_ms), over_1000


def compute_stats(send_times_ns: list[int], recv_events: list[tuple[int, int]], hz: float) -> dict:
    """Compute the full stats dict from raw send/receive timestamps.

    send_times_ns[seq] = monotonic_ns time seq was sent.
    recv_events: list of (seq, recv_time_ns) for every echo actually received.
    """
    sent = len(send_times_ns)
    recv_sorted = sorted(recv_events, key=lambda e: e[1])
    received = len(recv_sorted)
    loss_pct = round((sent - received) / sent * 100.0, 2) if sent else 0.0

    rtts_ms = [(recv_time - send_times_ns[seq]) / 1e6 for seq, recv_time in recv_sorted]
    sorted_rtts = sorted(rtts_ms)

    if rtts_ms:
        rtt_stats = {
            "mean": round(sum(rtts_ms) / len(rtts_ms), 4),
            "p50": round(percentile(sorted_rtts, 50), 4),
            "p95": round(percentile(sorted_rtts, 95), 4),
            "p99": round(percentile(sorted_rtts, 99), 4),
            "max": round(max(rtts_ms), 4),
        }
    else:
        rtt_stats = {"mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}

    if len(rtts_ms) >= 2:
        diffs = [abs(rtts_ms[i] - rtts_ms[i - 1]) for i in range(1, len(rtts_ms))]
        jitter = round(sum(diffs) / len(diffs), 4)
    else:
        jitter = 0.0

    gap_ms, gap_count = max_gap_ms(send_times_ns, recv_events)

    return {
        "sent": sent,
        "received": received,
        "loss_pct": loss_pct,
        "rtt_ms": rtt_stats,
        "jitter_ms": jitter,
        "max_gap_ms": round(gap_ms, 4),
        "gap_over_1000ms_count": gap_count,
    }


# --------------------------------------------------------------------------
# Wire format
# --------------------------------------------------------------------------

def build_packet(seq: int, send_time_ns: int, payload_bytes: int) -> bytes:
    header = struct.pack(HEADER_FMT, seq, send_time_ns)
    pad_len = max(0, payload_bytes - HEADER_SIZE)
    return header + b"\x00" * pad_len


def parse_header(data: bytes) -> tuple[int, int]:
    seq, send_time_ns = struct.unpack_from(HEADER_FMT, data, 0)
    return seq, send_time_ns


# --------------------------------------------------------------------------
# Echo role
# --------------------------------------------------------------------------

def run_echo(port: int, host: str = "0.0.0.0") -> None:
    """Bind UDP :port and echo every datagram back to its sender. Runs forever."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    print(f"echo listening on :{port}", flush=True)
    while True:
        try:
            data, addr = sock.recvfrom(RECV_BUF)
        except OSError:
            break
        try:
            sock.sendto(data, addr)
        except OSError:
            pass


# --------------------------------------------------------------------------
# Probe role
# --------------------------------------------------------------------------

def run_probe(target_host: str, target_port: int, hz: float, duration: float,
              payload_bytes: int) -> dict:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.2)

    n = int(round(hz * duration))
    send_times_ns: list[int] = [0] * n
    recv_events: list[tuple[int, int]] = []
    recv_lock = threading.Lock()
    stop_flag = threading.Event()

    def receiver() -> None:
        while not stop_flag.is_set():
            try:
                data, _ = sock.recvfrom(RECV_BUF)
            except socket.timeout:
                continue
            except OSError:
                break
            t = time.monotonic_ns()
            if len(data) < HEADER_SIZE:
                continue
            seq, _ = parse_header(data)
            with recv_lock:
                recv_events.append((seq, t))

    th = threading.Thread(target=receiver, daemon=True)
    th.start()

    start_ns = time.monotonic_ns()
    period_ns = 1e9 / hz
    for i in range(n):
        target_ns = start_ns + int(i * period_ns)
        now = time.monotonic_ns()
        if target_ns > now:
            time.sleep((target_ns - now) / 1e9)
        send_ns = time.monotonic_ns()
        send_times_ns[i] = send_ns
        pkt = build_packet(i, send_ns, payload_bytes)
        try:
            sock.sendto(pkt, (target_host, target_port))
        except OSError:
            pass

    time.sleep(DRAIN_SECONDS)
    stop_flag.set()
    sock.close()
    th.join(timeout=1.0)

    with recv_lock:
        events = list(recv_events)

    return compute_stats(send_times_ns, events, hz)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _parse_target(target: str) -> tuple[str, int]:
    if ":" not in target:
        raise ValueError("target must be HOST:PORT")
    host, port_s = target.rsplit(":", 1)
    if not host or not port_s:
        raise ValueError("target must be HOST:PORT")
    port = int(port_s)
    return host, port


def _print_table(stats: dict) -> None:
    print(f"target:            {stats.get('target', '')}")
    print(f"hz / duration:     {stats.get('hz')} Hz / {stats.get('duration_s')} s")
    print(f"payload:           {stats.get('payload_bytes')} bytes")
    print(f"sent / received:   {stats['sent']} / {stats['received']}")
    print(f"loss:              {stats['loss_pct']}%")
    r = stats["rtt_ms"]
    print(f"rtt_ms (mean/p50/p95/p99/max): "
          f"{r['mean']}/{r['p50']}/{r['p95']}/{r['p99']}/{r['max']}")
    print(f"jitter_ms:         {stats['jitter_ms']}")
    print(f"max_gap_ms:        {stats['max_gap_ms']}")
    print(f"gaps > 1000ms:     {stats['gap_over_1000ms_count']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="50 Hz link probe -- RTT/jitter/loss/max-gap over UDP.")
    parser.add_argument("--role", choices=["echo", "probe"], required=True)
    parser.add_argument("--port", type=int, help="UDP port to bind (echo role)")
    parser.add_argument("--target", help="HOST:PORT of the echo peer (probe role)")
    parser.add_argument("--hz", type=float, default=50.0)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--payload", type=int, default=64)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.role == "echo":
        if args.port is None:
            print("error: --port is required for --role echo", file=sys.stderr)
            return 2
        try:
            run_echo(args.port)
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0

    # role == probe
    if not args.target:
        print("error: --target is required for --role probe", file=sys.stderr)
        return 2
    try:
        host, port = _parse_target(args.target)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.hz <= 0:
        print("error: --hz must be > 0", file=sys.stderr)
        return 2
    if args.duration <= 0:
        print("error: --duration must be > 0", file=sys.stderr)
        return 2
    if args.payload < HEADER_SIZE:
        print(f"error: --payload must be >= {HEADER_SIZE}", file=sys.stderr)
        return 2

    try:
        stats = run_probe(host, port, args.hz, args.duration, args.payload)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    stats["hz"] = args.hz
    stats["duration_s"] = args.duration
    stats["payload_bytes"] = args.payload
    stats["target"] = args.target

    if args.json:
        print(json.dumps(stats))
    else:
        _print_table(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
