"use client";

import { useState } from "react";
import { Modal } from "@/components/Modal";

const TEMPLATE = `schema_version: 1
name: "new_automation"
description: ""
steps: []
`;

export function CreateAutomationModal({
  open,
  onClose,
  onCreate,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (payload: { name: string; description: string; yaml: string }) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [yaml, setYaml] = useState(TEMPLATE);

  return (
    <Modal open={open} title="Create Automation" onClose={onClose}>
      <div className="grid gap-3">
        <label className="auto-modal__field grid gap-1">
          <span className="auto-modal__field-label text-sm text-gray-600">Name (slug)</span>
          <input className="auto-input rounded-lg border p-2" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="auto-modal__field grid gap-1">
          <span className="auto-modal__field-label text-sm text-gray-600">Description</span>
          <input className="auto-input rounded-lg border p-2" value={desc} onChange={(e) => setDesc(e.target.value)} />
        </label>
        <label className="auto-modal__field grid gap-1">
          <span className="auto-modal__field-label text-sm text-gray-600">YAML</span>
          <textarea className="auto-textarea h-64 rounded-lg border p-2 font-mono text-sm" value={yaml} onChange={(e) => setYaml(e.target.value)} />
        </label>

        <div className="flex gap-2">
          <button
            className="auto-btn auto-btn--primary rounded-lg border px-3 py-2"
            onClick={async () => {
              await onCreate({ name: name.trim(), description: desc.trim(), yaml });
              setName("");
              setDesc("");
              setYaml(TEMPLATE);
              onClose();
            }}
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

