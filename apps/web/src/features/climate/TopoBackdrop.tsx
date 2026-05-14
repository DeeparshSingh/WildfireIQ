/**
 * Subtle topographic-line backdrop at 4% opacity. Procedural so we don't
 * have to ship a rendered SVG asset — uses smooth Catmull-like horizontal
 * lines layered at varying amplitudes to evoke contour lines without
 * matching an actual elevation crop. Decorative only.
 */
export function TopoBackdrop() {
  const W = 1200;
  const H = 800;
  const LINES = 28;
  const paths: string[] = [];
  for (let i = 0; i < LINES; i++) {
    const baseY = (H * (i + 1)) / (LINES + 1);
    const amp = 12 + (i * 7) % 50;
    const freq = 0.006 + ((i * 13) % 7) * 0.0012;
    const phase = (i * 37) % 360;
    let d = `M 0 ${baseY}`;
    for (let x = 0; x <= W; x += 12) {
      const y =
        baseY +
        Math.sin(x * freq + phase) * amp +
        Math.sin(x * freq * 2.3 + phase * 1.7) * amp * 0.3;
      d += ` L ${x} ${y.toFixed(1)}`;
    }
    paths.push(d);
  }

  return (
    <div
      className="topo-backdrop"
      aria-hidden
      style={{
        position: "fixed",
        inset: 0,
        pointerEvents: "none",
        opacity: 0.04,
        zIndex: 0,
      }}
    >
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid slice"
        style={{ width: "100%", height: "100%" }}
      >
        {paths.map((d, i) => (
          <path
            key={i}
            d={d}
            stroke="hsl(40 30% 96%)"
            strokeWidth={0.6}
            fill="none"
          />
        ))}
      </svg>
    </div>
  );
}
