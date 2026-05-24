// src/lib/types.ts
export type Context = { kind: "host" } | { kind: "container"; name: string };

export type ContainerRow = {
  name: string;
  description?: string;
  running: boolean;
  busy: boolean;
  busy_automation?: string | null;
  stop_latched?: boolean;
};

export type ContainerDetail = {
  name: string;
  description?: string;
  running: boolean;
  busy: boolean;
  busy_automation?: string | null;
  stop_latched: boolean;
  vnc_url?: string | null;
  run_lock?: Record<string, unknown> | null;
};

export type AutomationRow = {
  name: string;
  description?: string;
  updated_at?: string;
  compiled_at?: string;
};

export type VncInfo = {
  url: string;
  view_only: boolean;
};

export type StepParam = { key: string; type: "str" | "int" | "float" | "bool"; value: string };
export type StepClause = {
  head: "if" | "elif" | "else";
  lhs_kind?: "buffer" | "var" | "literal" | null;
  lhs_type?: "str" | "int" | "float" | "bool" | null;
  lhs_value?: string | null;
  op?: string | null;
  rhs_kind?: "buffer" | "var" | "literal" | null;
  rhs_type?: "str" | "int" | "float" | "bool" | null;
  rhs_value?: string | null;
  action: "goto" | "continue" | "stop" | "notify";
  stop_tag?: "SUCCESS" | "FAILURE" | "BREAK" | null;
  action_value?: string | null;
  note?: string;
};

export type GraphVar = { key: string; type: "str" | "int" | "float" | "bool"; value: string; description?: string };

export type GraphStep = {
  id?: number;            // backend returns it; we can ignore on save
  step_num?: number;      // backend returns it; we derive by array order on save
  label: string;
  action: string;
  enabled: number;        // 0/1
  note?: string;
  params: StepParam[];
  clauses: StepClause[];
};

export type AutomationGraph = {
  name: string;
  description: string;
  created_at?: string;
  updated_at?: string;
  compiled_at?: string;
  compiled_hash?: string;
  vars: GraphVar[];
  steps: GraphStep[];
};

export type ActionsCheck = {
  ok: boolean;
  wrapper_actions: string[];
  db_actions: string[];
  missing_in_wrapper: string[];
  extra_in_wrapper: string[];
};

// Action Schema Types
export type ActionParamDef = {
  name: string;
  type: "str" | "int" | "float" | "bool";
  required: boolean;
  default: string | number | boolean | null;
  kind: string;
};

export type ActionDef = {
  action: string;
  params: ActionParamDef[];
};

export type ActionsSchemaResponse = {
  ok: true;
  schema: Record<string, ActionDef> | ActionDef[];
};

// Input Recorder Types
export type InputStatus = {
  running: boolean;
  pid?: number | null;
  log_path?: string;
  runner_log_path?: string;
};

export type InputStatusResponse = {
  ok: boolean;
  status?: InputStatus;
  running?: boolean;
  pid?: number | null;
  log_path?: string;
  runner_log_path?: string;
};

export type InputEvent = {
  timestamp?: string;
  type: string;
  data: Record<string, string | number | boolean | null | undefined>;
};

export type InputEventsResponse = {
  ok: boolean;
  lines?: string[];
  events?: InputEvent[];
};

// Helper to normalize InputStatusResponse into InputStatus
export function normalizeInputStatus(resp: InputStatusResponse): InputStatus {
  // If backend returns nested status object
  if (resp.status) {
    return resp.status;
  }
  // If backend returns flat structure
  return {
    running: resp.running ?? false,
    pid: resp.pid,
    log_path: resp.log_path,
    runner_log_path: resp.runner_log_path,
  };
}

// Logs
export type LogsLinesResponse = { ok: true; container: string; tail: number; lines: string[] } | ApiErrorResponse;

export type StartupLogsResponse =
  | ({ ok: true; container: string; tail: number; timestamps: boolean; lines: string[] })
  | ApiErrorResponse;

export type AutomationLogsResponse =
  | ({ ok: true; container: string; date: string; tail: number; path: string; lines: string[] })
  | ApiErrorResponse;


// API Response Envelopes
export type ApiOkResponse<T = Record<string, unknown>> = { ok: true } & T;
export type ApiErrorResponse = { ok: false; error: string; detail?: string };
export type ApiResponse<T = Record<string, unknown>> = ApiOkResponse<T> | ApiErrorResponse;

// Specific API Response Types
export type ContainerDetailResponse = { ok: true; container: ContainerDetail };
export type AutomationGraphResponse = { ok: true; graph: AutomationGraph };
export type SaveAutomationResponse = { ok: true; exported: boolean } | ApiErrorResponse;

// Summary types (used in lists)
export type ContainerSummary = ContainerRow;
export type AutomationSummary = AutomationRow;
