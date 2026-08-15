import { notFound } from "next/navigation";
import { getPriceTrend } from "@/lib/api";
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

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{trend.product_name}</h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-500">Price history</p>
      </div>
      <PriceChart trend={trend} />
    </div>
  );
}
