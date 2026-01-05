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

import docker
from docker.errors import APIError, NotFound
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import db
from automatr_config import AutomatrConfig, load_config


cfg: AutomatrConfig = load_config()

# Ensure DB exists/initialized (db.py uses env AUTOMATR_DB_PATH)
db.init_db()

docker_client = docker.from_env()

# Runtime registry: db container name -> {container_id, container_name, novnc_port}
_RUNTIME: dict[str, dict] = {}
_NEXT_PORT = cfg.novnc_port_base


def allocate_port() -> int:
    global _NEXT_PORT
    p = _NEXT_PORT
    _NEXT_PORT += 1
    return p


# ---------- canonical host paths ----------
def container_mount_root(name: str) -> Path:
    return cfg.data_dir / name


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
    return cfg.bin_containers_dir / name / "metadata.json"


# ---------- input recorder (host-managed) ----------
def input_recorder_pid_path(name: str) -> Path:
    return container_dir(name) / "pid" / "input_recorder.pid"


def input_events_log_path(name: str) -> Path:
    return container_dir(name) / "logs" / "input_events.jsonl"


def input_recorder_runner_log_path(name: str) -> Path:
    return container_dir(name) / "logs" / "input_recorder_runner.log"


# ---------- logs ----------
def automation_log_path(name: str, date_ymd: str) -> Path:
    # runner.py writes to /automatr/logs/YYYY-MM-DD.log (UTC date)
    # host bind-mount: data/{name}/logs/YYYY-MM-DD.log
    return container_dir(name) / "logs" / f"{date_ymd}.log"


def _read_pid_file(p: Path) -> Optional[int]:
    try:
        s = p.read_text(encoding="utf-8").strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def docker_name(name: str) -> str:
    return f"automatr-{name}"


def docker_exec(container_name: str, argv: list[str], timeout: int = 2) -> tuple[int, str]:
    cmd = ["docker", "exec", container_name] + argv
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (cp.stdout or "") + (cp.stderr or "")
        return cp.returncode, out
    except Exception as e:
        return 99, str(e)


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


def _recorder_is_running(name: str) -> tuple[bool, Optional[int]]:
    """
    Returns (running, pid). If pidfile exists but process is dead, we clean it up.
    """
    pidfile = input_recorder_pid_path(name)
    pid = _read_pid_file(pidfile)
    if pid is None:
        return False, None

    if not is_container_running(name):
        # container down => recorder not running; remove stale pidfile
        try:
            pidfile.unlink()
        except Exception:
            pass
        return False, None

    cname = docker_name(name)
    rc, _out = docker_exec(cname, ["sh", "-lc", f"kill -0 {pid} >/dev/null 2>&1"], timeout=2)
    if rc == 0:
        return True, pid

    # stale pidfile -> cleanup
    try:
        pidfile.unlink()
    except Exception:
        pass
    return False, None


def _tail_lines(p: Path, n: int) -> list[str]:
    if n <= 0:
        return []
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-n:]
    except FileNotFoundError:
        return []


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


def clear_stop(name: str) -> None:
    sf = stop_file(name)
    if sf.exists():
        sf.unlink()


def set_stop(name: str) -> None:
    stop_file(name).write_text("", encoding="utf-8")


def _load_automatr_actions_module():
    """
    Load host-side bin/automatr_actions.py dynamically.
    We do this so the API can expose action schema without importing project packages.
    """
    actions_path = (cfg.bin_dir / "automatr_actions.py").resolve()
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
        if name.startswith("_") or name.startswith("__"):
            continue

        sig = inspect.signature(obj)
        params_out = []
        for pname, p in sig.parameters.items():
            ann = None if p.annotation is inspect._empty else p.annotation
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
                    "type": ptype,
                    "required": not has_default,
                    "default": default_val,
                    "kind": str(p.kind).split(".")[-1],
                }
            )

        doc = inspect.getdoc(obj) or ""
        schema[name] = {"params": params_out, "doc": doc}

    return schema


