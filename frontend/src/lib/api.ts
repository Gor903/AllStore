import type { components } from "@/lib/api-types";
import { catalogSearchParams, type CatalogQuery } from "@/lib/catalog-query";
import { API_PREFIX, env } from "@/lib/env";

// Types come from the backend OpenAPI schema, see docs/adr/0004-api-types-generation.md
export type BackendHealth = components["schemas"]["HealthResponse"];
export type User = components["schemas"]["UserRead"];
export type Business = components["schemas"]["BusinessRead"];
export type Storefront = components["schemas"]["StorefrontRead"];
export type CatalogProduct = components["schemas"]["CatalogProductRead"];
export type CatalogProductList = components["schemas"]["CatalogProductListResponse"];
export type CatalogStoreList = components["schemas"]["CatalogStoreListResponse"];
export type CategoryTree = components["schemas"]["CategoryTreeRead"];

export const PAGE_SIZE = 24;

async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${env.apiUrl}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`GET ${path} failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchBackendHealth(): Promise<BackendHealth | null> {
  try {
    return await apiGet<BackendHealth>("/health");
  } catch {
    return null;
  }
}

/**
 * Addressed by subdomain, not by Host: rendering happens on the server, and Node's fetch
 * replaces a Host header with the authority of the URL it dials.
 */
export async function fetchStorefront(subdomain: string): Promise<Storefront | null> {
  try {
    return await apiGet<Storefront>(`${API_PREFIX}/storefront/${encodeURIComponent(subdomain)}`);
  } catch {
    return null;
  }
}

/** null means the catalogue could not be read at all; an empty list is a valid answer. */
export async function fetchCatalogProducts(
  query: CatalogQuery,
): Promise<CatalogProductList | null> {
  const params = catalogSearchParams(query);
  params.set("limit", String(PAGE_SIZE));
  try {
    return await apiGet<CatalogProductList>(`${API_PREFIX}/catalog/products?${params}`);
  } catch {
    return null;
  }
}

export async function fetchCatalogProduct(productId: string): Promise<CatalogProduct | null> {
  try {
    return await apiGet<CatalogProduct>(
      `${API_PREFIX}/catalog/products/${encodeURIComponent(productId)}`,
    );
  } catch {
    return null;
  }
}

export async function fetchCatalogStores(offset: number): Promise<CatalogStoreList | null> {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  try {
    return await apiGet<CatalogStoreList>(`${API_PREFIX}/catalog/stores?${params}`);
  } catch {
    return null;
  }
}

/** An empty tree is survivable: the filter simply has nothing to offer. */
export async function fetchCategories(): Promise<CategoryTree[]> {
  try {
    return await apiGet<CategoryTree[]>(`${API_PREFIX}/catalog/categories`);
  } catch {
    return [];
  }
}
