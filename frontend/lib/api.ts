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

export interface Campaign {
  id: number;
  competitor_id: number;
  product_id: number | null;
  title: string;
  description: string;
  discount_text: string;
  starts_at: string | null;
  ends_at: string | null;
  source_url: string;
  discovered_at: string;
}

export interface ComparableProduct {
  id: number;
  name: string;
  competitor_id: number;
  competitor_slug: string;
  competitor_name: string;
  latest_price: string | null;
  currency: string | null;
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

export interface ProductsPage {
  products: Product[];
  total: number;
}

// A competitor's full catalog can now run into the thousands (the scraping
// pipeline tracks a competitor's whole catalog, not one category), so this
// is a real paginated fetch, not a capped snapshot — the backend reports
// the true total via the X-Total-Count header alongside the current page.
export async function getCompetitorProducts(
  slug: string,
  { limit = 50, offset = 0 }: { limit?: number; offset?: number } = {}
): Promise<ProductsPage> {
  const res = await fetch(`${INTERNAL_API_URL}/competitors/${slug}/products?limit=${limit}&offset=${offset}`, {
    cache: "no-store",
  });
  if (res.status === 404) return { products: [], total: 0 };
  if (!res.ok) {
    throw new Error(`API request to /competitors/${slug}/products failed: ${res.status} ${res.statusText}`);
  }
  const products: Product[] = await res.json();
  const total = Number(res.headers.get("X-Total-Count") ?? products.length);
  return { products, total };
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

export async function getCampaigns(slug: string): Promise<Campaign[]> {
  return (await apiFetch<Campaign[]>(`/competitors/${slug}/campaigns`)) ?? [];
}

export async function getProductCampaigns(productId: number): Promise<Campaign[]> {
  return (await apiFetch<Campaign[]>(`/products/${productId}/campaigns`)) ?? [];
}

export async function getComparableProducts(productId: number): Promise<ComparableProduct[]> {
  return (await apiFetch<ComparableProduct[]>(`/products/${productId}/comparable`)) ?? [];
}
