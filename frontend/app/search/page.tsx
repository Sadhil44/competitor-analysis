import Link from "next/link";
import { searchProducts } from "@/lib/api";

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const query = q?.trim() ?? "";
  const results = query ? await searchProducts(query, 50) : [];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Product search</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Searches every tracked product across every competitor by name, ranked by relevance —
          the same full-text match used to find comparable products.
        </p>
      </div>

      {!query ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-500">
          Use the search box in the header to look up a product across all competitors.
        </p>
      ) : (
        <>
          <p className="text-sm text-zinc-500 dark:text-zinc-500">
            {results.length} result{results.length === 1 ? "" : "s"} for &quot;{query}&quot;
          </p>
          {results.length === 0 ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-500">
              No products matched. Try fewer or more general words.
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
                  {results.map((p) => (
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
        </>
      )}
    </div>
  );
}
