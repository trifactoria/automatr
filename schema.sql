PRAGMA journal_mode=WAL;

-- Containers user creates in the UI
CREATE TABLE IF NOT EXISTS containers (
  name TEXT PRIMARY KEY,
  description TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Published automations (YAML is the canonical representation)
CREATE TABLE IF NOT EXISTS automations (
  name TEXT PRIMARY KEY,
  description TEXT NOT NULL DEFAULT '',
  yaml TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Executions (one container running one orchestration)
CREATE TABLE IF NOT EXISTS executions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  container_name TEXT NOT NULL,
  automation_name TEXT NOT NULL,
  exec_folder TEXT NOT NULL,        -- e.g. "price_watch-2025-12-30_12-41-09"
  status TEXT NOT NULL,             -- running|stopped|succeeded|failed
  run_description TEXT NOT NULL DEFAULT '',
  started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  finished_at TEXT,

  FOREIGN KEY(container_name) REFERENCES containers(name) ON DELETE CASCADE,
  FOREIGN KEY(automation_name) REFERENCES automations(name) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_exec_container_started
  ON executions(container_name, started_at DESC);
