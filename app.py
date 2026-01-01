from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import docker
from docker.errors import APIError, NotFound
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import db


def get_env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ---------------- Settings ----------------
AUTOMATR_HOST = get_env("AUTOMATR_HOST", "127.0.0.1")
AUTOMATR_PORT = int(get_env("AUTOMATR_PORT", "8766"))

# Your contract:
# - data/<name>/ is the container mount root
# - bin/containers/<name>/ holds durable container-specific artifacts (excluded from git)
DATA_DIR = Path(get_env("AUTOMATR_DATA_DIR", "./data")).resolve()
DB_PATH = Path(get_env("AUTOMATR_DB_PATH", str(DATA_DIR / "automatr.db"))).resolve()
BIN_DIR = Path(get_env("AUTOMATR_BIN_DIR", "./bin")).resolve()
BIN_CONTAINERS_DIR = Path(get_env("AUTOMATR_BIN_CONTAINERS_DIR", str(BIN_DIR / "containers"))).resolve()

RUNTIME_IMAGE = get_env("AUTOMATR_RUNTIME_IMAGE", "automatr-runtime:dev")
DOCKER_NETWORK = get_env("AUTOMATR_DOCKER_NETWORK", "")

SCREEN_W = get_env("AUTOMATR_SCREEN_W", "1366")
SCREEN_H = get_env("AUTOMATR_SCREEN_H", "768")
SCREEN_D = get_env("AUTOMATR_SCREEN_D", "24")

NOVNC_PORT_BASE = int(get_env("AUTOMATR_NOVNC_PORT_BASE", "6100"))
NOVNC_PATH = get_env("AUTOMATR_NOVNC_PATH", "/vnc.html?autoconnect=1&resize=remote")

CONTAINER_ROOT = get_env("AUTOMATR_CONTAINER_ROOT", "/automatr")
QUEUE_DIR = get_env("AUTOMATR_QUEUE_DIR", "/automatr/queue")

CORS_ORIGINS = get_env(
    "AUTOMATR_CORS_ORIGINS",
    "http://127.0.0.1:3000,http://localhost:3000",
)

# ---------------- Init ----------------
DATA_DIR.mkdir(parents=True, exist_ok=True)
BIN_DIR.mkdir(parents=True, exist_ok=True)
BIN_CONTAINERS_DIR.mkdir(parents=True, exist_ok=True)

db.init_db()
docker_client = docker.from_env()

# name -> {container_id, container_name, novnc_port}
_RUNTIME: dict[str, dict] = {}
_NEXT_PORT = NOVNC_PORT_BASE


def allocate_port() -> int:
    global _NEXT_PORT
    port = _NEXT_PORT
    _NEXT_PORT += 1
    return port


# ---------------- Path helpers (your contract) ----------------
def runtime_dir(name: str) -> Path:
    return DATA_DIR / name


def runtime_queue_dir(name: str) -> Path:
    return runtime_dir(name) / "queue"


def runtime_pid_dir(name: str) -> Path:
    return runtime_dir(name) / "pid"


def lock_file(name: str) -> Path:
    # Keep lock out of root; pid/ is fine per your note.
    return runtime_pid_dir(name) / "run.lock"


def backup_dir(name: str) -> Path:
    return BIN_CONTAINERS_DIR / name


def metadata_path(name: str) -> Path:
    return backup_dir(name) / "metadata.json"


def backup_automations_dir(name: str) -> Path:
    return backup_dir(name) / "bin" / "automations"


def shared_actions_path() -> Path:
    return BIN_DIR / "automatr_actions.py"


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def ensure_symlink(dst: Path, src: Path) -> None:
    """
    Ensure dst is a symlink to src.
    Refuse to overwrite a non-symlink file (safety).
    """
    ensure_dir(dst.parent)

    if dst.is_symlink():
        try:
            if dst.resolve() == src.resolve():
                return
        except FileNotFoundError:
            pass
        dst.unlink()

    if dst.exists():
        raise RuntimeError(f"Refusing to overwrite non-symlink path: {dst}")

    dst.symlink_to(src)


def bootstrap_container_fs(name: str) -> None:
    """
    Enforce EXACT symlink contract:

      data/<name>/bin/automatr_actions.py -> bin/automatr_actions.py

      data/<name>/bin/<automation> -> bin/containers/<name>/bin/automations/<automation>.py

    plus runtime dirs:
      data/<name>/{logs,queue,pid,config}/
    """
    # runtime dirs
    rt = runtime_dir(name)
    ensure_dir(rt / "bin")
    ensure_dir(rt / "logs")
    ensure_dir(rt / "queue")
    ensure_dir(rt / "pid")
    ensure_dir(rt / "config")

    # backup dirs (durable but excluded from git)
    ensure_dir(backup_automations_dir(name))

    # shared actions symlink (has .py, per your rule)
    actions_src = shared_actions_path()
    if not actions_src.exists():
        raise RuntimeError(f"Missing shared actions script: {actions_src}")
    ensure_symlink(rt / "bin" / "automatr_actions.py", actions_src)

    # automation symlinks (NO .py in data/bin)
    # data/<name>/bin/<automation> -> bin/containers/<name>/bin/automations/<automation>.py
    for src in sorted(backup_automations_dir(name).glob("*.py")):
        automation_name = src.stem  # remove .py
        dst = rt / "bin" / automation_name
        ensure_symlink(dst, src)


def read_metadata(name: str) -> dict:
    p = metadata_path(name)
    if not p.exists():
        return {"name": name}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"name": name, "metadata_error": True}


