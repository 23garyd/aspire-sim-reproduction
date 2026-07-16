import json
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import link_probe  # noqa: E402


def test_stats_no_loss_synthetic():
    # 5 packets at 100ms spacing, all echoed with 10ms RTT
    send = [i * 100_000_000 for i in range(5)]
    recv = [(i, send[i] + 10_000_000) for i in range(5)]
    s = link_probe.compute_stats(send, recv, hz=10)
    assert s["sent"] == 5 and s["received"] == 5 and s["loss_pct"] == 0.0
    assert abs(s["rtt_ms"]["mean"] - 10.0) < 0.01
    assert s["jitter_ms"] < 0.01


def test_stats_burst_loss_shows_in_max_gap():
    # 50 packets at 20ms spacing (50Hz); packets 10..39 lost (600ms hole)
    send = [i * 20_000_000 for i in range(50)]
    recv = [(i, send[i] + 5_000_000) for i in range(50) if not (10 <= i < 40)]
    s = link_probe.compute_stats(send, recv, hz=50)
    assert s["loss_pct"] == 60.0
    assert 580 <= s["max_gap_ms"] <= 640          # ~600ms hole
    assert s["gap_over_1000ms_count"] == 0


def test_gap_over_watchdog_threshold_counted():
    # 2s stream at 50Hz, packets 25..99 lost -> 1.5s hole > 1s watchdog
    send = [i * 20_000_000 for i in range(100)]
    recv = [(i, send[i] + 5_000_000) for i in range(100) if i < 25]
    s = link_probe.compute_stats(send, recv, hz=50)
    assert s["gap_over_1000ms_count"] == 1
    assert s["max_gap_ms"] >= 1400


def test_percentiles_on_known_distribution():
    vals = sorted(float(v) for v in range(1, 101))     # 1..100
    assert link_probe.percentile(vals, 50) == 50.5 or 50 <= link_probe.percentile(vals, 50) <= 51
    assert link_probe.percentile(vals, 99) >= 99


def test_loopback_end_to_end_json():
    # real sockets over loopback: start echo in-process, run a short probe via CLI
    port = 47999
    t = threading.Thread(target=link_probe.run_echo, args=(port,), daemon=True)
    t.start()
    time.sleep(0.3)
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "link_probe.py"),
         "--role", "probe", "--target", f"127.0.0.1:{port}",
         "--hz", "50", "--duration", "2", "--payload", "64", "--json"],
        capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    s = json.loads(proc.stdout.strip().splitlines()[-1])
    assert s["sent"] == 100
    assert s["loss_pct"] < 5.0                     # loopback: essentially lossless
    assert s["rtt_ms"]["p95"] < 50
    assert s["max_gap_ms"] < 500
