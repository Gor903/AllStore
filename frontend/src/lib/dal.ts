import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import type {
  AccountBlockList,
  AdminCategory,
  AuditLogList,
  Business,
  BusinessList,
  ContactList,
  CustomerBlockList,
  InvitationList,
  ModerationProductList,
  ModeratorRecord,
  Product,
  ProductList,
  ReportQueue,
  Store,
  User,
  UserList,
} from "@/lib/api";
import { accountApiParams, type AccountQuery } from "@/lib/account-query";
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
  // the server refuses every other route anyway; this is so the owner sees a screen with a
  // form on it rather than a page that failed to load
  if (user.must_change_password) {
    redirect("/password");
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

/** The shop's own door: who this seller will not serve, lifted entries included. */
export async function getMyBlockedBuyers(): Promise<CustomerBlockList | null> {
  return backendGet<CustomerBlockList>(`/stores/me/blocked-buyers?limit=${SELLER_PAGE_SIZE}`);
}

export async function getMyProducts(): Promise<ProductList | null> {
  return backendGet<ProductList>(`/products?limit=${SELLER_PAGE_SIZE}`);
}

export async function getMyProduct(productId: string): Promise<Product | null> {
  return backendGet<Product>(`/products/${encodeURIComponent(productId)}`);
}

/**
 * The queues are paged.
 *
 * They used to ask for a hundred and show whatever came back, which reads fine on an empty
 * stand and hides the oldest half of a real backlog — and the backlog is exactly when a
 * moderator needs the screen. `offset` defaults to the first page, because the counters in
 * the navigation only want the total.
 */
export async function getModerationProducts(offset = 0): Promise<ModerationProductList | null> {
  const params = new URLSearchParams({ limit: String(ADMIN_PAGE_SIZE), offset: String(offset) });
  return backendGet<ModerationProductList>(`/moderation/products?${params}`);
}

export async function getModerationBusinesses(offset = 0): Promise<BusinessList | null> {
  const params = new URLSearchParams({ limit: String(ADMIN_PAGE_SIZE), offset: String(offset) });
  return backendGet<BusinessList>(`/moderation/businesses?${params}`);
}

/** The administrator's screens. Every one of them is behind requireRole("admin"). */
export async function getAdminUsers(query: AccountQuery): Promise<UserList | null> {
  return backendGet<UserList>(`/admin/users?${accountApiParams(query, ADMIN_PAGE_SIZE)}`);
}

export async function getAdminUser(userId: string): Promise<User | null> {
  return backendGet<User>(`/admin/users/${encodeURIComponent(userId)}`);
}

/** The people the platform serves: buyers and sellers, for a moderator and an administrator alike. */
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

/** The moderator accounts themselves — the administrator's panel, not the accounts screen. */
export async function getModerators(query: string, offset: number): Promise<UserList | null> {
  const params = new URLSearchParams({ limit: String(ADMIN_PAGE_SIZE), offset: String(offset) });
  if (query !== "") {
    params.set("q", query);
  }
  return backendGet<UserList>(`/admin/moderators?${params}`);
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

export async function getAuditLogs(
  offset: number,
  filters: { actorId?: string; action?: string } = {},
): Promise<AuditLogList | null> {
  const params = new URLSearchParams({ limit: String(ADMIN_PAGE_SIZE), offset: String(offset) });
  if (filters.actorId !== undefined && filters.actorId !== "") {
    params.set("actor_id", filters.actorId);
  }
  if (filters.action !== undefined && filters.action !== "") {
    params.set("action", filters.action);
  }
  return backendGet<AuditLogList>(`/admin/audit-logs?${params}`);
}

/** One moderator's account and what they have decided with it. */
export async function getModeratorRecord(userId: string): Promise<ModeratorRecord | null> {
  return backendGet<ModeratorRecord>(`/admin/moderators/${encodeURIComponent(userId)}`);
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
