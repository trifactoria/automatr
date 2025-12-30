"use client";

export function Toggle({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className={`auto-toggle ${checked ? "auto-toggle--on" : ""} ${disabled ? "auto-toggle--disabled" : ""} flex items-center gap-2 ${disabled ? "opacity-50" : ""}`}>
      <span className="auto-toggle__label text-sm">{label}</span>
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={[
          "auto-toggle__switch relative h-6 w-11 rounded-full border transition",
          checked ? "bg-black" : "bg-white",
        ].join(" ")}
        aria-pressed={checked}
      >
        <span
          className={[
            "auto-toggle__knob absolute top-0.5 h-5 w-5 rounded-full bg-white transition",
            checked ? "left-5" : "left-0.5",
            checked ? "border border-black" : "border",
          ].join(" ")}
        />
      </button>
    </label>
  );
}

