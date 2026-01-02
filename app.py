# app.py
from __future__ import annotations

import importlib.util
import inspect
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import importlib.util
import inspect

import docker
from docker.errors import APIError, NotFound
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import db


def get_env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# Host API
AUTOMATR_HOST = get_env("AUTOMATR_HOST", "127.0.0.1")
AUTOMATR_PORT = int(get_env("AUTOMATR_PORT", "8766"))

# IMPORTANT: PROJECT_ROOT must be stable (don't rely on cwd drifting)
PROJECT_ROOT = Path(get_env("AUTOMATR_PROJECT_ROOT", str(Path(__file__).resolve().parent))).resolve()
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

# Host notifications
HOST_NOTIFY_BIN = get_env("AUTOMATR_HOST_NOTIFY_BIN", "notify-send")
HOST_NOTIFY_POLL = float(get_env("AUTOMATR_HOST_NOTIFY_POLL", "0.2"))


# Ensure base dirs
DATA_DIR.mkdir(parents=True, exist_ok=True)
BIN_CONTAINERS_DIR.mkdir(parents=True, exist_ok=True)

# ---------- XMPP (agent bots) ----------
XMPP_DOMAIN = get_env("AUTOMATR_XMPP_DOMAIN", "automatr-xmpp.local")
XMPP_HOST = get_env("AUTOMATR_XMPP_HOST", "automatr-prosody")
XMPP_PORT = get_env("AUTOMATR_XMPP_PORT", "5222")
XMPP_MUC = get_env("AUTOMATR_XMPP_MUC", f"automatr@conference.{XMPP_DOMAIN}")
XMPP_PASSWORD = get_env("AUTOMATR_XMPP_PASSWORD", "supersecret")
XMPP_INSECURE = get_env("AUTOMATR_XMPP_INSECURE_TLS", "1")


# Ensure DB exists/initialized (db.py uses env AUTOMATR_DB_PATH)
db.init_db()

docker_client = docker.from_env()

# Runtime registry: db container name -> {container_id, container_name, novnc_port}
_RUNTIME: dict[str, dict] = {}
_NEXT_PORT = NOVNC_PORT_BASE


def allocate_port() -> int:
    global _NEXT_PORT
    p = _NEXT_PORT
    _NEXT_PORT += 1
    return p


# ---------- canonical host paths ----------
def container_mount_root(name: str) -> Path:
    return DATA_DIR / name


def container_dir(name: str) -> Path:
    return container_mount_root(name)


def queue_dir(name: str) -> Path:
    return container_dir(name) / "queue"


def notify_queue_dir(name: str) -> Path:
    return container_dir(name) / "notify.queue"


def run_lock(name: str) -> Path:
    return container_dir(name) / "run.lock"


def stop_file(name: str) -> Path:
    return container_dir(name) / "STOP"


def metadata_path(name: str) -> Path:
    return BIN_CONTAINERS_DIR / name / "metadata.json"


def read_container_description(name: str) -> str:
    """
    Container description is sourced from bin/containers/{name}/metadata.json.
    DB table containers is intentionally minimal.
    """
    mp = metadata_path(name)
    if not mp.exists():
        return ""
    try:
        d = json.loads(mp.read_text(encoding="utf-8"))
        v = (d.get("description") or "").strip()
        return v
    except Exception:
        return ""


def write_container_metadata(name: str, description: str) -> None:
    mp = metadata_path(name)
    mp.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    if mp.exists():
        try:
            data = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    if "name" not in data:
        data["name"] = name
    if "created_at" not in data:
        data["created_at"] = datetime.utcnow().isoformat() + "Z"

    # Always update description to the latest provided value
    data["description"] = (description or "").strip()

    mp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def ensure_container_fs(name: str) -> None:
    root = container_dir(name)
    (root / "bin").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "queue").mkdir(parents=True, exist_ok=True)
    (root / "pid").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "notify.queue").mkdir(parents=True, exist_ok=True)


def is_container_busy(name: str) -> tuple[bool, Optional[str]]:
    lf = run_lock(name)
    if not lf.exists():
        return False, None
    try:
        d = json.loads(lf.read_text(encoding="utf-8"))
        return True, d.get("automation")
    except Exception:
        return True, None


def docker_name(name: str) -> str:
    return f"automatr-{name}"


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


