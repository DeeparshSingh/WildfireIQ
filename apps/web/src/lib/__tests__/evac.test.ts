/**
 * Evac helpers — past-zone predicate + newest-first sort. Pure functions.
 */
import { describe, expect, it } from "vitest";

import { isPastEvac, sortEvacByDateDesc, type EvacZone } from "../api/hooks";

function zone(partial: Partial<EvacZone>): EvacZone {
  return {
    event_id: null,
    event_name: null,
    status: null,
    issuing_agency: null,
    issued_utc: null,
    area_hectares: null,
    geom_wkt: null,
    fetched_at_utc: "2026-05-28T00:00:00Z",
    ...partial,
  };
}

describe("isPastEvac", () => {
  it("treats rescinded zones as past", () => {
    expect(isPastEvac(zone({ status: "Rescind" }))).toBe(true);
    expect(isPastEvac(zone({ status: "rescinded" }))).toBe(true);
  });
  it("treats active orders/alerts as not past", () => {
    expect(isPastEvac(zone({ status: "Order" }))).toBe(false);
    expect(isPastEvac(zone({ status: "Alert" }))).toBe(false);
    expect(isPastEvac(zone({ status: null }))).toBe(false);
  });
});

describe("sortEvacByDateDesc", () => {
  it("orders newest issued first and sinks nulls", () => {
    const zones = [
      zone({ event_name: "old", issued_utc: "2026-01-01T00:00:00Z" }),
      zone({ event_name: "new", issued_utc: "2026-05-20T00:00:00Z" }),
      zone({ event_name: "nodate", issued_utc: null }),
      zone({ event_name: "mid", issued_utc: "2026-03-15T00:00:00Z" }),
    ];
    const out = sortEvacByDateDesc(zones).map((z) => z.event_name);
    expect(out).toEqual(["new", "mid", "old", "nodate"]);
  });
  it("does not mutate the input array", () => {
    const zones = [
      zone({ event_name: "a", issued_utc: "2026-01-01T00:00:00Z" }),
      zone({ event_name: "b", issued_utc: "2026-02-01T00:00:00Z" }),
    ];
    const copy = [...zones];
    sortEvacByDateDesc(zones);
    expect(zones).toEqual(copy);
  });
});
