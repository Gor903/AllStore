import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import type {
  AdminCategory,
  AccountBlockList,
  AuditLogList,
  Business,
  BusinessList,
  ContactList,
  InvitationList,
  ModerationProductList,
  Product,
  ProductList,
  ReportQueue,
  Store,
  User,
  UserList,
} from "@/lib/api";
import { API_PREFIX, env } from "@/lib/env";

// the cabinet shows the whole shelf at once; pagination arrives when a shop outgrows it
const SELLER_PAGE_SIZE = 100;
export const ADMIN_PAGE_SIZE = 20;

async function backendGet<T>(path: string): Promise<T | null> {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader) {
    return null;
  }
  const response = await fetch(`${env.apiUrl}${API_PREFIX}${path}`, {
    headers: { cookie: cookieHeader },
    cache: "no-store",
  });
  if (!response.ok) {
    return null;
  }
  return (await response.json()) as T;
}

/** Cached per request: several components may ask for the user without extra round trips. */
export const getCurrentUser = cache(async (): Promise<User | null> =>
  backendGet<User>("/users/me"),
);

export async function requireUser(): Promise<User> {
  const user = await getCurrentUser();
  if (user === null) {
    redirect("/login");
  }
  return user;
}

/** Authorization sits next to the data, not in a layout: layouts do not re-render on navigation. */
export async function requireRole(...roles: User["role"][]): Promise<User> {
  const user = await requireUser();
  if (!roles.includes(user.role)) {
    redirect("/dashboard");
  }
  return user;
}

export async function getMyBusiness(): Promise<Business | null> {
  return backendGet<Business>("/users/me/business");
}

/** Null when the seller has not opened a storefront yet — the backend answers 404. */
export async function getMyStore(): Promise<Store | null> {
  return backendGet<Store>("/stores/me");
}

/** An empty set is a valid answer; null means the seller has no shop to ask about. */
export async function getMyContacts(): Promise<ContactList | null> {
  return backendGet<ContactList>("/stores/me/contacts");
}

export async function getMyProducts(): Promise<ProductList | null> {
  return backendGet<ProductList>(`/products?limit=${SELLER_PAGE_SIZE}`);
}

export async function getMyProduct(productId: string): Promise<Product | null> {
  return backendGet<Product>(`/products/${encodeURIComponent(productId)}`);
}

export async function getModerationProducts(): Promise<ModerationProductList | null> {
  return backendGet<ModerationProductList>(`/moderation/products?limit=${SELLER_PAGE_SIZE}`);
}

export async function getModerationBusinesses(): Promise<BusinessList | null> {
  return backendGet<BusinessList>(`/moderation/businesses?limit=${SELLER_PAGE_SIZE}`);
}

/** The administrator's screens. Every one of them is behind requireRole("admin"). */
export async function getAdminUsers(query: string, offset: number): Promise<UserList | null> {
  const params = new URLSearchParams({ limit: String(ADMIN_PAGE_SIZE), offset: String(offset) });
  if (query !== "") {
    params.set("q", query);
  }
  return backendGet<UserList>(`/admin/users?${params}`);
}

/** The accounts the signed-in moderator or administrator may actually act on. */
export async function getReachableAccounts(
  query: string,
  offset: number,
): Promise<UserList | null> {
  const params = new URLSearchParams({ limit: String(ADMIN_PAGE_SIZE), offset: String(offset) });
  if (query !== "") {
    params.set("q", query);
  }
  return backendGet<UserList>(`/accounts?${params}`);
}

export async function getAdminCategories(): Promise<AdminCategory[] | null> {
  return backendGet<AdminCategory[]>("/admin/categories");
}

export async function getModeratorInvitations(offset: number): Promise<InvitationList | null> {
  const params = new URLSearchParams({ limit: String(ADMIN_PAGE_SIZE), offset: String(offset) });
  return backendGet<InvitationList>(`/admin/moderator-invitations?${params}`);
}

/** Every ban this account has ever had. Moderators read it too — it is their decision to make. */
export async function getAccountBlocks(userId: string): Promise<AccountBlockList | null> {
  return backendGet<AccountBlockList>(`/accounts/${encodeURIComponent(userId)}/blocks`);
}

export async function getAuditLogs(offset: number): Promise<AuditLogList | null> {
  const params = new URLSearchParams({ limit: String(ADMIN_PAGE_SIZE), offset: String(offset) });
  return backendGet<AuditLogList>(`/admin/audit-logs?${params}`);
}

/** An empty query is not a search: the backend refuses it, so it is not asked. */
export async function searchModerationCatalog(
  query: string,
  offset: number,
): Promise<ModerationProductList | null> {
  if (query === "") {
    return { items: [], total: 0, limit: ADMIN_PAGE_SIZE, offset };
  }
  const params = new URLSearchParams({
    q: query,
    limit: String(ADMIN_PAGE_SIZE),
    offset: String(offset),
  });
  return backendGet<ModerationProductList>(`/moderation/catalog?${params}`);
}

export async function getReportQueue(offset: number): Promise<ReportQueue | null> {
  const params = new URLSearchParams({ limit: String(ADMIN_PAGE_SIZE), offset: String(offset) });
  return backendGet<ReportQueue>(`/moderation/reports?${params}`);
}
