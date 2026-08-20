import Link from "next/link";
import { Competitor, getCompetitors } from "@/lib/api";

function timeAgo(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.floor(minutes)}m ago`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.floor(hours)}h ago`;
  const days = hours / 24;
  return `${Math.floor(days)}d ago`;
}

const STATUS_STYLE: Record<string, string> = {
  success: "bg-emerald-500",
  partial_failure: "bg-amber-500",
  failed: "bg-rose-500",
  running: "bg-sky-500 animate-pulse",
};

const STATUS_LABEL: Record<string, string> = {
  success: "Crawled cleanly",
  partial_failure: "Crawled with some errors",
  failed: "Crawl failed",
  running: "Crawl in progress",
};

export default async function Home() {
  const competitors = await getCompetitors();
  const rivals = competitors.filter((c) => !c.is_own_brand);
  const ownBrands = competitors.filter((c) => c.is_own_brand);
  const totalProducts = competitors.reduce((sum, c) => sum + c.product_count, 0);
  const needsAttention = competitors.filter(
    (c) => c.last_crawl_status === "partial_failure" || c.last_crawl_status === "failed"
  ).length;

  return (
    <div className="flex flex-col gap-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Live view of every tracked competitor — pricing, campaigns, developments, and
          AI-generated SWOT, kept current by an automated crawl pipeline.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="Competitors tracked" value={rivals.length} />
        <StatTile label="Own brands" value={ownBrands.length} />
        <StatTile label="Products tracked" value={totalProducts.toLocaleString()} />
        <StatTile
          label="Needs attention"
          value={needsAttention}
          tone={needsAttention > 0 ? "warning" : "good"}
        />
      </div>

      <CompetitorSection title="Competitors" competitors={rivals} />
      <CompetitorSection title="Our brands" competitors={ownBrands} />
    </div>
  );
}

function StatTile({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  tone?: "neutral" | "good" | "warning";
}) {
  const toneClass =
    tone === "warning"
      ? "text-amber-600 dark:text-amber-400"
      : tone === "good"
        ? "text-emerald-600 dark:text-emerald-400"
        : "text-zinc-900 dark:text-zinc-100";
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <div className={`text-2xl font-semibold tabular-nums ${toneClass}`}>{value}</div>
      <div className="mt-1 text-xs text-zinc-500 dark:text-zinc-500">{label}</div>
    </div>
  );
}

function CompetitorSection({ title, competitors }: { title: string; competitors: Competitor[] }) {
  if (competitors.length === 0) return null;

  return (
    <section>
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-500">
        {title}
      </h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {competitors.map((competitor) => (
          <Link
            key={competitor.id}
            href={`/competitors/${competitor.slug}`}
            className="group rounded-lg border border-zinc-200 bg-white p-4 transition-all hover:border-zinc-300 hover:shadow-sm dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-zinc-700"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="font-medium group-hover:underline">{competitor.name}</div>
              {competitor.last_crawl_status && (
                <span
                  title={STATUS_LABEL[competitor.last_crawl_status] ?? competitor.last_crawl_status}
                  className={`mt-1 h-2 w-2 shrink-0 rounded-full ${STATUS_STYLE[competitor.last_crawl_status] ?? "bg-zinc-400"}`}
                />
              )}
            </div>
            <div className="mt-1 truncate text-xs text-zinc-500 dark:text-zinc-500">
              {competitor.website_url || "No public storefront"}
            </div>
            <div className="mt-3 flex items-center gap-3 text-xs text-zinc-500 dark:text-zinc-500">
              <span className="font-medium text-zinc-700 dark:text-zinc-300">
                {competitor.product_count.toLocaleString()} products
              </span>
              {competitor.last_crawled_at && <span>crawled {timeAgo(competitor.last_crawled_at)}</span>}
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
