export type Context =
  | { kind: "host" }
  | { kind: "container"; name: string };

export type ContainerRow = {
  name: string;
  description?: string;
  running: boolean;
  busy: boolean;
  busy_automation?: string | null;
};

export type AutomationRow = {
  name: string;
  description?: string;
  updated_at?: string;
};

export type VncInfo = {
  url: string;
  view_only: boolean;
};

