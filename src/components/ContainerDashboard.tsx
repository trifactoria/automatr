"use client";

import { Toggle } from "@/components/Toggle";
import type { AutomationRow, VncInfo } from "@/lib/types";

export function ContainerDashboard({
  containerName,
  vncVisible,
  setVncVisible,
  running,
  setRunning,
  vnc,
  takeover,
  setTakeover,
  automationName,
  setAutomationName,
  automations,
  editorVisible,
  setEditorVisible,
  loggerVisible,
  setLoggerVisible,
  onStopAuto,
  onRunAutomation,
  onNewAutomation,
  onSaveAutomation,
  onDeleteAutomation,
}: {
  containerName: string;

  vncVisible: boolean;
  setVncVisible: (v: boolean) => void;

  running: boolean;
  setRunning: (v: boolean) => void;

  vnc: VncInfo | null;

  takeover: boolean;
  setTakeover: (v: boolean) => void;

  automations: AutomationRow[];
  automationName: string;
  setAutomationName: (v: string) => void;

  editorVisible: boolean;
  setEditorVisible: (v: boolean) => void;

  loggerVisible: boolean;
  setLoggerVisible: (v: boolean) => void;

  onStopAuto: () => Promise<void>;
  onRunAutomation: () => Promise<void>;
  onNewAutomation: () => void;
  onSaveAutomation: () => void;
  onDeleteAutomation: () => void;
}) {
  return (
    <div className="auto-container grid gap-4">
      {/* VNC card */}
      <div className="auto-card rounded-2xl border p-4">
        <div className="flex items-center justify-between">
          <div className="text-lg font-semibold">Container: {containerName}</div>
          <div className="flex gap-4">
            <Toggle label="VNC" checked={vncVisible} onChange={setVncVisible} />
            <Toggle label="Running" checked={running} onChange={setRunning} />
          </div>
        </div>

        {vncVisible ? (
          <div className="mt-3 rounded-xl border overflow-hidden">
            <div className="flex items-center justify-between border-b bg-gray-50 p-2">
              <div className="text-sm text-gray-600">VNC</div>
              <div className="flex items-center gap-2">
                <button className="auto-btn auto-btn--danger rounded-lg border px-3 py-1" onClick={onStopAuto}>
                  Stop Auto
                </button>
                <Toggle label="Takeover" checked={takeover} onChange={setTakeover} />
              </div>
            </div>
            <div className="h-[420px] bg-black">
              {vnc?.url ? (
                <iframe
                  src={vnc.url}
                  className="h-full w-full"
                  // view-only is typically handled by the vnc URL or novnc settings;
                  // takeover toggle can later switch url params.
                />
              ) : (
                <div className="flex h-full items-center justify-center text-white/70">
                  No VNC URL yet
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>

      {/* Automation row */}
      <div className="auto-card rounded-2xl border p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="auto-select flex flex-col gap-1">
            <span className="auto-select__label text-sm text-gray-600">Automation</span>
            <select
              className="auto-select__control rounded-lg border p-2"
              value={automationName}
              onChange={(e) => setAutomationName(e.target.value)}
            >
              <option value="">—</option>
              {automations.map((a) => (
                <option key={a.name} value={a.name}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>

          <button className="auto-btn auto-btn--primary rounded-lg border px-3 py-2" onClick={onRunAutomation} disabled={!automationName || !running}>
            Run
          </button>
          <button className="auto-btn rounded-lg border px-3 py-2" onClick={onNewAutomation}>
            New
          </button>
          <button className="auto-btn rounded-lg border px-3 py-2" onClick={onSaveAutomation} disabled={!automationName}>
            Save
          </button>
          <button className="auto-btn auto-btn--danger rounded-lg border px-3 py-2" onClick={onDeleteAutomation} disabled={!automationName}>
            Delete
          </button>

          <div className="ml-auto flex gap-4">
            <Toggle label="Editor" checked={editorVisible} onChange={setEditorVisible} />
            <Toggle label="Show Logger" checked={loggerVisible} onChange={setLoggerVisible} />
          </div>
        </div>

        {editorVisible ? (
          <div className="mt-4 rounded-xl border p-3 text-sm text-gray-500">
            Editor panel is handled by the main automation workspace.
          </div>
        ) : null}

        {loggerVisible ? (
          <div className="mt-4 rounded-xl border p-3 text-sm text-gray-500">
            Logs are available from the main automation workspace.
          </div>
        ) : null}
      </div>
    </div>
  );
}
