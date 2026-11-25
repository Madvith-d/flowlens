import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom lacks fetch/AbortSignal parity with browsers in some versions;
// polyfill before tests stub it.
if (typeof window !== "undefined") {
  if (!("fetch" in window)) {
    Object.defineProperty(window, "fetch", { value: vi.fn(), writable: true });
  }
}

afterEach(() => {
  cleanup();
});
