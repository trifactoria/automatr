from __future__ import annotations

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import docker
from docker.errors import NotFound, APIError

import db

# --- Configuration from environment ---
def get_env(key: str, default: str = "") -> str:
    """Get env var with optional default"""
    return os.getenv(key, default)

# Host API settings
AUTOMATR_HOST = get_env("AUTOMATR_HOST", "127.0.0.1")
AUTOMATR_PORT = int(get_env("AUTOMATR_PORT", "8766"))

# Storage paths (resolve relative paths to absolute)
DATA_DIR = Path(get_env("AUTOMATR_DATA_DIR", "./data")).resolve()
CONTAINERS_DIR = Path(get_env("AUTOMATR_CONTAINERS_DIR", f"{DATA_DIR}/containers")).resolve()
DB_PATH = Path(get_env("AUTOMATR_DB_PATH", f"{DATA_DIR}/automatr.db")).resolve()

# Docker settings
DOCKER_BIN = get_env("AUTOMATR_DOCKER_BIN", "docker")
RUNTIME_IMAGE = get_env("AUTOMATR_RUNTIME_IMAGE", "automatr-runtime:dev")
DOCKER_NETWORK = get_env("AUTOMATR_DOCKER_NETWORK", "")

# Screen settings
SCREEN_W = get_env("AUTOMATR_SCREEN_W", "1366")
SCREEN_H = get_env("AUTOMATR_SCREEN_H", "768")
SCREEN_D = get_env("AUTOMATR_SCREEN_D", "24")

# noVNC settings
NOVNC_PORT_BASE = int(get_env("AUTOMATR_NOVNC_PORT_BASE", "6100"))
NOVNC_PATH = get_env("AUTOMATR_NOVNC_PATH", "/vnc.html?autoconnect=1&resize=remote")

# Container internal paths
CONTAINER_ROOT = get_env("AUTOMATR_CONTAINER_ROOT", "/automatr")
QUEUE_DIR = get_env("AUTOMATR_QUEUE_DIR", "/automatr/queue")

# CORS origins
CORS_ORIGINS = get_env("AUTOMATR_CORS_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000")

# --- Initialize ---
# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONTAINERS_DIR.mkdir(parents=True, exist_ok=True)

# Initialize database
db.init_db()

# Initialize Docker client
docker_client = docker.from_env()

# --- Runtime state (in-memory) ---
# Track running containers: name -> {container_id, novnc_port}
_RUNTIME: dict[str, dict] = {}

# Port allocation
_NEXT_PORT = NOVNC_PORT_BASE

def allocate_port() -> int:
    """Allocate next available noVNC port"""
    global _NEXT_PORT
    port = _NEXT_PORT
    _NEXT_PORT += 1
    return port

# --- App ---
app = FastAPI(title="Automatr Host API", version="0.1.0")

# --- CORS for Next.js dev server ---
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


# ---------------- Helper Functions ----------------
def get_container_dir(name: str) -> Path:
    """Get host directory for container"""
    return CONTAINERS_DIR / name


def get_queue_dir(name: str) -> Path:
    """Get host queue directory for container"""
    return get_container_dir(name) / "queue"


def get_lock_file(name: str) -> Path:
    """Get run.lock file path for container"""
    return get_container_dir(name) / "run.lock"


def is_container_busy(name: str) -> tuple[bool, Optional[str]]:
    """Check if container is busy (has run.lock)"""
    lock_file = get_lock_file(name)
    if not lock_file.exists():
        return False, None

    try:
        lock_data = json.loads(lock_file.read_text())
        automation = lock_data.get("automation", "unknown")
        return True, automation
    except Exception:
        return True, None


def is_container_running(name: str) -> bool:
    """Check if container is actually running"""
    if name not in _RUNTIME:
        return False

    container_id = _RUNTIME[name].get("container_id")
    if not container_id:
        return False

    try:
        container = docker_client.containers.get(container_id)
        return container.status == "running"
    except NotFound:
        # Container was removed externally
        del _RUNTIME[name]
        return False
    except Exception:
        return False


# ---------------- Containers ----------------
@app.get("/containers")
def list_containers():
    """List all containers with runtime status"""
    containers = db.list_containers()

    # Augment with runtime info
    result = []
    for c in containers:
        name = c["name"]
        running = is_container_running(name)
        busy, busy_automation = is_container_busy(name)

        result.append({
            "name": name,
            "description": c.get("description", ""),
            "running": running,
            "busy": busy,
            "busy_automation": busy_automation,
        })

    return result


@app.post("/containers")
def create_container(payload: dict):
    """Create a new container"""
    name = (payload.get("name") or "").strip()
    desc = (payload.get("description") or "").strip()

    if not name:
        return {"ok": False, "error": "name_required"}

    if db.container_exists(name):
        return {"ok": False, "error": "container_exists"}

    # Create in database
    db.create_container(name, desc)

    # Create host directories
    container_dir = get_container_dir(name)
    container_dir.mkdir(parents=True, exist_ok=True)
    get_queue_dir(name).mkdir(parents=True, exist_ok=True)

    return {"ok": True}


