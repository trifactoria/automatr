"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import * as api from "@/lib/api";
import type { ContainerSummary, ContainerDetail, AutomationSummary, AutomationGraph, ActionDef } from "@/lib/types";

import { HostDashboard } from "@/components/HostDashboard";
import { ContainerBar } from "@/components/ContainerBar";
import { VncPanel } from "@/components/VncPanel";
import { AutomationPanel } from "@/components/AutomationPanel";
import { Toggle } from "@/components/Toggle";
import { CreateContainerModal } from "@/components/modals/CreateContainerModal";
import { CreateAutomationModal } from "@/components/modals/CreateAutomationModal";

type ViewMode = "host" | "container";

export default function Page() {
  // View mode
  const [viewMode, setViewMode] = useState<ViewMode>("host");

  // Data
  const [containers, setContainers] = useState<ContainerSummary[]>([]);
  const [automations, setAutomations] = useState<AutomationSummary[]>([]);
  const [availableActions, setAvailableActions] = useState<string[]>(["sleep"]);
  const [actionsSchema, setActionsSchema] = useState<Record<string, ActionDef>>({});

  // Selected container
  const [selectedContainer, setSelectedContainer] = useState<string>("");
  const [containerDetail, setContainerDetail] = useState<ContainerDetail | null>(null);

  // VNC visibility and takeover (UI-only toggles)
  const [vncVisible, setVncVisible] = useState(false);
  const [takeover, setTakeover] = useState(false);

  // Selected automation
  const [selectedAutomation, setSelectedAutomation] = useState<string>("");
  const [automationGraph, setAutomationGraph] = useState<AutomationGraph | null>(null);

  // UI state
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Modals
  const [createContainerOpen, setCreateContainerOpen] = useState(false);
  const [createAutomationOpen, setCreateAutomationOpen] = useState(false);

  // Fetch containers and automations on mount
  useEffect(() => {
    refreshData();
  }, []);

  // Fetch container detail when selected container changes
  useEffect(() => {
    if (selectedContainer) {
      fetchContainerDetail();
    } else {
      setContainerDetail(null);
    }
  }, [selectedContainer]);

  // Fetch automation graph when selected automation changes
  useEffect(() => {
    if (selectedAutomation) {
      fetchAutomationGraph();
    } else {
      setAutomationGraph(null);
    }
  }, [selectedAutomation]);

  async function refreshData() {
    await Promise.all([refreshContainers(), refreshAutomations(), fetchAvailableActions()]);
  }

  async function refreshContainers() {
    try {
      const cs = await api.getContainers();
      setContainers(cs);
    } catch (e) {
      console.error("Failed to fetch containers:", e);
    }
  }

  async function refreshAutomations() {
    try {
      const as = await api.getAutomations();
      setAutomations(as);
    } catch (e) {
      console.error("Failed to fetch automations:", e);
    }
  }

  async function fetchAvailableActions() {
    try {
      const [check, schema] = await Promise.all([
        api.getActionsCheck(),
        api.getActionsSchema().catch(() => ({})), // Fallback to empty if schema endpoint doesn't exist yet
      ]);
      // Use wrapper_actions (public actions only)
      setAvailableActions(check.wrapper_actions.length > 0 ? check.wrapper_actions : ["sleep"]);
      setActionsSchema(schema);
    } catch (e) {
      console.error("Failed to fetch actions:", e);
    }
  }

  async function fetchContainerDetail() {
    if (!selectedContainer) return;
    try {
      const detail = await api.getContainerDetail(selectedContainer);
      setContainerDetail(detail);
    } catch (e) {
      console.error("Failed to fetch container detail:", e);
    }
  }

  async function fetchAutomationGraph() {
    if (!selectedAutomation) return;
    try {
      const graph = await api.getAutomationGraph(selectedAutomation);
      setAutomationGraph(graph);
    } catch (e) {
      console.error("Failed to fetch automation graph:", e);
      setAutomationGraph(null);
    }
  }

  // Container actions
  async function handleSelectContainer(name: string) {
    setSelectedContainer(name);
    setViewMode("container");
    setVncVisible(false);
  }

  async function handleStartContainer(name?: string) {
    const target = name || selectedContainer;
    if (!target) return;
    try {
      await api.startContainer(target);
      await refreshContainers();
      if (target === selectedContainer) {
        await fetchContainerDetail();
      }
    } catch (e) {
      console.error("Failed to start container:", e);
    }
  }

  async function handleStopContainer(name?: string) {
    const target = name || selectedContainer;
    if (!target) return;
    try {
      await api.stopContainer(target);
      await refreshContainers();
      if (target === selectedContainer) {
        await fetchContainerDetail();
      }
    } catch (e) {
      console.error("Failed to stop container:", e);
    }
  }

  async function handleRestartContainer() {
    if (!selectedContainer) return;
    try {
      await api.restartContainer(selectedContainer);
      await refreshContainers();
      await fetchContainerDetail();
    } catch (e) {
      console.error("Failed to restart container:", e);
    }
  }

  async function handleStopAuto() {
    if (!selectedContainer) return;
    try {
      await api.stopAuto(selectedContainer);
      await refreshContainers();
      await fetchContainerDetail();
    } catch (e) {
      console.error("Failed to stop auto:", e);
    }
  }

  async function handleClearStop() {
    if (!selectedContainer) return;
    try {
      await api.clearStop(selectedContainer);
      await refreshContainers();
      await fetchContainerDetail();
    } catch (e) {
      console.error("Failed to clear stop:", e);
    }
  }

  async function handleCreateContainer(payload: { name: string; description: string }) {
    try {
      await api.createContainer(payload);
      await refreshContainers();
      setSelectedContainer(payload.name);
      setViewMode("container");
    } catch (e) {
      console.error("Failed to create container:", e);
    }
  }

  // Automation actions
  async function handleRunAutomation() {
    if (!selectedContainer || !selectedAutomation) return;
    try {
      await api.runAutomation(selectedContainer, selectedAutomation);
      await refreshContainers();
      await fetchContainerDetail();
    } catch (e) {
      console.error("Failed to run automation:", e);
    }
  }

  async function handleSaveAutomation() {
    if (!selectedContainer || !selectedAutomation || !automationGraph) return;
    setSaving(true);
    setSaveError(null);
    try {
      // Save payload must be flat: {name, description, container, vars, steps}
      await api.saveAutomation({
        name: automationGraph.name,
        description: automationGraph.description,
        container: selectedContainer,
        vars: automationGraph.vars,
        steps: automationGraph.steps,
      });
      await refreshAutomations();
      await fetchAutomationGraph();
    } catch (e: any) {
      console.error("Failed to save automation:", e);
      setSaveError(e.message || String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteAutomation() {
    if (!selectedAutomation) return;
    if (!confirm(`Are you sure you want to delete automation "${selectedAutomation}"?`)) return;
    try {
      await api.deleteAutomation(selectedAutomation);
      await refreshAutomations();
      setSelectedAutomation("");
      setAutomationGraph(null);
    } catch (e) {
      console.error("Failed to delete automation:", e);
    }
  }

  function handleCreateAutomation(payload: { name: string; description: string }) {
    // Create empty automation graph in memory (don't call backend until user saves)
    const newGraph: AutomationGraph = {
      name: payload.name,
      description: payload.description,
      vars: [],
      steps: [],
    };

    // Set it as the selected automation and load into editor
    setSelectedAutomation(payload.name);
    setAutomationGraph(newGraph);

    // Add to local automations list (will sync with backend on save)
    setAutomations((prev) => [
      ...prev,
      { name: payload.name, description: payload.description },
    ]);
  }

  return (
    <main className="mx-auto min-h-screen max-w-[1400px] bg-gray-100 p-4">
      {/* Header */}
      <div className="mb-4 flex items-center gap-3 rounded-2xl border bg-white p-4 shadow-sm">
        <Image src="/logo.png" alt="Automatr logo" width={32} height={32} className="rounded-xl border" />
        <div className="text-2xl font-bold text-gray-900">Automatr</div>
        <div className="ml-auto text-sm text-gray-600">
          {viewMode === "host" ? "Host Dashboard" : `Container: ${selectedContainer}`}
        </div>
        {viewMode === "container" && (
          <button
            onClick={() => {
              setViewMode("host");
              setSelectedContainer("");
              setVncVisible(false);
            }}
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium hover:bg-gray-50"
          >
            ← Back to Host
          </button>
        )}
      </div>

      {/* Host View */}
      {viewMode === "host" && (
        <>
          <div className="mb-4 flex items-center gap-3 rounded-2xl border bg-white p-4">
            <button
              className="rounded-lg border border-blue-600 bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              onClick={() => setCreateContainerOpen(true)}
            >
              New Container
            </button>
          </div>
          <HostDashboard
            containers={containers}
            onStart={handleStartContainer}
            onStop={handleStopContainer}
            onRestart={async (name) => {
              setSelectedContainer(name);
              await handleRestartContainer();
            }}
            onViewVnc={handleSelectContainer}
          />
        </>
      )}

      {/* Container View */}
      {viewMode === "container" && selectedContainer && (
        <>
          {/* Container selector bar */}
          <div className="mb-4">
            <ContainerBar
              containers={containers}
              selectedContainer={selectedContainer}
              containerDetail={containerDetail}
              onSelectContainer={handleSelectContainer}
              onNewContainer={() => setCreateContainerOpen(true)}
              onStart={() => handleStartContainer()}
              onStop={() => handleStopContainer()}
              onRestart={handleRestartContainer}
              onStopAuto={handleStopAuto}
              onClearStop={handleClearStop}
            />
          </div>

          {/* VNC panel with UI-only show/hide + takeover toggles */}
          <div className="mb-4 rounded-2xl border bg-white p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-lg font-semibold text-gray-900">VNC Display</div>
              <div className="flex items-center gap-4">
                <Toggle label="Show VNC" checked={vncVisible} onChange={setVncVisible} />
                {vncVisible && (
                  <Toggle label="Takeover" checked={takeover} onChange={setTakeover} />
                )}
              </div>
            </div>
            {vncVisible && (
              <VncPanel
                vncUrl={containerDetail?.vnc_url}
                running={containerDetail?.running ?? false}
                takeover={takeover}
                onStart={() => handleStartContainer()}
              />
            )}
          </div>

          {/* Automation panel */}
          <div>
            <AutomationPanel
              automations={automations}
              selectedAutomation={selectedAutomation}
              automationGraph={automationGraph}
              availableActions={availableActions}
              actionsSchema={actionsSchema}
              containerName={selectedContainer}
              containerRunning={containerDetail?.running ?? false}
              onSelectAutomation={setSelectedAutomation}
              onNewAutomation={() => setCreateAutomationOpen(true)}
              onRun={handleRunAutomation}
              onSave={handleSaveAutomation}
              onDelete={handleDeleteAutomation}
              onUpdateGraph={setAutomationGraph}
              saveError={saveError}
              saving={saving}
            />
          </div>
        </>
      )}

      {/* Modals */}
      <CreateContainerModal
        open={createContainerOpen}
        onClose={() => setCreateContainerOpen(false)}
        onCreate={handleCreateContainer}
      />

      <CreateAutomationModal
        open={createAutomationOpen}
        onClose={() => setCreateAutomationOpen(false)}
        onCreate={handleCreateAutomation}
      />
    </main>
  );
}
