import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode; label?: string };
type State = { error: Error | null };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary]", this.props.label ?? "(unknown)", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "grid",
            placeItems: "center",
            padding: 24,
            background:
              "radial-gradient(ellipse at center, hsl(220 25% 6%) 0%, hsl(220 30% 2%) 70%)",
          }}
        >
          <div
            className="glass"
            style={{
              maxWidth: 720,
              padding: 32,
              borderRadius: "var(--radius-lg)",
              boxShadow: "var(--shadow-elevated)",
            }}
          >
            <div
              style={{
                fontFamily: "var(--font-data)",
                fontSize: 11,
                letterSpacing: "0.28em",
                textTransform: "uppercase",
                color: "var(--risk-extreme)",
                marginBottom: 12,
              }}
            >
              Runtime error · {this.props.label ?? "component"}
            </div>
            <h1
              style={{
                fontFamily: "var(--font-display)",
                fontSize: 28,
                fontWeight: 700,
                letterSpacing: "-0.03em",
                margin: 0,
                color: "var(--color-text-hi)",
              }}
            >
              Something failed during render.
            </h1>
            <pre
              style={{
                marginTop: 20,
                padding: 16,
                borderRadius: "var(--radius-md)",
                background: "var(--color-bg-2)",
                border: "1px solid var(--color-stroke)",
                fontFamily: "var(--font-data)",
                fontSize: 12,
                lineHeight: 1.55,
                color: "var(--color-text-mid)",
                overflow: "auto",
                maxHeight: 320,
                whiteSpace: "pre-wrap",
              }}
            >
              {this.state.error.name}: {this.state.error.message}
              {this.state.error.stack ? `\n\n${this.state.error.stack}` : ""}
            </pre>
            <button
              type="button"
              onClick={() => this.setState({ error: null })}
              style={{
                marginTop: 20,
                padding: "10px 18px",
                background: "var(--color-ember-500)",
                color: "white",
                fontFamily: "var(--font-data)",
                fontSize: 12,
                letterSpacing: "0.18em",
                textTransform: "uppercase",
                border: "none",
                borderRadius: "var(--radius-md)",
                cursor: "pointer",
              }}
            >
              Retry →
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
