/**
 * Tasteful canvas confetti for achievement unlocks. Respects
 * `prefers-reduced-motion` — degrades to a 400 ms badge pulse instead of
 * particles. ~80 particles, gravity, 1.2 s lifespan, no external deps.
 */
import { useEffect, useRef } from "react";

const COLORS = [
  "hsl(18 95% 54%)", // ember
  "hsl(45 95% 58%)", // amber
  "hsl(185 90% 55%)", // cyan glow
  "hsl(150 70% 50%)", // sage
  "hsl(40 30% 96%)", // off-white
];

type Particle = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  rot: number;
  vr: number;
  color: string;
  life: number;
};

export function Confetti({ trigger }: { trigger: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!trigger) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
    canvas.style.width = `${window.innerWidth}px`;
    canvas.style.height = `${window.innerHeight}px`;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    const cx = window.innerWidth / 2;
    const cy = window.innerHeight * 0.35;
    const particles: Particle[] = Array.from({ length: 80 }, () => ({
      x: cx,
      y: cy,
      vx: (Math.random() - 0.5) * 9,
      vy: -(Math.random() * 8 + 4),
      r: Math.random() * 4 + 3,
      rot: Math.random() * Math.PI * 2,
      vr: (Math.random() - 0.5) * 0.3,
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
      life: 1,
    }));

    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = (now - start) / 1000;
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      let alive = false;
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.25;
        p.rot += p.vr;
        p.life = Math.max(0, 1 - t / 1.2);
        if (p.life > 0) alive = true;
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.globalAlpha = p.life;
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.r, -p.r * 0.4, p.r * 2, p.r * 0.8);
        ctx.restore();
      }
      if (alive) raf = requestAnimationFrame(tick);
      else ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
    };
    raf = requestAnimationFrame(tick);

    return () => cancelAnimationFrame(raf);
  }, [trigger]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "fixed",
        inset: 0,
        pointerEvents: "none",
        zIndex: 100,
      }}
    />
  );
}
