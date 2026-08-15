// Server-only fetch helpers. Runs inside the frontend container, so it
// talks to the backend over the Docker Compose network by service name
// (INTERNAL_API_URL) rather than "localhost", which inside this container
// would mean the frontend itself. Browser-side code (the ask-agent form)
// uses NEXT_PUBLIC_API_URL instead — see components/AskAgentForm.tsx.
const INTERNAL_API_URL = process.env.INTERNAL_API_URL ?? "http://backend:8000";

export interface Competitor {
  id: number;
  slug: string;
  name: string;
  website_url: string;
  notes: string;
  is_own_brand: boolean;
  brand_num: number | null;
  created_at: string;
}

export interface Product {
  id: number;
  competitor_id: number;
  sku: string | null;
  name: string;
  grade: string | null;
  category: string;
  url: string;
  first_seen_at: string;
  last_seen_at: string;
  // Only populated by getCompetitorProducts (the list endpoint batches in
  // each product's latest observation) — null from any other call site.
  latest_price: string | null;
  currency: string | null;
  in_stock: boolean | null;
}

export interface PriceObservation {
  id: number;
  product_id: number;
  price: string | null;
  currency: string;
  in_stock: boolean;
  promo_text: string;
  observed_at: string;
  source: string;
}

export interface PriceTrend {
  product_id: number;
  product_name: string;
  observations: PriceObservation[];
  latest_price: string | null;
  price_change: string | null;
  price_change_pct: number | null;
}

export interface SWOTAnalysis {
  id: number;
  competitor_id: number;
  strengths: string[];
  weaknesses: string[];
  opportunities: string[];
  threats: string[];
  generated_at: string;
  model_used: string;
  source_summary: string;
}

export interface Development {
  id: number;
  competitor_id: number;
  title: string;
  summary: string;
  url: string;
  category: string;
  event_date: string;
  discovered_at: string;
}

// Every read here is live DB state (price data, agent output) — never
// worth caching stale, and this version of Next doesn't cache fetch by
// default anyway. cache: "no-store" just makes that explicit.
async function apiFetch<T>(path: string): Promise<T | null> {
  const res = await fetch(`${INTERNAL_API_URL}${path}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`API request to ${path} failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function getCompetitors(): Promise<Competitor[]> {
  return (await apiFetch<Competitor[]>("/competitors")) ?? [];
}

export function getCompetitor(slug: string): Promise<Competitor | null> {
  return apiFetch<Competitor>(`/competitors/${slug}`);
}

export async function getCompetitorProducts(slug: string, limit = 50): Promise<Product[]> {
  return (await apiFetch<Product[]>(`/competitors/${slug}/products?limit=${limit}`)) ?? [];
}

export function getLatestSWOT(slug: string): Promise<SWOTAnalysis | null> {
  return apiFetch<SWOTAnalysis>(`/competitors/${slug}/swot`);
}

export async function getDevelopments(slug: string): Promise<Development[]> {
  return (await apiFetch<Development[]>(`/competitors/${slug}/developments`)) ?? [];
}

export function getPriceTrend(productId: number, days = 3650): Promise<PriceTrend | null> {
  return apiFetch<PriceTrend>(`/products/${productId}/prices?days=${days}`);
}
