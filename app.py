from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import docker
from docker.errors import NotFound, APIError
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import db


def get_env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# Host API
AUTOMATR_HOST = get_env("AUTOMATR_HOST", "127.0.0.1")
AUTOMATR_PORT = int(get_env("AUTOMATR_PORT", "8766"))

PROJECT_ROOT = Path(get_env("AUTOMATR_PROJECT_ROOT", str(Path.cwd()))).resolve()
DATA_DIR = Path(get_env("AUTOMATR_DATA_DIR", str(PROJECT_ROOT / "data"))).resolve()
DB_PATH = Path(get_env("AUTOMATR_DB_PATH", str(DATA_DIR / "automatr.db"))).resolve()

BIN_DIR = PROJECT_ROOT / "bin"
EXPORT_PY = Path(get_env("AUTOMATR_EXPORT_PY", str(BIN_DIR / "export.py"))).resolve()

BIN_CONTAINERS_DIR = Path(get_env("AUTOMATR_BIN_CONTAINERS_DIR", str(BIN_DIR / "containers"))).resolve()

# Docker
RUNTIME_IMAGE = get_env("AUTOMATR_RUNTIME_IMAGE", "automatr-runtime:dev")
DOCKER_NETWORK = get_env("AUTOMATR_DOCKER_NETWORK", "")

# Screen
SCREEN_W = get_env("AUTOMATR_SCREEN_W", "1366")
SCREEN_H = get_env("AUTOMATR_SCREEN_H", "768")
SCREEN_D = get_env("AUTOMATR_SCREEN_D", "24")

# noVNC
NOVNC_PORT_BASE = int(get_env("AUTOMATR_NOVNC_PORT_BASE", "6100"))
NOVNC_PATH = get_env("AUTOMATR_NOVNC_PATH", "/vnc.html?autoconnect=1&resize=remote")

# Container internal paths
CONTAINER_ROOT = get_env("AUTOMATR_CONTAINER_ROOT", "/automatr")
QUEUE_DIR = get_env("AUTOMATR_QUEUE_DIR", "/automatr/queue")

# CORS
CORS_ORIGINS = get_env("AUTOMATR_CORS_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000")

# Ensure base dirs
DATA_DIR.mkdir(parents=True, exist_ok=True)
BIN_CONTAINERS_DIR.mkdir(parents=True, exist_ok=True)

# Ensure DB
db.init_db()

docker_client = docker.from_env()

_RUNTIME: dict[str, dict] = {}
_NEXT_PORT = NOVNC_PORT_BASE


def allocate_port() -> int:
    global _NEXT_PORT
    p = _NEXT_PORT
    _NEXT_PORT += 1
    return p


def container_mount_root(name: str) -> Path:
    return DATA_DIR / name


def container_dir(name: str) -> Path:
    # same as mount root (host side)
    return container_mount_root(name)


def queue_dir(name: str) -> Path:
    return container_dir(name) / "queue"


def run_lock(name: str) -> Path:
    return container_dir(name) / "run.lock"


def stop_file(name: str) -> Path:
    return container_dir(name) / "STOP"


def ensure_container_fs(name: str) -> None:
    root = container_dir(name)
    (root / "bin").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "queue").mkdir(parents=True, exist_ok=True)
    (root / "pid").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)


def is_container_busy(name: str) -> tuple[bool, Optional[str]]:
    lf = run_lock(name)
    if not lf.exists():
        return False, None
    try:
        d = json.loads(lf.read_text(encoding="utf-8"))
        return True, d.get("automation")
    except Exception:
        return True, None


def is_container_running(name: str) -> bool:
    if name not in _RUNTIME:
        return False
    cid = _RUNTIME[name].get("container_id")
    if not cid:
        return False
    try:
        c = docker_client.containers.get(cid)
        return c.status == "running"
    except NotFound:
        _RUNTIME.pop(name, None)
        return False
    except Exception:
        return False


def docker_name(name: str) -> str:
    return f"automatr-{name}"


def docker_exec(container_name: str, argv: list[str], timeout: int = 2) -> tuple[int, str]:
    """
    Execute inside container. Return (rc, combined_output).
    Uses `docker exec` via subprocess to avoid extra python packages/edge cases.
    """
    cmd = ["docker", "exec", container_name] + argv
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (cp.stdout or "") + (cp.stderr or "")
        return cp.returncode, out
    except Exception as e:
        return 99, str(e)


