import { cookies } from "next/headers";

import type { components } from "@/lib/api-types";
import { catalogSearchParams, type CatalogQuery } from "@/lib/catalog-query";
import { API_PREFIX, env } from "@/lib/env";

// Types come from the backend OpenAPI schema, see docs/adr/0004-api-types-generation.md
export type BackendHealth = components["schemas"]["HealthResponse"];
export type User = components["schemas"]["UserRead"];
export type Business = components["schemas"]["BusinessRead"];
export type Storefront = components["schemas"]["StorefrontRead"];
export type Store = components["schemas"]["StoreRead"];
export type Product = components["schemas"]["ProductRead"];
export type ProductList = components["schemas"]["ProductListResponse"];
export type ProductImage = components["schemas"]["ProductImageRead"];
export type ModerationProduct = components["schemas"]["ModerationProductRead"];
export type ModerationProductList = components["schemas"]["ModerationProductListResponse"];
export type BusinessReview = components["schemas"]["BusinessReviewRead"];
export type BusinessList = components["schemas"]["BusinessListResponse"];
export type Contact = components["schemas"]["ContactRead"];
export type ContactList = components["schemas"]["ContactsResponse"];
export type CatalogProduct = components["schemas"]["CatalogProductRead"];
// the card carries the ways to reach the seller; the listing deliberately does not
export type CatalogProductDetail = components["schemas"]["CatalogProductDetailRead"];
export type CatalogProductList = components["schemas"]["CatalogProductListResponse"];
export type CatalogStore = components["schemas"]["CatalogStoreRead"];
export type CatalogStoreList = components["schemas"]["CatalogStoreListResponse"];
export type CategoryTree = components["schemas"]["CategoryTreeRead"];
export type UserList = components["schemas"]["UserListResponse"];
export type AdminCategory = components["schemas"]["AdminCategoryRead"];
export type AuditLogList = components["schemas"]["AuditLogListResponse"];
export type ModeratorRecord = components["schemas"]["ModeratorRecordRead"];
export type SystemState = components["schemas"]["SystemStateRead"];
export type Activity = components["schemas"]["ActivityRead"];
export type Invitation = components["schemas"]["InvitationRead"];
export type InvitationList = components["schemas"]["InvitationListResponse"];
// the secret travels exactly once, in the answer to the request that created it
export type InvitationCreated = components["schemas"]["InvitationCreated"];
export type AccountBlockList = components["schemas"]["AccountBlockListResponse"];
export type CustomerBlock = components["schemas"]["CustomerBlockRead"];
export type CustomerBlockList = components["schemas"]["CustomerBlockListResponse"];
// one line of the assistant stream: the halves of an answer arrive as they become ready
export type AssistantLine =
  | components["schemas"]["AssistantProducts"]
  | components["schemas"]["AssistantText"]
  | components["schemas"]["AssistantError"];
export type ReportQueue = components["schemas"]["ReportQueueResponse"];
export type ReportedSubject = components["schemas"]["ReportedSubjectRead"];
export type AuditEntry = components["schemas"]["AuditLogRead"];

export const PAGE_SIZE = 24;

/** Answered when a shop has closed its door to the signed-in buyer, see the backend's
 *  services/customer_blocks.py. Not null, because "not found" would be a riddle to somebody
 *  who was shopping there last week. */
export const STORE_BLOCKED = "store-blocked";

class ApiStatusError extends Error {
  constructor(readonly status: number) {
    super(`request failed with ${status}`);
  }
}

/**
 * The viewer's cookies travel with public reads.
 *
 * Most of what the catalogue shows is the same for everyone, but not all of it: a shop that
 * has barred this buyer drops out of their listings and their search. The backend decides
 * that, and it can only decide it if it knows who is asking — rendering as an anonymous
 * visitor would quietly show the buyer a shop the API would refuse them.
 */
async function viewerHeaders(): Promise<HeadersInit> {
  const jar = (await cookies()).toString();
  return jar === "" ? {} : { cookie: jar };
}

async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${env.apiUrl}${path}`, {
    cache: "no-store",
    headers: await viewerHeaders(),
  });
  if (!response.ok) {
    throw new ApiStatusError(response.status);
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
export async function fetchStorefront(
  subdomain: string,
): Promise<Storefront | typeof STORE_BLOCKED | null> {
  try {
    return await apiGet<Storefront>(`${API_PREFIX}/storefront/${encodeURIComponent(subdomain)}`);
  } catch (error) {
    // the shop is there and the visitor knows it; saying so is kinder than a 404 riddle
    return error instanceof ApiStatusError && error.status === 403 ? STORE_BLOCKED : null;
  }
}

/** null means the catalogue could not be read at all; an empty list is a valid answer. */
export async function fetchCatalogProducts(
  query: CatalogQuery,
  limit: number = PAGE_SIZE,
): Promise<CatalogProductList | null> {
  const params = catalogSearchParams(query);
  params.set("limit", String(limit));
  try {
    return await apiGet<CatalogProductList>(`${API_PREFIX}/catalog/products?${params}`);
  } catch {
    return null;
  }
}

export async function fetchCatalogProduct(productId: string): Promise<CatalogProductDetail | null> {
  try {
    return await apiGet<CatalogProductDetail>(
      `${API_PREFIX}/catalog/products/${encodeURIComponent(productId)}`,
    );
  } catch {
    return null;
  }
}

export async function fetchCatalogStores(
  offset: number,
  limit: number = PAGE_SIZE,
): Promise<CatalogStoreList | null> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  try {
    return await apiGet<CatalogStoreList>(`${API_PREFIX}/catalog/stores?${params}`);
  } catch {
    return null;
  }
}

/**
 * null means the reference could not be read at all; an empty tree is a valid answer.
 *
 * The two used to be the same value, and that hid a backend that was down behind a form
 * with nothing to choose from — a seller filling in a product would only find out on submit,
 * and whoever debugged it had no error to go on either.
 */
export async function fetchCategories(): Promise<CategoryTree[] | null> {
  try {
    return await apiGet<CategoryTree[]>(`${API_PREFIX}/catalog/categories`);
  } catch {
    return null;
  }
}
