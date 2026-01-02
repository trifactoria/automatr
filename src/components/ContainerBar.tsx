"use client";

import type { ContainerRow, ContainerDetail } from "@/lib/types";

export function ContainerBar({
  containers,
  selectedContainer,
  containerDetail,
  onSelectContainer,
  onNewContainer,
  onStart,
  onStop,
  onRestart,
  onStopAuto,
  onClearStop,
}: {
  containers: ContainerRow[];
  selectedContainer: string;
  containerDetail: ContainerDetail | null;
  onSelectContainer: (name: string) => void;
  onNewContainer: () => void;
  onStart: () => void;
  onStop: () => void;
  onRestart: () => void;
  onStopAuto: () => void;
  onClearStop: () => void;
}) {
  const running = containerDetail?.running ?? false;
  const busy = containerDetail?.busy ?? false;
  const stopLatched = containerDetail?.stop_latched ?? false;

  return (
    <div className="rounded-2xl border bg-white p-4">
      <div className="flex flex-wrap items-center gap-3">
        {/* Container selector */}
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700">Container:</label>
          <select
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            value={selectedContainer}
            onChange={(e) => onSelectContainer(e.target.value)}
          >
            <option value="">Select container...</option>
            {containers.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        <button
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium hover:bg-gray-50"
          onClick={onNewContainer}
        >
          New Container
        </button>

        {/* Status chips */}
        {containerDetail && (
          <>
            <div className="ml-4 flex items-center gap-2">
              <span
                className={`rounded-full px-2 py-1 text-xs font-medium ${
                  running ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-800"
                }`}
              >
                {running ? "Running" : "Stopped"}
              </span>
              {busy && (
                <span className="rounded-full bg-yellow-100 px-2 py-1 text-xs font-medium text-yellow-800">
                  Busy{containerDetail.busy_automation ? `: ${containerDetail.busy_automation}` : ""}
                </span>
              )}
              {stopLatched && (
                <span className="rounded-full bg-red-100 px-2 py-1 text-xs font-medium text-red-800">
                  Stop Latched
                </span>
              )}
            </div>

            {/* Control buttons */}
            <div className="ml-auto flex items-center gap-2">
              {!running && (
                <button
                  className="rounded-lg border border-green-600 bg-green-600 px-3 py-2 text-sm font-medium text-white hover:bg-green-700"
                  onClick={onStart}
                >
                  Start
                </button>
              )}
              {running && (
                <>
                  <button
                    className="rounded-lg border border-red-600 bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700"
                    onClick={onStop}
                  >
                    Stop
                  </button>
                  <button
                    className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium hover:bg-gray-50"
                    onClick={onRestart}
                  >
                    Restart
                  </button>
                </>
              )}
              <button
                className="rounded-lg border border-orange-600 bg-orange-600 px-3 py-2 text-sm font-medium text-white hover:bg-orange-700"
                onClick={onStopAuto}
              >
                Stop Auto
              </button>
              {stopLatched && (
                <button
                  className="rounded-lg border border-blue-600 bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
                  onClick={onClearStop}
                >
                  Clear Stop
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
