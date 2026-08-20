"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { Product } from "@/lib/api";

type SortKey = "name" | "category" | "price" | "stock";
type SortDir = "asc" | "desc";

export default function ProductsTable({
  slug,
  products,
  total,
  page,
  perPage,
}: {
  slug: string;
  products: Product[];
  total: number;
  page: number;
  perPage: number;
}) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const rangeStart = total === 0 ? 0 : (page - 1) * perPage + 1;
  const rangeEnd = Math.min(page * perPage, total);
  const hasPrev = page > 1;
  const hasNext = rangeEnd < total;

  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    let rows = needle
      ? products.filter(
          (p) =>
            p.name.toLowerCase().includes(needle) ||
            p.category.toLowerCase().includes(needle) ||
            (p.sku ?? "").toLowerCase().includes(needle)
        )
      : products;

    if (sortKey) {
      rows = [...rows].sort((a, b) => {
        const dir = sortDir === "asc" ? 1 : -1;
        switch (sortKey) {
          case "name":
            return a.name.localeCompare(b.name) * dir;
          case "category":
            return a.category.localeCompare(b.category) * dir;
          case "price": {
            const av = a.latest_price !== null ? Number(a.latest_price) : -Infinity;
            const bv = b.latest_price !== null ? Number(b.latest_price) : -Infinity;
            return (av - bv) * dir;
          }
          case "stock":
            return (Number(a.in_stock ?? false) - Number(b.in_stock ?? false)) * dir;
        }
      });
    }
    return rows;
  }, [products, filter, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  return (
    <section>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-500">
          Products
          {total > 0 && (
            <span className="ml-2 normal-case text-zinc-400">
              (showing {rangeStart}–{rangeEnd} of {total})
            </span>
          )}
        </h2>
        {products.length > 0 && (
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter this page by name, category, or SKU…"
            className="w-full max-w-xs rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-xs outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:focus:border-zinc-500"
          />
        )}
      </div>
      {products.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-500">No products recorded yet for {slug}.</p>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
            <table className="w-full text-sm">
              <thead className="bg-zinc-100 text-left text-xs uppercase tracking-wide text-zinc-500 dark:bg-zinc-900 dark:text-zinc-500">
                <tr>
                  <SortableHeader label="Name" active={sortKey === "name"} dir={sortDir} onClick={() => toggleSort("name")} />
                  <SortableHeader
                    label="Category"
                    active={sortKey === "category"}
                    dir={sortDir}
                    onClick={() => toggleSort("category")}
                  />
                  <th className="px-4 py-2">SKU</th>
                  <th className="px-4 py-2">Grade</th>
                  <SortableHeader
                    label="Latest price"
                    active={sortKey === "price"}
                    dir={sortDir}
                    onClick={() => toggleSort("price")}
                  />
                  <SortableHeader label="Stock" active={sortKey === "stock"} dir={sortDir} onClick={() => toggleSort("stock")} />
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                {visible.map((p) => (
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
                          title="View on competitor's site"
                          className="ml-1.5 text-zinc-400 hover:text-sky-600 dark:hover:text-sky-400"
                        >
                          ↗
                        </a>
                      )}
                    </td>
                    <td className="px-4 py-2 text-zinc-500 dark:text-zinc-500">{p.category || "—"}</td>
                    <td className="px-4 py-2 text-zinc-500 dark:text-zinc-500">{p.sku ?? "—"}</td>
                    <td className="px-4 py-2 text-zinc-500 dark:text-zinc-500">{p.grade ?? "—"}</td>
                    <td className="px-4 py-2 tabular-nums">
                      {p.latest_price !== null
                        ? new Intl.NumberFormat("en-US", {
                            style: "currency",
                            currency: p.currency ?? "USD",
                          }).format(Number(p.latest_price))
                        : "—"}
                    </td>
                    <td className="px-4 py-2 text-zinc-500 dark:text-zinc-500">
                      {p.in_stock === null ? "—" : p.in_stock ? "In stock" : "Out of stock"}
                    </td>
                  </tr>
                ))}
                {visible.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-6 text-center text-zinc-500 dark:text-zinc-500">
                      No products on this page match &quot;{filter}&quot;.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {(hasPrev || hasNext) && (
            <div className="mt-3 flex items-center justify-between text-sm">
              {hasPrev ? (
                <Link
                  href={`/competitors/${slug}?page=${page - 1}`}
                  className="text-sky-600 hover:underline dark:text-sky-400"
                >
                  ← Previous
                </Link>
              ) : (
                <span />
              )}
              <span className="text-zinc-400">Page {page}</span>
              {hasNext ? (
                <Link
                  href={`/competitors/${slug}?page=${page + 1}`}
                  className="text-sky-600 hover:underline dark:text-sky-400"
                >
                  Next →
                </Link>
              ) : (
                <span />
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}

function SortableHeader({
  label,
  active,
  dir,
  onClick,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
}) {
  return (
    <th className="px-4 py-2">
      <button
        type="button"
        onClick={onClick}
        className={`flex items-center gap-1 hover:text-zinc-900 dark:hover:text-zinc-100 ${active ? "text-zinc-900 dark:text-zinc-100" : ""}`}
      >
        {label}
        <span className="text-[10px]">{active ? (dir === "asc" ? "▲" : "▼") : ""}</span>
      </button>
    </th>
  );
}
