"use client";

import { useState } from "react";
import type { GraphStep, StepClause } from "@/lib/types";
import { StepCard } from "./StepCard";
import { ConditionsModal } from "./ConditionsModal";

export function EditorTab({
  steps,
  availableActions,
  actionsSchema,
  onUpdateSteps,
}: {
  steps: GraphStep[];
  availableActions: string[];
  actionsSchema: Record<string, { name: string; params: Array<{ key: string; type: string; default: string }> }>;
  onUpdateSteps: (steps: GraphStep[]) => void;
}) {
  const [editingConditionsIndex, setEditingConditionsIndex] = useState<number | null>(null);

  const handleUpdateStep = (index: number, updates: Partial<GraphStep>) => {
    const newSteps = [...steps];
    newSteps[index] = { ...newSteps[index], ...updates };
    onUpdateSteps(newSteps);
  };

  const handleDeleteStep = (index: number) => {
    const newSteps = steps.filter((_, i) => i !== index);
    onUpdateSteps(newSteps);
  };

  const handleAddStep = () => {
    const newStep: GraphStep = {
      label: "",
      action: availableActions[0] || "sleep",
      enabled: 1,
      params: [],
      clauses: [],
    };
    onUpdateSteps([...steps, newStep]);
  };

  const handleSaveConditions = (clauses: StepClause[]) => {
    if (editingConditionsIndex === null) return;
    handleUpdateStep(editingConditionsIndex, { clauses });
  };

  return (
    <div className="space-y-4">
      {/* Steps list */}
      {steps.length === 0 ? (
        <div className="rounded-lg border border-gray-300 bg-gray-50 p-8 text-center text-gray-500">
          No steps defined. Click "Add Step" to get started.
        </div>
      ) : (
        <div className="space-y-3">
          {steps.map((step, idx) => (
            <StepCard
              key={idx}
              step={step}
              stepIndex={idx}
              availableActions={availableActions}
              actionsSchema={actionsSchema}
              onUpdate={(updates) => handleUpdateStep(idx, updates)}
              onDelete={() => handleDeleteStep(idx)}
              onEditConditions={() => setEditingConditionsIndex(idx)}
            />
          ))}
        </div>
      )}

      {/* Add step button */}
      <div className="flex justify-center">
        <button
          onClick={handleAddStep}
          className="rounded-lg border border-blue-600 bg-blue-600 px-6 py-3 text-sm font-medium text-white hover:bg-blue-700"
        >
          + Add Step
        </button>
      </div>

      {/* Conditions modal */}
      {editingConditionsIndex !== null && (
        <ConditionsModal
          open={true}
          clauses={steps[editingConditionsIndex]?.clauses || []}
          onClose={() => setEditingConditionsIndex(null)}
          onSave={handleSaveConditions}
        />
      )}
    </div>
  );
}
