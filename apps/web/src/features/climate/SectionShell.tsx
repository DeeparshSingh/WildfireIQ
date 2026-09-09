/**
 * Common scaffolding for each climate section — kicker label, headline,
 * subhead, info chip slot, scroll-trigger fade-in.
 */
import { type ReactNode, useEffect, useRef, useState } from "react";

import { DataNotice, type NoticeQuery } from "@/shell/DataNotice";

export function SectionShell({
  kicker,
  title,
  sub,
  info,
  queries,
  children,
}: {
  kicker: string;
  title: string;
  sub?: string;
  info?: ReactNode;
  /** The section's data sources, so it can say when one did not load. */
  queries?: NoticeQuery[];
  children: ReactNode;
}) {
  const ref = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          io.disconnect();
        }
      },
      { threshold: 0.15 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <section
      ref={ref}
      style={{
        padding: "64px 0 32px",
        opacity: visible ? 1 : 0,
        transform: visible ? "translateY(0)" : "translateY(24px)",
        transition:
          "opacity 600ms var(--ease-out-expo, ease), transform 600ms var(--ease-out-expo, ease)",
      }}
    >
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          gap: 16,
          flexWrap: "wrap",
          marginBottom: 24,
        }}
      >
        <div style={{ maxWidth: 720 }}>
          <div
            style={{
              fontFamily: "var(--font-data)",
              fontSize: 11,
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--color-cyan-glow)",
            }}
          >
            {kicker}
          </div>
          <h2
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "clamp(1.8rem, 3.2vw, 2.6rem)",
              fontWeight: 700,
              letterSpacing: "-0.03em",
              margin: "8px 0 0",
              color: "var(--color-text-hi)",
              lineHeight: 1.05,
            }}
          >
            {title}
          </h2>
          {sub && (
            <p
              style={{
                fontFamily: "var(--font-body)",
                fontSize: 14,
                lineHeight: 1.6,
                color: "var(--color-text-mid)",
                margin: "10px 0 0",
              }}
            >
              {sub}
            </p>
          )}
        </div>
        {info}
      </header>
      {queries && <DataNotice queries={queries} what={title.toLowerCase()} />}
      {children}
    </section>
  );
}
