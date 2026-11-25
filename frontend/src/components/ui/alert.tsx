import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const alertVariants = cva(
  "relative w-full rounded-lg border px-4 py-3 text-sm [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-3.5 [&>svg]:size-4 [&>svg+div]:pl-7",
  {
    variants: {
      variant: {
        default: "bg-card text-card-foreground",
        info: "border-primary/30 bg-accent text-accent-foreground [&>svg]:text-primary",
        warning: "border-amber-500/40 bg-amber-50 text-amber-900 [&>svg]:text-amber-600",
        destructive:
          "border-destructive/40 bg-destructive/5 text-destructive [&>svg]:text-destructive",
        success: "border-emerald-500/40 bg-emerald-50 text-emerald-900 [&>svg]:text-emerald-600",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

/** Status text is part of the content, never color alone. */
const Alert = ({
  className,
  variant,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>) => (
  <div role="alert" className={cn(alertVariants({ variant }), className)} {...props}>
    {children}
  </div>
);

const AlertTitle = ({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) => (
  <h5 className={cn("mb-1 font-medium leading-none", className)} {...props}>
    {children}
  </h5>
);

const AlertDescription = ({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("text-sm [&_p]:leading-relaxed", className)} {...props}>
    {children}
  </div>
);

export { Alert, AlertTitle, AlertDescription };
