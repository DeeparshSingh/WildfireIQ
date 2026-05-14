import type { AqPollutants } from "@/lib/api/hooks";

/** Canadian Ambient Air Quality Standards used as the bar's 100% reference. */
const CAAQS_24H = {
  pm25: 27,
  pm10: 50,
  o3: 62,
  no2: 60,
  so2: 70,
  co: 6_500,
};

type Row = {
  key: keyof typeof CAAQS_24H;
  label: string;
  value: number | null | undefined;
  unit: string;
};

export function PollutantBars({ pollutants }: { pollutants: AqPollutants }) {
  const rows: Row[] = [
    { key: "pm25", label: "PM2.5", value: pollutants?.pm25, unit: "AQI" },
    { key: "pm10", label: "PM10", value: pollutants?.pm10, unit: "AQI" },
    { key: "o3", label: "Ozone", value: pollutants?.o3, unit: "AQI" },
    { key: "no2", label: "NO₂", value: pollutants?.no2, unit: "AQI" },
    { key: "so2", label: "SO₂", value: pollutants?.so2, unit: "AQI" },
    { key: "co", label: "CO", value: pollutants?.co, unit: "AQI" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {rows.map((r) => {
        const norm =
          r.value != null
            ? Math.min(100, (r.value / CAAQS_24H[r.key]) * 100)
            : 0;
        const color =
          norm < 33
            ? "var(--aq-3)"
            : norm < 66
            ? "var(--aq-5)"
            : norm < 100
            ? "var(--aq-7)"
            : "var(--aq-9)";
        return (
          <div key={r.key} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                fontFamily: "var(--font-body)",
                fontSize: 12,
                color: "var(--color-text-mid)",
              }}
            >
              <span>{r.label}</span>
              <span
                className="tabular"
                style={{
                  color: "var(--color-text-hi)",
                  fontSize: 13,
                  fontFamily: "var(--font-data)",
                }}
              >
                {r.value == null ? "—" : r.value}
                <span style={{ color: "var(--color-text-low)", marginLeft: 6, fontSize: 10 }}>
                  {r.unit}
                </span>
              </span>
            </div>
            <div
              style={{
                position: "relative",
                height: 6,
                borderRadius: 3,
                background: "var(--color-bg-2)",
                overflow: "hidden",
                border: "1px solid var(--color-stroke)",
              }}
            >
              <div
                style={{
                  width: `${norm}%`,
                  height: "100%",
                  background: color,
                  borderRadius: 3,
                  transition: "width 600ms cubic-bezier(0.16,1,0.3,1)",
                  boxShadow: norm > 66 ? `0 0 12px ${color}55` : "none",
                }}
              />
            </div>
          </div>
        );
      })}
      <div
        style={{
          marginTop: 4,
          fontFamily: "var(--font-data)",
          fontSize: 9,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: "var(--color-text-low)",
        }}
      >
        Bars normalised to CAAQS 24-hour standards · WAQI / AQICN
      </div>
    </div>
  );
}
