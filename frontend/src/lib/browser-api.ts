"use client";

import { toFormError, type FormError } from "@/lib/errors";
import { API_PREFIX, env } from "@/lib/env";

export function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: FormError };

/**
 * Session cookies are httpOnly, so the browser never holds the token itself —
 * it only needs to echo the readable CSRF cookie back in a header.
 */
export async function apiPost<T>(path: string, body: unknown): Promise<ApiResult<T>> {
  const csrfToken = readCookie(env.csrfCookie);
  let response: Response;
  try {
    response = await fetch(`${env.apiUrl}${API_PREFIX}${path}`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { [env.csrfHeader]: csrfToken } : {}),
      },
      body: JSON.stringify(body),
    });
  } catch {
    return {
      ok: false,
      error: { message: "Сервер недоступен, попробуйте позже", fieldErrors: {} },
    };
  }

  if (response.status === 204) {
    return { ok: true, data: undefined as T };
  }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    return { ok: false, error: toFormError(payload) };
  }
  return { ok: true, data: payload as T };
}
