"use client";

import { useState } from "react";
import type { GraphVar } from "@/lib/types";

export function VarsCard({ vars, onUpdate }: { vars: GraphVar[]; onUpdate: (vars: GraphVar[]) => void }) {
  const [varsExpanded, setVarsExpanded] = useState(true);

  const handleAddVar = () => {
    const newVar: GraphVar = {
      key: "",
      type: "str",
      value: "",
      description: "",
    };
    onUpdate([...vars, newVar]);
    setVarsExpanded(true); // Auto-expand when adding
  };

  const handleUpdateVar = (index: number, updates: Partial<GraphVar>) => {
    const newVars = [...vars];
    newVars[index] = { ...newVars[index], ...updates };
    onUpdate(newVars);
  };

  const handleDeleteVar = (index: number) => {
    const newVars = vars.filter((_, i) => i !== index);
    onUpdate(newVars);
  };

  // Check for duplicate keys
  const getDuplicateKeys = () => {
    const keys = vars.map((v) => v.key).filter((k) => k.trim() !== "");
    const duplicates = keys.filter((k, idx) => keys.indexOf(k) !== idx);
    return new Set(duplicates);
  };

  const duplicateKeys = getDuplicateKeys();

  return (
    <div className="rounded-xl border border-gray-300 bg-white p-4 shadow-sm">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <button
          onClick={() => setVarsExpanded(!varsExpanded)}
          className="text-lg font-semibold text-gray-900 hover:text-gray-700"
        >
          Vars ({vars.length}) {varsExpanded ? "▼" : "▶"}
        </button>
        <button
          onClick={handleAddVar}
          className="rounded-lg border border-blue-600 bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          + Add Var
        </button>
      </div>

      {/* Vars list (collapsible) */}
      {varsExpanded && (
        <>
          {vars.length === 0 ? (
            <div className="rounded-lg border border-gray-200 bg-gray-50 p-6 text-center text-sm text-gray-500">
              No vars defined. Add one to get started.
            </div>
          ) : (
            <div className="space-y-2">
              {vars.map((varItem, idx) => {
                const isDuplicate = duplicateKeys.has(varItem.key) && varItem.key.trim() !== "";
                const isEmpty = varItem.key.trim() === "";

                return (
                  <div key={idx} className="rounded-lg border border-gray-300 bg-gray-50 p-2">
                    {/* Key, Type, Value row */}
                    <div className="mb-1.5 flex items-center gap-2">
                      <input
                        type="text"
                        value={varItem.key}
                        onChange={(e) => handleUpdateVar(idx, { key: e.target.value })}
                        placeholder="VAR_NAME"
                        className={`w-40 rounded border px-2 py-1 text-sm ${
                          isDuplicate
                            ? "border-red-400 bg-red-50"
                            : isEmpty
                              ? "border-yellow-400 bg-yellow-50"
                              : "border-gray-300 bg-white"
                        } focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200`}
                        title="Variable key"
                      />
                      <select
                        value={varItem.type}
                        onChange={(e) =>
                          handleUpdateVar(idx, { type: e.target.value as "str" | "int" | "float" | "bool" })
                        }
                        className="w-20 rounded border border-gray-300 bg-white px-2 py-1 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                        title="Variable type"
                      >
                        <option value="str">str</option>
                        <option value="int">int</option>
                        <option value="float">float</option>
                        <option value="bool">bool</option>
                      </select>
                      <input
                        type="text"
                        value={varItem.value}
                        onChange={(e) => handleUpdateVar(idx, { value: e.target.value })}
                        placeholder="default value"
                        className="flex-1 rounded border border-gray-300 bg-white px-2 py-1 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                        title="Variable value"
                      />
                      <button
                        onClick={() => handleDeleteVar(idx)}
                        className="flex-shrink-0 rounded border border-red-600 bg-red-600 px-2 py-1 text-xs font-medium text-white hover:bg-red-700"
                        title="Delete var"
                      >
                        Delete
                      </button>
                    </div>

                    {/* Description row */}
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={varItem.description || ""}
                        onChange={(e) => handleUpdateVar(idx, { description: e.target.value })}
                        placeholder="description (optional)"
                        className="flex-1 rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-600 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                        title="Variable description"
                      />
                    </div>

                    {/* Validation warnings */}
                    {(isEmpty || isDuplicate) && (
                      <div className="mt-1 text-xs">
                        {isEmpty && <div className="text-yellow-700">⚠ Key should not be empty</div>}
                        {isDuplicate && <div className="text-red-700">⚠ Duplicate key found</div>}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
