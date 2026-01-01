#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


AUTOMATR_ROOT = Path(os.getenv("AUTOMATR_CONTAINER_ROOT", "/automatr"))
QUEUE_DIR = Path(os.getenv("AUTOMATR_QUEUE_DIR", str(AUTOMATR_ROOT / "queue")))
LOGS_DIR = AUTOMATR_ROOT / "logs"

RUN_LOCK = AUTOMATR_ROOT / "run.lock"
STOP_FILE = AUTOMATR_ROOT / "STOP"

POLL_SECONDS = float(os.getenv("AUTOMATR_RUNNER_POLL", "0.2"))
KILL_GRACE_SECONDS = float(os.getenv("AUTOMATR_KILL_GRACE", "0.25"))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def log_line(msg: str) -> None:
    print(f"[runner] {msg}", flush=True)


def ensure_dirs() -> None:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def append_log(line: str) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = LOGS_DIR / f"{day}.log"
    with path.open("a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")


def stop_requested() -> bool:
    return STOP_FILE.exists()


def clear_run_lock() -> None:
    try:
        RUN_LOCK.unlink()
    except FileNotFoundError:
        pass


def write_run_lock(automation: str, pid: int | None, job_file: str, start_id: str) -> None:
    data = {
        "automation": automation,
        "pid": pid,
        "job_file": job_file,
        "started_at": utc_now_iso(),
        "start_id": start_id,
    }
    RUN_LOCK.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def load_job(job_path: Path) -> str:
    # content is just automation name (first non-empty line)
    txt = job_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in txt:
        s = line.strip()
        if s:
            return s

    # fallback: parse from filename job-<automation>-<ts>.job[.running]
    name = job_path.name
    base = name
    if base.endswith(".job.running"):
        base = base[: -len(".job.running")]
    if base.startswith("job-") and base.endswith(".job"):
        core = base[len("job-") : -len(".job")]
        parts = core.rsplit("-", 1)  # "<automation>-<timestamp>"
        if parts and parts[0]:
            return parts[0]

    raise RuntimeError(f"invalid_job: {job_path}")


def find_next_job() -> Optional[Path]:
    if not QUEUE_DIR.exists():
        return None
    jobs = sorted(QUEUE_DIR.glob("job-*.job"), key=lambda p: p.stat().st_mtime)
    return jobs[0] if jobs else None


def kill_process_tree(p: subprocess.Popen[str]) -> None:
    """
    Fast stop. We start scripts in a new process group, so killpg works.
    """
    if p.poll() is not None:
        return
    try:
        os.killpg(p.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    time.sleep(KILL_GRACE_SECONDS)

    if p.poll() is None:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            return


def run_automation(automation: str, job_path: Path) -> int:
    script_path = AUTOMATR_ROOT / "bin" / automation

    if not script_path.exists():
        raise RuntimeError(f"script_not_found: {script_path}")

    if not os.access(script_path, os.X_OK):
        raise RuntimeError(f"script_not_executable: {script_path}")

    start_id = str(int(time.time() * 1000))
    append_log(f"### STARTID:{start_id} automation={automation} job={job_path.name} at={utc_now_iso()} ###")

    p = subprocess.Popen(
        [str(script_path)],
        cwd=str(AUTOMATR_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        preexec_fn=os.setsid,
    )

    write_run_lock(automation=automation, pid=p.pid, job_file=job_path.name, start_id=start_id)

    try:
        assert p.stdout is not None
        for line in p.stdout:
            if stop_requested():
                append_log(f"[runner] STOP detected; killing automation={automation}")
                kill_process_tree(p)
                break
            append_log(line.rstrip("\n"))

        try:
            return p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            kill_process_tree(p)
            return p.wait(timeout=2)

    finally:
        append_log(f"### STOPID:{start_id} rc={p.poll()} at={utc_now_iso()} ###")
        clear_run_lock()


def main() -> None:
    ensure_dirs()
    log_line(f"runner up. queue={QUEUE_DIR} stop={STOP_FILE} runlock={RUN_LOCK}")

    while True:
        try:
            if stop_requested():
                time.sleep(POLL_SECONDS)
                continue

            job = find_next_job()
            if not job:
                time.sleep(POLL_SECONDS)
                continue

            claimed = job.with_suffix(".job.running")
            try:
                job.rename(claimed)
            except FileNotFoundError:
                continue

            try:
                automation = load_job(claimed).strip()
                log_line(f"running automation={automation} from {claimed.name}")
                rc = run_automation(automation, claimed)
                log_line(f"done automation={automation} rc={rc}")
            except Exception as e:
                append_log(f"[runner] ERROR: {e}")
                log_line(f"ERROR: {e}")
            finally:
                try:
                    claimed.unlink()
                except FileNotFoundError:
                    pass

        except KeyboardInterrupt:
            log_line("shutdown requested")
            break
        except Exception as e:
            log_line(f"loop_error: {e}")
            time.sleep(0.5)


if __name__ == "__main__":
    main()
