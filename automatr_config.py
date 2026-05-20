# automatr_config.py
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


def _env(key: str, default: str = "") -> str:
    """
    Read env var with default, treating empty strings as 'unset'.
    This is the key that makes `.env` be source-of-truth without requiring
    `${VAR}` expansion support.
    """
    v = os.getenv(key)
    if v is None:
        return default
    v = str(v).strip()
    return default if v == "" else v


def _env_int(key: str, default: int) -> int:
    v = _env(key, str(default))
    try:
        return int(v)
    except Exception:
        return default


def normalize_host(host: str) -> str:
    """
    Normalize a host-like value into just the hostname:
    - strips scheme
    - strips path/query
    - strips port
    """
    h = (host or "").strip()
    h = re.sub(r"^[a-zA-Z]+://", "", h)
    h = h.split("/", 1)[0]
    h = h.split("?", 1)[0]
    h = h.split("#", 1)[0]
    h = h.split(":", 1)[0]
    return h or "127.0.0.1"


def _split_origins(csv: str) -> List[str]:
    parts = [p.strip() for p in (csv or "").split(",") if p.strip()]
    out: List[str] = []
    seen = set()
    for p in parts:
        # CORS origins should not have trailing slash
        if p.endswith("/"):
            p = p[:-1]
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


@dataclass(frozen=True)
class AutomatrConfig:
    # Host API / public identity
    host: str
    port: int
    api_base: str  # http://{host}:{port}
    public_base: str

    # Project paths
    project_root: Path
    data_dir: Path
    db_path: Path
    bin_dir: Path
    export_py: Path
    bin_containers_dir: Path

    # Docker/runtime
    runtime_image: str
    docker_network: str

    # Screen
    screen_w: str
    screen_h: str
    screen_d: str

    # noVNC
    novnc_port_base: int
    novnc_path: str

    # container internal
    container_root: str
    queue_dir: str

    # CORS
    cors_origins: List[str]

    # Host notifications
    host_notify_bin: str
    host_notify_poll: float

    # XMPP / agent bots
    xmpp_domain: str
    xmpp_host: str
    xmpp_port: str
    xmpp_muc: str
    xmpp_password: str
    xmpp_insecure: str

    # Prosody http port (for deriving public chat urls elsewhere if needed)
    prosody_http_port: int
    prosody_name: str


