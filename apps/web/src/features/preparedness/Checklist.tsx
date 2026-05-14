/**
 * Middle column — the actionable checklist. Groups actions by HIZ zone,
 * supports per-item photo capture (stored in IndexedDB, never sent), and
 * an expandable "why this matters" details row.
 */
import { useEffect, useRef, useState } from "react";

import {
  useFireSmartChecklist,
  type FireSmartAction,
  type FireSmartGroup,
} from "@/lib/api/hooks";

import {
  deletePhoto,
  getPhoto,
  putPhoto,
  type Dwelling,
  type Season,
  type SituationId,
} from "./state";

export function Checklist({
  dwelling,
  season,
  situation,
  completedIds,
  photoIds,
  onToggle,
  onPhotoSet,
  onPhotoCleared,
}: {
  dwelling: Dwelling;
  season: Season;
  situation: SituationId[];
  completedIds: Set<string>;
  photoIds: Set<string>;
  onToggle: (id: string) => void;
  onPhotoSet: (id: string) => void;
  onPhotoCleared: (id: string) => void;
}) {
  // Map our wizard situation ids onto backend filter keys.
  const mappedSit = situation.map((s) =>
    s === "house_yard"
      ? "any"
      : s === "renter"
      ? "renter"
      : s === "pets"
      ? "pets"
      : s === "sensitive"
      ? "sensitive"
      : s === "outdoor_worker"
      ? "outdoor_worker"
      : s === "mobility"
      ? "mobility"
      : s,
  );

  const checklist = useFireSmartChecklist(dwelling, season, mappedSit);
  const groups = checklist.data?.groups ?? [];
  const actions = checklist.data?.actions ?? [];

  if (checklist.isLoading) {
    return (
      <div style={{ padding: 24, color: "var(--color-text-mid)" }}>
        Loading your tailored checklist…
      </div>
    );
  }

  return (
    <section style={{ display: "grid", gap: 16 }}>
      {groups.map((g) => {
        const groupActions = actions.filter((a) => a.zone === g.id);
        if (groupActions.length === 0) return null;
        return (
          <ZoneCard
            key={g.id}
            group={g}
            actions={groupActions}
            completedIds={completedIds}
            photoIds={photoIds}
            onToggle={onToggle}
            onPhotoSet={onPhotoSet}
            onPhotoCleared={onPhotoCleared}
          />
        );
      })}
    </section>
  );
}

function ZoneCard({
  group,
  actions,
  completedIds,
  photoIds,
  onToggle,
  onPhotoSet,
  onPhotoCleared,
}: {
  group: FireSmartGroup;
  actions: FireSmartAction[];
  completedIds: Set<string>;
  photoIds: Set<string>;
  onToggle: (id: string) => void;
  onPhotoSet: (id: string) => void;
  onPhotoCleared: (id: string) => void;
}) {
  const done = actions.filter((a) => completedIds.has(a.id)).length;
  return (
    <section
      className="glass"
      style={{
        padding: 20,
        borderRadius: "var(--radius-lg)",
        display: "grid",
        gap: 12,
      }}
    >
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div>
          <h2
            style={{
              fontFamily: "var(--font-display)",
              fontSize: 20,
              fontWeight: 600,
              color: "var(--color-text-hi)",
              margin: 0,
            }}
          >
            {group.label}
          </h2>
          <div
            style={{
              fontFamily: "var(--font-data)",
              fontSize: 11,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: "var(--color-cyan-glow)",
              marginTop: 4,
            }}
          >
            {group.distance}
          </div>
        </div>
        <span style={{ fontFamily: "var(--font-data)", fontSize: 12, color: "var(--color-text-mid)" }}>
          {done} / {actions.length}
        </span>
      </header>

      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
        {actions.map((a) => (
          <ActionRow
            key={a.id}
            action={a}
            isDone={completedIds.has(a.id)}
            hasPhoto={photoIds.has(a.id)}
            onToggle={() => onToggle(a.id)}
            onPhotoSet={() => onPhotoSet(a.id)}
            onPhotoCleared={() => onPhotoCleared(a.id)}
          />
        ))}
      </ul>
    </section>
  );
}

