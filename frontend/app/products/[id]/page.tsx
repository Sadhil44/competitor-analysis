import Link from "next/link";
import { notFound } from "next/navigation";
import {
  Campaign,
  ComparableProduct,
  getComparableProducts,
  getPriceTrend,
  getProductCampaigns,
} from "@/lib/api";
import PriceChart from "@/components/PriceChart";

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

  const [campaigns, comparable] = await Promise.all([
    getProductCampaigns(productId),
    getComparableProducts(productId),
  ]);

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{trend.product_name}</h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-500">Price history</p>
      </div>
      <PriceChart trend={trend} />
      <ProductCampaigns campaigns={campaigns} />
      <ComparableProducts products={comparable} />
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
