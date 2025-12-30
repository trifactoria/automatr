"use client";

import type { ContainerRow } from "@/lib/types";

export function HostDashboard({
  containers,
  onStart,
  onStop,
  onViewVnc,
}: {
  containers: ContainerRow[];
  onStart: (name: string) => Promise<void>;
  onStop: (name: string) => Promise<void>;
  onViewVnc: (name: string) => Promise<void>;
}) {
  return (
    <div className="auto-host auto-card rounded-2xl border p-4">
      <div className="mb-3 text-lg font-semibold">Host</div>
      <div className="text-sm text-gray-600 mb-3">
        Containers overview (schedules later).
      </div>

      <div className="auto-table-wrap overflow-auto rounded-xl border">
        <table className="auto-table w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="p-2 text-left">Name</th>
              <th className="p-2 text-left">Status</th>
              <th className="p-2 text-left">Busy</th>
              <th className="p-2 text-left">Actions</th>
            </tr>
          </thead>
          <tbody>
            {containers.map((c) => (
              <tr key={c.name} className="border-t">
                <td className="p-2 font-mono">{c.name}</td>
                <td className="p-2">{c.running ? "running" : "stopped"}</td>
                <td className="p-2">
                  {c.busy ? `yes${c.busy_automation ? ` (${c.busy_automation})` : ""}` : "no"}
                </td>
                <td className="p-2 flex gap-2">
                  <button className="auto-btn rounded-lg border px-2 py-1" onClick={() => onViewVnc(c.name)}>
                    View
                  </button>
                  {c.running ? (
                    <button className="auto-btn rounded-lg border px-2 py-1" onClick={() => onStop(c.name)}>
                      Stop
                    </button>
                  ) : (
                    <button className="auto-btn rounded-lg border px-2 py-1" onClick={() => onStart(c.name)}>
                      Start
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {containers.length === 0 && (
              <tr>
                <td className="p-2 text-gray-500" colSpan={4}>
                  No containers yet. Create one.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

