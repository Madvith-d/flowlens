import { cn } from "@/lib/utils";

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />;
}

/** Centered loading indicator with accessible label. */
function Spinner({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <span role="status" aria-live="polite" className={cn("inline-flex items-center gap-2 text-sm text-muted-foreground", className)}>
      <span
        aria-hidden="true"
        className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
      />
      <span className="sr-only">{label}</span>
      <span aria-hidden="true">{label}…</span>
    </span>
  );
}

export { Skeleton, Spinner };
