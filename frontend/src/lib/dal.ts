import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import type { Business, Product, ProductList, Store, User } from "@/lib/api";
import { API_PREFIX, env } from "@/lib/env";

// the cabinet shows the whole shelf at once; pagination arrives when a shop outgrows it
const SELLER_PAGE_SIZE = 100;

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

export async function getMyProducts(): Promise<ProductList | null> {
  return backendGet<ProductList>(`/products?limit=${SELLER_PAGE_SIZE}`);
}

export async function getMyProduct(productId: string): Promise<Product | null> {
  return backendGet<Product>(`/products/${encodeURIComponent(productId)}`);
}