def load_config() -> AutomatrConfig:
    # Source of truth
    host = normalize_host(_env("AUTOMATR_HOST", "127.0.0.1"))
    port = _env_int("AUTOMATR_PORT", 8766)
    api_base = _env("AUTOMATR_API_BASE", "") or f"http://{host}:{port}"
    public_base = _env("AUTOMATR_PUBLIC_BASE", "https://xps.local")

    # IMPORTANT: PROJECT_ROOT must be stable (don't rely on cwd drifting)
    project_root = Path(_env("AUTOMATR_PROJECT_ROOT", str(Path(__file__).resolve().parent))).resolve()
    data_dir = Path(_env("AUTOMATR_DATA_DIR", str(project_root / "data"))).resolve()
    db_path = Path(_env("AUTOMATR_DB_PATH", str(data_dir / "automatr.db"))).resolve()

    bin_dir = project_root / "bin"
    export_py = Path(_env("AUTOMATR_EXPORT_PY", str(bin_dir / "export.py"))).resolve()
    bin_containers_dir = Path(_env("AUTOMATR_BIN_CONTAINERS_DIR", str(bin_dir / "containers"))).resolve()

    runtime_image = _env("AUTOMATR_RUNTIME_IMAGE", "automatr-runtime:dev")
    docker_network = _env("AUTOMATR_DOCKER_NETWORK", "")

    screen_w = _env("AUTOMATR_SCREEN_W", "1366")
    screen_h = _env("AUTOMATR_SCREEN_H", "768")
    screen_d = _env("AUTOMATR_SCREEN_D", "24")

    novnc_port_base = _env_int("AUTOMATR_NOVNC_PORT_BASE", 6100)
    novnc_path = _env("AUTOMATR_NOVNC_PATH", "/vnc_lite.html?autoconnect=1&resize=remote&path=websockify")

    container_root = _env("AUTOMATR_CONTAINER_ROOT", "/automatr")
    queue_dir = _env("AUTOMATR_QUEUE_DIR", "/automatr/queue")

    # CORS: normalize + add host:3000 automatically if not present
    cors_csv = _env("AUTOMATR_CORS_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000")
    cors = _split_origins(cors_csv)
    host_origin = f"http://{host}:3000"
    if host_origin not in cors:
        cors.append(host_origin)

    host_notify_bin = _env("AUTOMATR_HOST_NOTIFY_BIN", "notify-send")
    try:
        host_notify_poll = float(_env("AUTOMATR_HOST_NOTIFY_POLL", "0.2"))
    except Exception:
        host_notify_poll = 0.2

    # Prosody naming/ports (used by scripts, and useful for derived chat urls elsewhere)
    prosody_name = _env("AUTOMATR_PROSODY_NAME", "automatr-prosody")
    prosody_http_port = _env_int("AUTOMATR_PROSODY_HTTP_PORT", 5280)

    # XMPP defaults:
    # - Domain defaults to AUTOMATR_HOST (the official server name)
    # - Host defaults to docker-internal prosody name
    xmpp_domain = _env("AUTOMATR_XMPP_DOMAIN", "") or host
    xmpp_host = _env("AUTOMATR_XMPP_HOST", "") or prosody_name
    xmpp_port = _env("AUTOMATR_XMPP_PORT", "5222")
    xmpp_muc = _env("AUTOMATR_XMPP_MUC", "") or f"automatr@conference.{xmpp_domain}"
    xmpp_password = _env("AUTOMATR_XMPP_PASSWORD", "change-me-dev-only")
    xmpp_insecure = _env("AUTOMATR_XMPP_INSECURE_TLS", "1")

    # Ensure base dirs
    data_dir.mkdir(parents=True, exist_ok=True)
    bin_containers_dir.mkdir(parents=True, exist_ok=True)

    # Make sure downstream modules that read env (db.py) see these
    os.environ.setdefault("AUTOMATR_PROJECT_ROOT", str(project_root))
    os.environ.setdefault("AUTOMATR_DATA_DIR", str(data_dir))
    os.environ.setdefault("AUTOMATR_DB_PATH", str(db_path))

    # Also ensure XMPP env defaults are visible to anything else that reads os.environ
    os.environ.setdefault("AUTOMATR_XMPP_DOMAIN", xmpp_domain)
    os.environ.setdefault("AUTOMATR_XMPP_HOST", xmpp_host)
    os.environ.setdefault("AUTOMATR_XMPP_PORT", xmpp_port)
    os.environ.setdefault("AUTOMATR_XMPP_MUC", xmpp_muc)

    return AutomatrConfig(
        host=host,
        port=port,
        api_base=api_base,
        public_base=public_base,
        project_root=project_root,
        data_dir=data_dir,
        db_path=db_path,
        bin_dir=bin_dir,
        export_py=export_py,
        bin_containers_dir=bin_containers_dir,
        runtime_image=runtime_image,
        docker_network=docker_network,
        screen_w=screen_w,
        screen_h=screen_h,
        screen_d=screen_d,
        novnc_port_base=novnc_port_base,
        novnc_path=novnc_path,
        container_root=container_root,
        queue_dir=queue_dir,
        cors_origins=cors,
        host_notify_bin=host_notify_bin,
        host_notify_poll=host_notify_poll,
        xmpp_domain=xmpp_domain,
        xmpp_host=xmpp_host,
        xmpp_port=xmpp_port,
        xmpp_muc=xmpp_muc,
        xmpp_password=xmpp_password,
        xmpp_insecure=xmpp_insecure,
        prosody_http_port=prosody_http_port,
        prosody_name=prosody_name,
    )
