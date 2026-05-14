/**
 * Right column — score, badges (all 12), streak, share + reset.
 */
import { useFireSmartAchievements, type FireSmartAchievement } from "@/lib/api/hooks";

export function ProgressPanel({
  points,
  maxPoints,
  completed,
  total,
  streak,
  earnedIds,
  onShare,
  onReset,
}: {
  points: number;
  maxPoints: number;
  completed: number;
  total: number;
  streak: number;
  earnedIds: Set<string>;
  onShare: () => void;
  onReset: () => void;
}) {
  const pct = maxPoints > 0 ? Math.round((points / maxPoints) * 100) : 0;
  const allAchievements = useFireSmartAchievements();

  return (
    <aside style={{ display: "grid", gap: 16 }}>
      <SectionHeader>Your progress</SectionHeader>

      <section className="glass-strong" style={{ padding: 18, borderRadius: "var(--radius-lg)", display: "grid", gap: 12 }}>
        <div>
          <div style={{ fontFamily: "var(--font-data)", fontSize: 10, letterSpacing: "0.2em", textTransform: "uppercase", color: "var(--color-text-mid)" }}>
            FireSmart score
          </div>
          <div
            style={{
              fontFamily: "var(--font-display)",
              fontSize: 36,
              fontWeight: 700,
              color: "var(--color-text-hi)",
              lineHeight: 1,
              marginTop: 6,
            }}
          >
            {points}
            <span style={{ fontSize: 14, color: "var(--color-text-mid)", fontWeight: 400 }}> / {maxPoints} pts</span>
          </div>
          <div style={{ fontFamily: "var(--font-body)", fontSize: 12, color: "var(--color-text-mid)", marginTop: 4 }}>
            {completed} of {total} actions · {pct}%
          </div>
        </div>

        <div style={{ height: 8, background: "hsl(220 30% 12%)", borderRadius: 8, overflow: "hidden" }}>
          <div
            style={{
              width: `${pct}%`,
              height: "100%",
              background: "linear-gradient(90deg, hsl(150 70% 50%), hsl(180 75% 55%), hsl(200 90% 60%))",
              transition: "width 0.4s ease",
            }}
          />
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontFamily: "var(--font-data)",
            fontSize: 11,
            color: "var(--color-text-mid)",
          }}
        >
          <span>🔥 {streak} day streak</span>
          <span>{Math.max(0, total - completed)} to go</span>
        </div>
      </section>

      <section style={{ display: "grid", gap: 8 }}>
        <SectionHeader>Achievements</SectionHeader>
        <div style={{ display: "grid", gap: 8 }}>
          {(allAchievements.data ?? []).map((a) => (
            <BadgeRow key={a.id} achievement={a} earned={earnedIds.has(a.id)} />
          ))}
        </div>
      </section>

      <div style={{ display: "grid", gap: 8 }}>
        <button type="button" onClick={onShare} style={primaryBtn}>
          🔗 Share my progress
        </button>
        <button type="button" onClick={onReset} style={secondaryBtn}>
          Reset profile + progress
        </button>
      </div>
    </aside>
  );
}

function BadgeRow({ achievement, earned }: { achievement: FireSmartAchievement; earned: boolean }) {
  return (
    <div
      style={{
        padding: "10px 12px",
        borderRadius: 10,
        background: earned ? "hsl(45 95% 58% / 0.10)" : "hsl(220 30% 10% / 0.5)",
        border: `1px solid ${earned ? "hsl(45 95% 58% / 0.45)" : "hsl(200 80% 50% / 0.10)"}`,
        opacity: earned ? 1 : 0.55,
        display: "grid",
        gridTemplateColumns: "auto 1fr",
        gap: 10,
        alignItems: "center",
      }}
    >
      <span style={{ fontSize: 22 }}>{achievement.emoji}</span>
      <div>
        <div style={{ fontFamily: "var(--font-body)", fontSize: 13, fontWeight: 600, color: "var(--color-text-hi)" }}>
          {achievement.label}
        </div>
        <div style={{ fontFamily: "var(--font-body)", fontSize: 11, color: "var(--color-text-mid)", lineHeight: 1.4, marginTop: 2 }}>
          {achievement.blurb}
        </div>
      </div>
    </div>
  );
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: "var(--font-data)",
        fontSize: 11,
        letterSpacing: "0.28em",
        textTransform: "uppercase",
        color: "var(--color-text-mid)",
      }}
    >
      {children}
    </div>
  );
}

const primaryBtn: React.CSSProperties = {
  background: "hsl(18 95% 54%)",
  color: "white",
  border: "none",
  borderRadius: 8,
  padding: "10px 14px",
  fontFamily: "var(--font-body)",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
};
const secondaryBtn: React.CSSProperties = {
  background: "transparent",
  color: "var(--color-text-mid)",
  border: "1px solid hsl(200 80% 50% / 0.2)",
  borderRadius: 8,
  padding: "8px 12px",
  fontFamily: "var(--font-body)",
  fontSize: 12,
  cursor: "pointer",
};
