"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import type { Context, ContainerRow, AutomationRow, VncInfo } from "@/lib/types";

import { Select } from "@/components/Select";
import { HostDashboard } from "@/components/HostDashboard";
import { ContainerDashboard } from "@/components/ContainerDashboard";

import { CreateContainerModal } from "@/components/modals/CreateContainerModal";
import { CreateAutomationModal } from "@/components/modals/CreateAutomationModal";

export default function Page() {
  // context
  const [context, setContext] = useState<Context>({ kind: "host" });

  // data
  const [containers, setContainers] = useState<ContainerRow[]>([]);
  const [automations, setAutomations] = useState<AutomationRow[]>([]);

  // UI state
  const [diag, setDiag] = useState<string>("");

  // container UI
  const selectedContainerName = context.kind === "container" ? context.name : "";
  const [vncVisible, setVncVisible] = useState(false);
  const [takeover, setTakeover] = useState(false);
  const [running, setRunning] = useState(false);
  const [vnc, setVnc] = useState<VncInfo | null>(null);

  // automation UI
  const [automationName, setAutomationName] = useState("");
  const [editorVisible, setEditorVisible] = useState(false);
  const [loggerVisible, setLoggerVisible] = useState(false);

  // modals
  const [createContainerOpen, setCreateContainerOpen] = useState(false);
  const [createAutomationOpen, setCreateAutomationOpen] = useState(false);

  async function refresh() {
    // These endpoints will be implemented in the host API.
    // For now they can return [] to keep UI running.
    const [cs, as] = await Promise.all([
      apiGet<ContainerRow[]>("/containers").catch(() => []),
      apiGet<AutomationRow[]>("/automations").catch(() => []),
    ]);
    setContainers(cs);
    setAutomations(as);
  }

  useEffect(() => {
    refresh().catch((e) => setDiag(String(e)));
  }, []);

  // when selecting a container, sync its running state from server view
  useEffect(() => {
    if (context.kind !== "container") return;
    const c = containers.find((x) => x.name === context.name);
    if (c) setRunning(!!c.running);
  }, [context, containers]);

  const dropdownOptions = useMemo(() => {
    const base = [{ value: "host" as const, label: "Host" }];
    const cs = containers.map((c) => ({ value: c.name, label: c.name }));
    return base.concat(cs as any);
  }, [containers]);

  async function handleSelectContext(v: string) {
    if (v === "host") {
      setContext({ kind: "host" });
      setVncVisible(false);
      setVnc(null);
      setRunning(false);
      setAutomationName("");
      setEditorVisible(false);
      setLoggerVisible(false);
      return;
    }
    setContext({ kind: "container", name: v });
  }

  async function ensureVncUrl(container: string) {
    const info = await apiGet<VncInfo>(`/containers/${encodeURIComponent(container)}/vnc_url`);
    setVnc(info);
  }

  async function startContainer(name: string) {
    await apiPost(`/containers/${encodeURIComponent(name)}/start`);
    await refresh();
  }

  async function stopContainer(name: string) {
    await apiPost(`/containers/${encodeURIComponent(name)}/stop`);
    await refresh();
  }

  async function stopAuto() {
    if (context.kind !== "container") return;
    await apiPost(`/containers/${encodeURIComponent(context.name)}/stop_auto`);
    await refresh();
  }

  // Toggle behavior (container dashboard)
  useEffect(() => {
    if (context.kind !== "container") return;

    // Running toggle changed -> call API
    // Note: this simplistic effect will call on mount; we prevent by checking server known state later if you want.
  }, [running, context]);

  async function onRunningToggle(v: boolean) {
    if (context.kind !== "container") return;
    setRunning(v);

    try {
      if (v) await startContainer(context.name);
      else await stopContainer(context.name);
    } catch (e: any) {
      setDiag(String(e));
      // revert
      setRunning(!v);
    }
  }

  async function onVncToggle(v: boolean) {
    setVncVisible(v);
    if (!v) return;
    if (context.kind !== "container") return;

    try {
      await ensureVncUrl(context.name);
    } catch (e: any) {
      setDiag(String(e));
    }
  }

  // Automation actions (stubs for now)
  async function createAutomation(payload: { name: string; description: string; yaml: string }) {
    // You’ll implement backend: POST /automations
    await apiPost("/automations", payload);
    await refresh();
    setAutomationName(payload.name);
  }

  async function createContainer(payload: { name: string; description: string }) {
    // You’ll implement backend: POST /containers
    await apiPost("/containers", payload);
    await refresh();
    setContext({ kind: "container", name: payload.name });
  }

  async function saveAutomation() {
    // stub: open a save modal later; for now just show diag
    setDiag("Save modal TODO (rename/overwrite confirmation).");
  }

  async function deleteAutomation() {
    // stub: open a delete modal later
    setDiag("Delete modal TODO (confirm).");
  }

  // Host dashboard “View” action
  async function hostViewVnc(name: string) {
    setContext({ kind: "container", name });
    setVncVisible(true);
    await ensureVncUrl(name);
  }

  return (
    <main className="mx-auto max-w-6xl p-6">
      {/* Header */}
      <div className="mb-4 flex items-center gap-3">
        <div className="h-8 w-8 rounded-xl border" />
        <div className="text-2xl font-bold">Automatr</div>
        <div className="ml-auto text-sm text-gray-500">
          {context.kind === "host" ? "Host Dashboard" : `Container Dashboard: ${context.name}`}
        </div>
      </div>

      {/* Top bar: context selector */}
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-2xl border p-4">
        <div className="w-72">
          <Select
            label="Container"
            value={context.kind === "host" ? ("host" as any) : (context.name as any)}
            onChange={handleSelectContext}
            options={dropdownOptions as any}
          />
        </div>

        <button className="rounded-lg border px-3 py-2" onClick={() => setCreateContainerOpen(true)}>
          New
        </button>

        <div className="ml-auto rounded-xl bg-gray-50 p-3 text-sm">
          <div className="font-semibold">Diagnostics</div>
          <div className="text-gray-700 whitespace-pre-wrap break-words">{diag || "—"}</div>
        </div>
      </div>

      {/* Body */}
      {context.kind === "host" ? (
        <HostDashboard containers={containers} onStart={startContainer} onStop={stopContainer} onViewVnc={hostViewVnc} />
      ) : (
        <ContainerDashboard
          containerName={selectedContainerName}
          vncVisible={vncVisible}
          setVncVisible={onVncToggle}
          running={running}
          setRunning={onRunningToggle}
          vnc={vnc}
          takeover={takeover}
          setTakeover={setTakeover}
          automations={automations}
          automationName={automationName}
          setAutomationName={setAutomationName}
          editorVisible={editorVisible}
          setEditorVisible={setEditorVisible}
          loggerVisible={loggerVisible}
          setLoggerVisible={setLoggerVisible}
          onStopAuto={stopAuto}
          onNewAutomation={() => setCreateAutomationOpen(true)}
          onSaveAutomation={saveAutomation}
          onDeleteAutomation={deleteAutomation}
        />
      )}

      {/* Modals */}
      <CreateContainerModal
        open={createContainerOpen}
        onClose={() => setCreateContainerOpen(false)}
        onCreate={createContainer}
      />

      <CreateAutomationModal
        open={createAutomationOpen}
        onClose={() => setCreateAutomationOpen(false)}
        onCreate={createAutomation}
      />
    </main>
  );
}

