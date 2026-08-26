"use client";

// Range/floating-bar chart (dataviz skill: 3 distinct entities compared on
// one shared axis -> categorical, 1-3 series is comfortable with color +
// direct labels, no legend box needed). Each brand gets a fixed slot from
// the validated 8-hue categorical order (references/palette.md) — slots
// 1/2/3 (blue/orange/aqua) are the ones proven to clear the all-pairs CVD
// floor in both themes, exactly this chart's 3-series comparison shape.
import { useState } from "react";
import type { BrandSummary } from "@/lib/api";

const WIDTH = 640;
const ROW_HEIGHT = 56;
const PADDING = { top: 8, right: 56, bottom: 32, left: 200 };
const TRACK_THICKNESS = 10;

// Fixed brand -> categorical slot assignment, not cycled — see module comment.
const BRAND_COLOR: Record<string, { light: string; dark: string }> = {
  "gardeners-supply": { light: "#2a78d6", dark: "#3987e5" }, // slot 1, blue
  "epic-gardening": { light: "#eb6834", dark: "#d95926" }, // slot 2, orange
  "vego-garden": { light: "#1baf7a", dark: "#199e70" }, // slot 3, aqua
};
const FALLBACK_COLOR = { light: "#898781", dark: "#898781" };

function formatUSD(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value >= 1000 ? 0 : 2,
    maximumFractionDigits: value >= 1000 ? 0 : 2,
  }).format(value);
}

function niceStep(range: number): number {
  const rough = (range || 1) / 4;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const steps = [1, 2, 2.5, 5, 10];
  const normalized = rough / magnitude;
  const step = steps.find((s) => s >= normalized) ?? 10;
  return step * magnitude;
}

export default function PricePositionChart({ brands }: { brands: BrandSummary[] }) {
  const [hoverSlug, setHoverSlug] = useState<string | null>(null);

  const rows = brands
    .filter((b) => b.min_price !== null && b.max_price !== null && b.median_price !== null)
    .map((b) => ({
      slug: b.competitor_slug,
      name: b.competitor_name,
      isOwn: b.is_own_brand,
      min: Number(b.min_price),
      max: Number(b.max_price),
      median: Number(b.median_price),
    }));

  if (rows.length === 0) {
    return (
      <p className="text-sm text-zinc-500 dark:text-zinc-500">Not enough priced products yet to chart positioning.</p>
    );
  }

  const height = PADDING.top + PADDING.bottom + rows.length * ROW_HEIGHT;
  const innerWidth = WIDTH - PADDING.left - PADDING.right;
  const innerHeight = rows.length * ROW_HEIGHT;

  const globalMin = Math.min(...rows.map((r) => r.min));
  const globalMax = Math.max(...rows.map((r) => r.max));
  const step = niceStep(globalMax - globalMin);
  const xMin = Math.max(0, Math.floor(globalMin / step) * step - step);
  const xMax = Math.ceil(globalMax / step) * step + step;
  const xScale = (v: number) => ((v - xMin) / (xMax - xMin)) * innerWidth;

  const xTicks: number[] = [];
  for (let v = xMin; v <= xMax + 0.001; v += step) xTicks.push(v);

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        className="w-full"
        role="img"
        aria-label="Price positioning by brand"
        onPointerLeave={() => setHoverSlug(null)}
      >
        <g transform={`translate(${PADDING.left}, ${PADDING.top})`}>
          {xTicks.map((tick) => (
            <g key={tick}>
              <line
                x1={xScale(tick)}
                x2={xScale(tick)}
                y1={0}
                y2={innerHeight}
                stroke="currentColor"
                strokeWidth={1}
                className="text-zinc-200 dark:text-zinc-800"
              />
              <text
                x={xScale(tick)}
                y={innerHeight + 18}
                textAnchor="middle"
                className="fill-zinc-500 text-[10px] tabular-nums dark:fill-zinc-500"
              >
                {formatUSD(tick)}
              </text>
            </g>
          ))}

          {rows.map((row, i) => {
            const y = i * ROW_HEIGHT + ROW_HEIGHT / 2;
            const colors = BRAND_COLOR[row.slug] ?? FALLBACK_COLOR;
            const hovered = hoverSlug === row.slug;
            return (
              <g key={row.slug}>
                <text
                  x={-12}
                  y={y}
                  textAnchor="end"
                  dominantBaseline="middle"
                  className="fill-zinc-700 text-xs font-medium dark:fill-zinc-300"
                >
                  {row.name}
                  {row.isOwn && " (us)"}
                </text>

                {/* range track: rounded data-ends, square-off avoided via round linecap */}
                <line
                  x1={xScale(row.min)}
                  x2={xScale(row.max)}
                  y1={y}
                  y2={y}
                  stroke={colors.light}
                  className="dark:hidden"
                  strokeWidth={TRACK_THICKNESS}
                  strokeLinecap="round"
                  opacity={hovered ? 1 : 0.55}
                />
                <line
                  x1={xScale(row.min)}
                  x2={xScale(row.max)}
                  y1={y}
                  y2={y}
                  stroke={colors.dark}
                  className="hidden dark:inline"
                  strokeWidth={TRACK_THICKNESS}
                  strokeLinecap="round"
                  opacity={hovered ? 1 : 0.55}
                />

                {/* median marker */}
                <circle cx={xScale(row.median)} cy={y} r={7} fill={colors.light} className="dark:hidden" stroke="white" strokeWidth={2} />
                <circle
                  cx={xScale(row.median)}
                  cy={y}
                  r={7}
                  fill={colors.dark}
                  className="hidden dark:inline"
                  stroke="#18181b"
                  strokeWidth={2}
                />

                {/* larger, invisible hit target for hover */}
                <rect
                  x={xScale(row.min) - 10}
                  y={y - ROW_HEIGHT / 2}
                  width={xScale(row.max) - xScale(row.min) + 20}
                  height={ROW_HEIGHT}
                  fill="transparent"
                  onPointerEnter={() => setHoverSlug(row.slug)}
                  onFocus={() => setHoverSlug(row.slug)}
                  tabIndex={0}
                  className="cursor-pointer outline-none"
                  aria-label={`${row.name}: median ${formatUSD(row.median)}, range ${formatUSD(row.min)} to ${formatUSD(row.max)}`}
                />

                <text
                  x={xScale(row.median)}
                  y={y - 14}
                  textAnchor="middle"
                  className="fill-zinc-700 text-[11px] font-semibold tabular-nums dark:fill-zinc-300"
                >
                  {formatUSD(row.median)}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      {hoverSlug &&
        (() => {
          const row = rows.find((r) => r.slug === hoverSlug);
          if (!row) return null;
          return (
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-500">
              {row.name}: {formatUSD(row.min)} – {formatUSD(row.max)}, median {formatUSD(row.median)}
            </p>
          );
        })()}
    </div>
  );
}
