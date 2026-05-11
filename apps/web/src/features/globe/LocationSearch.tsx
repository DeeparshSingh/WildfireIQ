import { useEffect, useMemo, useRef, useState } from "react";
import {
  Cartesian3,
  GeocodeType,
  IonGeocoderService,
  Math as CesiumMath,
  Rectangle,
} from "cesium";
// (Cartesian3 retained — geocoder Results can return either Cartesian3 or Rectangle types we test against.)
import type { Viewer as CesiumViewer } from "cesium";

import {
  cinematicFlyTo,
  cinematicFlyToRectangle,
} from "@/lib/cesium-helpers/cinematicFlyTo";

type Result = {
  displayName: string;
  destination: Cartesian3 | Rectangle;
};

function isRectangle(d: Cartesian3 | Rectangle): d is Rectangle {
  return d instanceof Rectangle;
}

/** Fly camera to a geocoder result with a cinematic arc. */
function flyToResult(viewer: CesiumViewer, r: Result) {
  if (isRectangle(r.destination)) {
    cinematicFlyToRectangle(viewer, r.destination);
  } else {
    const cart = viewer.scene.globe.ellipsoid.cartesianToCartographic(r.destination);
    const height = Math.max(cart.height || 0, 2_500); // 2.5 km default
    cinematicFlyTo(viewer, {
      lon: CesiumMath.toDegrees(cart.longitude),
      lat: CesiumMath.toDegrees(cart.latitude),
      height,
    });
  }
}

export function LocationSearch({ viewer }: { viewer: CesiumViewer | null }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Result[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Cesium Ion geocoder — Bing-backed, included with the Ion free tier.
  const geocoder = useMemo(() => {
    if (!viewer) return null;
    return new IonGeocoderService({ scene: viewer.scene });
  }, [viewer]);

  // Debounced autocomplete.
  useEffect(() => {
    if (!geocoder || !query.trim()) {
      setResults([]);
      return;
    }
    const trimmed = query.trim();
    setLoading(true);
    const id = window.setTimeout(async () => {
      try {
        const raw = await geocoder.geocode(trimmed, GeocodeType.AUTOCOMPLETE);
        setResults(
          raw.slice(0, 8).map((r) => ({
            displayName: r.displayName,
            destination: r.destination as Cartesian3 | Rectangle,
          })),
        );
        setActiveIndex(0);
      } catch (err) {
        console.warn("[LocationSearch] geocode failed", err);
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 220);
    return () => window.clearTimeout(id);
  }, [query, geocoder]);

  // Click outside → close.
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  // Keyboard shortcut: `/` focuses the search input from anywhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  function pick(r: Result) {
    if (!viewer) return;
    flyToResult(viewer, r);
    setOpen(false);
    setQuery(r.displayName);
    inputRef.current?.blur();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || results.length === 0) {
      if (e.key === "Enter" && query.trim()) {
        // Submit unfinished autocomplete as a full search.
        void (async () => {
          if (!geocoder) return;
          const raw = await geocoder.geocode(query.trim(), GeocodeType.SEARCH);
          if (raw[0]) pick({
            displayName: raw[0].displayName,
            destination: raw[0].destination as Cartesian3 | Rectangle,
          });
        })();
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      pick(results[activeIndex]);
    } else if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    }
  }

  if (!viewer) return null;

  return (
    <div
      ref={containerRef}
      style={{
        position: "absolute",
        top: 16,
        left: 16,
        width: 340,
        zIndex: 20,
        pointerEvents: "auto",
      }}
    >
      <div
        className="glass"
        style={{
          display: "flex",
          alignItems: "center",
          padding: "10px 14px",
          gap: 10,
          borderRadius: "var(--radius-md)",
        }}
      >
        <span
          aria-hidden
          style={{
            fontFamily: "var(--font-data)",
            fontSize: 14,
            color: "var(--color-text-low)",
            lineHeight: 1,
          }}
        >
          ⌕
        </span>
        <input
          ref={inputRef}
          type="text"
          value={query}
          placeholder="Search location  ( / )"
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => query.trim() && setOpen(true)}
          onKeyDown={onKeyDown}
          spellCheck={false}
          autoComplete="off"
          style={{
            flex: 1,
            background: "transparent",
            border: "none",
            outline: "none",
            color: "var(--color-text-hi)",
            fontFamily: "var(--font-body)",
            fontSize: 14,
            letterSpacing: 0,
          }}
        />
        {loading && (
          <span
            aria-label="Searching"
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "var(--color-cyan-glow)",
              boxShadow: "var(--glow-cyan)",
              animation: "cyan-blink 1s ease-in-out infinite",
            }}
          />
        )}
        {query && !loading && (
          <button
            type="button"
            aria-label="Clear"
            onClick={() => {
              setQuery("");
              setResults([]);
              setOpen(false);
              inputRef.current?.focus();
            }}
            style={{
              border: "none",
              background: "transparent",
              color: "var(--color-text-low)",
              cursor: "pointer",
              fontFamily: "var(--font-data)",
              fontSize: 12,
            }}
          >
            ×
          </button>
        )}
      </div>

      {open && results.length > 0 && (
        <div
          className="glass-strong"
          role="listbox"
          style={{
            marginTop: 6,
            borderRadius: "var(--radius-md)",
            overflow: "hidden",
            boxShadow: "var(--shadow-elevated)",
          }}
        >
          {results.map((r, i) => {
            const active = i === activeIndex;
            return (
              <button
                key={`${r.displayName}-${i}`}
                type="button"
                role="option"
                aria-selected={active}
                onMouseEnter={() => setActiveIndex(i)}
                onClick={() => pick(r)}
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  padding: "10px 14px",
                  background: active ? "var(--color-bg-3)" : "transparent",
                  border: "none",
                  borderBottom:
                    i === results.length - 1 ? "none" : "1px solid var(--color-stroke)",
                  color: "var(--color-text-hi)",
                  cursor: "pointer",
                  fontFamily: "var(--font-body)",
                  fontSize: 13,
                  lineHeight: 1.35,
                  letterSpacing: 0,
                  transition: "background var(--dur-fast) var(--ease-out-expo)",
                }}
              >
                {r.displayName}
              </button>
            );
          })}
        </div>
      )}

      {open && !loading && query.trim() && results.length === 0 && (
        <div
          className="glass"
          style={{
            marginTop: 6,
            padding: "10px 14px",
            borderRadius: "var(--radius-md)",
            fontFamily: "var(--font-data)",
            fontSize: 11,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--color-text-low)",
          }}
        >
          No results
        </div>
      )}
    </div>
  );
}
