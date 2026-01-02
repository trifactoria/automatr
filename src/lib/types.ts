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
  run_lock?: any | null;
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
  key: string;
  type: "str" | "int" | "float" | "bool";
  default: string;
  description?: string;
};

export type ActionSchema = {
  name: string;
  params: ActionParamDef[];
  description?: string;
};

export type ActionsSchemaResponse = {
  ok: true;
  schemas: Record<string, ActionSchema>;
};

// API Response Envelopes
export type ApiOkResponse<T = any> = { ok: true } & T;
export type ApiErrorResponse = { ok: false; error: string; detail?: string };
export type ApiResponse<T = any> = ApiOkResponse<T> | ApiErrorResponse;

// Specific API Response Types
export type ContainerDetailResponse = { ok: true; container: ContainerDetail };
export type AutomationGraphResponse = { ok: true; graph: AutomationGraph };
export type SaveAutomationResponse = { ok: true; exported: boolean } | ApiErrorResponse;

// Summary types (used in lists)
export type ContainerSummary = ContainerRow;
export type AutomationSummary = AutomationRow;

