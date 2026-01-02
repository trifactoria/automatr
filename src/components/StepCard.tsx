"use client";

import { useState } from "react";
import type { GraphStep, StepParam } from "@/lib/types";
import { Toggle } from "./Toggle";

export function StepCard({
  step,
  stepIndex,
  availableActions,
  actionsSchema,
  onUpdate,
  onDelete,
  onEditConditions,
}: {
  step: GraphStep;
  stepIndex: number;
  availableActions: string[];
  actionsSchema: Record<string, { name: string; params: Array<{ key: string; type: string; default: string }> }>;
  onUpdate: (updates: Partial<GraphStep>) => void;
  onDelete: () => void;
  onEditConditions: () => void;
}) {
  const [paramsExpanded, setParamsExpanded] = useState(false);

  const handleParamChange = (paramIndex: number, key: string, value: any) => {
    const newParams = [...step.params];
    newParams[paramIndex] = { ...newParams[paramIndex], [key]: value };
    onUpdate({ params: newParams });
  };

  const handleActionChange = (newAction: string) => {
    // Get schema for the new action
    const schema = actionsSchema[newAction];

    if (schema && schema.params) {
      // Auto-populate params from schema
      const newParams: StepParam[] = schema.params.map((paramDef) => {
        // Try to preserve existing value if param key matches
        const existingParam = step.params.find((p) => p.key === paramDef.key);
        return {
          key: paramDef.key,
          type: paramDef.type as "str" | "int" | "float" | "bool",
          value: existingParam?.value ?? paramDef.default,
        };
      });
      onUpdate({ action: newAction, params: newParams });
      setParamsExpanded(true); // Expand to show auto-populated params
    } else {
      // No schema available, reset to empty
      onUpdate({ action: newAction, params: [] });
    }
  };

  const handleDeleteParam = (paramIndex: number) => {
    const newParams = step.params.filter((_, i) => i !== paramIndex);
    onUpdate({ params: newParams });
  };

  return (
    <div className="rounded-xl border border-gray-300 bg-white p-4 shadow-sm">
      {/* Step header */}
      <div className="mb-3 flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-800">
          {stepIndex + 1}
        </div>
        <input
          type="text"
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
          placeholder="Step label"
          value={step.label}
          onChange={(e) => onUpdate({ label: e.target.value })}
        />
        <Toggle label="Enabled" checked={step.enabled === 1} onChange={(v) => onUpdate({ enabled: v ? 1 : 0 })} />
        <button
          onClick={onDelete}
          className="rounded-lg border border-red-600 bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
        >
          Delete
        </button>
      </div>

      {/* Action dropdown */}
      <div className="mb-3 flex items-center gap-3">
        <label className="text-sm font-medium text-gray-700">Action:</label>
        <select
          className="flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
          value={step.action}
          onChange={(e) => handleActionChange(e.target.value)}
        >
          {availableActions.map((action) => (
            <option key={action} value={action}>
              {action}
            </option>
          ))}
        </select>
      </div>

      {/* Params section */}
      <div className="mb-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
        <div className="mb-2 flex items-center justify-between">
          <button
            onClick={() => setParamsExpanded(!paramsExpanded)}
            className="text-sm font-medium text-gray-700 hover:text-gray-900"
          >
            Parameters ({step.params.length}) {paramsExpanded ? "▼" : "▶"}
          </button>
          {!actionsSchema[step.action] && (
            <div className="text-xs text-gray-500 italic">Schema not loaded</div>
          )}
        </div>

        {paramsExpanded && (
          <div className="mt-2 space-y-2">
            {step.params.length === 0 ? (
              <div className="text-sm text-gray-500">
                {actionsSchema[step.action] ? "No parameters defined for this action" : "No schema available"}
              </div>
            ) : (
              step.params.map((param, idx) => (
                <div key={idx} className="flex items-center gap-2 rounded border border-gray-300 bg-white p-2">
                  <input
                    type="text"
                    className="w-32 rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                    placeholder="Key"
                    value={param.key}
                    readOnly={!!actionsSchema[step.action]}
                    onChange={(e) => handleParamChange(idx, "key", e.target.value)}
                    title={actionsSchema[step.action] ? "Key is defined by action schema" : "Parameter key"}
                  />
                  <select
                    className="w-24 rounded border border-gray-300 bg-white px-2 py-1 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                    value={param.type}
                    disabled={!!actionsSchema[step.action]}
                    onChange={(e) => handleParamChange(idx, "type", e.target.value)}
                    title={actionsSchema[step.action] ? "Type is defined by action schema" : "Parameter type"}
                  >
                    <option value="str">str</option>
                    <option value="int">int</option>
                    <option value="float">float</option>
                    <option value="bool">bool</option>
                  </select>
                  <input
                    type="text"
                    className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                    placeholder="Value"
                    value={param.value}
                    onChange={(e) => handleParamChange(idx, "value", e.target.value)}
                  />
                  {!actionsSchema[step.action] && (
                    <button
                      onClick={() => handleDeleteParam(idx)}
                      className="rounded border border-red-600 bg-red-600 px-2 py-1 text-xs font-medium text-white hover:bg-red-700"
                    >
                      Delete
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Conditions button */}
      <div className="flex items-center gap-2">
        <button
          onClick={onEditConditions}
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-gray-50"
        >
          Conditions ({step.clauses.length})...
        </button>
        {step.note && <div className="text-xs text-gray-500">Note: {step.note}</div>}
      </div>
    </div>
  );
}
