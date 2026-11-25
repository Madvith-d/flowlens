import { Inbox, CircleAlert, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Consistent empty state. `title` and `description` are text; meaning is
 * never carried by the icon alone.
 */
export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
  className?: string;
}) {
  return (
    <Card className={cn("border-dashed", className)}>
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <span
          role="img"
          aria-hidden="true"
          className="flex size-12 items-center justify-center rounded-full bg-muted"
        >
          <Icon className="size-6 text-muted-foreground" />
        </span>
        <div className="space-y-1">
          <CardTitle>{title}</CardTitle>
          {description ? (
            <CardDescription className="mx-auto max-w-sm">{description}</CardDescription>
          ) : null}
        </div>
        {action ? (
          <Button variant="outline" onClick={action.onClick}>
            {action.label}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

/**
 * Consistent error state with a retry affordance. `message` must be an
 * actionable, human-readable message; raw backend errors are pre-mapped by
 * the API client before reaching this component.
 */
export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  retryLabel = "Try again",
  className,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}) {
  return (
    <Card role="alert" className={cn("border-destructive/40", className)}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-destructive">
          <CircleAlert aria-hidden="true" className="size-5 shrink-0" />
          {title}
        </CardTitle>
        <CardDescription>{message}</CardDescription>
      </CardHeader>
      {onRetry ? (
        <CardContent>
          <Button variant="outline" onClick={onRetry}>
            {retryLabel}
          </Button>
        </CardContent>
      ) : null}
    </Card>
  );
}
