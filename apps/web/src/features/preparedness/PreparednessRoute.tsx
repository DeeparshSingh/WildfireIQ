/**
 * /preparedness — Phase 5 orchestrator.
 *
 * Layout (12-col):
 *   ┌──────────┬───────────────────┬──────────┐
 *   │ LiveStat │ Checklist         │ Progress │
 *   │  (4)     │  (5)              │   (3)    │
 *   └──────────┴───────────────────┴──────────┘
 *
 * On iPad portrait + narrow viewports it stacks to a single column.
 *
 * State flow:
 *   • Profile (localStorage)  : neighbourhood, dwelling, season, situation, notify
 *   • Progress (localStorage) : completed actions, streak, flags
 *   • Photos (IndexedDB)      : per-action photo blobs (set + cleared in Checklist)
 *   • Network                 : checklist + evac/check + AQHI + FWI + season-context
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { useAqCurrent, useEvacCheck, useFireSmartChecklist } from "@/lib/api/hooks";

import { Checklist } from "./Checklist";
import { Confetti } from "./Confetti";
import { LiveStatusPanel } from "./LiveStatusPanel";
import { OnboardingWizard } from "./OnboardingWizard";
import { ProgressPanel } from "./ProgressPanel";
import {
  clearProfile,
  encodeShare,
  loadProfile,
  loadProgress,
  notify,
  rolloverStreak,
  saveProfile,
  saveProgress,
  type PrepProfile,
  type ProgressV1,
} from "./state";

export function PreparednessRoute() {
  const [profile, setProfile] = useState<PrepProfile | null>(() => loadProfile());
  const [progress, setProgress] = useState<ProgressV1>(() => rolloverStreak(loadProgress()));
  const [confettiTick, setConfettiTick] = useState(0);
  const [shareLink, setShareLink] = useState<string | null>(null);

  // Persist on every change.
  useEffect(() => saveProgress(progress), [progress]);
  useEffect(() => {
    if (profile) saveProfile(profile);
  }, [profile]);

  // Server-filtered checklist (drives points + total).
  const sit = useMemo(() => profile?.situation ?? [], [profile]);
  const mappedSit = useMemo(
    () =>
      sit.map((s) =>
        s === "house_yard"
          ? "any"
          : s,
      ),
    [sit],
  );
  const checklist = useFireSmartChecklist(
    profile?.dwelling ?? "house",
    profile?.season ?? "summer",
    mappedSit,
  );
  const actions = checklist.data?.actions ?? [];

  const completedSet = useMemo(
    () => new Set(progress.completedActions.map((c) => c.id)),
    [progress.completedActions],
  );
  const photoIds = useMemo(
    () => new Set(progress.completedActions.filter((c) => c.hasPhoto).map((c) => c.id)),
    [progress.completedActions],
  );

  const stats = useMemo(() => {
    const total = actions.length;
    const done = actions.filter((a) => completedSet.has(a.id)).length;
    const pts = actions
      .filter((a) => completedSet.has(a.id))
      .reduce((a, b) => a + b.points, 0);
    const max = actions.reduce((a, b) => a + b.points, 0);
    return { total, done, pts, max };
  }, [actions, completedSet]);

  // ─── Achievement rules (client mirror of backend) ─────────────────────
  const photosCount = progress.completedActions.filter((c) => c.hasPhoto).length;
  const earnedNow = useMemo(() => {
    const e = new Set<string>();
    if (stats.done >= 1) e.add("first_steps");
    if (stats.done >= 5) e.add("ember_aware");
    if (stats.pts >= 25) e.add("defensible_space");
    if (stats.total > 0 && stats.done >= stats.total / 2) e.add("halfway");
    if (photosCount >= 5) e.add("photo_documentarian");
    if (progress.smokeAware) e.add("smoke_aware");
    if (progress.streakDays >= 7) e.add("streak_7");
    if (progress.streakDays >= 30) e.add("streak_30");
    if (progress.shared) e.add("neighbour");
    if (stats.total > 0 && stats.done === stats.total) e.add("firesmart_home");

    // Zone 1 hero
    const z1 = actions.filter((a) => a.zone === "immediate");
    if (z1.length > 0 && z1.every((a) => completedSet.has(a.id))) e.add("zone_one_hero");

    // Storm ready — Plan & Go-Bag complete before July 1
    const pg = actions.filter((a) => a.zone === "plan_gobag");
    const now = new Date();
    const beforeJuly = now.getMonth() < 6; // Jan-Jun
    if (pg.length > 0 && pg.every((a) => completedSet.has(a.id)) && beforeJuly) {
      e.add("storm_ready");
    }
    return e;
  }, [stats, actions, completedSet, photosCount, progress]);

  // Fire confetti once per newly-earned badge.
  useEffect(() => {
    const already = new Set(progress.earnedAchievements);
    const fresh: string[] = [];
    earnedNow.forEach((id) => {
      if (!already.has(id)) fresh.push(id);
    });
    if (fresh.length > 0) {
      setProgress((p) => ({ ...p, earnedAchievements: [...p.earnedAchievements, ...fresh] }));
      setConfettiTick((t) => t + 1);
    }
  }, [earnedNow]);

  // ─── Smoke-aware flag: flip on if user is here while AQHI ≥ 7 ──────
  const aq = useAqCurrent();
  const aqhi =
    aq.data?.stations.find((s) => s.station_name?.toLowerCase().includes("kamloops"))?.aqhi ??
    aq.data?.stations[0]?.aqhi ??
    null;
  useEffect(() => {
    if (!progress.smokeAware && typeof aqhi === "number" && aqhi >= 7) {
      setProgress((p) => ({ ...p, smokeAware: true }));
    }
  }, [aqhi, progress.smokeAware]);

  // ─── Evac state-change Web Notification ───────────────────────────────
  const evac = useEvacCheck(
    profile?.neighbourhoodLat ?? null,
    profile?.neighbourhoodLon ?? null,
  );
  const lastStatusRef = useRef<typeof progress.lastEvacStatus>(progress.lastEvacStatus);
  useEffect(() => {
    const cur = evac.data?.status ?? null;
    if (!cur) return;
    const last = lastStatusRef.current;
    if (
      profile?.notify.evacAlerts &&
      last !== cur &&
      (cur === "alert" || cur === "order") &&
      last !== "order" // don't re-notify if escalating from order
    ) {
      notify(
        cur === "order" ? "Evacuation Order issued" : "Evacuation Alert issued",
        `${profile.neighbourhood ?? "Your area"} is now in an active ${cur}. Open WildfireIQ for details.`,
      );
    }
    lastStatusRef.current = cur;
    if (progress.lastEvacStatus !== cur) {
      setProgress((p) => ({ ...p, lastEvacStatus: cur }));
    }
  }, [evac.data?.status, profile]);

  // ─── Mutations ───────────────────────────────────────────────────────
  const toggle = (id: string) =>
    setProgress((p) => {
      const has = p.completedActions.some((c) => c.id === id);
      if (has) {
        return { ...p, completedActions: p.completedActions.filter((c) => c.id !== id) };
      }
      return {
        ...p,
        completedActions: [
          ...p.completedActions,
          { id, completedAt: new Date().toISOString(), hasPhoto: false },
        ],
      };
    });

  const setPhoto = (id: string) =>
    setProgress((p) => ({
      ...p,
      completedActions: p.completedActions.map((c) =>
        c.id === id ? { ...c, hasPhoto: true } : c,
      ),
    }));
  const clearPhotoFlag = (id: string) =>
    setProgress((p) => ({
      ...p,
      completedActions: p.completedActions.map((c) =>
        c.id === id ? { ...c, hasPhoto: false } : c,
      ),
    }));

  const onShare = () => {
    if (!profile) return;
    setProgress((p) => ({ ...p, shared: true }));
    const hash = encodeShare(profile, { ...progress, shared: true });
    const url = `${window.location.origin}/preparedness/shared#${hash}`;
    setShareLink(url);
    try {
      navigator.clipboard?.writeText(url);
    } catch {
      /* noop */
    }
  };

  const onReset = () => {
    if (!confirm("Reset your profile, progress, and badges? Photos will also be deleted.")) return;
    clearProfile();
    setProfile(null);
    setProgress({
      version: "1",
      completedActions: [],
      shared: false,
      smokeAware: false,
      streakDays: 0,
      lastVisitDay: new Date().toISOString().slice(0, 10),
      lastEvacStatus: null,
      earnedAchievements: [],
    });
  };

  // ─── Render ──────────────────────────────────────────────────────────
  if (!profile) {
    return <OnboardingWizard onComplete={(p) => setProfile(p)} />;
  }

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        overflowY: "auto",
        pointerEvents: "auto",
        padding: "32px 48px 80px",
        background:
          "radial-gradient(ellipse at top, hsl(220 25% 6% / 0.92), hsl(220 30% 2% / 0.96) 80%)",
      }}
    >
      <Confetti trigger={confettiTick} />

      <div style={{ maxWidth: 1320, margin: "0 auto" }}>
        <Header profile={profile} setProfile={setProfile} />

        {shareLink && (
          <ShareBanner url={shareLink} onClose={() => setShareLink(null)} />
        )}

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(240px, 320px) 1fr minmax(260px, 320px)",
            gap: 20,
            alignItems: "start",
            marginTop: 20,
          }}
          className="prep-grid"
        >
          <LiveStatusPanel
            lat={profile.neighbourhoodLat ?? 50.6745}
            lon={profile.neighbourhoodLon ?? -120.3273}
            neighbourhood={profile.neighbourhood}
          />

          <main>
            <Checklist
              dwelling={profile.dwelling}
              season={profile.season}
              situation={profile.situation}
              completedIds={completedSet}
              photoIds={photoIds}
              onToggle={toggle}
              onPhotoSet={setPhoto}
              onPhotoCleared={clearPhotoFlag}
            />
          </main>

          <ProgressPanel
            points={stats.pts}
            maxPoints={stats.max}
            completed={stats.done}
            total={stats.total}
            streak={progress.streakDays}
            earnedIds={new Set(progress.earnedAchievements)}
            onShare={onShare}
            onReset={onReset}
          />
        </div>

        <PrivacyFooter />
      </div>

      <style>{`
        @media (max-width: 1100px) {
          .prep-grid { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </div>
  );
}

// ─── Header strip ──────────────────────────────────────────────────────

function Header({
  profile,
  setProfile,
}: {
  profile: PrepProfile;
  setProfile: (p: PrepProfile) => void;
}) {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "flex-end",
        justifyContent: "space-between",
        gap: 20,
        flexWrap: "wrap",
      }}
    >
      <div>
        <div
          style={{
            fontFamily: "var(--font-data)",
            fontSize: 11,
            letterSpacing: "0.28em",
            textTransform: "uppercase",
            color: "var(--color-cyan-glow)",
          }}
        >
          Community Preparedness Hub
        </div>
        <h1
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "clamp(1.8rem, 3.2vw, 2.5rem)",
            fontWeight: 700,
            letterSpacing: "-0.03em",
            margin: "8px 0 0",
            color: "var(--color-text-hi)",
            lineHeight: 1.05,
          }}
        >
          {profile.neighbourhood ?? "Kamloops"} · {profile.dwelling}
        </h1>
        <p
          style={{
            fontFamily: "var(--font-body)",
            fontSize: 13,
            color: "var(--color-text-mid)",
            margin: "8px 0 0",
          }}
        >
          Tailored checklist · live evac · all on this device
        </p>
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        <select
          value={profile.season}
          onChange={(e) => setProfile({ ...profile, season: e.target.value as PrepProfile["season"] })}
          style={selectStyle}
        >
          <option value="any">All year</option>
          <option value="spring">Spring</option>
          <option value="summer">Summer</option>
          <option value="fall">Fall</option>
        </select>
        <select
          value={profile.dwelling}
          onChange={(e) => setProfile({ ...profile, dwelling: e.target.value as PrepProfile["dwelling"] })}
          style={selectStyle}
        >
          <option value="house">Detached house</option>
          <option value="townhome">Townhome / apartment</option>
          <option value="cabin">Cabin / rural</option>
          <option value="mobile">Mobile home</option>
        </select>
      </div>
    </header>
  );
}

function ShareBanner({ url, onClose }: { url: string; onClose: () => void }) {
  return (
    <div
      style={{
        marginTop: 16,
        padding: 14,
        background: "hsl(45 95% 58% / 0.10)",
        border: "1px solid hsl(45 95% 58% / 0.45)",
        borderRadius: "var(--radius-lg)",
        display: "flex",
        gap: 12,
        alignItems: "center",
      }}
    >
      <span style={{ fontSize: 18 }}>🔗</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: "var(--font-body)", fontSize: 13, color: "var(--color-text-hi)" }}>
          Share link copied. Your progress is encoded in the URL — no server stores it.
        </div>
        <div
          style={{
            fontFamily: "var(--font-data)",
            fontSize: 10,
            color: "var(--color-text-mid)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
          title={url}
        >
          {url}
        </div>
      </div>
      <button
        type="button"
        onClick={onClose}
        style={{
          background: "transparent",
          color: "var(--color-text-mid)",
          border: "1px solid hsl(200 80% 50% / 0.2)",
          borderRadius: 8,
          padding: "6px 12px",
          fontSize: 12,
          cursor: "pointer",
        }}
      >
        Dismiss
      </button>
    </div>
  );
}

function PrivacyFooter() {
  return (
    <p
      style={{
        marginTop: 32,
        padding: 14,
        borderRadius: 12,
        background: "hsl(220 30% 8% / 0.4)",
        border: "1px dashed hsl(200 80% 50% / 0.2)",
        fontFamily: "var(--font-body)",
        fontSize: 11,
        lineHeight: 1.6,
        color: "var(--color-text-mid)",
        textAlign: "center",
      }}
    >
      <strong style={{ color: "var(--color-text-hi)" }}>Private by design.</strong>{" "}
      Profile + progress in localStorage. Photos in IndexedDB. Coordinates
      are sent to the backend only for the polygon lookup that powers the
      evac widget — never stored or logged with an identifier.
    </p>
  );
}

const selectStyle: React.CSSProperties = {
  background:
    // custom chevron drawn as inline SVG; native arrow hidden via -webkit-appearance:none
    "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M1 1l4 4 4-4' stroke='%2399aabb' stroke-width='1.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/></svg>\") no-repeat right 12px center / 10px 6px, hsl(220 30% 8% / 0.85)",
  color: "var(--color-text-hi)",
  border: "1px solid hsl(200 80% 50% / 0.25)",
  borderRadius: 8,
  padding: "8px 32px 8px 12px",
  fontFamily: "var(--font-body)",
  fontSize: 13,
  appearance: "none",
  WebkitAppearance: "none",
  MozAppearance: "none",
  cursor: "pointer",
};
