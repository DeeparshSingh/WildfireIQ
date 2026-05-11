import { type ReactNode } from "react";
import { motion } from "motion/react";

import { LeftRail } from "./LeftRail";
import { TopBar } from "./TopBar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        display: "grid",
        gridTemplateColumns: "72px 1fr",
        gridTemplateRows: "56px 1fr",
        gridTemplateAreas: `"rail top" "rail main"`,
      }}
    >
      <motion.div
        style={{ gridArea: "rail", zIndex: 10 }}
        initial={{ x: -32, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.6, delay: 0.9, ease: [0.16, 1, 0.3, 1] }}
      >
        <LeftRail />
      </motion.div>

      <motion.div
        style={{ gridArea: "top", zIndex: 10 }}
        initial={{ y: -16, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.6, delay: 0.9, ease: [0.16, 1, 0.3, 1] }}
      >
        <TopBar />
      </motion.div>

      <main
        style={{
          gridArea: "main",
          position: "relative",
          overflow: "hidden",
          background: "var(--color-bg-0)",
        }}
      >
        {children}
      </main>
    </div>
  );
}