def clear_stop(name: str) -> None:
    sf = stop_file(name)
    if sf.exists():
        sf.unlink()


def set_stop(name: str) -> None:
    # latch STOP until cleared by run/save or explicit endpoint
    sf = stop_file(name)
    sf.write_text("", encoding="utf-8")


def export_automation(container: str, automation: str) -> tuple[bool, str]:
    """
    Calls bin/export.py <container> <automation>.
    Returns (ok, error_text_or_stdout).
    """
    env = os.environ.copy()
    env["AUTOMATR_PROJECT_ROOT"] = str(PROJECT_ROOT)
    env["AUTOMATR_DATA_DIR"] = str(DATA_DIR)
    env["AUTOMATR_DB_PATH"] = str(DB_PATH)

    try:
        cp = subprocess.run(
            [sys.executable, str(EXPORT_PY), container, automation],
            capture_output=True,
            text=True,
            env=env,
        )
        out = (cp.stdout or "") + (cp.stderr or "")
        return (cp.returncode == 0), out
    except Exception as e:
        return False, str(e)


app = FastAPI(title="Automatr Host API", version="0.2.0")

origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


# ---------------- Containers ----------------
@app.get("/containers")
def list_containers():
    cs = db.list_containers()
    out = []
    for c in cs:
        name = c["name"]
        running = is_container_running(name)
        busy, busy_automation = is_container_busy(name)
        out.append(
            {
                "name": name,
                "description": c.get("description", ""),
                "running": running,
                "busy": busy,
                "busy_automation": busy_automation,
                "stop_latched": stop_file(name).exists(),
            }
        )
    return out


@app.post("/containers")
def create_container(payload: dict):
    name = (payload.get("name") or "").strip()
    desc = (payload.get("description") or "").strip()

    if not name:
        return {"ok": False, "error": "name_required"}
    if db.container_exists(name):
        return {"ok": False, "error": "container_exists"}

    db.create_container(name, desc)
    ensure_container_fs(name)

    # create metadata.json (untracked) if you want it early
    meta = BIN_CONTAINERS_DIR / name / "metadata.json"
    meta.parent.mkdir(parents=True, exist_ok=True)
    if not meta.exists():
        meta.write_text(json.dumps({"name": name, "created_at": datetime.utcnow().isoformat() + "Z"}, indent=2), encoding="utf-8")

    return {"ok": True}


@app.post("/containers/{name}/start")
def start_container(name: str):
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}
    if is_container_running(name):
        return {"ok": False, "error": "already_running"}

    try:
        ensure_container_fs(name)
        novnc_port = allocate_port()
        cname = docker_name(name)

        environment = {
            "AUTOMATR_CONTAINER_ROOT": CONTAINER_ROOT,
            "AUTOMATR_QUEUE_DIR": QUEUE_DIR,
            "AUTOMATR_SCREEN_W": SCREEN_W,
            "AUTOMATR_SCREEN_H": SCREEN_H,
            "AUTOMATR_SCREEN_D": SCREEN_D,
            "DISPLAY": ":99",
        }

        volumes = {str(container_dir(name)): {"bind": CONTAINER_ROOT, "mode": "rw"}}
        ports = {"6080/tcp": novnc_port}

        run_kwargs = {
            "name": cname,
            "image": RUNTIME_IMAGE,
            "detach": True,
            "auto_remove": False,
            "environment": environment,
            "volumes": volumes,
            "ports": ports,
        }
        if DOCKER_NETWORK:
            run_kwargs["network"] = DOCKER_NETWORK

        container = docker_client.containers.run(**run_kwargs)

        _RUNTIME[name] = {"container_id": container.id, "container_name": cname, "novnc_port": novnc_port}
        return {"ok": True}
    except APIError as e:
        return {"ok": False, "error": f"docker_error: {str(e)}"}
    except Exception as e:
        return {"ok": False, "error": f"start_failed: {str(e)}"}