def docker_exec(container_name: str, argv: list[str], timeout: int = 2) -> tuple[int, str]:
    cmd = ["docker", "exec", container_name] + argv
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (cp.stdout or "") + (cp.stderr or "")
        return cp.returncode, out
    except Exception as e:
        return 99, str(e)


def _load_automatr_actions_module():
    """
    Load host-side bin/automatr_actions.py dynamically.
    We do this so the API can expose action schema without importing project packages.
    """
    actions_path = (BIN_DIR / "automatr_actions.py").resolve()
    if not actions_path.exists():
        raise FileNotFoundError(f"automatr_actions.py not found at {actions_path}")

    spec = importlib.util.spec_from_file_location("automatr_actions_host", str(actions_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to build import spec for automatr_actions.py")

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _actions_schema_from_module(mod) -> dict:
    schema: dict[str, dict] = {}

    for name, obj in vars(mod).items():
        if not (callable(obj) and inspect.isfunction(obj)):
            continue

        # Public API surface rule: user-callable actions DO NOT start with "_"
        if name.startswith("_") or name.startswith("__"):
            continue

        sig = inspect.signature(obj)
        params_out = []
        for pname, p in sig.parameters.items():
            # We treat everything as keyword-friendly (your DB stores key/type/value anyway)
            ann = None if p.annotation is inspect._empty else p.annotation
            # Normalize annotation to a simple string when possible
            if ann is None:
                ptype = None
            elif isinstance(ann, type):
                ptype = ann.__name__
            else:
                ptype = str(ann)

            has_default = p.default is not inspect._empty
            default_val = None if not has_default else p.default

            params_out.append(
                {
                    "name": pname,
                    "type": ptype,               # e.g. "str", "float", etc. (or None)
                    "required": not has_default, # required if no default
                    "default": default_val,      # JSON-serializable if simple
                    "kind": str(p.kind).split(".")[-1],  # POSITIONAL_OR_KEYWORD, etc.
                }
            )

        doc = inspect.getdoc(obj) or ""
        schema[name] = {"params": params_out, "doc": doc}

    return schema


def clear_stop(name: str) -> None:
    sf = stop_file(name)
    if sf.exists():
        sf.unlink()


def set_stop(name: str) -> None:
    stop_file(name).write_text("", encoding="utf-8")


def export_automation(container: str, automation: str) -> tuple[bool, str]:
    """
    Calls: bin/export.py <container> <automation>
    """
    if not EXPORT_PY.exists():
        return False, f"export.py not found at {EXPORT_PY}"

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


# ---------------- Host notify consumer ----------------
_NOTIFY_THREAD_STARTED = False


def _host_notify(title: str, msg: str) -> None:
    try:
        subprocess.run([HOST_NOTIFY_BIN, title, msg], check=False)
    except Exception:
        pass


def _consume_notify_queue_forever(stop_evt: threading.Event) -> None:
    # Poll all containers’ notify.queue dirs
    while not stop_evt.is_set():
        try:
            if DATA_DIR.exists():
                for d in DATA_DIR.iterdir():
                    if not d.is_dir():
                        continue
                    qdir = d / "notify.queue"
                    if not qdir.exists():
                        continue

                    # process oldest first for sanity
                    files = sorted(qdir.glob("*.txt"), key=lambda p: p.stat().st_mtime)
                    for p in files:
                        try:
                            txt = p.read_text(encoding="utf-8", errors="replace").splitlines()
                            title = (txt[0].strip() if len(txt) >= 1 and txt[0].strip() else "AUTOMATR")
                            msg = ""
                            if len(txt) >= 2:
                                msg = "\n".join(txt[1:]).strip()
                            _host_notify(title, msg)
                        finally:
                            # always delete so it doesn't spam forever
                            try:
                                p.unlink()
                            except FileNotFoundError:
                                pass
        except Exception:
            pass

        time.sleep(HOST_NOTIFY_POLL)


app = FastAPI(title="Automatr Host API", version="0.2.2")

origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_notify_stop = threading.Event()


@app.on_event("startup")
def _startup() -> None:
    global _NOTIFY_THREAD_STARTED
    if not _NOTIFY_THREAD_STARTED:
        t = threading.Thread(target=_consume_notify_queue_forever, args=(_notify_stop,), daemon=True)
        t.start()
        _NOTIFY_THREAD_STARTED = True


@app.on_event("shutdown")
def _shutdown() -> None:
    _notify_stop.set()


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
                "description": read_container_description(name),
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

    # Metadata is the durable place for container description.
    write_container_metadata(name, desc)

    return {"ok": True}


def _start_container_impl(name: str) -> tuple[bool, str]:
    if not db.container_exists(name):
        return False, "not_found"
    if is_container_running(name):
        return False, "already_running"

    try:
        ensure_container_fs(name)
        novnc_port = allocate_port()
        cname = docker_name(name)

        environment = {
            "AUTOMATR_CONTAINER_NAME": name,
            "AUTOMATR_CONTAINER_ROOT": CONTAINER_ROOT,
            "AUTOMATR_QUEUE_DIR": QUEUE_DIR,
            "AUTOMATR_SCREEN_W": SCREEN_W,
            "AUTOMATR_SCREEN_H": SCREEN_H,
            "AUTOMATR_SCREEN_D": SCREEN_D,
            "DISPLAY": ":99",
            # agent bot identity + xmpp routing
            "AUTOMATR_NODE": name,
            "AUTOMATR_XMPP_DOMAIN": XMPP_DOMAIN,
            "AUTOMATR_XMPP_HOST": XMPP_HOST,
            "AUTOMATR_XMPP_PORT": str(XMPP_PORT),
            "AUTOMATR_XMPP_MUC": XMPP_MUC,
            "AUTOMATR_XMPP_PASSWORD": XMPP_PASSWORD,
            "AUTOMATR_XMPP_INSECURE_TLS": XMPP_INSECURE,
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
        return True, ""
    except APIError as e:
        return False, f"docker_error: {str(e)}"
    except Exception as e:
        return False, f"start_failed: {str(e)}"


@app.post("/containers/{name}/start")
def start_container(name: str):
    ok, err = _start_container_impl(name)
    if not ok:
        return {"ok": False, "error": err}
    return {"ok": True}


def _stop_container_impl(name: str) -> tuple[bool, str]:
    if not db.container_exists(name):
        return False, "not_found"
    if name not in _RUNTIME:
        return False, "not_running"

    try:
        cid = _RUNTIME[name]["container_id"]
        c = docker_client.containers.get(cid)
        c.stop(timeout=10)
        c.remove()
        _RUNTIME.pop(name, None)
        return True, ""
    except NotFound:
        _RUNTIME.pop(name, None)
        return True, ""
    except Exception as e:
        return False, f"stop_failed: {str(e)}"


@app.post("/containers/{name}/stop")
def stop_container(name: str):
    ok, err = _stop_container_impl(name)
    if not ok:
        return {"ok": False, "error": err}
    return {"ok": True}


@app.post("/containers/{name}/restart")
def restart_container(name: str):
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}

    # If running, stop first. If not running, treat stop as no-op.
    if is_container_running(name) or name in _RUNTIME:
        _stop_container_impl(name)

    ok, err = _start_container_impl(name)
    if not ok:
        return {"ok": False, "error": err}
    return {"ok": True}


@app.get("/containers/{name}/vnc_url")
def container_vnc_url(name: str):
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}
    if not is_container_running(name):
        return {"ok": False, "error": "not_running"}
    novnc_port = _RUNTIME[name]["novnc_port"]
    url = f"http://127.0.0.1:{novnc_port}{NOVNC_PATH}"
    return {"url": url, "view_only": True}


# ---------------- STOP latch + hard stop ----------------
@app.post("/containers/{name}/stop_auto")
def stop_auto(name: str):
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}

    ensure_container_fs(name)
    set_stop(name)

    if is_container_running(name):
        cname = docker_name(name)
        pid: Optional[int] = None
        try:
            if run_lock(name).exists():
                d = json.loads(run_lock(name).read_text(encoding="utf-8"))
                if "pid" in d and d["pid"] is not None:
                    pid = int(d["pid"])
        except Exception:
            pid = None

        if pid:
            docker_exec(cname, ["kill", "-TERM", str(pid)], timeout=1)
            docker_exec(cname, ["kill", "-KILL", str(pid)], timeout=1)

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
    return db.list_automations()


