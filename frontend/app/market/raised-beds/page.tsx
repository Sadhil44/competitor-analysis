import Link from "next/link";
import {
  BrandSummary,
  MatrixCell,
  RaisedBedProduct,
  getRaisedBedMatrix,
  getRaisedBedProducts,
  getRaisedBedSummary,
} from "@/lib/api";

const STATUS_STYLE: Record<string, string> = {
  success: "bg-emerald-500",
  partial_failure: "bg-amber-500",
  failed: "bg-rose-500",
  running: "bg-sky-500 animate-pulse",
};

function timeAgo(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.floor(minutes)}m ago`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.floor(hours)}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function formatMoney(value: string | null, currency: string | null): string {
  if (value === null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: currency ?? "USD" }).format(Number(value));
}

function formatPct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export default async function RaisedBedWorkbenchPage() {
  const [summary, matrix] = await Promise.all([getRaisedBedSummary(), getRaisedBedMatrix()]);

  if (!summary) {
    return (
      <div className="rounded-lg border border-dashed border-zinc-300 p-6 text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-500">
        No raised-bed data yet — run backend/scripts/crawl_demo_scope.py.
      </div>
    );
  }

  const productsByBrand = await Promise.all(summary.brands.map((b) => getRaisedBedProducts(b.competitor_slug)));

  return (
    <div className="flex flex-col gap-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Category Deep-Dive: Raised Beds</h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
          Gardener&apos;s Supply vs. Epic Gardening and Vego Garden, scoped to raised beds and elevated planters —
          a deterministic snapshot, not a generated report.
        </p>
        <p className="mt-2 max-w-2xl text-xs text-zinc-500 dark:text-zinc-500">
          This is one worked example of a category-level comparison the platform can run for any product
          line — pricing, campaigns, and Q&amp;A elsewhere in the dashboard already cover every tracked
          competitor&apos;s full catalog, not just this category.
        </p>
        <p className="mt-2 text-xs text-zinc-400 dark:text-zinc-600">
          {summary.scope_note} Generated {new Date(summary.generated_at).toLocaleString()}.
        </p>
      </div>

      <SnapshotBar brands={summary.brands} />
      <PortfolioKPIs brands={summary.brands} />
      <AssortmentMatrix cells={matrix?.cells ?? []} excluded={matrix?.excluded_incomplete_count ?? 0} />

      {summary.brands.map((brand, i) => (
        <BrandProductTable key={brand.competitor_slug} brand={brand} products={productsByBrand[i]} />
      ))}
    </div>
  );
}

function SnapshotBar({ brands }: { brands: BrandSummary[] }) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex flex-wrap gap-x-8 gap-y-3">
        {brands.map((b) => (
          <div key={b.competitor_slug} className="flex items-center gap-2 text-sm">
            <span
              title={b.last_crawl_status ?? "no crawl yet"}
              className={`h-2 w-2 shrink-0 rounded-full ${
                b.last_crawl_status ? STATUS_STYLE[b.last_crawl_status] ?? "bg-zinc-400" : "bg-zinc-300"
              }`}
            />
            <span className="font-medium">{b.competitor_name}</span>
            <span className="text-zinc-400 dark:text-zinc-600">
              {b.last_crawled_at ? `crawled ${timeAgo(b.last_crawled_at)}` : "not yet crawled"}
              {b.pages_fetched !== null && ` · ${b.pages_fetched} pages`}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function PortfolioKPIs({ brands }: { brands: BrandSummary[] }) {
  return (
    <section>
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-500">
        Portfolio KPIs
      </h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {brands.map((b) => (
          <div
            key={b.competitor_slug}
            className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900"
          >
            <div className="flex items-center gap-2">
              <span className="font-medium">{b.competitor_name}</span>
              {b.is_own_brand && (
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
                  Us
                </span>
              )}
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-xs text-zinc-500 dark:text-zinc-500">Raised-bed SKUs</dt>
                <dd className="font-semibold tabular-nums">{b.product_count}</dd>
              </div>
              <div>
                <dt className="text-xs text-zinc-500 dark:text-zinc-500">Median price</dt>
                <dd className="font-semibold tabular-nums">{formatMoney(b.median_price, "USD")}</dd>
              </div>
              <div>
                <dt className="text-xs text-zinc-500 dark:text-zinc-500">On promo</dt>
                <dd className="font-semibold tabular-nums">{formatPct(b.promo_share)}</dd>
              </div>
              <div>
                <dt className="text-xs text-zinc-500 dark:text-zinc-500">In stock</dt>
                <dd className="font-semibold tabular-nums">{formatPct(b.in_stock_share)}</dd>
              </div>
            </dl>
          </div>
        ))}
      </div>
    </section>
  );
}

function AssortmentMatrix({ cells, excluded }: { cells: MatrixCell[]; excluded: number }) {
  return (
    <section>
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-500">
          Assortment matrix — material × height × form
        </h2>
        {excluded > 0 && (
          <span className="text-xs text-zinc-400" title="Products missing material, height, or form aren't shown here">
            {excluded} excluded (incomplete data)
          </span>
        )}
      </div>
      {cells.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-500">
          No products have a complete material + height + form yet.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-sm">
            <thead className="bg-zinc-100 text-left text-xs uppercase tracking-wide text-zinc-500 dark:bg-zinc-900 dark:text-zinc-500">
              <tr>
                <th className="px-4 py-2">Brand</th>
                <th className="px-4 py-2">Material</th>
                <th className="px-4 py-2">Height</th>
                <th className="px-4 py-2">Form</th>
                <th className="px-4 py-2 text-right">Count</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {cells
                .sort((a, b) => b.count - a.count)
                .map((cell, i) => (
                  <tr key={i} className="bg-white hover:bg-zinc-50 dark:bg-zinc-950 dark:hover:bg-zinc-900">
                    <td className="px-4 py-2">{cell.competitor_slug}</td>
                    <td className="px-4 py-2">{cell.material.replace(/_/g, " ")}</td>
                    <td className="px-4 py-2">{cell.height_band}</td>
                    <td className="px-4 py-2">{cell.form}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{cell.count}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function BrandProductTable({ brand, products }: { brand: BrandSummary; products: RaisedBedProduct[] }) {
  return (
    <section>
      <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-500">
        {brand.competitor_name} — raised beds &amp; planters ({products.length})
      </h2>
      {products.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-500">No raised-bed products found for this brand yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-sm">
            <thead className="bg-zinc-100 text-left text-xs uppercase tracking-wide text-zinc-500 dark:bg-zinc-900 dark:text-zinc-500">
              <tr>
                <th className="px-4 py-2">Product</th>
                <th className="px-4 py-2">Material</th>
                <th className="px-4 py-2">Height</th>
                <th className="px-4 py-2">Footprint</th>
                <th className="px-4 py-2 text-right">Price</th>
                <th className="px-4 py-2">Stock</th>
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
                    {p.material?.replace(/_/g, " ") ?? "—"}
                  </td>
                  <td className="px-4 py-2 text-zinc-500 dark:text-zinc-500">{p.height_band ?? "—"}</td>
                  <td className="px-4 py-2 text-zinc-500 dark:text-zinc-500">{p.footprint ?? "—"}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{formatMoney(p.latest_price, p.currency)}</td>
                  <td className="px-4 py-2">
                    {p.in_stock === null ? (
                      <span className="text-zinc-400">—</span>
                    ) : p.in_stock ? (
                      <span className="text-emerald-600 dark:text-emerald-400">In stock</span>
                    ) : (
                      <span className="text-rose-600 dark:text-rose-400">Out of stock</span>
                    )}
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
