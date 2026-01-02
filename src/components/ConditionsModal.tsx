"use client";

import * as React from "react";
import type { StepClause } from "@/lib/types";
import { Modal } from "./Modal";

export function ConditionsModal({
  open,
  clauses,
  onClose,
  onSave,
}: {
  open: boolean;
  clauses: StepClause[];
  onClose: () => void;
  onSave: (clauses: StepClause[]) => void;
}) {
  const [localClauses, setLocalClauses] = React.useState<StepClause[]>(clauses);

  React.useEffect(() => {
    setLocalClauses(clauses);
  }, [clauses, open]);

  const handleAddClause = () => {
    const newClause: StepClause = {
      head: localClauses.length === 0 ? "if" : "elif",
      action: "goto",
      action_value: "",
    };
    setLocalClauses([...localClauses, newClause]);
  };

  const handleUpdateClause = (index: number, updates: Partial<StepClause>) => {
    const newClauses = [...localClauses];
    newClauses[index] = { ...newClauses[index], ...updates };
    setLocalClauses(newClauses);
  };

  const handleDeleteClause = (index: number) => {
    setLocalClauses(localClauses.filter((_, i) => i !== index));
  };

  const handleMoveUp = (index: number) => {
    if (index === 0) return;
    const newClauses = [...localClauses];
    [newClauses[index - 1], newClauses[index]] = [newClauses[index], newClauses[index - 1]];
    setLocalClauses(newClauses);
  };

  const handleMoveDown = (index: number) => {
    if (index === localClauses.length - 1) return;
    const newClauses = [...localClauses];
    [newClauses[index], newClauses[index + 1]] = [newClauses[index + 1], newClauses[index]];
    setLocalClauses(newClauses);
  };

  // Validate clause ordering
  const validateClauseOrder = (): { valid: boolean; error?: string } => {
    if (localClauses.length === 0) return { valid: true };

    // Must start with "if" if any conditionals exist
    if (localClauses[0].head !== "if") {
      return { valid: false, error: "First clause must be 'if'" };
    }

    let sawElse = false;
    for (let i = 0; i < localClauses.length; i++) {
      const head = localClauses[i].head;

      // No clauses allowed after "else"
      if (sawElse) {
        return { valid: false, error: "'else' must be the last clause" };
      }

      // "elif" cannot appear before "if"
      if (head === "elif" && i === 0) {
        return { valid: false, error: "'elif' cannot be first" };
      }

      // "else" can only appear once and must be last
      if (head === "else") {
        sawElse = true;
      }
    }

    return { valid: true };
  };

  const autoFixOrder = () => {
    // Sort clauses: if first, then elif, then else last
    const sorted = [...localClauses].sort((a, b) => {
      const order = { if: 0, elif: 1, else: 2 };
      return order[a.head] - order[b.head];
    });
    setLocalClauses(sorted);
  };

  const validation = validateClauseOrder();

  const handleSave = () => {
    if (!validation.valid) return; // Block save if invalid
    onSave(localClauses);
    onClose();
  };

  return (
    <Modal open={open} onClose={onClose} title="Edit Conditions">
      <div className="space-y-4">
        {/* Clauses list */}
        <div className="max-h-[500px] space-y-3 overflow-y-auto">
          {localClauses.length === 0 ? (
            <div className="text-sm text-gray-500">No conditions defined</div>
          ) : (
            localClauses.map((clause, idx) => (
              <div key={idx} className="rounded-lg border border-gray-300 bg-gray-50 p-3">
                {/* Clause header */}
                <div className="mb-2 flex items-center justify-between">
                  <select
                    className="rounded border border-gray-300 bg-white px-2 py-1 text-sm font-medium focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                    value={clause.head}
                    onChange={(e) => handleUpdateClause(idx, { head: e.target.value as any })}
                  >
                    <option value="if">if</option>
                    <option value="elif">elif</option>
                    <option value="else">else</option>
                  </select>

                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => handleMoveUp(idx)}
                      disabled={idx === 0}
                      className="rounded border border-gray-300 bg-white px-2 py-1 text-xs font-medium disabled:opacity-50 hover:bg-gray-50"
                    >
                      ↑
                    </button>
                    <button
                      onClick={() => handleMoveDown(idx)}
                      disabled={idx === localClauses.length - 1}
                      className="rounded border border-gray-300 bg-white px-2 py-1 text-xs font-medium disabled:opacity-50 hover:bg-gray-50"
                    >
                      ↓
                    </button>
                    <button
                      onClick={() => handleDeleteClause(idx)}
                      className="rounded border border-red-600 bg-red-600 px-2 py-1 text-xs font-medium text-white hover:bg-red-700"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                {/* Condition expression (only for if/elif) */}
                {clause.head !== "else" && (
                  <div className="mb-2 grid grid-cols-3 gap-2 rounded border border-gray-300 bg-white p-2">
                    {/* LHS */}
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-gray-600">LHS</label>
                      <select
                        className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                        value={clause.lhs_kind ?? ""}
                        onChange={(e) => handleUpdateClause(idx, { lhs_kind: (e.target.value || null) as any })}
                      >
                        <option value="">—</option>
                        <option value="buffer">buffer</option>
                        <option value="var">var</option>
                        <option value="literal">literal</option>
                      </select>
                      <select
                        className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                        value={clause.lhs_type ?? ""}
                        onChange={(e) => handleUpdateClause(idx, { lhs_type: (e.target.value || null) as any })}
                      >
                        <option value="">—</option>
                        <option value="str">str</option>
                        <option value="int">int</option>
                        <option value="float">float</option>
                        <option value="bool">bool</option>
                      </select>
                      <input
                        type="text"
                        className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                        placeholder="value"
                        value={clause.lhs_value ?? ""}
                        onChange={(e) => handleUpdateClause(idx, { lhs_value: e.target.value || null })}
                      />
                    </div>

                    {/* Operator */}
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-gray-600">Operator</label>
                      <select
                        className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                        value={clause.op ?? ""}
                        onChange={(e) => handleUpdateClause(idx, { op: e.target.value || null })}
                      >
                        <option value="">—</option>
                        <option value="==">==</option>
                        <option value="!=">!=</option>
                        <option value="<">&lt;</option>
                        <option value=">">&gt;</option>
                        <option value="<=">≤</option>
                        <option value=">=">≥</option>
                        <option value="in">in</option>
                        <option value="not in">not in</option>
                      </select>
                    </div>

                    {/* RHS */}
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-gray-600">RHS</label>
                      <select
                        className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                        value={clause.rhs_kind ?? ""}
                        onChange={(e) => handleUpdateClause(idx, { rhs_kind: (e.target.value || null) as any })}
                      >
                        <option value="">—</option>
                        <option value="buffer">buffer</option>
                        <option value="var">var</option>
                        <option value="literal">literal</option>
                      </select>
                      <select
                        className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                        value={clause.rhs_type ?? ""}
                        onChange={(e) => handleUpdateClause(idx, { rhs_type: (e.target.value || null) as any })}
                      >
                        <option value="">—</option>
                        <option value="str">str</option>
                        <option value="int">int</option>
                        <option value="float">float</option>
                        <option value="bool">bool</option>
                      </select>
                      <input
                        type="text"
                        className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                        placeholder="value"
                        value={clause.rhs_value ?? ""}
                        onChange={(e) => handleUpdateClause(idx, { rhs_value: e.target.value || null })}
                      />
                    </div>
                  </div>
                )}

                {/* Action */}
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-gray-600">Action</label>
                    <select
                      className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                      value={clause.action}
                      onChange={(e) => handleUpdateClause(idx, { action: e.target.value as any })}
                    >
                      <option value="goto">goto</option>
                      <option value="continue">continue</option>
                      <option value="stop">stop</option>
                      <option value="notify">notify</option>
                    </select>
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-medium text-gray-600">
                      {clause.action === "stop" ? "Stop Tag" : "Action Value"}
                    </label>
                    {clause.action === "stop" ? (
                      <select
                        className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                        value={clause.stop_tag ?? ""}
                        onChange={(e) => handleUpdateClause(idx, { stop_tag: (e.target.value || null) as any })}
                      >
                        <option value="">—</option>
                        <option value="SUCCESS">SUCCESS</option>
                        <option value="FAILURE">FAILURE</option>
                        <option value="BREAK">BREAK</option>
                      </select>
                    ) : (
                      <input
                        type="text"
                        className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                        placeholder={clause.action === "goto" ? "step label" : "value"}
                        value={clause.action_value ?? ""}
                        onChange={(e) => handleUpdateClause(idx, { action_value: e.target.value || null })}
                      />
                    )}
                  </div>
                </div>

                {/* Note */}
                <div className="mt-2">
                  <input
                    type="text"
                    className="w-full rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
                    placeholder="Note (optional)"
                    value={clause.note ?? ""}
                    onChange={(e) => handleUpdateClause(idx, { note: e.target.value })}
                  />
                </div>
              </div>
            ))
          )}
        </div>

        {/* Validation Error */}
        {!validation.valid && (
          <div className="rounded-lg border border-red-300 bg-red-50 p-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-red-800">Invalid clause order</div>
                <div className="text-xs text-red-700">{validation.error}</div>
              </div>
              <button
                onClick={autoFixOrder}
                className="rounded border border-red-600 bg-red-600 px-3 py-1 text-xs font-medium text-white hover:bg-red-700"
              >
                Auto-fix Order
              </button>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-between border-t border-gray-200 pt-4">
          <button
            onClick={handleAddClause}
            className="rounded-lg border border-blue-600 bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            + Add Clause
          </button>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={!validation.valid}
              className="rounded-lg border border-green-600 bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
