// src/lib/api.ts
import type {
  ContainerSummary,
  ContainerDetail,
  ContainerDetailResponse,
  AutomationSummary,
  AutomationGraph,
  AutomationGraphResponse,
  SaveAutomationResponse,
  ActionsCheck,
  ActionsSchemaResponse,
  ActionDef,
  VncInfo,
  ApiResponse,
  GraphVar,
  GraphStep,
} from "./types";

export const API_BASE = "http://127.0.0.1:8766";

async function readErr(res: Response): Promise<string> {
  try {
    const text = await res.text();
    return text || `${res.status}`;
  } catch {
    return `${res.status}`;
  }
}

// Low-level API helpers
async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} failed: ${await readErr(res)}`);
  return res.json();
}

async function apiPost<T>(path: string, body?: any): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${await readErr(res)}`);
  return res.json();
}

async function apiDelete<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE", cache: "no-store" });
  if (!res.ok) throw new Error(`DELETE ${path} failed: ${await readErr(res)}`);
  return res.json();
}

// Helper to check API responses with {ok: false} envelopes
function checkApiResponse<T>(response: ApiResponse<T>, context: string): T {
  if (!response.ok) {
    const msg = response.detail || response.error || "Unknown error";
    throw new Error(`${context}: ${msg}`);
  }
  return response as T;
}

// ============================================================================
// HIGH-LEVEL API WRAPPERS (Single source of truth for envelope unwrapping)
// ============================================================================

// CONTAINERS
export async function getContainers(): Promise<ContainerSummary[]> {
  // GET /containers returns array directly
  return apiGet<ContainerSummary[]>("/containers");
}

export async function getContainerDetail(name: string): Promise<ContainerDetail> {
  // GET /containers/{name} returns {ok: true, container: {...}}
  const response = await apiGet<ContainerDetailResponse>(`/containers/${encodeURIComponent(name)}`);
  checkApiResponse(response, "Get container detail");
  return response.container;
}

export async function createContainer(payload: { name: string; description: string }): Promise<void> {
  // POST /containers returns {ok: true} | {ok: false, error}
  const response = await apiPost<ApiResponse>("/containers", payload);
  checkApiResponse(response, "Create container");
}

export async function startContainer(name: string): Promise<void> {
  // POST /containers/{name}/start returns {ok: true}
  const response = await apiPost<ApiResponse>(`/containers/${encodeURIComponent(name)}/start`);
  checkApiResponse(response, "Start container");
}

export async function stopContainer(name: string): Promise<void> {
  // POST /containers/{name}/stop returns {ok: true}
  const response = await apiPost<ApiResponse>(`/containers/${encodeURIComponent(name)}/stop`);
  checkApiResponse(response, "Stop container");
}

export async function restartContainer(name: string): Promise<void> {
  // POST /containers/{name}/restart returns {ok: true}
  const response = await apiPost<ApiResponse>(`/containers/${encodeURIComponent(name)}/restart`);
  checkApiResponse(response, "Restart container");
}

export async function getVncUrl(name: string): Promise<VncInfo> {
  // GET /containers/{name}/vnc_url returns {url, view_only}
  return apiGet<VncInfo>(`/containers/${encodeURIComponent(name)}/vnc_url`);
}

export async function stopAuto(name: string): Promise<void> {
  // POST /containers/{name}/stop_auto returns {ok: true, stop_latched: true}
  const response = await apiPost<ApiResponse>(`/containers/${encodeURIComponent(name)}/stop_auto`);
  checkApiResponse(response, "Stop auto");
}

export async function clearStop(name: string): Promise<void> {
  // POST /containers/{name}/clear_stop returns {ok: true}
  const response = await apiPost<ApiResponse>(`/containers/${encodeURIComponent(name)}/clear_stop`);
  checkApiResponse(response, "Clear stop");
}

export async function runAutomation(container: string, automation: string): Promise<void> {
  // POST /containers/{name}/run body: {automation: "name"}
  const response = await apiPost<ApiResponse>(`/containers/${encodeURIComponent(container)}/run`, {
    automation,
  });
  checkApiResponse(response, "Run automation");
}

// AUTOMATIONS
export async function getAutomations(): Promise<AutomationSummary[]> {
  // GET /automations returns array directly
  return apiGet<AutomationSummary[]>("/automations");
}

export async function getAutomationGraph(name: string): Promise<AutomationGraph> {
  // GET /automations/{name}/graph returns {ok: true, graph: {...}}
  const response = await apiGet<AutomationGraphResponse>(`/automations/${encodeURIComponent(name)}/graph`);
  checkApiResponse(response, "Get automation graph");
  return response.graph;
}

export async function saveAutomation(payload: {
  name: string;
  description: string;
  container: string;
  vars: GraphVar[];
  steps: GraphStep[];
}): Promise<void> {
  // POST /automations/save - payload must be flat (not nested under "automation")
  // Returns {ok: true, exported: true} | {ok: false, error, detail?}
  const response = await apiPost<SaveAutomationResponse>("/automations/save", payload);
  checkApiResponse(response, "Save automation");
}

export async function deleteAutomation(name: string): Promise<void> {
  // DELETE /automations/{name} returns {ok: true}
  const response = await apiDelete<ApiResponse>(`/automations/${encodeURIComponent(name)}`);
  checkApiResponse(response, "Delete automation");
}

// ACTIONS
export async function getActionsCheck(): Promise<ActionsCheck> {
  // GET /actions/check returns {ok: true, wrapper_actions: [...], ...}
  return apiGet<ActionsCheck>("/actions/check");
}

export async function getActionsSchema(): Promise<Record<string, ActionDef>> {
  try {
    // GET /actions/schema returns {ok: true, schema: {...}} or {ok: true, schema: [...]}
    const response = await apiGet<ActionsSchemaResponse>("/actions/schema");
    checkApiResponse(response, "Get actions schema");

    // Normalize response: if list, convert to map by action name
    if (Array.isArray(response.schema)) {
      const map: Record<string, ActionDef> = {};
      for (const actionDef of response.schema) {
        map[actionDef.action] = actionDef;
      }
      return map;
    }

    // Already a map
    return response.schema;
  } catch (error) {
    console.error("Failed to fetch actions schema:", error);
    // Return empty object on any failure (never undefined)
    return {};
  }
}