def export_automation(container: str, automation: str) -> tuple[bool, str]:
    """
    Calls: bin/export.py <container> <automation>
    """
    if not cfg.export_py.exists():
        return False, f"export.py not found at {cfg.export_py}"

    env = os.environ.copy()
    env["AUTOMATR_PROJECT_ROOT"] = str(cfg.project_root)
    env["AUTOMATR_DATA_DIR"] = str(cfg.data_dir)
    env["AUTOMATR_DB_PATH"] = str(cfg.db_path)

    try:
        cp = subprocess.run(
            [sys.executable, str(cfg.export_py), container, automation],
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
        subprocess.run([cfg.host_notify_bin, title, msg], check=False)
    except Exception:
        pass


def _consume_notify_queue_forever(stop_evt: threading.Event) -> None:
    while not stop_evt.is_set():
        try:
            if cfg.data_dir.exists():
                for d in cfg.data_dir.iterdir():
                    if not d.is_dir():
                        continue
                    qdir = d / "notify.queue"
                    if not qdir.exists():
                        continue
                    files = sorted(qdir.glob("*.txt"), key=lambda p: p.stat().st_mtime)
                    for p in files:
                        try:
                            txt = p.read_text(encoding="utf-8", errors="replace").splitlines()
                            title = (txt[0].strip() if len(txt) >= 1 and txt[0].strip() else "AUTOMATR")
                            msg = "\n".join(txt[1:]).strip() if len(txt) >= 2 else ""
                            _host_notify(title, msg)
                        finally:
                            try:
                                p.unlink()
                            except FileNotFoundError:
                                pass
        except Exception:
            pass

        time.sleep(cfg.host_notify_poll)


# ---------------- FastAPI ----------------
app = FastAPI(title="Automatr Host API", version="0.2.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.cors_origins,
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

        # Env injected into runtime container:
        # - XMPP derived from AUTOMATR_HOST via cfg (domain) + docker-internal (host)
        # - API base so agents can phone home
        environment = {
            "AUTOMATR_CONTAINER_NAME": name,
            "AUTOMATR_AGENT_NAME": "agent-" + name,
            "AUTOMATR_AGENT_JID": "agent-" + name + "@" + cfg.xmpp_domain,
            "AUTOMATR_CONTAINER_ROOT": cfg.container_root,
            "AUTOMATR_QUEUE_DIR": cfg.queue_dir,
            "AUTOMATR_SCREEN_W": cfg.screen_w,
            "AUTOMATR_SCREEN_H": cfg.screen_h,
            "AUTOMATR_SCREEN_D": cfg.screen_d,
            "DISPLAY": ":99",
            "AUTOMATR_NODE": name,
            "AUTOMATR_XMPP_DOMAIN": cfg.xmpp_domain,
            "AUTOMATR_XMPP_HOST": cfg.xmpp_host,
            "AUTOMATR_XMPP_PORT": str(cfg.xmpp_port),
            "AUTOMATR_XMPP_MUC": cfg.xmpp_muc,
            "AUTOMATR_XMPP_PASSWORD": cfg.xmpp_password,
            "AUTOMATR_XMPP_INSECURE_TLS": cfg.xmpp_insecure,
            # "This runs here" info
            "AUTOMATR_HOST": cfg.host,
            "AUTOMATR_PORT": str(cfg.port),
            "AUTOMATR_API_BASE": cfg.api_base,
        }

        volumes = {str(container_dir(name)): {"bind": cfg.container_root, "mode": "rw"}}
        ports = {"6080/tcp": novnc_port}

        run_kwargs = {
            "name": cname,
            "image": cfg.runtime_image,
            "detach": True,
            "auto_remove": False,
            "environment": environment,
            "volumes": volumes,
            "ports": ports,
        }
        if cfg.docker_network:
            run_kwargs["network"] = cfg.docker_network

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

    # Caddy routes by Docker DNS name on the automatr network:
    #   /c/<container>/vnc.html -> http://<container>:6080/vnc.html
    docker_name = f"automatr-{name}"

    # If AUTOMATR_PUBLIC_BASE is set, return absolute URL for the correct host
    # (xps.local / tailscale). Otherwise return a relative path.
    if getattr(cfg, "public_base", ""):
        url = f"{cfg.public_base}/c/{docker_name}{cfg.novnc_path}"
    else:
        url = f"/c/{docker_name}{cfg.novnc_path}"

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
    actions_path = cfg.bin_dir / "automatr_actions.py"
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

    vnc_url = None
    if running:
        auto_name = f"automatr-{name}"
        vnc_url = f"/c/{auto_name}/vnc.html?autoconnect=1&resize=remote&path=c/{auto_name}/websockify"

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


@app.get("/containers/{name}/input/status")
def input_status(name: str):
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}

    running, pid = _recorder_is_running(name)
    return {
        "ok": True,
        "status": {
            "running": running,
            "pid": pid,
            "log_path": str(input_events_log_path(name)),
            "runner_log_path": str(input_recorder_runner_log_path(name)),
        },
    }


@app.post("/containers/{name}/input/start")
def input_start(name: str):
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}
    if not is_container_running(name):
        return {"ok": False, "error": "not_running"}

    ensure_container_fs(name)

    running, pid = _recorder_is_running(name)
    if running:
        return {"ok": True, "running": True, "pid": pid}

    cname = docker_name(name)

    cmd = (
        "mkdir -p /automatr/pid /automatr/logs; "
        "nohup /usr/bin/automatr-input-recorder "
        ">>/automatr/logs/input_recorder_runner.log 2>&1 "
        "& echo $! > /automatr/pid/input_recorder.pid"
    )
    rc, out = docker_exec(cname, ["sh", "-lc", cmd], timeout=3)
    if rc != 0:
        return {"ok": False, "error": "start_failed", "detail": out}

    running, pid = _recorder_is_running(name)
    return {"ok": True, "running": running, "pid": pid}


