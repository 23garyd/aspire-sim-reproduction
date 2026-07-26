#!/usr/bin/env python3
"""Parallel queue runner for the Phase-3 arm cells of libero_tiling.sh.

Runs the remaining (task x arm x rep) cells of the tiling campaign N at a time
instead of sequentially, mirroring run_one() from scripts/libero_tiling.sh
exactly: same dirs, same env vars, same command, same unconditional DONE
marker, then the Phase-4 analysis once every cell is DONE.

Safe to run alongside one orphaned in-flight aspire.run from the old driver:
cells whose task-dir belongs to a live external aspire.run are skipped and
finalized (DONE) when that process exits. Cells are claimed atomically via a
.claim file so a second copy of this runner cannot double-run a cell.

Usage:  python3 scripts/libero_tiling_parallel.py [--jobs 6] [--dry]
"""
import argparse
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENV = "/home/demo/cap-x/.venv-libero/bin/python"
CAPX = str(REPO / "scripts/capx_execute.py")
BOWLXY = str(REPO / "scripts/capx_bowl_xy.py")
BASELINE = REPO / "runs/2026-07-22-libero-accum-frontier/baseline_grasp_lift.py"
TMPL = REPO / "runs/2026-07-24-libero-tiling/franka_libero_spatial_0_privileged.yaml"

# Campaign parameters — defaults reproduce the original spatial tiling
# campaign; overridable from the CLI for follow-up campaigns (e.g. harder
# held-out suites). Set in main() before any scheduling.
ROOT = Path(os.environ.get("ROOT", str(Path.home() / "aspire_runs/libero_tiling")))
CFGDIR = ROOT / "configs"
TILED_LIB = ROOT / "tiled_library"
XYDIR = ROOT / "bowl_xy"
SUITE = "libero_spatial"
PREFIX = "spatial"
HELDOUT_TASKS = [3, 6, 8]
REPEATS = 5
TEST_T = "2"
ARMS = ["warm_geo", "warm_dumpall", "cold"]
API_PORTS = [8114, 8115, 8116]
XY_RE = re.compile(r"^-?[0-9]+(\.[0-9]+)?,-?[0-9]+(\.[0-9]+)?$")

STOP = threading.Event()
children = []            # live subprocess.Popen handles, for signal cleanup
children_lock = threading.Lock()
PLANNER_FAILS = {"consecutive": 0}   # circuit breaker on shared-cause failures
PLANNER_FAIL_LIMIT = 3


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _is_json(line):
    import json
    try:
        json.loads(line)
        return True
    except ValueError:
        return False


def gen_cfg(tid):
    out = CFGDIR / f"{PREFIX}_{tid}.yaml"
    if not out.exists():
        CFGDIR.mkdir(parents=True, exist_ok=True)
        out.write_text(TMPL.read_text()
                       .replace("task_id: 0", f"task_id: {tid}")
                       .replace("suite_name: libero_spatial", f"suite_name: {SUITE}"))
    return out


def bowl_xy(tid):
    """Cached bowl xy per task, same validation as the shell driver."""
    XYDIR.mkdir(parents=True, exist_ok=True)
    f = XYDIR / f"{PREFIX}_{tid}.txt"
    if not f.exists() or not f.read_text().strip():
        log(f"computing bowl_xy for task {tid} (not cached)")
        env = dict(os.environ, MUJOCO_GL="egl")
        res = subprocess.run(
            [VENV, BOWLXY, "--workdir", "/home/demo/cap-x", "--config-path", str(gen_cfg(tid))],
            capture_output=True, text=True, env=env, cwd=str(REPO))
        lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
        f.write_text((lines[-1] if lines else "") + "\n")
    xy = f.read_text().strip()
    if not XY_RE.match(xy):
        f.unlink(missing_ok=True)
        raise RuntimeError(f"bowl_xy for task {tid} is not a coordinate: {xy!r}")
    return xy


def cells():
    """Enumerate Phase-3 cells in the same order as the shell driver."""
    out = []
    for tid in HELDOUT_TASKS:
        for rep in range(1, REPEATS + 1):
            for arm in ARMS:
                sub = f"test/{PREFIX}_{tid}/{arm}/{rep}"
                rdir = ROOT / sub
                extra = {}
                if arm == "warm_geo":
                    extra = {"ASPIRE_RETRIEVAL": "geometry", "ASPIRE_TARGET_XY": None}  # xy filled lazily
                out.append({
                    "tid": tid, "arm": arm, "rep": rep, "sub": sub,
                    "rdir": rdir, "task": rdir / "task", "out": rdir / "exec",
                    "lib": rdir / "lib", "copy_lib": arm.startswith("warm"),
                    "extra": extra,
                })
    return out


