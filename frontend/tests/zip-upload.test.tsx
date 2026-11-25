import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { ZipUploadForm } from "@/features/projects/components/zip-upload-form";
import type { Project } from "@/types/api";

/**
 * Phase 3B ZIP upload tests: client-side type feedback, real XHR upload
 * progress, backend validation errors (envelope mapping), retry, and a
 * successful creation. XHR is stubbed; the app itself always uploads to the
 * real endpoint.
 */

const PROJECT: Project = {
  id: "p9",
  name: "Uploaded project",
  source_provider: "upload",
  created_at: "2025-06-04T10:00:00Z",
  updated_at: "2025-06-04T10:00:00Z",
};

class FakeXHR {
  static instances: FakeXHR[] = [];
  status = 0;
  responseText = "";
  withCredentials = false;
  timeout = 0;
  method = "";
  url = "";
  sentBody: FormData | null = null;
  upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  onabort: (() => void) | null = null;

  constructor() {
    FakeXHR.instances.push(this);
  }

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }

  send(body: FormData) {
    this.sentBody = body;
  }

  abort() {
    this.onabort?.();
  }

  // Test helpers -----------------------------------------------------------
  emitProgress(loaded: number, total: number) {
    this.upload.onprogress?.({
      lengthComputable: true,
      loaded,
      total,
    } as ProgressEvent);
  }

  respond(status: number, body: string) {
    this.status = status;
    this.responseText = body;
    this.onload?.();
  }

  fail() {
    this.onerror?.();
  }
}

function zipFile(name = "project.zip", size = 1024): File {
  const file = new File([new ArrayBuffer(size)], name, {
    type: "application/zip",
  });
  return file;
}

beforeEach(() => {
  FakeXHR.instances = [];
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function fillForm() {
  const onCreated = vi.fn();
  render(<ZipUploadForm onCreated={onCreated} />);

  await userEvent.type(screen.getByLabelText(/Project name/), "My service");

  const input = screen.getByLabelText(/ZIP archive/) as HTMLInputElement;
  fireEvent.change(input, { target: { files: [zipFile()] } });
  return { onCreated };
}

describe("ZIP upload form", () => {
  it("creates a project via the contract endpoint with credentials, real progress, and redirects on completion", async () => {
    const { onCreated } = await fillForm();

    await userEvent.click(screen.getByRole("button", { name: /Create project from ZIP/ }));

    const [xhr] = FakeXHR.instances;
    expect(xhr).toBeDefined();
    expect(xhr.method).toBe("POST");
    expect(xhr.url).toBe("http://localhost:8000/api/v1/projects/from-upload");
    expect(xhr.withCredentials).toBe(true);
    expect(xhr.sentBody?.get("name")).toBe("My service");
    expect((xhr.sentBody?.get("file") as File).name).toBe("project.zip");

    // Real progress from the XHR upload event is reflected honestly.
    xhr.emitProgress(512, 1024);
    await vi.waitFor(() =>
      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50")
    );

    xhr.respond(201, JSON.stringify(PROJECT));

    await vi.waitFor(() => expect(onCreated).toHaveBeenCalledWith(PROJECT));
  });

  it("rejects a non-ZIP selection with client-side feedback", async () => {
    render(<ZipUploadForm />);
    const input = screen.getByLabelText(/ZIP archive/) as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File([new ArrayBuffer(8)], "bundle.tar.gz", { type: "application/gzip" })] },
    });

    expect(screen.getByRole("alert")).toHaveTextContent(
      /Choose a ZIP archive \(\.zip\)/
    );
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("shows the backend UPLOAD_INVALID envelope and allows retry", async () => {
    const { onCreated } = await fillForm();

    await userEvent.click(screen.getByRole("button", { name: /Create project from ZIP/ }));
    FakeXHR.instances[0].respond(
      400,
      JSON.stringify({
        error: {
          code: "UPLOAD_INVALID",
          message: "The archive entry '../../etc/passwd' is outside the allowed directory.",
          request_id: "r2",
        },
      })
    );

    expect(
      await screen.findByRole("alert")
    ).toHaveTextContent(/outside the allowed directory/);

    // The selection is kept: retry sends again with the same file.
    await userEvent.click(screen.getByRole("button", { name: /Create project from ZIP/ }));
    expect(FakeXHR.instances).toHaveLength(2);
    expect((FakeXHR.instances[1].sentBody?.get("file") as File).name).toBe("project.zip");

    FakeXHR.instances[1].respond(201, JSON.stringify(PROJECT));
    await vi.waitFor(() => expect(onCreated).toHaveBeenCalledWith(PROJECT));
  });

  it("reports the backend UPLOAD_TOO_LARGE limit as an actionable error", async () => {
    await fillForm();

    await userEvent.click(screen.getByRole("button", { name: /Create project from ZIP/ }));
    FakeXHR.instances[0].respond(
      413,
      JSON.stringify({
        error: {
          code: "UPLOAD_TOO_LARGE",
          message: "The archive exceeds the 100 MB limit.",
          request_id: "r3",
        },
      })
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(/exceeds the 100 MB limit/);
  });

  it("surfaces network failures without raw browser errors", async () => {
    await fillForm();

    await userEvent.click(screen.getByRole("button", { name: /Create project from ZIP/ }));
    FakeXHR.instances[0].fail();

    expect(await screen.findByRole("alert")).toHaveTextContent(/upload could not reach/i);
  });
});