function ActionRow({
  action,
  isDone,
  hasPhoto,
  onToggle,
  onPhotoSet,
  onPhotoCleared,
}: {
  action: FireSmartAction;
  isDone: boolean;
  hasPhoto: boolean;
  onToggle: () => void;
  onPhotoSet: () => void;
  onPhotoCleared: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!hasPhoto) {
      setPhotoUrl(null);
      return;
    }
    let url: string | null = null;
    let cancelled = false;
    getPhoto(action.id).then((blob) => {
      if (cancelled || !blob) return;
      url = URL.createObjectURL(blob);
      setPhotoUrl(url);
    });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [action.id, hasPhoto]);

  const onFile = async (file: File) => {
    await putPhoto(action.id, file);
    onPhotoSet();
  };

  const clearPhoto = async () => {
    await deletePhoto(action.id);
    onPhotoCleared();
  };

  return (
    <li>
      <div
        style={{
          padding: "12px 14px",
          borderRadius: 10,
          background: isDone ? "hsl(150 60% 40% / 0.12)" : "hsl(220 30% 10% / 0.6)",
          border: `1px solid ${isDone ? "hsl(150 70% 50% / 0.4)" : "hsl(200 80% 50% / 0.15)"}`,
        }}
      >
        <div style={{ display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 12, alignItems: "start" }}>
          <button
            type="button"
            onClick={onToggle}
            aria-label={isDone ? "Mark incomplete" : "Mark complete"}
            style={{
              width: 22,
              height: 22,
              marginTop: 2,
              borderRadius: 6,
              border: `1.5px solid ${isDone ? "hsl(150 70% 60%)" : "hsl(200 50% 60% / 0.5)"}`,
              background: isDone ? "hsl(150 70% 50%)" : "transparent",
              color: "white",
              fontSize: 14,
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            {isDone ? "✓" : ""}
          </button>
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            style={{
              textAlign: "left",
              background: "transparent",
              border: "none",
              padding: 0,
              cursor: "pointer",
              color: "var(--color-text-hi)",
            }}
          >
            <div
              style={{
                fontFamily: "var(--font-body)",
                fontSize: 14,
                fontWeight: 500,
                textDecoration: isDone ? "line-through" : "none",
                color: isDone ? "var(--color-text-mid)" : "var(--color-text-hi)",
              }}
            >
              {action.title}
            </div>
            <div
              style={{
                fontFamily: "var(--font-data)",
                fontSize: 11,
                color: "var(--color-text-mid)",
                marginTop: 4,
                display: "flex",
                gap: 12,
              }}
            >
              <span>
                {action.estimated_minutes ? `~${action.estimated_minutes} min` : "—"}
              </span>
              <span style={{ textTransform: "uppercase", letterSpacing: "0.12em" }}>
                {action.cost === "free" ? "free" : action.cost}
              </span>
              <span style={{ textTransform: "capitalize" }}>{action.category}</span>
              {open ? <span style={{ color: "var(--color-cyan-glow)" }}>hide why</span> : <span style={{ color: "var(--color-cyan-glow)" }}>why this matters →</span>}
            </div>
          </button>
          <span
            style={{
              fontFamily: "var(--font-data)",
              fontSize: 11,
              color: "var(--color-cyan-glow)",
              padding: "2px 8px",
              borderRadius: 999,
              background: "hsl(200 80% 50% / 0.1)",
              border: "1px solid hsl(200 80% 50% / 0.2)",
              whiteSpace: "nowrap",
            }}
          >
            +{action.points} pts
          </span>
        </div>

        {open && (
          <div
            style={{
              marginTop: 10,
              padding: 12,
              background: "hsl(220 30% 8% / 0.5)",
              borderRadius: 8,
              border: "1px dashed hsl(200 80% 50% / 0.2)",
            }}
          >
            <p style={{ fontFamily: "var(--font-body)", fontSize: 12, lineHeight: 1.6, color: "var(--color-text-mid)", margin: 0 }}>
              {action.why}
            </p>
          </div>
        )}

        {isDone && (
          <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 10 }}>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              capture="environment"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onFile(f);
              }}
            />
            {photoUrl ? (
              <>
                <img
                  src={photoUrl}
                  alt="proof"
                  style={{ width: 56, height: 56, objectFit: "cover", borderRadius: 8, border: "1px solid hsl(200 80% 50% / 0.3)" }}
                />
                <button
                  type="button"
                  onClick={clearPhoto}
                  style={smallBtn}
                >
                  Remove photo
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                style={smallBtn}
              >
                📷 Add photo
              </button>
            )}
            <span style={{ fontFamily: "var(--font-data)", fontSize: 10, color: "var(--color-text-mid)" }}>
              stored on this device only
            </span>
          </div>
        )}
      </div>
    </li>
  );
}

const smallBtn: React.CSSProperties = {
  background: "hsl(200 80% 50% / 0.12)",
  color: "var(--color-text-hi)",
  border: "1px solid hsl(200 80% 50% / 0.3)",
  borderRadius: 8,
  padding: "6px 12px",
  fontSize: 12,
  fontFamily: "var(--font-body)",
  cursor: "pointer",
};
