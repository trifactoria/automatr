from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def stamp_now_local() -> str:
    # e.g. 2025-12-30_13-22-10
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def slug(s: str) -> str:
    s = s.strip().lower()
    out = []
    for ch in s:
        if ch.isalnum() or ch in "-_":
            out.append(ch)
        elif ch.isspace():
            out.append("-")
    return "".join(out).strip("-") or "automation"


@dataclass
class RunPaths:
    container_dir: Path
    exec_dir: Path
    lock_path: Path
    log_path: Path
    events_path: Path
    screenshots_dir: Path
    published_yaml_path: Path
    meta_path: Path


def prepare_run_paths(data_dir: Path, container_name: str, automation_name: str) -> RunPaths:
    container_dir = data_dir / container_name
    container_dir.mkdir(parents=True, exist_ok=True)

    base = f"{slug(automation_name)}-{stamp_now_local()}"
    exec_dir = container_dir / base

    # If same second collision, suffix -a, -b, ...
    if exec_dir.exists():
        suffix = ord("a")
        while True:
            candidate = container_dir / f"{base}-{chr(suffix)}"
            if not candidate.exists():
                exec_dir = candidate
                break
            suffix += 1

    exec_dir.mkdir(parents=True, exist_ok=False)

    screenshots_dir = exec_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    lock_path = container_dir / "run.lock"
    log_path = exec_dir / "run.log"
    events_path = exec_dir / "events.jsonl"
    published_yaml_path = exec_dir / "published.yaml"
    meta_path = exec_dir / "meta.json"

    return RunPaths(
        container_dir=container_dir,
        exec_dir=exec_dir,
        lock_path=lock_path,
        log_path=log_path,
        events_path=events_path,
        screenshots_dir=screenshots_dir,
        published_yaml_path=published_yaml_path,
        meta_path=meta_path,
    )


def write_lock(paths: RunPaths, automation_name: str) -> None:
    payload = {
        "automation": automation_name,
        "started_at": datetime.now().isoformat(),
        "exec_folder": paths.exec_dir.name,
        "status": "running",
    }
    paths.lock_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear_lock(paths: RunPaths) -> None:
    try:
        paths.lock_path.unlink()
    except FileNotFoundError:
        pass


def log_line(paths: RunPaths, line: str) -> None:
    paths.log_path.parent.mkdir(parents=True, exist_ok=True)
    with paths.log_path.open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


def event(paths: RunPaths, kind: str, data: dict) -> None:
    rec = {"ts": datetime.now().isoformat(), "kind": kind, "data": data}
    with paths.events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def run_stub(data_dir: str, container_name: str, automation_name: str, yaml_text: str, run_description: str = "") -> str:
    paths = prepare_run_paths(Path(data_dir), container_name, automation_name)

    # Write meta + yaml
    paths.published_yaml_path.write_text(yaml_text, encoding="utf-8")
    paths.meta_path.write_text(
        json.dumps(
            {
                "container": container_name,
                "automation": automation_name,
                "description": run_description,
                "created_at": datetime.now().isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Enforce single run per container via lock
    if paths.lock_path.exists():
        raise RuntimeError(f"Container '{container_name}' is busy (run.lock exists)")

    write_lock(paths, automation_name)

    try:
        log_line(paths, f"=== BEGIN automation={automation_name} ts={datetime.now().isoformat()} ===")
        event(paths, "begin", {"automation": automation_name})

        # Stub "work"
        log_line(paths, "stub: would execute YAML steps here")
        event(paths, "stub", {"msg": "no execution yet"})

        log_line(paths, f"=== END automation={automation_name} ts={datetime.now().isoformat()} status=ok ===")
        event(paths, "end", {"automation": automation_name, "status": "ok"})
        return str(paths.exec_dir)
    except Exception as e:
        log_line(paths, f'=== END automation={automation_name} ts={datetime.now().isoformat()} status=error reason="{e}" ===')
        event(paths, "end", {"automation": automation_name, "status": "error", "reason": str(e)})
        raise
    finally:
        clear_lock(paths)
