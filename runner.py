#!/usr/bin/env python3
"""
Automatr Runner - In-container automation executor
Watches queue directory and executes YAML automation scripts
"""

import os
import sys
import time
import json
import subprocess
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Read env config
CONTAINER_ROOT = Path(os.getenv("AUTOMATR_CONTAINER_ROOT", "/automatr"))
QUEUE_DIR = Path(os.getenv("AUTOMATR_QUEUE_DIR", "/automatr/queue"))
DISPLAY = os.getenv("DISPLAY", ":99")

# Lock file location
LOCK_FILE = CONTAINER_ROOT / "run.lock"


class AutomationRunner:
    def __init__(self, exec_folder: Path, automation_name: str):
        self.exec_folder = exec_folder
        self.automation_name = automation_name
        self.log_file = exec_folder / "run.log"
        self.events_file = exec_folder / "events.jsonl"
        self.screenshots_dir = exec_folder / "screenshots"
        self.screenshot_count = 0

    def log(self, message: str, level: str = "INFO"):
        """Write to run.log"""
        timestamp = datetime.utcnow().isoformat() + "Z"
        log_line = f"[{timestamp}] [{level}] {message}\n"
        with open(self.log_file, "a") as f:
            f.write(log_line)
        print(log_line.strip())

    def log_event(self, event_type: str, data: Dict[str, Any]):
        """Write to events.jsonl"""
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "type": event_type,
            "data": data
        }
        with open(self.events_file, "a") as f:
            f.write(json.dumps(event) + "\n")

    def run_command(self, cmd: List[str], description: str) -> tuple[bool, str]:
        """Run a shell command and capture output"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ, "DISPLAY": DISPLAY}
            )
            success = result.returncode == 0
            output = result.stdout + result.stderr

            if success:
                self.log(f"{description}: OK")
            else:
                self.log(f"{description}: FAILED - {output}", "ERROR")

            return success, output
        except subprocess.TimeoutExpired:
            self.log(f"{description}: TIMEOUT", "ERROR")
            return False, "Command timed out"
        except Exception as e:
            self.log(f"{description}: EXCEPTION - {str(e)}", "ERROR")
            return False, str(e)

    def execute_step(self, step: Dict[str, Any], step_num: int) -> bool:
        """Execute a single automation step"""
        step_type = step.get("type", "unknown")
        self.log(f"Step {step_num}: {step_type}")
        self.log_event("step_start", {"step_num": step_num, "type": step_type, "step": step})

        success = False

        try:
            if step_type == "sleep":
                # Sleep for specified duration
                duration = step.get("duration", 1)
                self.log(f"  Sleeping for {duration}s")
                time.sleep(duration)
                success = True

            elif step_type == "mouse_move":
                # Move mouse to x,y
                x = step.get("x", 0)
                y = step.get("y", 0)
                success, _ = self.run_command(
                    ["xdotool", "mousemove", str(x), str(y)],
                    f"  Move mouse to ({x}, {y})"
                )

            elif step_type == "click":
                # Click mouse button (1=left, 2=middle, 3=right)
                button = step.get("button", 1)
                success, _ = self.run_command(
                    ["xdotool", "click", str(button)],
                    f"  Click button {button}"
                )

            elif step_type == "type":
                # Type text
                text = step.get("text", "")
                success, _ = self.run_command(
                    ["xdotool", "type", "--delay", "100", "--", text],
                    f"  Type text"
                )

            elif step_type == "key":
                # Press key combination (e.g., "ctrl+c", "Return", "alt+F4")
                combo = step.get("combo", "")
                success, _ = self.run_command(
                    ["xdotool", "key", combo],
                    f"  Press key: {combo}"
                )

            elif step_type == "screenshot":
                # Take screenshot
                self.screenshots_dir.mkdir(exist_ok=True)
                name = step.get("name", f"screenshot_{self.screenshot_count:04d}")
                if not name.endswith(".png"):
                    name += ".png"
                screenshot_path = self.screenshots_dir / name
                success, _ = self.run_command(
                    ["scrot", str(screenshot_path)],
                    f"  Screenshot: {name}"
                )
                self.screenshot_count += 1

            else:
                self.log(f"  Unknown step type: {step_type}", "WARN")
                success = False

            self.log_event("step_complete", {
                "step_num": step_num,
                "type": step_type,
                "success": success
            })

        except Exception as e:
            self.log(f"  Step failed with exception: {str(e)}", "ERROR")
            self.log_event("step_error", {
                "step_num": step_num,
                "type": step_type,
                "error": str(e)
            })
            success = False

        return success

    def run_automation(self, yaml_content: str) -> bool:
        """Execute all steps in the automation"""
        try:
            # Parse YAML
            automation = yaml.safe_load(yaml_content)

            # Extract metadata
            automation_name = automation.get("name", self.automation_name)
            description = automation.get("description", "")
            steps = automation.get("steps", [])

            self.log(f"Starting automation: {automation_name}")
            if description:
                self.log(f"Description: {description}")
            self.log(f"Total steps: {len(steps)}")

            self.log_event("automation_start", {
                "name": automation_name,
                "description": description,
                "step_count": len(steps)
            })

            # Execute each step
            for i, step in enumerate(steps, 1):
                success = self.execute_step(step, i)

                # On failure, you could choose to stop or continue
                # For now, we continue but log the failure
                if not success:
                    self.log(f"Step {i} failed, but continuing...", "WARN")

            self.log("Automation completed")
            self.log_event("automation_complete", {
                "name": automation_name,
                "step_count": len(steps)
            })

            return True

        except yaml.YAMLError as e:
            self.log(f"YAML parsing error: {str(e)}", "ERROR")
            self.log_event("automation_error", {"error": f"YAML parse error: {str(e)}"})
            return False
        except Exception as e:
            self.log(f"Automation failed: {str(e)}", "ERROR")
            self.log_event("automation_error", {"error": str(e)})
            return False


def acquire_lock(automation_name: str) -> bool:
    """Try to acquire run lock"""
    if LOCK_FILE.exists():
        return False

    lock_data = {
        "automation": automation_name,
        "started_at": datetime.utcnow().isoformat() + "Z",
        "pid": os.getpid()
    }

    LOCK_FILE.write_text(json.dumps(lock_data, indent=2))
    return True


def release_lock():
    """Release run lock"""
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()


def process_job(job_file: Path):
    """Process a single job file"""
    print(f"Processing job: {job_file.name}")

    try:
        # Read job file
        yaml_content = job_file.read_text()

        # Extract automation name from job file or YAML
        # Job filename format: job-<automation_name>-<timestamp>.yaml
        parts = job_file.stem.split("-")
        if len(parts) >= 2:
            automation_name = parts[1]
        else:
            automation_name = "unknown"

        # Try to acquire lock
        if not acquire_lock(automation_name):
            print(f"Could not acquire lock - another automation is running")
            return

        try:
            # Create execution folder with timestamp
            timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
            exec_folder = CONTAINER_ROOT / f"{automation_name}-{timestamp}"
            exec_folder.mkdir(exist_ok=True)

            # Copy YAML to published.yaml
            (exec_folder / "published.yaml").write_text(yaml_content)

            # Create meta.json
            meta = {
                "automation_name": automation_name,
                "started_at": datetime.utcnow().isoformat() + "Z",
                "job_file": job_file.name
            }
            (exec_folder / "meta.json").write_text(json.dumps(meta, indent=2))

            # Run automation
            runner = AutomationRunner(exec_folder, automation_name)
            success = runner.run_automation(yaml_content)

            # Update meta with completion
            meta["finished_at"] = datetime.utcnow().isoformat() + "Z"
            meta["success"] = success
            (exec_folder / "meta.json").write_text(json.dumps(meta, indent=2))

            # Move job file to exec folder (or delete it)
            job_file.rename(exec_folder / job_file.name)

            print(f"Job completed: {automation_name}")

        finally:
            # Always release lock
            release_lock()

    except Exception as e:
        print(f"Error processing job {job_file.name}: {str(e)}")
        # Clean up lock on error
        release_lock()


def watch_queue():
    """Main loop - watch queue directory for jobs"""
    print(f"Automatr Runner starting...")
    print(f"  Container root: {CONTAINER_ROOT}")
    print(f"  Queue dir: {QUEUE_DIR}")
    print(f"  Display: {DISPLAY}")
    print(f"  Lock file: {LOCK_FILE}")

    # Ensure queue directory exists
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)

    print("Watching queue for jobs...")

    while True:
        try:
            # Look for job files
            job_files = sorted(QUEUE_DIR.glob("job-*.yaml"))

            if job_files:
                # Process oldest job first
                job_file = job_files[0]
                process_job(job_file)
            else:
                # No jobs, sleep and check again
                time.sleep(1)

        except KeyboardInterrupt:
            print("\nShutting down runner...")
            break
        except Exception as e:
            print(f"Error in main loop: {str(e)}")
            time.sleep(5)


if __name__ == "__main__":
    watch_queue()