@app.get("/automations/{name}")
def get_automation(name: str):
    a = db.get_automation_full(name)
    if not a:
        return {"ok": False, "error": "not_found"}
    return {"ok": True, "automation": a}


@app.delete("/automations/{name}")
def delete_automation(name: str):
    a = db.get_automation(name)
    if not a:
        return {"ok": False, "error": "not_found"}
    db.delete_automation(name)
    return {"ok": True}


def _load_actions_module() -> tuple[Optional[object], str]:
    actions_path = BIN_DIR / "automatr_actions.py"
    if not actions_path.exists():
        return None, f"missing:{actions_path}"
    try:
        spec = importlib.util.spec_from_file_location("automatr_actions_live", str(actions_path))
        if spec is None or spec.loader is None:
            return None, "import_spec_failed"
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
        return mod, ""
    except Exception as e:
        return None, f"import_failed:{e}"


@app.get("/actions/check")
def actions_check():
    mod, err = _load_actions_module()
    if not mod:
        return {"ok": False, "error": err}

    public: list[str] = []
    for name, obj in inspect.getmembers(mod):
        # rule: user-facing actions do NOT start with underscore
        if name.startswith("_"):
            continue
        if inspect.isfunction(obj):
            public.append(name)

    public = sorted(set(public))
    db_actions = db.list_distinct_step_actions()

    missing_in_wrapper = sorted([a for a in db_actions if a not in public])
    extra_in_wrapper = sorted([a for a in public if a not in db_actions])

    return {
        "ok": True,
        "wrapper_actions": public,
        "db_actions": db_actions,
        "missing_in_wrapper": missing_in_wrapper,
        "extra_in_wrapper": extra_in_wrapper,
    }


