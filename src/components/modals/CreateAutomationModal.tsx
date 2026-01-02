"use client";

import { useState } from "react";
import { Modal } from "@/components/Modal";

export function CreateAutomationModal({
  open,
  onClose,
  onCreate,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (payload: { name: string; description: string }) => void;
}) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");

  const handleCreate = () => {
    if (!name.trim()) return;
    onCreate({ name: name.trim(), description: desc.trim() });
    setName("");
    setDesc("");
    onClose();
  };

  return (
    <Modal open={open} title="Create Automation" onClose={onClose}>
      <div className="grid gap-3">
        <label className="auto-modal__field grid gap-1">
          <span className="auto-modal__field-label text-sm text-gray-600">Name (slug)</span>
          <input
            className="auto-input rounded-lg border p-2"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="my_automation"
          />
        </label>
        <label className="auto-modal__field grid gap-1">
          <span className="auto-modal__field-label text-sm text-gray-600">Description</span>
          <input
            className="auto-input rounded-lg border p-2"
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            placeholder="Brief description"
          />
        </label>

        <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs text-blue-800">
          <div className="font-medium">New automation will be created with:</div>
          <ul className="mt-1 list-inside list-disc text-blue-700">
            <li>Empty steps list</li>
            <li>No variables</li>
            <li>Ready to edit in the Editor tab</li>
          </ul>
        </div>

        <div className="flex gap-2">
          <button
            className="auto-btn auto-btn--primary rounded-lg border px-3 py-2"
            onClick={handleCreate}
            disabled={!name.trim()}
          >
            Create
          </button>
          <button className="auto-btn rounded-lg border px-3 py-2" onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </Modal>
  );
}
