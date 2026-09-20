"use client";

import { API_PREFIX, env } from "@/lib/env";
import { toFormError, type FormError } from "@/lib/errors";

export function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: FormError };

const OFFLINE: FormError = { message: "Сервер недоступен, попробуйте позже", fieldErrors: {} };

/**
 * Session cookies are httpOnly, so the browser never holds the token itself —
 * it only needs to echo the readable CSRF cookie back in a header.
 */
async function send<T>(method: string, path: string, init: RequestInit): Promise<ApiResult<T>> {
  const csrfToken = readCookie(env.csrfCookie);
  let response: Response;
  try {
    response = await fetch(`${env.apiUrl}${API_PREFIX}${path}`, {
      ...init,
      method,
      credentials: "include",
      headers: {
        ...init.headers,
        ...(csrfToken ? { [env.csrfHeader]: csrfToken } : {}),
      },
    });
  } catch {
    return { ok: false, error: OFFLINE };
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

function withJson(body: unknown): RequestInit {
  return { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export async function apiPost<T>(path: string, body: unknown): Promise<ApiResult<T>> {
  return send<T>("POST", path, withJson(body));
}

export async function apiPatch<T>(path: string, body: unknown): Promise<ApiResult<T>> {
  return send<T>("PATCH", path, withJson(body));
}

export async function apiDelete<T>(path: string): Promise<ApiResult<T>> {
  return send<T>("DELETE", path, {});
}

/** Multipart: the browser writes the boundary itself, so no Content-Type is set here. */
export async function apiUpload<T>(path: string, form: FormData): Promise<ApiResult<T>> {
  return send<T>("POST", path, { body: form });
}