@app.post("/containers/{name}/stop")
def stop_container(name: str):
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}
    if name not in _RUNTIME:
        return {"ok": False, "error": "not_running"}

    try:
        cid = _RUNTIME[name]["container_id"]
        c = docker_client.containers.get(cid)
        c.stop(timeout=10)
        c.remove()
        _RUNTIME.pop(name, None)
        return {"ok": True}
    except NotFound:
        _RUNTIME.pop(name, None)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"stop_failed: {str(e)}"}


@app.get("/containers/{name}/vnc_url")
def container_vnc_url(name: str):
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}
    if not is_container_running(name):
        return {"ok": False, "error": "not_running"}
    novnc_port = _RUNTIME[name]["novnc_port"]
    url = f"http://127.0.0.1:{novnc_port}{NOVNC_PATH}"
    return {"url": url, "view_only": True}


# ---------------- Stop latch + hard stop ----------------
@app.post("/containers/{name}/stop_auto")
def stop_auto(name: str):
    """
    Immediate stop:
    - touch STOP latch (so wrappers stop)
    - attempt docker exec kill if run.lock has pid
    - clear run.lock
    """
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}

    ensure_container_fs(name)
    set_stop(name)

    # Try hard-kill if container running and we can resolve pid
    if is_container_running(name):
        cname = docker_name(name)
        pid: Optional[int] = None
        try:
            if run_lock(name).exists():
                d = json.loads(run_lock(name).read_text(encoding="utf-8"))
                if "pid" in d:
                    pid = int(d["pid"])
        except Exception:
            pid = None

        if pid:
            docker_exec(cname, ["kill", "-TERM", str(pid)], timeout=1)
            docker_exec(cname, ["kill", "-KILL", str(pid)], timeout=1)

    # Clear lock so UI shows idle
    if run_lock(name).exists():
        run_lock(name).unlink()

    return {"ok": True, "stop_latched": True}


@app.post("/containers/{name}/clear_stop")
def clear_stop_endpoint(name: str):
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}
    clear_stop(name)
    return {"ok": True}


# ---------------- Automations (DB-backed) ----------------
@app.get("/automations")
def list_automations():
    # You’ll update db.py to match your schema; this assumes it returns name/description/updated_at
    return db.list_automations()


@app.post("/automations/save")
def save_automation(payload: dict):
    """
    Payload should include everything needed to write:
    - automations row
    - automation_vars
    - automation_steps
    - step_params
    - step_clauses
    Then export for a target container.
    """
    name = (payload.get("name") or "").strip()
    container = (payload.get("container") or "").strip()
    description = (payload.get("description") or "").strip()

    if not name:
        return {"ok": False, "error": "name_required"}
    if not container:
        return {"ok": False, "error": "container_required"}
    if not db.container_exists(container):
        return {"ok": False, "error": "container_not_found"}

    # db.save_automation_graph should be your atomic “write everything” call.
    # It should also renumber steps + clauses.
    try:
        db.save_automation_graph(payload)  # <-- you’ll implement in db.py
    except Exception as e:
        return {"ok": False, "error": f"db_save_failed: {e}"}

    ok, out = export_automation(container, name)
    if not ok:
        return {"ok": False, "error": "export_failed", "detail": out}

    return {"ok": True}


@app.post("/containers/{name}/run")
def run_automation(name: str, payload: dict):
    """
    Run:
    - clear STOP latch
    - save+export first (or at least export)
    - create queue job: "RUN <automation>"
    """
    automation = (payload.get("automation") or "").strip()
    if not automation:
        return {"ok": False, "error": "automation_required"}
    if not db.container_exists(name):
        return {"ok": False, "error": "container_not_found"}
    if not is_container_running(name):
        return {"ok": False, "error": "container_not_running"}

    busy, _ = is_container_busy(name)
    if busy:
        return {"ok": False, "error": "container_busy"}

    ensure_container_fs(name)
    clear_stop(name)

    # Export must succeed before running
    ok, out = export_automation(name, automation)
    if not ok:
        return {"ok": False, "error": "export_failed", "detail": out}

    # Write queue job
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
    job = queue_dir(name) / f"job-{ts}.job"
    job.write_text(f"RUN {automation}\n", encoding="utf-8")

    return {"ok": True, "queued": True}
