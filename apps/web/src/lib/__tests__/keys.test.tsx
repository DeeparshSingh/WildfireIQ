/**
 * API keys: the visitor's copy, the store around it, and the panel that edits it.
 *
 * The properties worth pinning: the browser's keys round-trip through storage
 * and never go to the server on their own; the owner's keys go to the server
 * only through a deliberate save, with the admin token when the deployment
 * has one; notices follow the server's report and stay quiet until it
 * arrives; and the panel never shows a value as plain text unless asked.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { emptyKeys, readKeys, writeKeys } from "@/lib/keys";
import { KeyNotice } from "@/shell/KeyNotice";
import { SettingsPanel } from "@/shell/SettingsPanel";
import { useKeysStore } from "@/stores/keys";

function statusEnvelope(configured: Partial<Record<string, boolean>>, writeProtected = false) {
  const keys = Object.fromEntries(
    ["firms_map_key", "waqi_token", "openrouter_api_key"].map((n) => [
      n,
      { configured: Boolean(configured[n]), unlocks: "x" },
    ]),
  );
  return { data: { keys, all_configured: false, write_protected: writeProtected } };
}
const serverStatus = (configured: Partial<Record<string, boolean>>, writeProtected = false) => ({
  keys: {
    firms_map_key: Boolean(configured.firms_map_key),
    waqi_token: Boolean(configured.waqi_token),
    openrouter_api_key: Boolean(configured.openrouter_api_key),
  },
  writeProtected,
});

beforeEach(() => {
  localStorage.clear();
  useKeysStore.setState({ keys: emptyKeys(), status: null, offline: false, panelOpen: false });
});
afterEach(() => vi.restoreAllMocks());

describe("keys storage", () => {
  it("round-trips the visitor's keys through local storage and trims", () => {
    writeKeys({ ...emptyKeys(), openrouter_api_key: "  sk  " });
    expect(readKeys().openrouter_api_key).toBe("sk");
  });

  it("returns empty keys for missing or malformed storage", () => {
    expect(readKeys()).toEqual(emptyKeys());
    localStorage.setItem("wildfireiq.keys.v1", "{not json");
    expect(readKeys()).toEqual(emptyKeys());
    localStorage.setItem("wildfireiq.keys.v1", JSON.stringify({ cesium_ion_token: 42 }));
    expect(readKeys()).toEqual(emptyKeys());
  });
});

describe("keys store", () => {
  it("sync only reads server status; it never pushes the visitor's keys", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify(statusEnvelope({ waqi_token: true }))));
    useKeysStore.setState({ keys: { ...emptyKeys(), openrouter_api_key: "sk-mine" } });
    await useKeysStore.getState().sync();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1]?.method).toBeUndefined();
    expect(useKeysStore.getState().status?.keys.waqi_token).toBe(true);
  });

  it("marks the store offline when the API cannot be reached", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    await useKeysStore.getState().sync();
    expect(useKeysStore.getState().offline).toBe(true);
  });

  it("saves the visitor's keys locally without any network call", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const result = useKeysStore
      .getState()
      .saveBrowserKeys({ ...emptyKeys(), openrouter_api_key: "sk-mine" });
    expect(result.ok).toBe(true);
    expect(readKeys().openrouter_api_key).toBe("sk-mine");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends server keys with the admin token and reports a rejected token", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify(statusEnvelope({ waqi_token: true }, true))),
      )
      .mockResolvedValueOnce(new Response("nope", { status: 401 }));
    const ok = await useKeysStore.getState().saveServerKeys({ waqi_token: "t" }, "owner-secret");
    expect(ok.ok).toBe(true);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("PUT");
    expect((init.headers as Record<string, string>)["X-Admin-Token"]).toBe("owner-secret");
    expect(JSON.parse(String(init.body))).toEqual({ waqi_token: "t" });

    const bad = await useKeysStore.getState().saveServerKeys({ waqi_token: "t" }, "guess");
    expect(bad.ok).toBe(false);
    if (!bad.ok) expect(bad.message).toMatch(/admin token did not match/i);
  });
});

describe("KeyNotice", () => {
  it("stays silent until the server has reported", () => {
    const { container } = render(<KeyNotice keyName="firms_map_key" what="Hotspots" />);
    expect(container.innerHTML).toBe("");
  });

  it("appears when the server says the key is missing, and opens settings", () => {
    useKeysStore.setState({ status: serverStatus({}) });
    render(<KeyNotice keyName="firms_map_key" what="Hotspots" />);
    expect(screen.getByText(/hotspots needs a nasa firms key/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /settings/i }));
    expect(useKeysStore.getState().panelOpen).toBe(true);
  });

  it("disappears once the key is configured", () => {
    useKeysStore.setState({ status: serverStatus({ firms_map_key: true }) });
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
    useKeysStore.setState({
      panelOpen: true,
      keys: { ...emptyKeys(), openrouter_api_key: "secret-1" },
    });
    render(<SettingsPanel />);
    const input = document.getElementById("key-openrouter_api_key") as HTMLInputElement;
    expect(input.type).toBe("password");
    expect(document.body.textContent).not.toContain("secret-1");
    fireEvent.click(screen.getByRole("button", { name: /^show openrouter api key$/i }));
    expect(input.type).toBe("text");
  });

  it("saves the visitor's keys to this browser only", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    useKeysStore.setState({ panelOpen: true });
    render(<SettingsPanel />);
    fireEvent.change(document.getElementById("key-openrouter_api_key") as HTMLInputElement, {
      target: { value: "  sk-mine  " },
    });
    fireEvent.click(screen.getByRole("button", { name: /save my keys/i }));
    expect(screen.getByText(/saved in this browser/i)).toBeTruthy();
    expect(readKeys().openrouter_api_key).toBe("sk-mine");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("asks for the admin token when the deployment is protected", () => {
    useKeysStore.setState({ panelOpen: true, status: serverStatus({}, true) });
    render(<SettingsPanel />);
    expect(screen.getByPlaceholderText(/required to change server keys/i)).toBeTruthy();
    expect(screen.queryByText(/no admin token/i)).toBeNull();
  });

  it("warns when the deployment has no admin token", () => {
    useKeysStore.setState({ panelOpen: true, status: serverStatus({}, false) });
    render(<SettingsPanel />);
    expect(screen.getByText(/no admin token/i)).toBeTruthy();
  });

  it("closes on Escape", () => {
    useKeysStore.setState({ panelOpen: true });
    render(<SettingsPanel />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(useKeysStore.getState().panelOpen).toBe(false);
  });
});