@app.get("/actions/schema")
def actions_schema():
    try:
        mod = _load_automatr_actions_module()
        schema = _actions_schema_from_module(mod)
        return {"ok": True, "schema": schema}
    except Exception as e:
        return {"ok": False, "error": f"schema_failed: {str(e)}"}


@app.post("/automations/save")
def save_automation(payload: dict):
    name = (payload.get("name") or "").strip()
    container = (payload.get("container") or "").strip()

    if not name:
        return {"ok": False, "error": "name_required"}
    if not container:
        return {"ok": False, "error": "container_required"}
    if not db.container_exists(container):
        return {"ok": False, "error": "container_not_found"}

    try:
        db.save_automation_graph(payload)
    except Exception as e:
        return {"ok": False, "error": f"db_save_failed: {e}"}

    ok, out = export_automation(container, name)
    if not ok:
        return {"ok": False, "error": "export_failed", "detail": out}

    return {"ok": True, "exported": True}


@app.post("/containers/{name}/run")
def run_automation(name: str, payload: dict):
    automation = (payload.get("automation") or payload.get("automation_name") or "").strip()

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

    ok, out = export_automation(name, automation)
    if not ok:
        return {"ok": False, "error": "export_failed", "detail": out}

    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
    job = queue_dir(name) / f"job-{automation}-{ts}.job"
    job.write_text(f"{automation}\n", encoding="utf-8")

    return {"ok": True, "queued": True}


@app.get("/automations/{name}/graph")
def get_automation_graph(name: str):
    g = db.get_automation_graph(name)
    if not g:
        return {"ok": False, "error": "not_found"}
    return {"ok": True, "graph": g}


@app.get("/containers/{name}")
def get_container(name: str):
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}

    running = is_container_running(name)
    busy, busy_automation = is_container_busy(name)
    stop_latched = stop_file(name).exists()

    # Optional: include vnc_url if running
    vnc_url = None
    if running and name in _RUNTIME and _RUNTIME[name].get("novnc_port"):
        novnc_port = _RUNTIME[name]["novnc_port"]
        vnc_url = f"http://127.0.0.1:{novnc_port}{NOVNC_PATH}"

    # Optional: include run.lock contents if present
    run_lock_data = None
    lf = run_lock(name)
    if lf.exists():
        try:
            run_lock_data = json.loads(lf.read_text(encoding="utf-8"))
        except Exception:
            run_lock_data = {"_error": "run_lock_unparseable"}

    return {
        "ok": True,
        "container": {
            "name": name,
            "description": read_container_description(name),
            "running": running,
            "busy": busy,
            "busy_automation": busy_automation,
            "stop_latched": stop_latched,
            "vnc_url": vnc_url,
            "run_lock": run_lock_data,
        },
    }

