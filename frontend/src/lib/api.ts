import type { components } from "@/lib/api-types";
import { env } from "@/lib/env";

// Types come from the backend OpenAPI schema, see docs/adr/0004-api-types-generation.md
export type BackendHealth = components["schemas"]["HealthResponse"];
export type User = components["schemas"]["UserRead"];
export type Business = components["schemas"]["BusinessRead"];

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
