import type { Metadata } from "next";
import { Toaster } from "sonner";

import "./globals.css";
import { SessionProvider } from "@/features/auth/session-provider";

export const metadata: Metadata = {
  title: {
    default: "FlowLens",
    template: "%s · FlowLens",
  },
  description:
    "FlowLens — code dependency and change impact visualizer for Python projects.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <SessionProvider>
          {children}
          <Toaster position="top-right" closeButton />
        </SessionProvider>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
        >
          Skip to main content
        </a>
      </body>
    </html>
  );
}
