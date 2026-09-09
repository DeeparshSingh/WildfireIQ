/**
 * The banner that tells a reader a data source did not load.
 *
 * The case worth pinning is the paused one. TanStack suspends a query's
 * retries when it decides the network is unavailable, and a suspended query
 * reports `isError: false` and `status: "pending"` — forever. A notice keyed
 * only on `isError` renders nothing in exactly that situation, which is the
 * one a reader is most likely to hit: a dropped connection, a captive portal,
 * a backend that has not finished starting.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { ApiResponseError, ApiUnreachableError } from "@/lib/api/client";
import { DataNotice, type NoticeQuery } from "@/shell/DataNotice";

function q(over: Partial<NoticeQuery> = {}): NoticeQuery {
  return {
    isError: false,
    error: null,
    isFetching: false,
    fetchStatus: "idle",
    refetch: vi.fn(),
    ...over,
  };
}

function mount(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("DataNotice", () => {
  it("renders nothing while every source is healthy", () => {
    const { container } = mount(<DataNotice queries={[q(), q()]} what="air-quality data" />);
    expect(container.innerHTML).toBe("");
  });

  it("reports a paused query, which never reaches isError", () => {
    mount(<DataNotice queries={[q({ fetchStatus: "paused" })]} what="air-quality data" />);
    expect(screen.getByText(/waiting for a connection/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
  });

  it("names the backend when it is unreachable", () => {
    const query = q({ isError: true, error: new ApiUnreachableError("/api/aq/current", null) });
    mount(<DataNotice queries={[query]} what="air-quality data" />);
    expect(screen.getByText(/cannot reach the wildfireiq api/i)).toBeTruthy();
  });

  it("distinguishes a server error from an unreachable server", () => {
    const query = q({ isError: true, error: new ApiResponseError("/api/aq/current", 500) });
    mount(<DataNotice queries={[query]} what="air-quality data" />);
    expect(screen.getByText(/could not load air-quality data/i)).toBeTruthy();
    expect(screen.queryByText(/cannot reach/i)).toBeNull();
  });

  it("counts only the sources that are actually in trouble", () => {
    const queries = [
      q(),
      q({ isError: true, error: new ApiResponseError("/a", 500) }),
      q({ isError: true, error: new ApiResponseError("/b", 503) }),
    ];
    mount(<DataNotice queries={queries} what="air-quality data" />);
    expect(screen.getByText(/2 of this page's data sources/i)).toBeTruthy();
  });

  it("disables the retry button while a retry is in flight", () => {
    const query = q({ isError: true, error: new Error("x"), isFetching: true });
    mount(<DataNotice queries={[query]} what="air-quality data" />);
    const button = screen.getByRole("button") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.textContent).toMatch(/retrying/i);
  });

  it("is an <output>, so a screen reader announces it when it appears", () => {
    const { container } = mount(
      <DataNotice queries={[q({ fetchStatus: "paused" })]} what="air-quality data" />,
    );
    expect(container.querySelector("output")).not.toBeNull();
  });
});
