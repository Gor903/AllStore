import type { components } from "@/lib/api-types";
import { API_PREFIX, env } from "@/lib/env";

// Types come from the backend OpenAPI schema, see docs/adr/0004-api-types-generation.md
export type BackendHealth = components["schemas"]["HealthResponse"];
export type User = components["schemas"]["UserRead"];
export type Business = components["schemas"]["BusinessRead"];
export type Storefront = components["schemas"]["StorefrontRead"];

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
