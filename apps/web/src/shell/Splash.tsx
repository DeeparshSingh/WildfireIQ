import { motion } from "motion/react";

export function Splash() {
  return (
    <motion.div
      initial={{ opacity: 1 }}
      animate={{ opacity: 0 }}
      transition={{ duration: 0.6, delay: 0.8, ease: [0.16, 1, 0.3, 1] }}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 200,
        display: "grid",
        placeItems: "center",
        background:
          "radial-gradient(ellipse at center, hsl(220 25% 6%) 0%, hsl(220 30% 2%) 65%)",
        pointerEvents: "none",
      }}
    >
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        style={{ textAlign: "center" }}
      >
        <div
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "clamp(2rem, 6vw, 4rem)",
            letterSpacing: "-0.04em",
            fontWeight: 700,
            color: "var(--color-text-hi)",
            lineHeight: 1,
          }}
        >
          Wildfire<span style={{ color: "var(--color-ember-500)" }}>IQ</span>
        </div>
        <div
          style={{
            marginTop: 12,
            fontFamily: "var(--font-data)",
            fontSize: "0.75rem",
            letterSpacing: "0.32em",
            textTransform: "uppercase",
            color: "var(--color-text-low)",
          }}
        >
          Thompson · Okanagan · 50.6745°N 120.3273°W
        </div>
      </motion.div>
    </motion.div>
  );
}
