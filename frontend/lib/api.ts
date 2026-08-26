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
  product_count: number;
  last_crawled_at: string | null;
  last_crawl_status: string | null;
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
  product_url: string;
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
  url: string;
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

export async function searchProducts(q: string, limit = 20): Promise<ComparableProduct[]> {
  if (!q.trim()) return [];
  return (
    (await apiFetch<ComparableProduct[]>(`/products/search?q=${encodeURIComponent(q)}&limit=${limit}`)) ?? []
  );
}

export async function getComparableProducts(productId: number): Promise<ComparableProduct[]> {
  return (await apiFetch<ComparableProduct[]>(`/products/${productId}/comparable`)) ?? [];
}

// --- Raised-bed workbench (backend/app/api/intelligence.py) ---
// Scoped to the three demo competitors and gated to attributes.product_type
// in (raised_bed, elevated_planter) — see backend/app/intelligence/.

export interface BrandSummary {
  competitor_slug: string;
  competitor_name: string;
  is_own_brand: boolean;
  product_count: number;
  median_price: string | null;
  min_price: string | null;
  max_price: string | null;
  promo_share: number;
  in_stock_share: number;
  last_crawled_at: string | null;
  last_crawl_status: string | null;
  pages_fetched: number | null;
}

export interface RaisedBedSummary {
  generated_at: string;
  scope_note: string;
  brands: BrandSummary[];
}

export interface MatrixCell {
  competitor_slug: string;
  material: string;
  height_band: string;
  form: string;
  count: number;
}

export interface RaisedBedMatrix {
  cells: MatrixCell[];
  excluded_incomplete_count: number;
}

export interface ComparableMatch {
  product_id: number;
  name: string;
  url: string;
  competitor_slug: string;
  competitor_name: string;
  latest_price: string | null;
  currency: string | null;
  score: number;
  confidence: "high" | "medium" | "low";
  matched_fields: string[];
  missing_fields: string[];
}

export async function getRaisedBedSummary(): Promise<RaisedBedSummary | null> {
  return apiFetch<RaisedBedSummary>("/intelligence/raised-beds/summary");
}

export interface RaisedBedProduct {
  id: number;
  name: string;
  url: string;
  latest_price: string | null;
  currency: string | null;
  in_stock: boolean | null;
  material: string | null;
  height_band: string | null;
  form: string | null;
  footprint: string | null;
}

export async function getRaisedBedProducts(competitorSlug: string): Promise<RaisedBedProduct[]> {
  return (
    (await apiFetch<RaisedBedProduct[]>(
      `/intelligence/raised-beds/products?competitor_slug=${encodeURIComponent(competitorSlug)}`
    )) ?? []
  );
}

export interface OpportunityOut {
  material: string;
  height_band: string;
  form: string;
  kind: "gap" | "strength";
  own_count: number;
  competitor_counts: Record<string, number>;
  total_competitor_count: number;
}

export interface OpportunityAnalysis {
  own_brand_slug: string;
  gaps: OpportunityOut[];
  strengths: OpportunityOut[];
}

export async function getRaisedBedOpportunities(): Promise<OpportunityAnalysis | null> {
  return apiFetch<OpportunityAnalysis>("/intelligence/raised-beds/opportunities");
}

export async function getRaisedBedMatrix(): Promise<RaisedBedMatrix | null> {
  return apiFetch<RaisedBedMatrix>("/intelligence/raised-beds/matrix");
}

export async function getRaisedBedComparables(productId: number, limit = 10): Promise<ComparableMatch[]> {
  return (
    (await apiFetch<ComparableMatch[]>(`/intelligence/raised-beds/comparables?product_id=${productId}&limit=${limit}`)) ??
    []
  );
}

export interface ActivityItem {
  kind: "campaign" | "development" | "price_move";
  id: number;
  competitor_slug: string;
  competitor_name: string;
  title: string;
  detail: string;
  at: string;
  category?: string;
  discount_text?: string;
  pct_change?: number;
  product_id?: number;
}

export interface PriceMove {
  product_id: number;
  product_name: string;
  product_url: string;
  competitor_slug: string;
  competitor_name: string;
  is_own_brand: boolean;
  first_price: string;
  last_price: string;
  pct_change: number;
  currency: string;
  last_observed_at: string;
}

export async function getPriceChanges(days = 14, minPctChange = 5.0, limit = 20): Promise<PriceMove[]> {
  return (
    (await apiFetch<PriceMove[]>(
      `/activity/price-changes?days=${days}&min_pct_change=${minPctChange}&limit=${limit}`
    )) ?? []
  );
}

// No dedicated backend endpoint for campaigns/developments here — it fans
// the existing per-competitor calls out across every tracked competitor
// and merges them client-side (server-side here; this runs in a Server
// Component) into one timeline; cheap enough at this data volume to skip a
// new aggregate route. Price moves DO have a dedicated cross-company
// endpoint already (app/api/activity.py) since that comparison can't be
// done per-competitor at all, so that one's folded in directly.
export async function getRecentActivity(competitors: Competitor[], limit = 12): Promise<ActivityItem[]> {
  const perCompetitor = await Promise.all(
    competitors.map(async (c) => {
      const [campaigns, developments] = await Promise.all([getCampaigns(c.slug), getDevelopments(c.slug)]);
      const campaignItems: ActivityItem[] = campaigns.map((camp) => ({
        kind: "campaign",
        id: camp.id,
        competitor_slug: c.slug,
        competitor_name: c.name,
        title: camp.title,
        detail: camp.description,
        at: camp.discovered_at,
        discount_text: camp.discount_text,
      }));
      const developmentItems: ActivityItem[] = developments.map((dev) => ({
        kind: "development",
        id: dev.id,
        competitor_slug: c.slug,
        competitor_name: c.name,
        title: dev.title,
        detail: dev.summary,
        at: dev.discovered_at,
        category: dev.category,
      }));
      return [...campaignItems, ...developmentItems];
    })
  );
  const priceMoves = await getPriceChanges(30, 5.0, 15);
  const priceMoveItems: ActivityItem[] = priceMoves.map((m) => ({
    kind: "price_move",
    id: m.product_id,
    competitor_slug: m.competitor_slug,
    competitor_name: m.competitor_name,
    title: m.product_name,
    detail: `${m.currency} ${m.first_price} → ${m.currency} ${m.last_price}`,
    at: m.last_observed_at,
    pct_change: m.pct_change,
    product_id: m.product_id,
  }));
  perCompetitor.push(priceMoveItems);
  return perCompetitor
    .flat()
    .sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime())
    .slice(0, limit);
}
