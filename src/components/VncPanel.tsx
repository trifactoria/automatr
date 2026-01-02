"use client";

export function VncPanel({
  vncUrl,
  running,
  onStart,
}: {
  vncUrl: string | null | undefined;
  running: boolean;
  onStart: () => void;
}) {
  return (
    <div className="rounded-2xl border bg-white p-4">
      <div className="mb-3 text-lg font-semibold text-gray-900">VNC Display</div>
      <div className="overflow-hidden rounded-xl border border-gray-300 bg-black">
        {running && vncUrl ? (
          <iframe src={vncUrl} className="h-[500px] w-full" title="VNC Display" />
        ) : (
          <div className="flex h-[500px] flex-col items-center justify-center gap-4 text-white/70">
            {!running ? (
              <>
                <div className="text-lg">Container is not running</div>
                <button
                  className="rounded-lg border border-green-600 bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
                  onClick={onStart}
                >
                  Start Container
                </button>
              </>
            ) : (
              <div className="text-lg">VNC URL not available</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
