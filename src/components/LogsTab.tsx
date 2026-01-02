"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Toggle } from "@/components/Toggle";
import * as api from "@/lib/api";

type LogType = "startup" | "automation";

export function LogsTab({ containerName }: { containerName?: string | null }) {
  const [activeLogType, setActiveLogType] = useState<LogType>("startup");
  const [lines, setLines] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [tail, setTail] = useState(200);
  const [timestamps, setTimestamps] = useState(false); // OFF by default
  const [autoRefresh, setAutoRefresh] = useState(false); // OFF by default

  const lastTextRef = useRef<string>("");

  const title = useMemo(
    () => (activeLogType === "startup" ? "Startup Logs" : "Automation Logs"),
    [activeLogType]
  );

  async function refresh(opts?: { silent?: boolean }) {
    if (!containerName) return;
    const silent = opts?.silent ?? false;

    // Silent refresh should NOT toggle loading/error UI (prevents jitter)
    if (!silent) {
      setLoading(true);
      setError(null);
    }

    try {
      const res =
        activeLogType === "startup"
          ? await api.getStartupLogs(containerName, { tail, timestamps })
          : await api.getAutomationLogs(containerName, { tail });

      const nextLines = res.lines ?? [];
      const nextText = nextLines.join("\n");

      // Only update state if content actually changed (prevents re-render churn)
      if (nextText !== lastTextRef.current) {
        lastTextRef.current = nextText;
        setLines(nextLines);
      }
    } catch (e: any) {
      if (!silent) {
        setError(e?.message || String(e));
        setLines([]);
        lastTextRef.current = "";
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }

  // Refresh when switching container or tab (manual-style refresh, not silent)
  useEffect(() => {
    setLines([]);
    lastTextRef.current = "";
    setError(null);
    if (containerName) refresh({ silent: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerName, activeLogType]);

  // Auto-refresh polling (silent)
  useEffect(() => {
    if (!containerName) return;
    if (!autoRefresh) return;

    const id = window.setInterval(() => {
      refresh({ silent: true });
    }, 1200);

    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerName, activeLogType, autoRefresh, tail, timestamps]);

  return (
    <div className="space-y-4">
      {/* Log type tabs */}
      <div className="flex gap-2 border-b border-gray-300">
        <button
          onClick={() => setActiveLogType("startup")}
          className={`px-4 py-2 text-sm font-medium ${
            activeLogType === "startup"
              ? "border-b-2 border-blue-600 text-blue-600"
              : "text-gray-600 hover:text-gray-900"
          }`}
        >
          Startup Logs
        </button>
        <button
          onClick={() => setActiveLogType("automation")}
          className={`px-4 py-2 text-sm font-medium ${
            activeLogType === "automation"
              ? "border-b-2 border-blue-600 text-blue-600"
              : "text-gray-600 hover:text-gray-900"
          }`}
        >
          Automation Logs
        </button>

        {/* Controls (right side) */}
        <div className="ml-auto flex items-center gap-3 px-2">
          <label className="flex items-center gap-2 text-xs text-gray-600">
            tail
            <input
              value={tail}
              onChange={(e) => {
                const n = Number(e.target.value);
                if (Number.isFinite(n)) setTail(n);
              }}
              className="w-20 rounded border border-gray-300 bg-white px-2 py-1 text-xs"
              type="number"
              min={1}
              max={5000}
            />
          </label>

          {activeLogType === "startup" && (
            <Toggle
              label="timestamps"
              checked={timestamps}
              onChange={setTimestamps}
              disabled={!containerName}
            />
          )}

          <Toggle
            label="auto"
            checked={autoRefresh}
            onChange={setAutoRefresh}
            disabled={!containerName}
          />

          <button
            onClick={() => refresh({ silent: true})}
            disabled={!containerName || loading}
            className="min-w-[86px] rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium hover:bg-gray-50 disabled:opacity-50"
          >
            <span className="inline-flex items-center gap-2">
              <span>Refresh</span>
              {loading && <span className="opacity-60">•</span>}
            </span>
          </button>
         </div>
      </div>

      {/* Log content */}
      <div className="rounded-lg border border-gray-300 bg-gray-50 p-4">
        <div className="rounded bg-black p-3 font-mono text-xs text-green-400">
          {!containerName ? (
            <div>
              <div className="mb-2 text-gray-400"># {title}</div>
              <div className="text-yellow-400">Select a container to view logs.</div>
            </div>
          ) : (
            <div>
              <div className="mb-2 text-gray-400">
                # {title} (container: {containerName})
              </div>

              {error && <div className="mb-2 whitespace-pre-wrap text-red-300">{error}</div>}

              {lines.length === 0 && !error ? (
                <div className="text-gray-500">No log lines.</div>
              ) : (
                <div className="max-h-[420px] overflow-auto whitespace-pre-wrap">
                  {lines.join("\n")}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
