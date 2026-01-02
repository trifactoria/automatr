"use client";

import type { GraphVar } from "@/lib/types";

export function VarsCard({ vars, onUpdate }: { vars: GraphVar[]; onUpdate: (vars: GraphVar[]) => void }) {
  const handleAddVar = () => {
    const newVar: GraphVar = {
      key: "",
      type: "str",
      value: "",
      description: "",
    };
    onUpdate([...vars, newVar]);
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
        <h3 className="text-lg font-semibold text-gray-900">Vars</h3>
        <button
          onClick={handleAddVar}
          className="rounded-lg border border-blue-600 bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          + Add Var
        </button>
      </div>

      {/* Vars list */}
      {vars.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-6 text-center text-sm text-gray-500">
          No vars defined. Add one to get started.
        </div>
      ) : (
        <div className="space-y-3">
          {vars.map((varItem, idx) => {
            const isDuplicate = duplicateKeys.has(varItem.key) && varItem.key.trim() !== "";
            const isEmpty = varItem.key.trim() === "";

            return (
              <div key={idx} className="rounded-lg border border-gray-300 bg-gray-50 p-3">
                <div className="flex items-start gap-3">
                  {/* Var number badge */}
                  <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-purple-100 text-xs font-bold text-purple-800">
                    {idx + 1}
                  </div>

                  {/* Var fields */}
                  <div className="flex-1 space-y-2">
                    {/* Key and Type row */}
                    <div className="flex gap-2">
                      <div className="flex-1">
                        <label className="mb-1 block text-xs font-medium text-gray-700">Key</label>
                        <input
                          type="text"
                          value={varItem.key}
                          onChange={(e) => handleUpdateVar(idx, { key: e.target.value })}
                          placeholder="VAR_NAME"
                          className={`w-full rounded border px-2 py-1.5 text-sm ${
                            isDuplicate
                              ? "border-red-400 bg-red-50"
                              : isEmpty
                                ? "border-yellow-400 bg-yellow-50"
                                : "border-gray-300"
                          } focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200`}
                        />
                        {isEmpty && (
                          <div className="mt-0.5 text-xs text-yellow-700">Key should not be empty</div>
                        )}
                        {isDuplicate && (
                          <div className="mt-0.5 text-xs text-red-700">Duplicate key found</div>
                        )}
                      </div>

                      <div className="w-24">
                        <label className="mb-1 block text-xs font-medium text-gray-700">Type</label>
                        <select
                          value={varItem.type}
                          onChange={(e) =>
                            handleUpdateVar(idx, { type: e.target.value as "str" | "int" | "float" | "bool" })
                          }
                          className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                        >
                          <option value="str">str</option>
                          <option value="int">int</option>
                          <option value="float">float</option>
                          <option value="bool">bool</option>
                        </select>
                      </div>
                    </div>

                    {/* Value row */}
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-700">Value</label>
                      <input
                        type="text"
                        value={varItem.value}
                        onChange={(e) => handleUpdateVar(idx, { value: e.target.value })}
                        placeholder="default value"
                        className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                      />
                    </div>

                    {/* Description row */}
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-600">Description (optional)</label>
                      <input
                        type="text"
                        value={varItem.description || ""}
                        onChange={(e) => handleUpdateVar(idx, { description: e.target.value })}
                        placeholder="what this var is for"
                        className="w-full rounded border border-gray-300 px-2 py-1.5 text-xs text-gray-600 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                      />
                    </div>
                  </div>

                  {/* Delete button */}
                  <button
                    onClick={() => handleDeleteVar(idx)}
                    className="flex-shrink-0 rounded border border-red-400 bg-white px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50"
                    title="Delete var"
                  >
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
