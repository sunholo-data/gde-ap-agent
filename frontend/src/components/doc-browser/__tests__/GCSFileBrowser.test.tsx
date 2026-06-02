import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GCSBucketInput } from "../GCSBucketInput";
import { GCSFileBrowser } from "../GCSFileBrowser";

// vitest forks pool passes --localstorage-file without a valid path, which
// disables jsdom's native localStorage. Provide a minimal working stub.
const _lsStore: Record<string, string> = {};
const _lsStub = {
  getItem: (k: string) => _lsStore[k] ?? null,
  setItem: (k: string, v: string) => { _lsStore[k] = v; },
  removeItem: (k: string) => { delete _lsStore[k]; },
  clear: () => { Object.keys(_lsStore).forEach((k) => delete _lsStore[k]); },
  key: (i: number) => Object.keys(_lsStore)[i] ?? null,
  get length() { return Object.keys(_lsStore).length; },
};
vi.stubGlobal("localStorage", _lsStub);

vi.mock("@/lib/apiClient", () => ({
  fetchWithAuth: vi.fn(),
}));

const { fetchWithAuth } = await import("@/lib/apiClient");
const mockFetch = vi.mocked(fetchWithAuth);

function makeListOk(objects: unknown[] = [], saEmail: string | null = null, error: string | null = null): Response {
  return {
    ok: true,
    json: () => Promise.resolve({ objects, prefixes: [], error, sa_email: saEmail }),
  } as unknown as Response;
}

function makeListErr(detail: string, status = 400): Response {
  return {
    ok: false,
    status,
    json: () => Promise.resolve({ detail }),
  } as unknown as Response;
}

describe("GCSFileBrowser", () => {
  beforeEach(() => {
    mockFetch.mockResolvedValue(makeListOk());
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("renders skeleton during demo bucket load", async () => {
    // Fetch hangs — skeleton should appear after the 300ms debounce fires
    mockFetch.mockImplementation(() => new Promise(() => {}));
    const { container } = render(<GCSFileBrowser />);
    await waitFor(
      () => expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0),
      { timeout: 1500 },
    );
  });

  it("renders file list with Import buttons after load", async () => {
    mockFetch.mockResolvedValue(
      makeListOk([
        { name: "acme-invoice.docx", displayName: "acme-invoice.docx", size: 37000, contentType: "application/docx", updated: "" },
      ]),
    );
    render(<GCSFileBrowser />);

    await waitFor(
      () => expect(screen.getByText("acme-invoice.docx")).toBeInTheDocument(),
      { timeout: 1500 },
    );
    expect(screen.getByRole("button", { name: /import/i })).toBeInTheDocument();
  });

  it("import button shows Importing… while pending, then Done on success", async () => {
    // Deferred promise so we can observe the intermediate Importing… state
    let resolveImport!: (r: Response) => void;
    const importPending = new Promise<Response>((res) => { resolveImport = res; });

    mockFetch
      .mockResolvedValueOnce(
        makeListOk([
          { name: "acme-invoice.docx", displayName: "acme-invoice.docx", size: 37000, contentType: "application/docx", updated: "" },
        ]),
      )
      .mockReturnValueOnce(importPending);

    render(<GCSFileBrowser />);

    const importBtn = await screen.findByRole("button", { name: /import/i }, { timeout: 1500 });
    await userEvent.click(importBtn);
    // Fetch is still pending — "Importing…" should be visible
    expect(screen.getByText(/importing/i)).toBeInTheDocument();

    // Resolve import
    resolveImport({ ok: true, json: () => Promise.resolve({ docId: "doc-1", status: "parsed" }) } as unknown as Response);
    await waitFor(() => expect(screen.getByText(/done/i)).toBeInTheDocument(), { timeout: 2000 });
  });

  it("error state shows SA email when bucket is denied", async () => {
    const saEmail = "aitana-v6@multivac-dev.iam.gserviceaccount.com";
    mockFetch.mockResolvedValue(makeListOk([], saEmail, "403 Forbidden"));
    render(<GCSFileBrowser />);

    await waitFor(
      () => expect(screen.getByText(new RegExp(saEmail))).toBeInTheDocument(),
      { timeout: 1500 },
    );
  });

  it("shows error message from backend on list failure", async () => {
    mockFetch.mockResolvedValue(makeListErr("Invalid GCS bucket name"));
    render(<GCSFileBrowser />);

    await waitFor(
      () => expect(screen.getByText(/invalid gcs bucket name/i)).toBeInTheDocument(),
      { timeout: 1500 },
    );
  });
});

describe("GCSBucketInput", () => {
  afterEach(() => {
    localStorage.clear();
  });

  it("strips gs:// prefix when typing", async () => {
    const onBucketChange = vi.fn();
    render(<GCSBucketInput onBucketChange={onBucketChange} onBrowse={vi.fn()} />);
    const input = screen.getByPlaceholderText(/bucket-name/i);
    await userEvent.type(input, "gs://my-bucket");
    expect(input).toHaveValue("my-bucket");
    expect(onBucketChange).toHaveBeenLastCalledWith("my-bucket");
  });

  it("persists bucket name in localStorage", async () => {
    const onBucketChange = vi.fn();
    render(<GCSBucketInput onBucketChange={onBucketChange} onBrowse={vi.fn()} />);
    const input = screen.getByPlaceholderText(/bucket-name/i);
    await userEvent.type(input, "my-bucket");
    expect(localStorage.getItem("ap-gcs-user-bucket")).toBe("my-bucket");
  });

  it("loads persisted bucket from localStorage on mount", () => {
    localStorage.setItem("ap-gcs-user-bucket", "saved-bucket");
    const onBucketChange = vi.fn();
    render(<GCSBucketInput onBucketChange={onBucketChange} onBrowse={vi.fn()} />);
    const input = screen.getByPlaceholderText(/bucket-name/i);
    expect(input).toHaveValue("saved-bucket");
    expect(onBucketChange).toHaveBeenCalledWith("saved-bucket");
  });

  it("clears input and localStorage when Clear is clicked", async () => {
    localStorage.setItem("ap-gcs-user-bucket", "my-bucket");
    const onBucketChange = vi.fn();
    render(<GCSBucketInput onBucketChange={onBucketChange} onBrowse={vi.fn()} />);

    const clearBtn = screen.getByLabelText("Clear bucket");
    await userEvent.click(clearBtn);
    const input = screen.getByPlaceholderText(/bucket-name/i);
    expect(input).toHaveValue("");
    expect(localStorage.getItem("ap-gcs-user-bucket")).toBeNull();
  });
});
