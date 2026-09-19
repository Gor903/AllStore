import { env } from "@/lib/env";

export type BackendHealth = {
  status: "ok";
  env: string;
};

/** Thin wrapper over fetch; generated OpenAPI types replace the hand-written ones later. */
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