def write_metadata(name: str, payload: dict) -> None:
    ensure_dir(backup_dir(name))
    metadata_path(name).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def is_container_busy(name: str) -> tuple[bool, Optional[str]]:
    lf = lock_file(name)
    if not lf.exists():
        return False, None
    try:
        d = json.loads(lf.read_text(encoding="utf-8"))
        return True, d.get("automation", "unknown")
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
        del _RUNTIME[name]
        return False
    except Exception:
        return False


def automation_exists_for_container(container: str, automation_name: str) -> bool:
    # file-backed automation (durable)
    src = backup_automations_dir(container) / f"{automation_name}.py"
    return src.exists()


# ---------------- App ----------------
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
    """
    Uses DB as the list of containers for now (since schema/db.py is built).
    Filesystem bootstrap runs per-container to ensure mount + symlinks are sane.
    """
    rows = db.list_containers()
    result = []

    for r in rows:
        name = r["name"]
        running = is_container_running(name)
        busy, busy_automation = is_container_busy(name)

        fs_ok = True
        fs_error = ""
        try:
            bootstrap_container_fs(name)
        except Exception as e:
            fs_ok = False
            fs_error = str(e)

        result.append(
            {
                "name": name,
                "description": r.get("description", ""),
                "running": running,
                "busy": busy,
                "busy_automation": busy_automation,
                "fs_ok": fs_ok,
                "fs_error": fs_error or None,
            }
        )

    return result


@app.post("/containers")
def create_container(payload: dict):
    name = (payload.get("name") or "").strip()
    desc = (payload.get("description") or "").strip()

    if not name:
        return {"ok": False, "error": "name_required"}
    if db.container_exists(name):
        return {"ok": False, "error": "container_exists"}

    # DB row
    db.create_container(name, desc)

    # durable backup dirs + metadata (excluded from git by your plan)
    ensure_dir(backup_automations_dir(name))
    write_metadata(
        name,
        {
            "name": name,
            "description": desc,
            "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )

    # runtime mount dirs + symlinks
    try:
        bootstrap_container_fs(name)
    except Exception as e:
        return {"ok": False, "error": f"bootstrap_failed: {e}"}

    return {"ok": True}


@app.post("/containers/{name}/start")
def start_container(name: str):
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}
    if is_container_running(name):
        return {"ok": False, "error": "already_running"}

    try:
        bootstrap_container_fs(name)

        novnc_port = allocate_port()
        container_name = f"automatr-{name}"

        environment = {
            "AUTOMATR_CONTAINER_ROOT": CONTAINER_ROOT,
            "AUTOMATR_QUEUE_DIR": QUEUE_DIR,
            "AUTOMATR_SCREEN_W": SCREEN_W,
            "AUTOMATR_SCREEN_H": SCREEN_H,
            "AUTOMATR_SCREEN_D": SCREEN_D,
            "DISPLAY": ":99",
            "AUTOMATR_NODE": name,
        }

        volumes = {str(runtime_dir(name)): {"bind": CONTAINER_ROOT, "mode": "rw"}}
        ports = {"6080/tcp": novnc_port}

        run_kwargs = {
            "name": container_name,
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

        _RUNTIME[name] = {
            "container_id": container.id,
            "container_name": container_name,
            "novnc_port": novnc_port,
        }

        return {"ok": True}
    except APIError as e:
        return {"ok": False, "error": f"docker_error: {str(e)}"}
    except Exception as e:
        return {"ok": False, "error": f"start_failed: {str(e)}"}


@app.post("/containers/{name}/stop")
def stop_container(name: str):
    if name not in _RUNTIME:
        return {"ok": False, "error": "not_running"}

    try:
        cid = _RUNTIME[name]["container_id"]
        c = docker_client.containers.get(cid)

        c.stop(timeout=10)
        c.remove()

        del _RUNTIME[name]
        return {"ok": True}
    except NotFound:
        if name in _RUNTIME:
            del _RUNTIME[name]
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
    url = f"http://{AUTOMATR_HOST}:{novnc_port}{NOVNC_PATH}"
    return {"url": url, "view_only": True}


@app.post("/containers/{name}/stop_auto")
def stop_auto(name: str):
    lf = lock_file(name)
    if lf.exists():
        lf.unlink()
    return {"ok": True}


@app.post("/containers/{name}/run")
def run_automation(name: str, payload: dict):
    """
    Queue a job file into:
      data/<name>/queue/

    Job file content:
      RUN <automation_name>

    (No YAML, no JSON runtime in scripts.)
    """
    automation_name = (payload.get("automation_name") or "").strip()
    if not automation_name:
        return {"ok": False, "error": "automation_name_required"}

    if not db.container_exists(name):
        return {"ok": False, "error": "container_not_found"}
    if not is_container_running(name):
        return {"ok": False, "error": "container_not_running"}

    busy, _ = is_container_busy(name)
    if busy:
        return {"ok": False, "error": "container_busy"}

    # For this architecture turn, automation existence is file-backed per container.
    if not automation_exists_for_container(name, automation_name):
        return {"ok": False, "error": "automation_not_found"}

    try:
        bootstrap_container_fs(name)

        qdir = runtime_queue_dir(name)
        ensure_dir(qdir)

        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        job_file = qdir / f"job-{ts}.job"
        job_file.write_text(f"RUN {automation_name}\n", encoding="utf-8")

        return {"ok": True, "queued": True}
    except Exception as e:
        return {"ok": False, "error": f"queue_failed: {str(e)}"}