@app.post("/containers/{name}/input/stop")
def input_stop(name: str):
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}

    running, pid = _recorder_is_running(name)
    if not running or not pid:
        return {"ok": True, "stopped": True, "pid": pid}

    cname = docker_name(name)

    docker_exec(cname, ["sh", "-lc", f"kill -TERM {pid} >/dev/null 2>&1 || true"], timeout=2)
    time.sleep(0.1)
    docker_exec(cname, ["sh", "-lc", f"kill -KILL {pid} >/dev/null 2>&1 || true"], timeout=2)

    try:
        input_recorder_pid_path(name).unlink()
    except Exception:
        pass

    return {"ok": True, "stopped": True, "pid": pid}


@app.post("/containers/{name}/input/clear")
def input_clear(name: str):
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}
    ensure_container_fs(name)

    p = input_events_log_path(name)
    try:
        p.write_text("", encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": "clear_failed", "detail": str(e)}
    return {"ok": True}


@app.get("/containers/{name}/input/events")
def input_events(name: str, tail: int = 200, parse: int = 1):
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}

    p = input_events_log_path(name)
    lines = _tail_lines(p, int(tail))

    events = []
    if int(parse) == 1:
        for ln in lines:
            try:
                events.append(json.loads(ln))
            except Exception:
                events.append({"_raw": ln})

    return {"ok": True, "lines": lines, "events": events}


@app.get("/containers/{name}/logs/startup")
def logs_startup(name: str, tail: int = 200, timestamps: int = 0):
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}

    try:
        tail_i = int(tail)
    except Exception:
        return {"ok": False, "error": "bad_tail"}

    if tail_i <= 0:
        return {"ok": False, "error": "bad_tail"}
    if tail_i > 5000:
        tail_i = 5000

    cname = docker_name(name)

    try:
        c = docker_client.containers.get(cname)
    except NotFound:
        return {"ok": False, "error": "docker_not_found"}
    except Exception as e:
        return {"ok": False, "error": "docker_error", "detail": str(e)}

    try:
        use_ts = int(timestamps) == 1
        raw = c.logs(tail=tail_i, timestamps=use_ts)
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
        lines = text.splitlines()
        return {"ok": True, "container": name, "tail": tail_i, "timestamps": use_ts, "lines": lines}
    except Exception as e:
        return {"ok": False, "error": "logs_failed", "detail": str(e)}


@app.get("/containers/{name}/logs/automation")
def logs_automation(name: str, date: str | None = None, tail: int = 400):
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}

    try:
        tail_i = int(tail)
    except Exception:
        return {"ok": False, "error": "bad_tail"}

    if tail_i <= 0:
        return {"ok": False, "error": "bad_tail"}
    if tail_i > 5000:
        tail_i = 5000

    if not date:
        date_ymd = datetime.utcnow().strftime("%Y-%m-%d")
    else:
        date_ymd = str(date).strip()
        try:
            datetime.strptime(date_ymd, "%Y-%m-%d")
        except Exception:
            return {"ok": False, "error": "bad_date", "detail": "expected YYYY-MM-DD"}

    ensure_container_fs(name)

    p = automation_log_path(name, date_ymd)
    lines = _tail_lines(p, tail_i)

    return {
        "ok": True,
        "container": name,
        "date": date_ymd,
        "tail": tail_i,
        "path": str(p),
        "lines": lines,
    }
