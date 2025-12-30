from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# --- App ---
app = FastAPI(title="Automatr Host API", version="0.1.0")

# --- CORS for Next.js dev server ---
# In dev, Next is typically http://localhost:3000
origins = os.getenv("AUTOMATR_CORS_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-memory stubs (MVP placeholder) ---
_CONTAINERS: dict[str, dict] = {}
_AUTOMATIONS: dict[str, dict] = {}


@app.get("/health")
def health():
    return {"ok": True}


# ---------------- Containers ----------------
@app.get("/containers")
def list_containers():
    return list(_CONTAINERS.values())


@app.post("/containers")
def create_container(payload: dict):
    name = (payload.get("name") or "").strip()
    desc = (payload.get("description") or "").strip()

    if not name:
        return {"ok": False, "error": "name_required"}

    if name in _CONTAINERS:
        return {"ok": False, "error": "container_exists"}

    _CONTAINERS[name] = {
        "name": name,
        "description": desc,
        "running": False,
        "busy": False,
        "busy_automation": None,
    }
    return {"ok": True}


@app.post("/containers/{name}/start")
def start_container(name: str):
    c = _CONTAINERS.get(name)
    if not c:
        return {"ok": False, "error": "not_found"}
    c["running"] = True
    return {"ok": True}


@app.post("/containers/{name}/stop")
def stop_container(name: str):
    c = _CONTAINERS.get(name)
    if not c:
        return {"ok": False, "error": "not_found"}
    c["running"] = False
    c["busy"] = False
    c["busy_automation"] = None
    return {"ok": True}


@app.get("/containers/{name}/vnc_url")
def container_vnc_url(name: str):
    # Placeholder URL for now
    # Later: host will return real noVNC URL, view_only default.
    if name not in _CONTAINERS:
        return {"ok": False, "error": "not_found"}
    return {"url": "about:blank", "view_only": True}


@app.post("/containers/{name}/stop_auto")
def stop_auto(name: str):
    # MVP: treat same as stop container
    return stop_container(name)


# ---------------- Automations ----------------
@app.get("/automations")
def list_automations():
    # Return list matching UI type
    return [
        {
            "name": a["name"],
            "description": a.get("description", ""),
            "updated_at": a.get("updated_at"),
        }
        for a in _AUTOMATIONS.values()
    ]


@app.post("/automations")
def create_automation(payload: dict):
    name = (payload.get("name") or "").strip()
    desc = (payload.get("description") or "").strip()
    yaml_text = payload.get("yaml") or ""

    if not name:
        return {"ok": False, "error": "name_required"}

    _AUTOMATIONS[name] = {
        "name": name,
        "description": desc,
        "yaml": yaml_text,
        "updated_at": None,
    }
    return {"ok": True}


@app.get("/automations/{name}")
def get_automation(name: str):
    a = _AUTOMATIONS.get(name)
    if not a:
        return {"ok": False, "error": "not_found"}
    return {"name": a["name"], "description": a.get("description", ""), "yaml": a.get("yaml", "")}
