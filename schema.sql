PRAGMA foreign_keys = ON;

-- ============================================================
-- Core: automation definitions (compile target)
-- ============================================================

CREATE TABLE IF NOT EXISTS automations (
  name            TEXT PRIMARY KEY,
  description     TEXT NOT NULL DEFAULT '',
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),

  -- Optional: store latest compiled script for export/audit.
  compiled_py     TEXT,
  compiled_hash   TEXT,
  compiled_at     TEXT
);

CREATE TRIGGER IF NOT EXISTS automations_touch_updated_at
AFTER UPDATE ON automations
FOR EACH ROW
BEGIN
  UPDATE automations
     SET updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
   WHERE name = OLD.name;
END;


-- ============================================================
-- Variables: typed automation constants (target, min_ok, etc.)
-- Values stored as TEXT; compiler emits typed Python literals.
-- ============================================================

CREATE TABLE IF NOT EXISTS automation_vars (
  automation_name TEXT NOT NULL,
  key             TEXT NOT NULL,
  type            TEXT NOT NULL CHECK (type IN ('str','int','float','bool')),
  value           TEXT NOT NULL,
  description     TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (automation_name, key),
  FOREIGN KEY (automation_name) REFERENCES automations(name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_automation_vars_name
ON automation_vars (automation_name);


-- ============================================================
-- Steps: ordered actions (UI rows)
-- Action is a method name exposed by automatr_actions.py
-- ============================================================

CREATE TABLE IF NOT EXISTS automation_steps (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  automation_name TEXT NOT NULL,
  step_num        INTEGER NOT NULL,           -- 1..N
  label           TEXT NOT NULL DEFAULT '',
  action          TEXT NOT NULL,              -- e.g. 'type_text', 'click', 'dragcopy'
  enabled         INTEGER NOT NULL DEFAULT 1, -- 0/1
  note            TEXT NOT NULL DEFAULT '',
  FOREIGN KEY (automation_name) REFERENCES automations(name) ON DELETE CASCADE,
  UNIQUE (automation_name, step_num)
);

CREATE INDEX IF NOT EXISTS idx_automation_steps_name
ON automation_steps (automation_name);

CREATE INDEX IF NOT EXISTS idx_automation_steps_name_step
ON automation_steps (automation_name, step_num);


-- ============================================================
-- Step parameters: (key, type, value) tuples per step
-- No JSON required; UI can render these as a small table.
-- ============================================================

CREATE TABLE IF NOT EXISTS step_params (
  step_id         INTEGER NOT NULL,
  key             TEXT NOT NULL,
  type            TEXT NOT NULL CHECK (type IN ('str','int','float','bool')),
  value           TEXT NOT NULL,
  PRIMARY KEY (step_id, key),
  FOREIGN KEY (step_id) REFERENCES automation_steps(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_step_params_step
ON step_params (step_id);


-- ============================================================
-- Clauses / Conditions (chip rows)
--
-- Each step can have 0..N ordered clauses.
-- A clause is:
--   head: if | elif | else
--   predicate: lhs/op/rhs (NULL for else)
--   action: goto | continue | stop | notify
--
-- stop_tag: SUCCESS|FAILURE|BREAK (required when action='stop')
-- action_value:
--   - goto: step number as text ("10")
--   - notify: message text
--   - stop: message text (required by your design)
-- ============================================================

CREATE TABLE IF NOT EXISTS step_clauses (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  step_id         INTEGER NOT NULL,
  clause_order    INTEGER NOT NULL,  -- 0..N (drag/drop changes this)

  head            TEXT NOT NULL CHECK (head IN ('if','elif','else')),

  -- predicate (NULL allowed only for else):
  lhs_kind        TEXT CHECK (lhs_kind IN ('buffer','var','literal')),
  lhs_type        TEXT CHECK (lhs_type IN ('str','int','float','bool')),
  lhs_value       TEXT,  -- for var: var name; for literal: literal; for buffer: optional/ignored

  op              TEXT,  -- '==','!=','>','>=','<','<=','contains','startswith','endswith','regex'

  rhs_kind        TEXT CHECK (rhs_kind IN ('buffer','var','literal')),
  rhs_type        TEXT CHECK (rhs_type IN ('str','int','float','bool')),
  rhs_value       TEXT,

  action          TEXT NOT NULL CHECK (action IN ('goto','continue','stop','notify')),
  stop_tag        TEXT CHECK (stop_tag IN ('SUCCESS','FAILURE','BREAK')),
  action_value    TEXT, -- goto target / notify msg / stop msg

  note            TEXT NOT NULL DEFAULT '',

  FOREIGN KEY (step_id) REFERENCES automation_steps(id) ON DELETE CASCADE,
  UNIQUE (step_id, clause_order)
);

CREATE INDEX IF NOT EXISTS idx_step_clauses_step
ON step_clauses (step_id);

CREATE INDEX IF NOT EXISTS idx_step_clauses_step_order
ON step_clauses (step_id, clause_order);


-- ============================================================
-- Optional: host container registry (already exists in your host app)
-- Keep this if it helps the UI, but it’s not required for portable scripts.
-- ============================================================

CREATE TABLE IF NOT EXISTS containers (
  name            TEXT PRIMARY KEY,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Optional: which automations are "installed" to which container
CREATE TABLE IF NOT EXISTS container_automations (
  container_name  TEXT NOT NULL,
  automation_name TEXT NOT NULL,
  installed_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (container_name, automation_name),
  FOREIGN KEY (container_name) REFERENCES containers(name) ON DELETE CASCADE,
  FOREIGN KEY (automation_name) REFERENCES automations(name) ON DELETE CASCADE
);


-- ============================================================
-- Optional: run metadata/log pointers (JSON allowed here, but NOT required)
-- ============================================================

CREATE TABLE IF NOT EXISTS runs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  automation_name TEXT NOT NULL,
  container_name  TEXT,
  started_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  finished_at     TEXT,
  status          TEXT NOT NULL DEFAULT 'running', -- running|success|fail|stopped
  meta_json       TEXT,
  FOREIGN KEY (automation_name) REFERENCES automations(name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_runs_automation
ON runs (automation_name);

CREATE INDEX IF NOT EXISTS idx_runs_container
ON runs (container_name);
