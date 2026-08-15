"use client";

// Single-series line chart (dataviz skill: form = "trend over time" -> line;
// 1 series needs no legend box, the page title already names it). Series
// color is categorical slot 1 (blue), validated against this app's actual
// card surfaces (white / zinc-900) via scripts/validate_palette.js before
// use — both light (#2a78d6 on #ffffff) and dark (#3987e5 on #18181b) pass
// the lightness/chroma/contrast checks.
import { useState } from "react";
import type { PriceTrend } from "@/lib/api";

const WIDTH = 640;
const HEIGHT = 260;
const PADDING = { top: 16, right: 16, bottom: 12, left: 56 };

function formatUSD(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

// Rounds a price range down to a clean gridline step (1 / 2 / 2.5 / 5 / 10 x
// a power of ten) rather than whatever the raw min/max happen to be.
function niceStep(range: number): number {
  const rough = (range || 1) / 4;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const steps = [1, 2, 2.5, 5, 10];
  const normalized = rough / magnitude;
  const step = steps.find((s) => s >= normalized) ?? 10;
  return step * magnitude;
}

export default function PriceChart({ trend }: { trend: PriceTrend }) {
  const points = trend.observations
    .filter((o) => o.price !== null)
    .map((o) => ({ date: o.observed_at, price: Number(o.price) }));

  const delta = trend.price_change !== null ? Number(trend.price_change) : null;
  const deltaPct = trend.price_change_pct;
  const deltaUp = delta !== null && delta > 0;
  const deltaDown = delta !== null && delta < 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end gap-6 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-500">
            Latest price
          </div>
          <div className="text-3xl font-semibold">
            {trend.latest_price !== null ? formatUSD(Number(trend.latest_price)) : "—"}
          </div>
        </div>
        {delta !== null && (
          <div
            className={`pb-1 text-sm font-medium tabular-nums ${
              deltaUp
                ? "text-[#006300] dark:text-[#0ca30c]"
                : deltaDown
                  ? "text-rose-600 dark:text-rose-400"
                  : "text-zinc-500 dark:text-zinc-500"
            }`}
          >
            {deltaUp ? "▲" : deltaDown ? "▼" : "–"} {formatUSD(Math.abs(delta))}
            {deltaPct !== null && ` (${deltaPct > 0 ? "+" : ""}${deltaPct.toFixed(1)}%)`}
          </div>
        )}
      </div>

      {points.length < 2 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-500">
          Not enough price history yet to chart a trend.
        </p>
      ) : (
        <LineChart points={points} />
      )}

      <ObservationsTable observations={trend.observations} />
    </div>
  );
}

