"use client";

import { useState } from "react";
import { Modal } from "@/components/Modal";

export function CreateContainerModal({
  open,
  onClose,
  onCreate,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (payload: { name: string; description: string }) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");

  return (
    <Modal open={open} title="Create Container" onClose={onClose}>
      <div className="grid gap-3">
        <label className="grid gap-1">
          <span className="text-sm text-gray-600">Name (slug)</span>
          <input
            className="rounded-lg border p-2"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="rh-watch"
          />
        </label>
        <label className="grid gap-1">
          <span className="text-sm text-gray-600">Description</span>
          <input
            className="rounded-lg border p-2"
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            placeholder="Watches price and reacts"
          />
        </label>

        <div className="flex gap-2">
          <button
            className="rounded-lg border px-3 py-2"
            onClick={async () => {
              await onCreate({ name: name.trim(), description: desc.trim() });
              setName("");
              setDesc("");
              onClose();
            }}
          >
            Create
          </button>
          <button className="rounded-lg border px-3 py-2" onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </Modal>
  );
}

