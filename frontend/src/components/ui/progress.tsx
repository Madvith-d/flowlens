import { cn } from "@/lib/utils";

/**
 * Progress bar. `value` is a real 0–100 measurement (e.g. XMLHttpRequest
 * upload progress); omit it for an honest indeterminate state (duration
 * unknown). Never pass a fabricated percentage.
 *
 * Accessible: `role="progressbar"` with label text; state is never
 * color-only.
 */
export function Progress({
  value,
  label,
  className,
}: {
  /** Measured percentage 0–100. Omit when the total is unknown. */
  value?: number;
  /** Visible status text, e.g. "Uploading archive — 42%". */
  label?: string;
  className?: string;
}) {
  const determinate = typeof value === "number" && Number.isFinite(value);
  const clamped = determinate ? Math.min(100, Math.max(0, value)) : undefined;
  const percentText = determinate ? `${Math.round(clamped as number)}%` : undefined;

  return (
    <div className={cn("space-y-1.5", className)}>
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={clamped}
        aria-label={label ?? (determinate ? "Progress" : "In progress")}
        aria-valuetext={percentText}
        className="h-2 w-full overflow-hidden rounded-full bg-muted"
      >
        <div
          className={cn(
            "h-full rounded-full bg-primary transition-[width] ease-out",
            determinate
              ? "duration-150"
              : "w-1/3 animate-[progress-indeterminate_1.2s_ease-in-out_infinite_alternate]"
          )}
          style={determinate ? { width: `${clamped as number}%` } : undefined}
        />
      </div>
      {label ? (
        <p className="text-xs text-muted-foreground">
          {label} {percentText && !label.includes("%") ? `— ${percentText}` : null}
        </p>
      ) : null}
    </div>
  );
}
