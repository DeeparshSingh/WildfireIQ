/**
 * Phase 5 state helpers — share encoder + streak rollover. Pure
 * functions, run in jsdom (no IndexedDB needed).
 */
import { describe, expect, it } from "vitest";

import {
  decodeShare,
  encodeShare,
  rolloverStreak,
} from "../../features/preparedness/state";
import type {
  PrepProfile,
  ProgressV1,
} from "../../features/preparedness/state";

const baseProfile: PrepProfile = {
  version: "1",
  neighbourhood: "Sahali",
  neighbourhoodLat: 50.6555,
  neighbourhoodLon: -120.365,
  dwelling: "house",
  season: "summer",
  situation: ["pets", "sensitive"],
  notify: { aqhiThreshold: 7, evacAlerts: true },
  createdAt: "2026-05-14T00:00:00.000Z",
};

const baseProgress: ProgressV1 = {
  version: "1",
  completedActions: [
    { id: "im_roof_debris", completedAt: "2026-05-14", hasPhoto: true },
    { id: "im_no_combustibles", completedAt: "2026-05-13", hasPhoto: false },
  ],
  shared: false,
  smokeAware: false,
  streakDays: 3,
  lastVisitDay: "2026-05-14",
  lastEvacStatus: null,
  earnedAchievements: ["first_steps", "ember_aware"],
};

describe("encodeShare / decodeShare", () => {
  it("round-trips a profile + progress through the URL hash", () => {
    const hash = encodeShare(baseProfile, baseProgress);
    expect(typeof hash).toBe("string");
    expect(hash.length).toBeGreaterThan(20);

    const decoded = decodeShare(hash);
    expect(decoded).not.toBeNull();
    expect(decoded!.p.neighbourhood).toBe("Sahali");
    expect(decoded!.p.situation).toEqual(["pets", "sensitive"]);
    expect(decoded!.g.completedActions).toHaveLength(2);
    expect(decoded!.g.earnedAchievements).toContain("first_steps");
  });

  it("strips photo blobs from the encoded payload", () => {
    const hash = encodeShare(baseProfile, baseProgress);
    const decoded = decodeShare(hash);
    // hasPhoto must be false in the shared payload regardless of source.
    expect(decoded!.g.completedActions.every((c) => c.hasPhoto === false)).toBe(true);
  });

  it("returns null for garbage input", () => {
    expect(decodeShare("not_valid_base64!!!")).toBeNull();
  });
});

describe("rolloverStreak", () => {
  it("no-ops when lastVisitDay === today", () => {
    const today = new Date().toISOString().slice(0, 10);
    const next = rolloverStreak({ ...baseProgress, lastVisitDay: today, streakDays: 5 });
    expect(next.streakDays).toBe(5);
  });

  it("increments when yesterday was the last visit", () => {
    const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
    const next = rolloverStreak({ ...baseProgress, lastVisitDay: yesterday, streakDays: 4 });
    expect(next.streakDays).toBe(5);
  });

  it("resets to 1 on a longer gap", () => {
    const next = rolloverStreak({ ...baseProgress, lastVisitDay: "2020-01-01", streakDays: 30 });
    expect(next.streakDays).toBe(1);
  });
});
