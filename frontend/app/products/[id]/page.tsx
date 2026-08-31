import Link from "next/link";
import { notFound } from "next/navigation";
import {
  Campaign,
  ComparableMatch,
  ComparableProduct,
  getComparableProducts,
  getPriceTrend,
  getProductCampaigns,
  getRaisedBedComparables,
} from "@/lib/api";
import PriceChart from "@/components/PriceChart";
import MarkdownText from "@/components/MarkdownText";

export default async function ProductPricePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const productId = Number(id);
  if (!Number.isFinite(productId)) notFound();

  const trend = await getPriceTrend(productId);
  if (!trend) notFound();

  const [campaigns, comparable, smartMatches] = await Promise.all([
    getProductCampaigns(productId),
    getComparableProducts(productId),
    getRaisedBedComparables(productId),
  ]);

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{trend.product_name}</h1>
        <div className="mt-1 flex items-center gap-2 text-sm text-zinc-500 dark:text-zinc-500">
          <span>Price history</span>
          {trend.product_url && (
            <>
              <span aria-hidden>·</span>
              <a
                href={trend.product_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sky-600 hover:underline dark:text-sky-400"
              >
                View on site ↗
              </a>
            </>
          )}
        </div>
      </div>
      <PriceChart trend={trend} />
      <ProductCampaigns campaigns={campaigns} />
      {/* The raised-bed workbench's attribute-based matcher only returns
          results for products it's classified as raised_bed/elevated_planter
          (see app/intelligence/matching.py) — for everything else this is
          empty and the name-based comparison below is what's shown. */}
      {smartMatches.length > 0 ? (
        <SmartComparableProducts matches={smartMatches} />
      ) : (
        <ComparableProducts products={comparable} />
      )}
    </div>
  );
}

function ProductCampaigns({ campaigns }: { campaigns: Campaign[] }) {
  if (campaigns.length === 0) return null;
  return (
    <section>
      <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-500">
        Campaigns on this product
      </h2>
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
            </div>
            <h3 className="mt-1 font-medium">{c.title}</h3>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              <MarkdownText variant="inline">{c.description}</MarkdownText>
            </p>
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
    </section>
  );
}

const CONFIDENCE_STYLE: Record<string, string> = {
  high: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  medium: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  low: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
};

function SmartComparableProducts({ matches }: { matches: ComparableMatch[] }) {
  return (
    <section>
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-500">
          Comparable products at other brands
        </h2>
        <span className="text-xs text-zinc-400">
          Scored on material/height/footprint/form/configuration —{" "}
          <Link href="/market/raised-beds" className="hover:underline">
            raised-bed workbench
          </Link>
        </span>
      </div>
      <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
        <table className="w-full text-sm">
          <thead className="bg-zinc-100 text-left text-xs uppercase tracking-wide text-zinc-500 dark:bg-zinc-900 dark:text-zinc-500">
            <tr>
              <th className="px-4 py-2">Product</th>
              <th className="px-4 py-2">Brand</th>
              <th className="px-4 py-2">Latest price</th>
              <th className="px-4 py-2">Match</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {matches.map((m) => (
              <tr key={m.product_id} className="bg-white hover:bg-zinc-50 dark:bg-zinc-950 dark:hover:bg-zinc-900">
                <td className="px-4 py-2">
                  <Link href={`/products/${m.product_id}`} className="hover:underline">
                    {m.name}
                  </Link>
                  {m.url && (
                    <a
                      href={m.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title="View on site"
                      className="ml-1.5 text-zinc-400 hover:text-sky-600 dark:hover:text-sky-400"
                    >
                      ↗
                    </a>
                  )}
                </td>
                <td className="px-4 py-2 text-zinc-500 dark:text-zinc-500">
                  <Link href={`/competitors/${m.competitor_slug}`} className="hover:underline">
                    {m.competitor_name}
                  </Link>
                </td>
                <td className="px-4 py-2 tabular-nums">
                  {m.latest_price !== null
                    ? new Intl.NumberFormat("en-US", {
                        style: "currency",
                        currency: m.currency ?? "USD",
                      }).format(Number(m.latest_price))
                    : "—"}
                </td>
                <td className="px-4 py-2">
                  <span
                    title={`Matched: ${m.matched_fields.join(", ") || "none"} · Missing: ${m.missing_fields.join(", ") || "none"}`}
                    className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${CONFIDENCE_STYLE[m.confidence] ?? CONFIDENCE_STYLE.low}`}
                  >
                    {m.confidence} ({m.score})
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ComparableProducts({ products }: { products: ComparableProduct[] }) {
  return (
    <section>
      <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-500">
        Comparable products at other brands
      </h2>
      {products.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-500">
          No comparable products found by name — try a differently-named product, or this may be
          genuinely unique in the catalog.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-sm">
            <thead className="bg-zinc-100 text-left text-xs uppercase tracking-wide text-zinc-500 dark:bg-zinc-900 dark:text-zinc-500">
              <tr>
                <th className="px-4 py-2">Product</th>
                <th className="px-4 py-2">Brand</th>
                <th className="px-4 py-2">Latest price</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {products.map((p) => (
                <tr key={p.id} className="bg-white hover:bg-zinc-50 dark:bg-zinc-950 dark:hover:bg-zinc-900">
                  <td className="px-4 py-2">
                    <Link href={`/products/${p.id}`} className="hover:underline">
                      {p.name}
                    </Link>
                    {p.url && (
                      <a
                        href={p.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title="View on site"
                        className="ml-1.5 text-zinc-400 hover:text-sky-600 dark:hover:text-sky-400"
                      >
                        ↗
                      </a>
                    )}
                  </td>
                  <td className="px-4 py-2 text-zinc-500 dark:text-zinc-500">
                    <Link href={`/competitors/${p.competitor_slug}`} className="hover:underline">
                      {p.competitor_name}
                    </Link>
                  </td>
                  <td className="px-4 py-2 tabular-nums">
                    {p.latest_price !== null
                      ? new Intl.NumberFormat("en-US", {
                          style: "currency",
                          currency: p.currency ?? "USD",
                        }).format(Number(p.latest_price))
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
