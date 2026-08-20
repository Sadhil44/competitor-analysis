import Link from "next/link";
import { ActivityItem, Competitor, getCompetitors, getRecentActivity } from "@/lib/api";

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

const STATUS_BORDER: Record<string, string> = {
  success: "border-l-emerald-400 dark:border-l-emerald-600",
  partial_failure: "border-l-amber-400 dark:border-l-amber-600",
  failed: "border-l-rose-400 dark:border-l-rose-600",
  running: "border-l-sky-400 dark:border-l-sky-600",
};

export default async function Home() {
  const competitors = await getCompetitors();
  const rivals = competitors.filter((c) => !c.is_own_brand);
  const ownBrands = competitors.filter((c) => c.is_own_brand);
  const totalProducts = competitors.reduce((sum, c) => sum + c.product_count, 0);
  const needsAttention = competitors.filter(
    (c) => c.last_crawl_status === "partial_failure" || c.last_crawl_status === "failed"
  ).length;
  const activity = await getRecentActivity(competitors);

  return (
    <div className="flex flex-col gap-10">
      <div className="relative overflow-hidden rounded-2xl border border-zinc-200 bg-gradient-to-br from-indigo-50 via-white to-white p-6 dark:border-zinc-800 dark:from-indigo-950/30 dark:via-zinc-950 dark:to-zinc-950">
        <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-indigo-200/40 blur-3xl dark:bg-indigo-900/20" />
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
          Live view of every tracked competitor — pricing, campaigns, developments, and
          AI-generated SWOT, kept current by an automated crawl pipeline.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="Competitors tracked" value={rivals.length} accent="indigo" />
        <StatTile label="Own brands" value={ownBrands.length} accent="violet" />
        <StatTile label="Products tracked" value={totalProducts.toLocaleString()} accent="sky" />
        <StatTile
          label="Needs attention"
          value={needsAttention}
          accent={needsAttention > 0 ? "amber" : "emerald"}
        />
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        <div className="flex flex-col gap-8 lg:col-span-2">
          <CompetitorSection title="Competitors" competitors={rivals} />
          <CompetitorSection title="Our brands" competitors={ownBrands} />
        </div>
        <ActivityFeed items={activity} />
      </div>
    </div>
  );
}

const ACCENT_STYLE: Record<string, { bg: string; text: string }> = {
  indigo: { bg: "bg-indigo-50 dark:bg-indigo-950/40", text: "text-indigo-600 dark:text-indigo-400" },
  violet: { bg: "bg-violet-50 dark:bg-violet-950/40", text: "text-violet-600 dark:text-violet-400" },
  sky: { bg: "bg-sky-50 dark:bg-sky-950/40", text: "text-sky-600 dark:text-sky-400" },
  amber: { bg: "bg-amber-50 dark:bg-amber-950/40", text: "text-amber-600 dark:text-amber-400" },
  emerald: { bg: "bg-emerald-50 dark:bg-emerald-950/40", text: "text-emerald-600 dark:text-emerald-400" },
};

function StatTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: string | number;
  accent: keyof typeof ACCENT_STYLE;
}) {
  const style = ACCENT_STYLE[accent];
  return (
    <div
      className={`rounded-xl border border-zinc-200 p-4 shadow-sm transition-shadow hover:shadow-md dark:border-zinc-800 ${style.bg}`}
    >
      <div className={`text-2xl font-semibold tabular-nums ${style.text}`}>{value}</div>
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
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {competitors.map((competitor) => (
          <Link
            key={competitor.id}
            href={`/competitors/${competitor.slug}`}
            className={`group rounded-lg border border-l-4 border-zinc-200 bg-white p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900 ${
              competitor.last_crawl_status
                ? STATUS_BORDER[competitor.last_crawl_status] ?? "border-l-zinc-300 dark:border-l-zinc-700"
                : "border-l-zinc-300 dark:border-l-zinc-700"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="font-medium group-hover:text-indigo-600 dark:group-hover:text-indigo-400">
                {competitor.name}
              </div>
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

const ACTIVITY_STYLE: Record<ActivityItem["kind"], { badge: string; label: string }> = {
  campaign: { badge: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300", label: "Campaign" },
  development: { badge: "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300", label: "Development" },
};

function ActivityFeed({ items }: { items: ActivityItem[] }) {
  return (
    <section>
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-500">
        Recent activity
      </h2>
      <div className="rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
        {items.length === 0 ? (
          <p className="p-4 text-sm text-zinc-500 dark:text-zinc-500">
            Nothing recorded yet — ask the agent to research a competitor to populate this feed.
          </p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {items.map((item) => {
              const style = ACTIVITY_STYLE[item.kind];
              return (
                <li key={`${item.kind}-${item.id}`} className="p-3.5">
                  <div className="flex items-center gap-1.5 text-[11px]">
                    <span className={`rounded-full px-2 py-0.5 font-medium ${style.badge}`}>{style.label}</span>
                    <Link
                      href={`/competitors/${item.competitor_slug}`}
                      className="font-medium text-zinc-600 hover:underline dark:text-zinc-400"
                    >
                      {item.competitor_name}
                    </Link>
                    <span className="ml-auto shrink-0 text-zinc-400 dark:text-zinc-600">{timeAgo(item.at)}</span>
                  </div>
                  <div className="mt-1.5 text-sm font-medium">{item.title}</div>
                  {item.detail && (
                    <p className="mt-0.5 line-clamp-2 text-xs text-zinc-500 dark:text-zinc-500">{item.detail}</p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
