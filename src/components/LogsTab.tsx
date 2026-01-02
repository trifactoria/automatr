"use client";

import { useState } from "react";

export function LogsTab() {
  const [activeLogType, setActiveLogType] = useState<"startup" | "automation">("startup");

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
      </div>

      {/* Log content */}
      <div className="rounded-lg border border-gray-300 bg-gray-50 p-4">
        <div className="rounded bg-black p-3 font-mono text-xs text-green-400">
          {activeLogType === "startup" ? (
            <div>
              <div className="mb-2 text-gray-400"># Startup Logs</div>
              <div className="text-yellow-400">Backend endpoint not implemented yet.</div>
              <div className="mt-2 text-gray-500">
                Placeholder for container startup logs.
                <br />
                Future endpoint: GET /containers/&#123;name&#125;/logs/startup
              </div>
            </div>
          ) : (
            <div>
              <div className="mb-2 text-gray-400"># Automation Logs</div>
              <div className="text-yellow-400">Backend endpoint not implemented yet.</div>
              <div className="mt-2 text-gray-500">
                Placeholder for automation execution logs.
                <br />
                Future endpoint: GET /containers/&#123;name&#125;/logs/automation
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
