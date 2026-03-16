import { useEffect, useRef, useState } from "react";
import client from "../api/client";
import styles from "./HistoryChart.module.css";

interface DataPoint {
  date: string;
  value: number;
}

function buildPath(points: DataPoint[], w: number, h: number): string {
  if (points.length < 2) return "";
  const minV = Math.min(...points.map((p) => p.value));
  const maxV = Math.max(...points.map((p) => p.value));
  const range = maxV - minV || 1;
  const pad = { x: 0, y: 8 };
  const scaleX = (i: number) => pad.x + (i / (points.length - 1)) * (w - pad.x * 2);
  const scaleY = (v: number) => pad.y + (1 - (v - minV) / range) * (h - pad.y * 2);

  const coords = points.map((p, i) => `${scaleX(i).toFixed(1)},${scaleY(p.value).toFixed(1)}`);
  const line = "M" + coords.join(" L");

  // Closed path for gradient fill
  const first = `${scaleX(0).toFixed(1)},${h}`;
  const last = `${scaleX(points.length - 1).toFixed(1)},${h}`;
  const fill = `M${first} L` + coords.join(" L") + ` L${last} Z`;

  return `${line}|||${fill}`;
}

function fmt(n: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function HistoryChart() {
  const [data, setData] = useState<DataPoint[]>([]);
  const [hovered, setHovered] = useState<DataPoint | null>(null);
  const [error, setError] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    client
      .get<DataPoint[]>("/portfolio/history/")
      .then((r) => setData(r.data))
      .catch(() => setError(true));
  }, []);

  if (error || data.length === 0) return null;

  const W = 800;
  const H = 140;
  const paths = buildPath(data, W, H).split("|||");
  const linePath = paths[0];
  const fillPath = paths[1];

  const first = data[0].value;
  const last = data[data.length - 1].value;
  const change = last - first;
  const changePct = first ? (change / first) * 100 : 0;
  const positive = change >= 0;

  const displayPoint = hovered ?? data[data.length - 1];

  function handleMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = svgRef.current!.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * W;
    const idx = Math.round((x / W) * (data.length - 1));
    const clamped = Math.max(0, Math.min(data.length - 1, idx));
    setHovered(data[clamped]);
  }

  return (
    <section className={styles.section}>
      <div className={styles.header}>
        <h2 className={styles.title}>30-Day Performance</h2>
        <div className={styles.summary}>
          <span className={styles.pointValue}>${fmt(displayPoint.value)}</span>
          <span className={positive ? styles.pos : styles.neg}>
            {positive ? "+" : ""}{fmt(change)} ({positive ? "+" : ""}{changePct.toFixed(2)}%)
          </span>
          <span className={styles.date}>{displayPoint.date}</span>
        </div>
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className={styles.svg}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHovered(null)}
      >
        <defs>
          <linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.25" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={fillPath} fill="url(#chartFill)" />
        <path d={linePath} fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </section>
  );
}