def external_task_dirs():
    """Task-dirs of live aspire.run processes not started by this runner."""
    with children_lock:
        ours = {p.pid for p in children}
    found = {}
    for pid_dir in Path("/proc").iterdir():
        if not pid_dir.name.isdigit() or int(pid_dir.name) in ours:
            continue
        try:
            argv = (pid_dir / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if b"aspire.run" not in b" ".join(argv):
            continue
        for i, a in enumerate(argv):
            if a == b"--task-dir" and i + 1 < len(argv):
                found[argv[i + 1].decode()] = int(pid_dir.name)
    return found


def claim(cell):
    """Atomically claim a cell; False if done, claimed, or externally running."""
    rdir = cell["rdir"]
    if (rdir / "DONE").exists():
        return False
    rdir.mkdir(parents=True, exist_ok=True)
    cf = rdir / ".claim"
    if cf.exists():
        try:  # stale claim from a dead runner -> reclaim
            os.kill(int(cf.read_text().split()[0]), 0)
            return False
        except (OSError, ValueError, IndexError):
            cf.unlink(missing_ok=True)
    try:
        fd = os.open(cf, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w") as fh:
        fh.write(f"{os.getpid()} {time.strftime('%F %T')}\n")
    return True


def finalize(cell, note=""):
    """Match the shell driver: summary.json from last log line, then DONE."""
    rdir = cell["rdir"]
    logf, summf = rdir / "log.txt", rdir / "summary.json"
    if logf.exists() and not summf.exists():
        lines = [ln for ln in logf.read_text(errors="replace").splitlines() if ln.strip()]
        # Prefer the last JSON line (aspire.run's machine-readable summary) —
        # the plain last line can be a stray stderr warning.
        chosen = next((ln for ln in reversed(lines)
                       if ln.lstrip().startswith("{") and _is_json(ln)), None)
        summf.write_text(((chosen or (lines[-1] if lines else ""))) + "\n")
    (rdir / "DONE").touch()
    (rdir / ".claim").unlink(missing_ok=True)
    log(f"DONE {cell['sub']} {note}")


def run_cell(cell, dry=False):
    if STOP.is_set():
        return
    if not claim(cell):        # claim at execution time, not submission time,
        return                 # so a second runner can pick up queued cells
    cfg = gen_cfg(cell["tid"])
    extra = dict(cell["extra"])
    if dry:
        log(f"[dry] {cell['sub']} env={extra}")
        (cell["rdir"] / ".claim").unlink(missing_ok=True)
        return
    if "ASPIRE_TARGET_XY" in extra:
        extra["ASPIRE_TARGET_XY"] = bowl_xy(cell["tid"])
    cell["task"].mkdir(parents=True, exist_ok=True)
    cell["out"].mkdir(parents=True, exist_ok=True)
    if cell["copy_lib"]:
        cell["lib"].mkdir(parents=True, exist_ok=True)
        if TILED_LIB.exists():
            shutil.copytree(TILED_LIB, cell["lib"], dirs_exist_ok=True)
    shutil.copy(BASELINE, cell["task"] / "code.py")

    env = dict(os.environ, MUJOCO_GL="egl",
               PATH=f"{Path.home()}/.local/bin:{os.environ.get('PATH', '')}", **extra)
    # Planner cost control: force the claude CLI onto the claude.ai
    # subscription login, never per-token API billing (see 2026-07-25 incident:
    # inherited ANTHROPIC_API_KEY hit rate limits and failed 11 cells at once).
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    capxcmd = f"{VENV} {CAPX} --workdir /home/demo/cap-x --config-path {cfg}"
    cmd = ["python3", "-m", "aspire.run",
           "--task-dir", str(cell["task"]), "--engine", "capx",
           "--capx-cmd", capxcmd, "--out-root", str(cell["out"]),
           "--library", str(cell["lib"]), "--s-dbg", "0", "--s-val", "100",
           "--t", TEST_T]
    log(f"START {cell['sub']}")
    t0 = time.time()
    with open(cell["rdir"] / "log.txt", "w") as lf:
        proc = subprocess.Popen(cmd, cwd=str(REPO), env=env,
                                stdout=lf, stderr=subprocess.STDOUT,
                                start_new_session=True)
        with children_lock:
            children.append(proc)
        rc = proc.wait()
        with children_lock:
            children.remove(proc)
    if STOP.is_set():   # we killed it: not a completed cell, leave it re-runnable
        (cell["rdir"] / ".claim").unlink(missing_ok=True)
        log(f"ABORTED {cell['sub']} (stop requested)")
        return
    logf = cell["rdir"] / "log.txt"
    tail = logf.read_text(errors="replace")[-4000:] if logf.exists() else ""
    if rc != 0 and "claude exited" in tail:
        # Planner (claude CLI) died — auth/rate-limit, not a real result.
        # Leave the cell re-runnable and trip the breaker on repeats.
        logf.rename(cell["rdir"] / f"log.plannerfail.{int(time.time())}.txt")
        (cell["rdir"] / ".claim").unlink(missing_ok=True)
        PLANNER_FAILS["consecutive"] += 1
        log(f"PLANNER-FAIL {cell['sub']} rc={rc} "
            f"({PLANNER_FAILS['consecutive']}/{PLANNER_FAIL_LIMIT} consecutive)")
        if PLANNER_FAILS["consecutive"] >= PLANNER_FAIL_LIMIT:
            log("circuit breaker: repeated planner failures — stopping runner "
                "(fix auth/rate limit, then rerun; cells stay re-runnable)")
            STOP.set()
        return
    PLANNER_FAILS["consecutive"] = 0
    finalize(cell, f"rc={rc} {int(time.time() - t0)}s")


def start_server_holder():
    """Pre-start the shared API servers (8114-8116) in a stable holder process
    so every worker attaches to singletons instead of racing to bind."""
    code = (
        "import time\n"
        "from capx.envs.configs.loader import DictLoader\n"
        "from capx.envs.runner import _start_api_servers\n"
        f"cfgs = DictLoader.load(['{gen_cfg(HELDOUT_TASKS[0])}'])\n"
        "_start_api_servers(cfgs.get('api_servers'))\n"
        "print('api servers up', flush=True)\n"
        "while True: time.sleep(60)\n"
    )
    holder = subprocess.Popen([VENV, "-c", code], cwd="/home/demo/cap-x",
                              env=dict(os.environ, MUJOCO_GL="egl"),
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              start_new_session=True)
    deadline = time.time() + 240
    pending = set(API_PORTS)
    while pending and time.time() < deadline and holder.poll() is None:
        for port in list(pending):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                pending.discard(port)
            except OSError:
                time.sleep(2)
    log(f"server holder pid={holder.pid} up, ports pending={sorted(pending) or 'none'}")
    return holder


def main():
    global ROOT, CFGDIR, TILED_LIB, XYDIR, SUITE, PREFIX, HELDOUT_TASKS, REPEATS, ARMS, TEST_T
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--stagger", type=float, default=20.0,
                    help="seconds between worker launches on startup")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--root", default=str(ROOT), help="campaign root directory")
    ap.add_argument("--suite", default=SUITE, help="LIBERO suite name")
    ap.add_argument("--prefix", default=None,
                    help="dir/config prefix (default: suite name minus 'libero_')")
    ap.add_argument("--tasks", default=",".join(map(str, HELDOUT_TASKS)),
                    help="comma list of held-out task ids")
    ap.add_argument("--reps", type=int, default=REPEATS)
    ap.add_argument("--arms", default=",".join(ARMS),
                    help="comma subset of warm_geo,warm_dumpall,cold")
    ap.add_argument("--t", default=TEST_T, help="aspire.run --t iterations")
    ap.add_argument("--library", default=None,
                    help="tiled library to copy for warm arms "
                         "(default: <root>/tiled_library)")
    ap.add_argument("--no-analyze", action="store_true",
                    help="skip Phase-4 analysis at the end (e.g. probe runs)")
    args = ap.parse_args()

    ROOT = Path(args.root)
    CFGDIR = ROOT / "configs"
    XYDIR = ROOT / "bowl_xy"
    SUITE = args.suite
    PREFIX = args.prefix or SUITE.removeprefix("libero_")
    HELDOUT_TASKS = [int(t) for t in args.tasks.split(",") if t.strip()]
    REPEATS = args.reps
    ARMS = [a.strip() for a in args.arms.split(",") if a.strip()]
    TEST_T = str(args.t)
    TILED_LIB = Path(args.library) if args.library else ROOT / "tiled_library"
    ROOT.mkdir(parents=True, exist_ok=True)
    log(f"campaign: root={ROOT} suite={SUITE} prefix={PREFIX} "
        f"tasks={HELDOUT_TASKS} reps={REPEATS} arms={ARMS} t={TEST_T} lib={TILED_LIB}")

    def on_signal(signum, _frame):
        log(f"signal {signum}: stopping (claims released, running cells keep their logs)")
        STOP.set()
        with children_lock:
            for p in children:
                try:
                    os.killpg(p.pid, signal.SIGTERM)
                except OSError:
                    pass
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    todo = [c for c in cells() if not (c["rdir"] / "DONE").exists()]
    log(f"{len(cells()) - len(todo)} cells DONE, {len(todo)} to schedule, jobs={args.jobs}")
    if args.dry:
        external = external_task_dirs()
        for c in todo:
            state = "external-in-flight" if str(c["task"]) in external else "pending"
            log(f"[dry] {c['sub']} {state} env={ {k: v for k, v in c['extra'].items()} }")
        return
    holder = None
    if not args.dry and todo:
        holder = start_server_holder()
        for tid in sorted({c["tid"] for c in todo if c["arm"] == "warm_geo"}):
            bowl_xy(tid)  # compute serially up front (spatial_8 is uncached)

    external = external_task_dirs()
    ext_cells = [c for c in todo if str(c["task"]) in external]
    for c in ext_cells:
        log(f"external in-flight: {c['sub']} (pid {external[str(c['task'])]}) — will finalize on exit")

    def watch_external():
        while ext_cells and not STOP.is_set():
            live = external_task_dirs()
            for c in list(ext_cells):
                if str(c["task"]) not in live:
                    finalize(c, "(external run finished)")
                    ext_cells.remove(c)
            time.sleep(30)

    watcher = threading.Thread(target=watch_external, daemon=True)
    watcher.start()

    runnable = [c for c in todo if c not in ext_cells]
    launched = 0
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = []
        for cell in runnable:
            if STOP.is_set():
                break
            if (cell["rdir"] / "DONE").exists():
                continue
            if launched < args.jobs and args.stagger and not args.dry:
                time.sleep(args.stagger if launched else 0)
            futures.append(pool.submit(run_cell, cell, args.dry))
            launched += 1
        for f in futures:
            f.result()

    while ext_cells and not STOP.is_set():   # wait for the orphaned cell too
        time.sleep(15)

    remaining = [c for c in cells() if not (c["rdir"] / "DONE").exists()]
    if not remaining and not args.dry and not STOP.is_set():
        if args.no_analyze:
            log(f"all cells DONE (analysis skipped) root={ROOT}")
        else:
            log("all cells DONE -> Phase 4 analysis")
            heldout = ",".join(str(t) for t in HELDOUT_TASKS)
            with open(ROOT / "analysis.log", "w") as lf:
                subprocess.run(["python3", str(REPO / "scripts/analyze_libero_tiling.py"),
                                "--root", str(ROOT), "--heldout", heldout,
                                "--prefix", PREFIX],
                               cwd=str(REPO), stdout=lf, stderr=subprocess.STDOUT)
            log(f"TILING CAMPAIGN DONE root={ROOT} (analysis in {ROOT}/analysis.log)")
    else:
        log(f"exiting with {len(remaining)} cells not DONE")
    if remaining and not args.dry and not STOP.is_set() \
            and PLANNER_FAILS["consecutive"] < PLANNER_FAIL_LIMIT:
        # Cells dropped by transient failures: signal the caller to re-invoke.
        if holder:
            log(f"leaving API-server holder alive (pid {holder.pid})")
        sys.exit(4)
    if holder:
        # Leave the shared API servers running: another runner instance or an
        # orphaned episode may still need them. Clean up manually when idle:
        log(f"leaving API-server holder alive (pid {holder.pid}); "
            f"kill with: pkill -g {holder.pid}")
    if PLANNER_FAILS["consecutive"] >= PLANNER_FAIL_LIMIT:
        sys.exit(3)   # circuit breaker tripped: caller may cool down and retry


if __name__ == "__main__":
    main()
