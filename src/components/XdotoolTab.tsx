"use client";

import { useState } from "react";

type RecordedEvent = {
  timestamp: string;
  button: "left" | "middle" | "right";
  x: number;
  y: number;
  window_title?: string;
};

export function XdotoolTab() {
  const [recording, setRecording] = useState(false);
  const [events, setEvents] = useState<RecordedEvent[]>([]);

  const handleStartRecording = () => {
    setRecording(true);
    // TODO: Call backend endpoint when available
    // POST /containers/{name}/xdotool/start
  };

  const handleStopRecording = () => {
    setRecording(false);
    // TODO: Call backend endpoint when available
    // POST /containers/{name}/xdotool/stop
  };

  const handleClearEvents = () => {
    setEvents([]);
  };

  return (
    <div className="space-y-4">
      {/* Recorder controls */}
      <div className="flex items-center gap-3 rounded-lg border border-gray-300 bg-white p-4">
        <div className="text-sm font-medium text-gray-700">Recorder:</div>
        {!recording ? (
          <button
            onClick={handleStartRecording}
            className="rounded-lg border border-green-600 bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
          >
            Start Recording
          </button>
        ) : (
          <button
            onClick={handleStopRecording}
            className="rounded-lg border border-red-600 bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
          >
            Stop Recording
          </button>
        )}
        <button
          onClick={handleClearEvents}
          disabled={events.length === 0}
          className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-50"
        >
          Clear Events
        </button>
        {recording && (
          <div className="ml-auto flex items-center gap-2">
            <div className="h-3 w-3 animate-pulse rounded-full bg-red-600"></div>
            <span className="text-sm text-gray-600">Recording...</span>
          </div>
        )}
      </div>

      {/* Events list */}
      <div className="rounded-lg border border-gray-300 bg-white p-4">
        <div className="mb-2 text-sm font-medium text-gray-700">Captured Events ({events.length})</div>
        {events.length === 0 ? (
          <div className="rounded bg-gray-50 p-8 text-center text-sm text-gray-500">
            <div className="mb-2">No events captured yet.</div>
            <div className="text-xs text-gray-400">
              Backend endpoint not implemented yet.
              <br />
              Future endpoints: POST /containers/&#123;name&#125;/xdotool/start|stop
            </div>
          </div>
        ) : (
          <div className="max-h-[300px] space-y-2 overflow-y-auto">
            {events.map((event, idx) => (
              <div key={idx} className="rounded border border-gray-200 bg-gray-50 p-2 text-xs font-mono">
                <div className="flex items-center gap-3">
                  <span className="text-gray-500">{event.timestamp}</span>
                  <span
                    className={`rounded px-2 py-0.5 font-medium ${
                      event.button === "left"
                        ? "bg-blue-100 text-blue-800"
                        : event.button === "middle"
                          ? "bg-yellow-100 text-yellow-800"
                          : "bg-green-100 text-green-800"
                    }`}
                  >
                    {event.button}
                  </span>
                  <span className="text-gray-700">
                    x:{event.x} y:{event.y}
                  </span>
                  {event.window_title && <span className="text-gray-500">({event.window_title})</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Info panel */}
      <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs text-blue-800">
        <div className="font-medium">About Xdotool Recorder</div>
        <div className="mt-1 text-blue-700">
          The recorder captures mouse clicks and coordinates for use in automation steps. When backend endpoints are
          implemented, recorded events will appear here and can be used to generate click actions.
        </div>
      </div>
    </div>
  );
}
