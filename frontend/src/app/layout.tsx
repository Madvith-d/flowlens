import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "FlowLens",
  description: "Code dependency and change impact visualizer",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
