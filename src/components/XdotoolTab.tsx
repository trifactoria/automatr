"use client";

import { useCallback, useState, useEffect, useRef } from "react";
import * as api from "@/lib/api";
import type { InputEvent } from "@/lib/types";

type Props = {
  containerName?: string | null;
  containerRunning?: boolean;
};

export function XdotoolTab({ containerName, containerRunning }: Props) {
  const [recording, setRecording] = useState(false);
  const [events, setEvents] = useState<InputEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const fetchStatus = useCallback(async () => {
    if (!containerName) return;
    try {
      const status = await api.getInputStatus(containerName);
      setRecording(status.running);
    } catch (e) {
      console.error("Failed to fetch input status:", e);
      setError(`Failed to fetch status: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [containerName]);

  const fetchEvents = useCallback(async () => {
    if (!containerName) return;
    try {
      const evts = await api.getInputEvents(containerName, { tail: 200, parse: true });
      setEvents(evts);
      setError(null);
    } catch (e) {
      console.error("Failed to fetch input events:", e);
      setError(`Failed to fetch events: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [containerName]);

  // Fetch initial status and events when container changes
  useEffect(() => {
    if (!containerName) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setRecording(false);
      setEvents([]);
      setError(null);
      return;
    }

    fetchStatus();
    fetchEvents();
  }, [containerName, fetchEvents, fetchStatus]);

  // Cleanup polling on unmount or container change
  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, [containerName]);

  function startPolling() {
    // Clear any existing interval
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }

    // Poll events every 750ms
    pollingIntervalRef.current = setInterval(() => {
      fetchEvents();
    }, 750);
  }

  function stopPolling() {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  }

  async function handleStartRecording() {
    if (!containerName) return;
    try {
      await api.startInputRecorder(containerName);
      setRecording(true);
      setError(null);
      startPolling();
    } catch (e) {
      console.error("Failed to start recording:", e);
      setError(`Failed to start recording: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function handleStopRecording() {
    if (!containerName) return;
    try {
      await api.stopInputRecorder(containerName);
      setRecording(false);
      setError(null);
      stopPolling();
      // Fetch final events after stopping
      await fetchEvents();
    } catch (e) {
      console.error("Failed to stop recording:", e);
      setError(`Failed to stop recording: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function handleClearEvents() {
    if (!containerName) return;
    try {
      await api.clearInputEvents(containerName);
      setError(null);
      // Refresh events after clearing
      await fetchEvents();
    } catch (e) {
      console.error("Failed to clear events:", e);
      setError(`Failed to clear events: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  // Helper to map button number to name
  function mapButton(button: unknown): string {
    if (button === undefined || button === null) return "";
    const num = typeof button === "number" ? button : parseInt(String(button), 10);
    if (num === 1) return "left";
    if (num === 2) return "middle";
    if (num === 3) return "right";
    return `button${num}`;
  }

  // Helper to format event for display
  function formatEvent(event: InputEvent, idx: number) {
    const { timestamp, type, data } = event;
    const ts = timestamp || `#${idx}`;

    // For mouse events, try to extract button, action, x, y
    const button = mapButton(data.button);
    const action = data.action;
    const x = data.x;
    const y = data.y;

    return (
      <div key={idx} className="rounded border border-gray-200 bg-gray-50 p-2 text-xs font-mono">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-gray-500">{ts}</span>
          <span className="rounded bg-blue-100 px-2 py-0.5 text-blue-800 font-medium">{type}</span>
          {button && (
            <span
              className={`rounded px-2 py-0.5 font-medium ${
                button === "left"
                  ? "bg-green-100 text-green-800"
                  : button === "middle"
                    ? "bg-yellow-100 text-yellow-800"
                    : button === "right"
                      ? "bg-red-100 text-red-800"
                      : "bg-gray-100 text-gray-800"
              }`}
            >
              {button}
            </span>
          )}
          {action && <span className="text-gray-700">{action}</span>}
          {x !== undefined && y !== undefined && (
            <span className="text-gray-700">
              x:{x} y:{y}
            </span>
          )}
          {data.line && <span className="text-gray-600 italic">{data.line}</span>}
        </div>
      </div>
    );
  }

  // If no container selected
  if (!containerName) {
    return (
      <div className="flex h-[300px] items-center justify-center text-gray-500">
        Select a container to use the recorder.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Error display */}
      {error && (
        <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">
          <div className="font-medium">Error:</div>
          <div className="mt-1">{error}</div>
        </div>
      )}

      {/* Recorder controls */}
      <div className="flex items-center gap-3 rounded-lg border border-gray-300 bg-white p-4">
        <div className="text-sm font-medium text-gray-700">Recorder:</div>
        {!recording ? (
          <button
            onClick={handleStartRecording}
            disabled={!containerRunning}
            title={!containerRunning ? "Container must be running to record" : ""}
            className="rounded-lg border border-green-600 bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
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
            No events captured yet.
          </div>
        ) : (
          <div className="max-h-[300px] space-y-2 overflow-y-auto">
            {events.map((event, idx) => formatEvent(event, idx))}
          </div>
        )}
      </div>

      {/* Info panel */}
      <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs text-blue-800">
        <div className="font-medium">About Input Recorder</div>
        <div className="mt-1 text-blue-700">
          The recorder captures mouse and keyboard events for use in automation steps. Start recording to capture
          events, then use them to generate automation actions.
        </div>
      </div>
    </div>
  );
}
