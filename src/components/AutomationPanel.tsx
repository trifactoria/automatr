"use client";

import { useState } from "react";
import type { AutomationRow, AutomationGraph } from "@/lib/types";
import { EditorTab } from "./EditorTab";
import { LogsTab } from "./LogsTab";
import { XdotoolTab } from "./XdotoolTab";

export function AutomationPanel({
  automations,
  selectedAutomation,
  automationGraph,
  availableActions,
  actionsSchema,
  containerRunning,
  onSelectAutomation,
  onNewAutomation,
  onRun,
  onSave,
  onDelete,
  onUpdateGraph,
  saveError,
  saving,
}: {
  automations: AutomationRow[];
  selectedAutomation: string;
  automationGraph: AutomationGraph | null;
  availableActions: string[];
  actionsSchema: Record<string, { name: string; params: Array<{ key: string; type: string; default: string }> }>;
  containerRunning: boolean;
  onSelectAutomation: (name: string) => void;
  onNewAutomation: () => void;
  onRun: () => void;
  onSave: () => void;
  onDelete: () => void;
  onUpdateGraph: (graph: AutomationGraph) => void;
  saveError: string | null;
  saving: boolean;
}) {
  const [activeTab, setActiveTab] = useState<"editor" | "logs" | "xdotool">("editor");

  return (
    <div className="rounded-2xl border bg-white p-4">
      {/* Automation controls */}
      <div className="mb-4 flex flex-wrap items-center gap-3 border-b border-gray-200 pb-4">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700">Automation:</label>
          <select
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            value={selectedAutomation}
            onChange={(e) => onSelectAutomation(e.target.value)}
          >
            <option value="">Select automation...</option>
            {automations.map((a) => (
              <option key={a.name} value={a.name}>
                {a.name}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={onRun}
          disabled={!selectedAutomation || !containerRunning}
          className="rounded-lg border border-green-600 bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
        >
          Run
        </button>

        <button
          onClick={onNewAutomation}
          className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium hover:bg-gray-50"
        >
          New
        </button>

        <button
          onClick={onSave}
          disabled={!selectedAutomation || saving}
          className="rounded-lg border border-blue-600 bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save"}
        </button>

        <button
          onClick={onDelete}
          disabled={!selectedAutomation}
          className="rounded-lg border border-red-600 bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
        >
          Delete
        </button>
      </div>

      {/* Save error display */}
      {saveError && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">
          <div className="font-medium">Save failed:</div>
          <div className="mt-1 whitespace-pre-wrap">{saveError}</div>
        </div>
      )}

      {/* Tabs */}
      <div className="mb-4 flex gap-1 border-b border-gray-300">
        <button
          onClick={() => setActiveTab("editor")}
          className={`px-4 py-2 text-sm font-medium ${
            activeTab === "editor"
              ? "border-b-2 border-blue-600 text-blue-600"
              : "text-gray-600 hover:text-gray-900"
          }`}
        >
          Editor
        </button>
        <button
          onClick={() => setActiveTab("logs")}
          className={`px-4 py-2 text-sm font-medium ${
            activeTab === "logs" ? "border-b-2 border-blue-600 text-blue-600" : "text-gray-600 hover:text-gray-900"
          }`}
        >
          Logs
        </button>
        <button
          onClick={() => setActiveTab("xdotool")}
          className={`px-4 py-2 text-sm font-medium ${
            activeTab === "xdotool"
              ? "border-b-2 border-blue-600 text-blue-600"
              : "text-gray-600 hover:text-gray-900"
          }`}
        >
          Xdotool
        </button>
      </div>

      {/* Tab content */}
      <div className="min-h-[300px]">
        {activeTab === "editor" && (
          <>
            {!selectedAutomation ? (
              <div className="flex h-[300px] items-center justify-center text-gray-500">
                Select an automation to edit
              </div>
            ) : !automationGraph ? (
              <div className="flex h-[300px] items-center justify-center text-gray-500">Loading...</div>
            ) : (
              <EditorTab
                steps={automationGraph.steps}
                availableActions={availableActions}
                actionsSchema={actionsSchema}
                onUpdateSteps={(steps) => onUpdateGraph({ ...automationGraph, steps })}
              />
            )}
          </>
        )}

        {activeTab === "logs" && <LogsTab />}

        {activeTab === "xdotool" && <XdotoolTab />}
      </div>
    </div>
  );
}
