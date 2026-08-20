import Link from "next/link";
import { notFound } from "next/navigation";
import {
  Campaign,
  Development,
  SWOTAnalysis,
  getCampaigns,
  getCompetitor,
  getCompetitorProducts,
  getDevelopments,
  getLatestSWOT,
} from "@/lib/api";
import ProductsTable from "@/components/ProductsTable";

const PRODUCTS_PER_PAGE = 50;

export default async function CompetitorPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const { slug } = await params;
  const { page: pageParam } = await searchParams;
  const page = Math.max(1, Number(pageParam) || 1);

  const competitor = await getCompetitor(slug);
  if (!competitor) notFound();

  const [productsPage, swot, developments, campaigns] = await Promise.all([
    getCompetitorProducts(slug, { limit: PRODUCTS_PER_PAGE, offset: (page - 1) * PRODUCTS_PER_PAGE }),
    getLatestSWOT(slug),
    getDevelopments(slug),
    getCampaigns(slug),
  ]);

  return (
    <div className="flex flex-col gap-8">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{competitor.name}</h1>
          {competitor.is_own_brand && (
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
              Our brand
            </span>
          )}
        </div>
        {competitor.website_url && (
          <a
            href={competitor.website_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-zinc-500 hover:underline dark:text-zinc-500"
          >
            {competitor.website_url}
          </a>
        )}
        {competitor.notes && (
          <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
            {competitor.notes}
          </p>
        )}
      </div>

      <SWOTPanel swot={swot} />
      <CampaignsFeed campaigns={campaigns} />
      <DevelopmentsFeed developments={developments} />
      <ProductsTable
        slug={slug}
        products={productsPage.products}
        total={productsPage.total}
        page={page}
        perPage={PRODUCTS_PER_PAGE}
      />
    </div>
  );
}

function SWOTPanel({ swot }: { swot: SWOTAnalysis | null }) {
  if (!swot) {
    return (
      <section className="rounded-lg border border-dashed border-zinc-300 p-4 text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-500">
        No SWOT analysis generated yet — ask the agent to analyze this competitor.
      </section>
    );
  }

  const quadrants: { label: string; items: string[]; tone: string }[] = [
    { label: "Strengths", items: swot.strengths, tone: "border-emerald-200 dark:border-emerald-900" },
    { label: "Weaknesses", items: swot.weaknesses, tone: "border-rose-200 dark:border-rose-900" },
    { label: "Opportunities", items: swot.opportunities, tone: "border-sky-200 dark:border-sky-900" },
    { label: "Threats", items: swot.threats, tone: "border-amber-200 dark:border-amber-900" },
  ];

  return (
    <section>
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-500">
          SWOT analysis
        </h2>
        <span className="text-xs text-zinc-400">
          Generated {new Date(swot.generated_at).toLocaleDateString()} · {swot.model_used}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {quadrants.map((q) => (
          <div key={q.label} className={`rounded-lg border p-4 bg-white dark:bg-zinc-900 ${q.tone}`}>
            <h3 className="mb-2 text-sm font-semibold">{q.label}</h3>
            <ul className="list-inside list-disc space-y-1 text-sm text-zinc-700 dark:text-zinc-300">
              {q.items.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-500">{swot.source_summary}</p>
    </section>
  );
}

function DevelopmentsFeed({ developments }: { developments: Development[] }) {
  return (
    <section>
      <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-500">
        Developments
      </h2>
      {developments.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-500">
          No developments recorded yet — ask the agent what&apos;s new with this competitor.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {developments.map((d) => (
            <li
              key={d.id}
              className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
            >
              <div className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-500">
                <span className="rounded-full bg-zinc-100 px-2 py-0.5 font-medium uppercase tracking-wide dark:bg-zinc-800">
                  {d.category}
                </span>
                <span>{new Date(d.event_date).toLocaleDateString()}</span>
              </div>
              <h3 className="mt-1 font-medium">{d.title}</h3>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{d.summary}</p>
              {d.url && (
                <a
                  href={d.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 inline-block text-xs text-sky-600 hover:underline dark:text-sky-400"
                >
                  Source
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function CampaignsFeed({ campaigns }: { campaigns: Campaign[] }) {
  return (
    <section>
      <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-500">
        Campaigns &amp; promotions
      </h2>
      {campaigns.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-500">
          No campaigns recorded yet — ask the agent what promotions this competitor is running.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {campaigns.map((c) => (
            <li
              key={c.id}
              className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950/30"
            >
              <div className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-500">
                {c.discount_text && (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 font-medium text-amber-800 dark:bg-amber-900/50 dark:text-amber-300">
                    {c.discount_text}
                  </span>
                )}
                {(c.starts_at || c.ends_at) && (
                  <span>
                    {c.starts_at ? new Date(c.starts_at).toLocaleDateString() : "?"}
                    {" – "}
                    {c.ends_at ? new Date(c.ends_at).toLocaleDateString() : "ongoing"}
                  </span>
                )}
                {c.product_id && (
                  <Link href={`/products/${c.product_id}`} className="hover:underline">
                    View product
                  </Link>
                )}
              </div>
              <h3 className="mt-1 font-medium">{c.title}</h3>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{c.description}</p>
              {c.source_url && (
                <a
                  href={c.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 inline-block text-xs text-sky-600 hover:underline dark:text-sky-400"
                >
                  Source
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
