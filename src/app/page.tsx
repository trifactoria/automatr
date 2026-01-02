"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import type { ContainerRow, ContainerDetail, AutomationRow, AutomationGraph, ActionsCheck } from "@/lib/types";

import { ContainerBar } from "@/components/ContainerBar";
import { VncPanel } from "@/components/VncPanel";
import { AutomationPanel } from "@/components/AutomationPanel";
import { CreateContainerModal } from "@/components/modals/CreateContainerModal";
import { CreateAutomationModal } from "@/components/modals/CreateAutomationModal";

export default function Page() {
  // Data
  const [containers, setContainers] = useState<ContainerRow[]>([]);
  const [automations, setAutomations] = useState<AutomationRow[]>([]);
  const [availableActions, setAvailableActions] = useState<string[]>(["sleep"]);

  // Selected container
  const [selectedContainer, setSelectedContainer] = useState<string>("");
  const [containerDetail, setContainerDetail] = useState<ContainerDetail | null>(null);

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
    refreshContainers();
    refreshAutomations();
    fetchAvailableActions();
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

  async function refreshContainers() {
    try {
      const cs = await apiGet<ContainerRow[]>("/containers");
      setContainers(cs);
    } catch (e) {
      console.error("Failed to fetch containers:", e);
    }
  }

  async function refreshAutomations() {
    try {
      const as = await apiGet<AutomationRow[]>("/automations");
      setAutomations(as);
    } catch (e) {
      console.error("Failed to fetch automations:", e);
    }
  }

  async function fetchAvailableActions() {
    try {
      const check = await apiGet<ActionsCheck>("/actions/check");
      const actions = [...check.wrapper_actions, ...check.db_actions];
      setAvailableActions(actions.length > 0 ? actions : ["sleep"]);
    } catch (e) {
      console.error("Failed to fetch actions:", e);
    }
  }

  async function fetchContainerDetail() {
    if (!selectedContainer) return;
    try {
      const detail = await apiGet<ContainerDetail>(`/containers/${encodeURIComponent(selectedContainer)}`);
      setContainerDetail(detail);
    } catch (e) {
      console.error("Failed to fetch container detail:", e);
    }
  }

  async function fetchAutomationGraph() {
    if (!selectedAutomation) return;
    try {
      const graph = await apiGet<AutomationGraph>(`/automations/${encodeURIComponent(selectedAutomation)}/graph`);
      setAutomationGraph(graph);
    } catch (e) {
      console.error("Failed to fetch automation graph:", e);
      setAutomationGraph(null);
    }
  }

  // Container actions
  async function handleStartContainer() {
    if (!selectedContainer) return;
    try {
      await apiPost(`/containers/${encodeURIComponent(selectedContainer)}/start`);
      await refreshContainers();
      await fetchContainerDetail();
    } catch (e) {
      console.error("Failed to start container:", e);
    }
  }

  async function handleStopContainer() {
    if (!selectedContainer) return;
    try {
      await apiPost(`/containers/${encodeURIComponent(selectedContainer)}/stop`);
      await refreshContainers();
      await fetchContainerDetail();
    } catch (e) {
      console.error("Failed to stop container:", e);
    }
  }

  async function handleRestartContainer() {
    if (!selectedContainer) return;
    try {
      await apiPost(`/containers/${encodeURIComponent(selectedContainer)}/restart`);
      await refreshContainers();
      await fetchContainerDetail();
    } catch (e) {
      console.error("Failed to restart container:", e);
    }
  }

  async function handleStopAuto() {
    if (!selectedContainer) return;
    try {
      await apiPost(`/containers/${encodeURIComponent(selectedContainer)}/stop_auto`);
      await refreshContainers();
      await fetchContainerDetail();
    } catch (e) {
      console.error("Failed to stop auto:", e);
    }
  }

  async function handleClearStop() {
    if (!selectedContainer) return;
    try {
      await apiPost(`/containers/${encodeURIComponent(selectedContainer)}/clear_stop`);
      await refreshContainers();
      await fetchContainerDetail();
    } catch (e) {
      console.error("Failed to clear stop:", e);
    }
  }

  async function handleCreateContainer(payload: { name: string; description: string }) {
    try {
      await apiPost("/containers", payload);
      await refreshContainers();
      setSelectedContainer(payload.name);
    } catch (e) {
      console.error("Failed to create container:", e);
    }
  }

  // Automation actions
  async function handleRunAutomation() {
    if (!selectedContainer || !selectedAutomation) return;
    try {
      await apiPost(`/containers/${encodeURIComponent(selectedContainer)}/run`, {
        automation: selectedAutomation,
      });
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
      await apiPost("/automations/save", {
        automation: automationGraph,
        container: selectedContainer,
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
      await apiDelete(`/automations/${encodeURIComponent(selectedAutomation)}`);
      await refreshAutomations();
      setSelectedAutomation("");
      setAutomationGraph(null);
    } catch (e) {
      console.error("Failed to delete automation:", e);
    }
  }

  async function handleCreateAutomation(payload: { name: string; description: string; yaml: string }) {
    try {
      await apiPost("/automations", payload);
      await refreshAutomations();
      setSelectedAutomation(payload.name);
    } catch (e) {
      console.error("Failed to create automation:", e);
    }
  }

  return (
    <main className="mx-auto min-h-screen max-w-[1400px] bg-gray-100 p-4">
      {/* Header */}
      <div className="mb-4 flex items-center gap-3 rounded-2xl border bg-white p-4 shadow-sm">
        <Image src="/logo.png" alt="Automatr logo" width={32} height={32} className="rounded-xl border" />
        <div className="text-2xl font-bold text-gray-900">Automatr</div>
        <div className="ml-auto text-sm text-gray-600">
          {selectedContainer ? `Container: ${selectedContainer}` : "Host Dashboard"}
        </div>
      </div>

      {/* Container selector bar */}
      <div className="mb-4">
        <ContainerBar
          containers={containers}
          selectedContainer={selectedContainer}
          containerDetail={containerDetail}
          onSelectContainer={setSelectedContainer}
          onNewContainer={() => setCreateContainerOpen(true)}
          onStart={handleStartContainer}
          onStop={handleStopContainer}
          onRestart={handleRestartContainer}
          onStopAuto={handleStopAuto}
          onClearStop={handleClearStop}
        />
      </div>

      {/* VNC panel (always present when container selected) */}
      {selectedContainer && (
        <div className="mb-4">
          <VncPanel
            vncUrl={containerDetail?.vnc_url}
            running={containerDetail?.running ?? false}
            onStart={handleStartContainer}
          />
        </div>
      )}

      {/* Automation panel (always present when container selected) */}
      {selectedContainer && (
        <div>
          <AutomationPanel
            automations={automations}
            selectedAutomation={selectedAutomation}
            automationGraph={automationGraph}
            availableActions={availableActions}
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
      )}

      {/* No container selected state */}
      {!selectedContainer && (
        <div className="flex h-[400px] items-center justify-center rounded-2xl border bg-white text-gray-500">
          <div className="text-center">
            <div className="mb-2 text-lg font-medium">No container selected</div>
            <div className="text-sm">Select a container or create a new one to get started</div>
          </div>
        </div>
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
