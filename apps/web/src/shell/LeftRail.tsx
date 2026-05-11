import { NavLink } from "react-router-dom";

const items = [
  { to: "/", label: "Globe", glyph: "◉" },
  { to: "/air-quality", label: "Air Quality", glyph: "≋" },
  { to: "/preparedness", label: "Prepare", glyph: "▲" },
  { to: "/climate", label: "Climate", glyph: "∿" },
  { to: "/about", label: "About", glyph: "i" },
] as const;

export function LeftRail() {
  return (
    <nav
      aria-label="Primary navigation"
      style={{
        height: "100%",
        background: "var(--color-bg-1)",
        borderRight: "1px solid var(--color-stroke)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        paddingTop: 16,
        gap: 4,
      }}
    >
      <div
        aria-hidden
        style={{
          width: 40,
          height: 40,
          display: "grid",
          placeItems: "center",
          fontFamily: "var(--font-display)",
          fontWeight: 800,
          fontSize: 20,
          color: "var(--color-ember-500)",
          letterSpacing: "-0.04em",
          marginBottom: 16,
        }}
      >
        WF
      </div>
      {items.map((it) => (
        <NavLink
          key={it.to}
          to={it.to}
          end={it.to === "/"}
          aria-label={it.label}
          style={({ isActive }) => ({
            position: "relative",
            width: 40,
            height: 40,
            display: "grid",
            placeItems: "center",
            borderRadius: 10,
            color: isActive ? "var(--color-ember-400)" : "var(--color-text-mid)",
            background: isActive ? "var(--color-bg-3)" : "transparent",
            transition: "background 200ms, color 200ms",
            fontFamily: "var(--font-data)",
            fontSize: 16,
            textDecoration: "none",
          })}
        >
          {({ isActive }) => (
            <>
              <span aria-hidden>{it.glyph}</span>
              {isActive && (
                <span
                  aria-hidden
                  style={{
                    position: "absolute",
                    left: -16,
                    top: 8,
                    bottom: 8,
                    width: 2,
                    background: "var(--color-ember-500)",
                    boxShadow: "var(--glow-ember)",
                    borderRadius: 2,
                  }}
                />
              )}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
