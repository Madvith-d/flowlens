"use client";

import { useRouter } from "next/navigation";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Spinner } from "@/components/ui/skeleton";
import { CircleAlert, Info, CheckCircle2 } from "lucide-react";
import { Box } from "lucide-react";

import { GitHubLoginButton } from "@/features/auth/components/github-login-button";
import { useSession } from "@/features/auth/session-provider";
import type { SessionStatus } from "@/features/auth/session-provider";

/** Status-specific copy for the sign-in button area. */
function buttonLabel(status: SessionStatus): string {
  switch (status) {
    case "loading":
      return "Checking your session…";
    case "authenticated":
      return "Opening FlowLens…";
    default:
      return "Continue with GitHub";
  }
}

function isCallbackError(value: string | null): boolean {
  return value === "oauth" || value === "oauth_denied" || value === "auth";
}

export default function LoginPage() {
  const { status, loginReason } = useSession();
  const router = useRouter();

  const callbackError = React.useMemo(() => {
    if (typeof window === "undefined") return null;
    const params = new URLSearchParams(window.location.search);
    if (isCallbackError(params.get("reason"))) return "oauth";
    if (isCallbackError(params.get("error"))) return "oauth";
    return null;
  }, []);

  // Already signed in: go straight to the dashboard.
  React.useEffect(() => {
    if (status === "authenticated") {
      router.replace("/dashboard");
    }
  }, [status, router]);

  return (
    <main id="main-content" className="flex min-h-dvh flex-col">
      <div className="container flex flex-1 items-center justify-center py-12">
        <div className="w-full max-w-md space-y-8">
          <div className="flex flex-col items-center gap-3 text-center">
            <span
              aria-hidden="true"
              className="flex size-14 items-center justify-center rounded-xl bg-primary text-primary-foreground"
            >
              <Box className="size-8" />
            </span>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">FlowLens</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Visualize Python code dependencies and simulate the impact of
                your changes — before you make them.
              </p>
            </div>
            <Badge variant="secondary">Python · Static analysis · GitHub</Badge>
          </div>

          {callbackError ? (
            <Alert variant="destructive">
              <CircleAlert aria-hidden="true" />
              <div>
                <AlertTitle>GitHub sign-in failed</AlertTitle>
                <AlertDescription>
                  Authorization did not complete. This can happen if the
                  authorization was denied or the session state was invalid.
                  Try signing in again; if it keeps failing, verify the GitHub
                  App configuration.
                </AlertDescription>
              </div>
            </Alert>
          ) : null}

          {loginReason === "expired" ? (
            <Alert variant="warning">
              <Info aria-hidden="true" />
              <div>
                <AlertTitle>Session expired</AlertTitle>
                <AlertDescription>
                  Your FlowLens session has expired. Sign in again to continue.
                </AlertDescription>
              </div>
            </Alert>
          ) : null}

          {loginReason === "signed-out" ? (
            <Alert variant="success">
              <CheckCircle2 aria-hidden="true" />
              <div>
                <AlertTitle>Signed out</AlertTitle>
                <AlertDescription>You have been signed out of FlowLens.</AlertDescription>
              </div>
            </Alert>
          ) : null}

          <Card>
            <CardContent className="p-6">
              {status === "loading" ? (
                <Spinner label="Checking your session" className="justify-center" />
              ) : status === "error" ? (
                <div className="space-y-4">
                  <Alert variant="destructive">
                    <CircleAlert aria-hidden="true" />
                    <div>
                      <AlertTitle>Cannot reach the FlowLens backend</AlertTitle>
                      <AlertDescription>
                        Sign-in requires the FlowLens backend. Check that it is
                        running at <code>{process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}</code>{" "}
                        and reload this page.
                      </AlertDescription>
                    </div>
                  </Alert>
                  <Button variant="outline" className="w-full" onClick={() => window.location.reload()}>
                    Reload
                  </Button>
                </div>
              ) : (
                <div className="space-y-3">
                  <GitHubLoginButton disabled={status === "authenticated"} label={buttonLabel(status)} />
                  <p className="text-center text-xs text-muted-foreground">
                    FlowLens requests read-only repository access. Your GitHub
                    credentials are never shared with this application.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </main>
  );
}
