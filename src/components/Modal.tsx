"use client";

export function Modal({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  if (!open) return null;
  return (
    <div className="auto-modal__overlay fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="auto-modal w-full max-w-2xl rounded-2xl bg-white shadow-xl">
        <div className="auto-modal__header flex items-center justify-between border-b p-4">
          <div className="auto-modal__title text-lg font-semibold">{title}</div>
          <button className="auto-btn rounded-lg border px-3 py-1" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="auto-modal__body p-4">{children}</div>
      </div>
    </div>
  );
}