@app.post("/containers/{name}/start")
def start_container(name: str):
    """Start a container with Docker"""
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}

    if is_container_running(name):
        return {"ok": False, "error": "already_running"}

    try:
        # Ensure directories exist
        container_dir = get_container_dir(name)
        container_dir.mkdir(parents=True, exist_ok=True)
        get_queue_dir(name).mkdir(parents=True, exist_ok=True)

        # Allocate noVNC port
        novnc_port = allocate_port()

        # Container name
        container_name = f"automatr-{name}"

        # Build docker run config
        environment = {
            "AUTOMATR_CONTAINER_ROOT": CONTAINER_ROOT,
            "AUTOMATR_QUEUE_DIR": QUEUE_DIR,
            "AUTOMATR_SCREEN_W": SCREEN_W,
            "AUTOMATR_SCREEN_H": SCREEN_H,
            "AUTOMATR_SCREEN_D": SCREEN_D,
            "DISPLAY": ":99",
        }

        volumes = {
            str(container_dir): {"bind": CONTAINER_ROOT, "mode": "rw"}
        }

        ports = {
            "6080/tcp": novnc_port
        }

        # Additional docker run options
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

        # Start container
        container = docker_client.containers.run(**run_kwargs)

        # Store runtime info
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
    """Stop and remove a container"""
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}

    if name not in _RUNTIME:
        return {"ok": False, "error": "not_running"}

    try:
        container_id = _RUNTIME[name]["container_id"]
        container = docker_client.containers.get(container_id)

        # Stop container
        container.stop(timeout=10)
        container.remove()

        # Clear runtime info
        del _RUNTIME[name]

        return {"ok": True}

    except NotFound:
        # Container already removed
        if name in _RUNTIME:
            del _RUNTIME[name]
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"stop_failed: {str(e)}"}


@app.get("/containers/{name}/vnc_url")
def container_vnc_url(name: str):
    """Get VNC URL for container"""
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}

    if not is_container_running(name):
        return {"ok": False, "error": "not_running"}

    # Get noVNC port
    novnc_port = _RUNTIME[name]["novnc_port"]

    # Build URL
    url = f"http://127.0.0.1:{novnc_port}{NOVNC_PATH}"

    return {
        "url": url,
        "view_only": True  # Can be toggled later
    }


@app.post("/containers/{name}/stop_auto")
def stop_auto(name: str):
    """Stop running automation (remove lock file)"""
    if not db.container_exists(name):
        return {"ok": False, "error": "not_found"}

    # Remove lock file if exists
    lock_file = get_lock_file(name)
    if lock_file.exists():
        lock_file.unlink()

    return {"ok": True}


@app.post("/containers/{name}/run")
def run_automation(name: str, payload: dict):
    """Queue an automation to run in container"""
    automation_name = (payload.get("automation_name") or "").strip()

    if not automation_name:
        return {"ok": False, "error": "automation_name_required"}

    if not db.container_exists(name):
        return {"ok": False, "error": "container_not_found"}

    # Get automation YAML from database
    automation = db.get_automation(automation_name)
    if not automation:
        return {"ok": False, "error": "automation_not_found"}

    if not is_container_running(name):
        return {"ok": False, "error": "container_not_running"}

    # Check if busy
    busy, _ = is_container_busy(name)
    if busy:
        return {"ok": False, "error": "container_busy"}

    try:
        # Create job file in queue
        queue_dir = get_queue_dir(name)
        queue_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        job_filename = f"job-{automation_name}-{timestamp}.yaml"
        job_file = queue_dir / job_filename

        # Write YAML to job file
        job_file.write_text(automation["yaml"])

        return {"ok": True, "queued": True}

    except Exception as e:
        return {"ok": False, "error": f"queue_failed: {str(e)}"}


# ---------------- Automations ----------------
@app.get("/automations")
def list_automations():
    """List all automations"""
    automations = db.list_automations()
    return [
        {
            "name": a["name"],
            "description": a.get("description", ""),
            "updated_at": a.get("updated_at"),
        }
        for a in automations
    ]


@app.post("/automations")
def create_automation(payload: dict):
    """Create or update an automation"""
    name = (payload.get("name") or "").strip()
    desc = (payload.get("description") or "").strip()
    yaml_text = payload.get("yaml") or ""

    if not name:
        return {"ok": False, "error": "name_required"}

    # Upsert to database
    db.upsert_automation(name, desc, yaml_text)

    return {"ok": True}


@app.get("/automations/{name}")
def get_automation(name: str):
    """Get automation details"""
    automation = db.get_automation(name)
    if not automation:
        return {"ok": False, "error": "not_found"}

    return {
        "name": automation["name"],
        "description": automation.get("description", ""),
        "yaml": automation.get("yaml", "")
    }
