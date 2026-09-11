/**
 * API keys: the browser's copy, the store around it, and the panel that edits it.
 *
 * The properties worth pinning: storage round-trips and tolerates junk, the
 * globe gate follows the browser's copy, notices follow the server's report
 * and stay quiet until that report arrives, and the panel never leaks a
 * value into the DOM as plain text unless asked.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { KEY_NAMES, emptyKeys, readKeys, writeKeys } from "@/lib/keys";
import { KeyNotice } from "@/shell/KeyNotice";
import { SettingsPanel } from "@/shell/SettingsPanel";
import { useKeysStore } from "@/stores/keys";

function statusEnvelope(configured: Partial<Record<string, boolean>>) {
  const keys = Object.fromEntries(
    KEY_NAMES.map((n) => [n, { configured: Boolean(configured[n]), unlocks: "x" }]),
  );
  return { data: { keys, all_configured: false } };
}

beforeEach(() => {
  localStorage.clear();
  useKeysStore.setState({ keys: emptyKeys(), status: null, offline: false, panelOpen: false });
});
afterEach(() => vi.restoreAllMocks());

describe("keys storage", () => {
  it("round-trips through local storage and trims", () => {
    writeKeys({ ...emptyKeys(), waqi_token: "  tok  " });
    expect(readKeys().waqi_token).toBe("tok");
  });

  it("returns empty keys for missing or malformed storage", () => {
    expect(readKeys()).toEqual(emptyKeys());
    localStorage.setItem("wildfireiq.keys.v1", "{not json");
    expect(readKeys()).toEqual(emptyKeys());
    localStorage.setItem("wildfireiq.keys.v1", JSON.stringify({ waqi_token: 42, bogus: "x" }));
    expect(readKeys()).toEqual(emptyKeys());
  });
});

describe("keys store", () => {
  it("syncs by pushing local keys when any are set, else by fetching status", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify(statusEnvelope({ waqi_token: true }))));

    await useKeysStore.getState().sync();
    expect(fetchMock.mock.calls[0][1]?.method).toBeUndefined(); // plain GET

    useKeysStore.setState({ keys: { ...emptyKeys(), waqi_token: "t" } });
    await useKeysStore.getState().sync();
    expect(fetchMock.mock.calls[1][1]?.method).toBe("PUT");
    expect(useKeysStore.getState().status?.waqi_token).toBe(true);
  });

  it("marks the store offline when the API cannot be reached", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    await useKeysStore.getState().sync();
    expect(useKeysStore.getState().offline).toBe(true);
  });

  it("still saves locally when the API is down, and says so", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const result = await useKeysStore.getState().save({ ...emptyKeys(), firms_map_key: "k" });
    expect(result.ok).toBe(false);
    expect(readKeys().firms_map_key).toBe("k");
    if (!result.ok) expect(result.message).toMatch(/saved in this browser/i);
  });
});

describe("KeyNotice", () => {
  it("stays silent until the server has reported", () => {
    const { container } = render(<KeyNotice keyName="firms_map_key" what="Hotspots" />);
    expect(container.innerHTML).toBe("");
  });

  it("appears when the server says the key is missing, and opens settings", () => {
    useKeysStore.setState({ status: { ...emptyKeys(), firms_map_key: false } as never });
    render(<KeyNotice keyName="firms_map_key" what="Hotspots" />);
    expect(screen.getByText(/hotspots needs a nasa firms key/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /enter key/i }));
    expect(useKeysStore.getState().panelOpen).toBe(true);
  });

  it("disappears once the key is configured", () => {
    useKeysStore.setState({ status: { ...emptyKeys(), firms_map_key: true } as never });
    const { container } = render(<KeyNotice keyName="firms_map_key" what="Hotspots" />);
    expect(container.innerHTML).toBe("");
  });
});

describe("SettingsPanel", () => {
  it("renders nothing while closed", () => {
    const { container } = render(<SettingsPanel />);
    expect(container.innerHTML).toBe("");
  });

  it("masks values by default and shows them on request", () => {
    useKeysStore.setState({ panelOpen: true, keys: { ...emptyKeys(), waqi_token: "secret-1" } });
    render(<SettingsPanel />);
    const input = screen.getByLabelText(/WAQI token/i) as HTMLInputElement;
    expect(input.type).toBe("password");
    expect(document.body.textContent).not.toContain("secret-1");
    fireEvent.click(screen.getAllByRole("button", { name: /show key/i })[2]);
    expect(input.type).toBe("text");
  });

  it("saves trimmed values and pushes them to the API", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify(statusEnvelope({ waqi_token: true }))));
    useKeysStore.setState({ panelOpen: true });
    render(<SettingsPanel />);

    fireEvent.change(screen.getByLabelText(/WAQI token/i), { target: { value: "  abc  " } });
    fireEvent.click(screen.getByRole("button", { name: /save keys/i }));
    await screen.findByText(/saved\./i);

    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body.waqi_token).toBe("abc");
    expect(readKeys().waqi_token).toBe("abc");
  });

  it("closes on Escape", () => {
    useKeysStore.setState({ panelOpen: true });
    render(<SettingsPanel />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(useKeysStore.getState().panelOpen).toBe(false);
  });
});
