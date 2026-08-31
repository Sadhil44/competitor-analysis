import Skeleton from "@/components/Skeleton";

export default function Loading() {
  return (
    <div className="flex flex-col gap-10">
      <Skeleton className="h-28 w-full rounded-2xl" />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-xl" />
        ))}
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        <div className="flex flex-col gap-8 lg:col-span-2">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 rounded-lg" />
            ))}
          </div>
        </div>
        <Skeleton className="h-96 rounded-xl" />
      </div>
    </div>
  );
}