function LineChart({ points }: { points: { date: string; price: number }[] }) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const innerWidth = WIDTH - PADDING.left - PADDING.right;
  const innerHeight = HEIGHT - PADDING.top - PADDING.bottom;

  const dates = points.map((p) => new Date(p.date).getTime());
  const prices = points.map((p) => p.price);
  const minDate = Math.min(...dates);
  const maxDate = Math.max(...dates);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);

  const step = niceStep(maxPrice - minPrice);
  const yMin = Math.max(0, Math.floor(minPrice / step) * step - step);
  const yMax = Math.ceil(maxPrice / step) * step + step;

  const xScale = (t: number) =>
    maxDate === minDate ? innerWidth / 2 : ((t - minDate) / (maxDate - minDate)) * innerWidth;
  const yScale = (v: number) => innerHeight - ((v - yMin) / (yMax - yMin)) * innerHeight;

  const coords = points.map((p) => ({ x: xScale(new Date(p.date).getTime()), y: yScale(p.price) }));
  const linePath = coords.map((c, i) => `${i === 0 ? "M" : "L"} ${c.x} ${c.y}`).join(" ");
  const areaPath = `${linePath} L ${coords[coords.length - 1].x} ${innerHeight} L ${coords[0].x} ${innerHeight} Z`;

  const yTicks: number[] = [];
  for (let v = yMin; v <= yMax + 0.001; v += step) yTicks.push(v);

  const hovered =
    hoverIndex !== null ? { point: points[hoverIndex], coord: coords[hoverIndex] } : null;

  return (
    <div className="relative rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full"
        role="img"
        aria-label="Price over time"
        onPointerLeave={() => setHoverIndex(null)}
      >
        <g transform={`translate(${PADDING.left}, ${PADDING.top})`}>
          {yTicks.map((tick) => (
            <g key={tick}>
              <line
                x1={0}
                x2={innerWidth}
                y1={yScale(tick)}
                y2={yScale(tick)}
                stroke="currentColor"
                strokeWidth={1}
                className="text-zinc-200 dark:text-zinc-800"
              />
              <text
                x={-8}
                y={yScale(tick)}
                textAnchor="end"
                dominantBaseline="middle"
                className="fill-zinc-500 text-[10px] tabular-nums dark:fill-zinc-500"
              >
                {formatUSD(tick)}
              </text>
            </g>
          ))}

          <path d={areaPath} fill="#2a78d6" className="opacity-[0.08] dark:fill-[#3987e5]" />

          <path
            d={linePath}
            fill="none"
            stroke="#2a78d6"
            className="dark:stroke-[#3987e5]"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {hovered && (
            <line
              x1={hovered.coord.x}
              x2={hovered.coord.x}
              y1={0}
              y2={innerHeight}
              stroke="currentColor"
              strokeWidth={1}
              className="text-zinc-300 dark:text-zinc-700"
            />
          )}

          {coords.map((c, i) => (
            <g key={i}>
              {/* hit target — bigger than the painted mark, per interaction.md */}
              <circle
                cx={c.x}
                cy={c.y}
                r={24}
                fill="transparent"
                onPointerEnter={() => setHoverIndex(i)}
                onFocus={() => setHoverIndex(i)}
                tabIndex={0}
                className="cursor-pointer outline-none"
                aria-label={`${formatDate(points[i].date)}: ${formatUSD(points[i].price)}`}
              />
              <circle
                cx={c.x}
                cy={c.y}
                r={5}
                fill="#2a78d6"
                className="dark:fill-[#3987e5]"
                stroke="white"
                strokeWidth={2}
                pointerEvents="none"
              />
            </g>
          ))}

          <text
            x={coords[coords.length - 1].x}
            y={coords[coords.length - 1].y - 12}
            textAnchor="end"
            className="fill-zinc-700 text-xs font-medium tabular-nums dark:fill-zinc-300"
          >
            {formatUSD(points[points.length - 1].price)}
          </text>
        </g>
      </svg>

      {hovered && (
        <div
          className="pointer-events-none absolute rounded-md border border-zinc-200 bg-white px-3 py-2 text-xs shadow-sm dark:border-zinc-700 dark:bg-zinc-800"
          style={{
            left: `${((PADDING.left + hovered.coord.x) / WIDTH) * 100}%`,
            top: `${((PADDING.top + hovered.coord.y) / HEIGHT) * 100}%`,
            transform: "translate(-50%, -120%)",
          }}
        >
          <div className="font-semibold tabular-nums text-zinc-900 dark:text-zinc-50">
            {formatUSD(hovered.point.price)}
          </div>
          <div className="text-zinc-500 dark:text-zinc-500">{formatDate(hovered.point.date)}</div>
        </div>
      )}
    </div>
  );
}

function ObservationsTable({ observations }: { observations: PriceTrend["observations"] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
      <table className="w-full text-sm">
        <thead className="bg-zinc-100 text-left text-xs uppercase tracking-wide text-zinc-500 dark:bg-zinc-900 dark:text-zinc-500">
          <tr>
            <th className="px-4 py-2">Date</th>
            <th className="px-4 py-2">Price</th>
            <th className="px-4 py-2">In stock</th>
            <th className="px-4 py-2">Source</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
          {[...observations].reverse().map((o) => (
            <tr key={o.id} className="bg-white dark:bg-zinc-950">
              <td className="px-4 py-2 tabular-nums">{formatDate(o.observed_at)}</td>
              <td className="px-4 py-2 tabular-nums">
                {o.price !== null ? formatUSD(Number(o.price)) : "—"}
              </td>
              <td className="px-4 py-2">{o.in_stock ? "Yes" : "No"}</td>
              <td className="px-4 py-2 text-zinc-500 dark:text-zinc-500">{o.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
