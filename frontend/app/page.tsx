import Link from "next/link";
import { getCompetitors } from "@/lib/api";

export default async function Home() {
  const competitors = await getCompetitors();
  const rivals = competitors.filter((c) => !c.is_own_brand);
  const ownBrands = competitors.filter((c) => c.is_own_brand);

  return (
    <div className="flex flex-col gap-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          {rivals.length} competitor{rivals.length === 1 ? "" : "s"} tracked,{" "}
          {ownBrands.length} own brand{ownBrands.length === 1 ? "" : "s"}.
        </p>
      </div>

      <CompetitorSection title="Competitors" competitors={rivals} />
      <CompetitorSection title="Our brands" competitors={ownBrands} />
    </div>
  );
}

function CompetitorSection({
  title,
  competitors,
}: {
  title: string;
  competitors: Awaited<ReturnType<typeof getCompetitors>>;
}) {
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
            className="rounded-lg border border-zinc-200 bg-white p-4 transition-colors hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-zinc-700"
          >
            <div className="font-medium">{competitor.name}</div>
            <div className="mt-1 truncate text-xs text-zinc-500 dark:text-zinc-500">
              {competitor.website_url || "No public storefront"}
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
