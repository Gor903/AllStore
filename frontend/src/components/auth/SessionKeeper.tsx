"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import { apiPost, readCookie } from "@/lib/browser-api";
import { deviceKey, deviceProof } from "@/lib/device-key";
import { API_PREFIX, env } from "@/lib/env";

/**
 * Registers this browser's key with the session, and renews the session while a tab is open.
 *
 * Renders nothing. Mounted once in the root layout, and does nothing at all for a visitor who
 * is not signed in — the readable CSRF cookie is the signal, because it is set alongside the
 * session and is the only one of the pair a script is allowed to see.
 *
 * Every failure in here is silent and survivable by design. A browser that cannot hold a key
 * keeps an ordinary session; a renewal that does not happen leaves a session that is still
 * perfectly alive, because staying signed in is the sliding clock's job and not this one's.
 * Nothing a person is in the middle of should ever stop because of what happens here.
 */
const RENEW_EVERY_MS = 60 * 60 * 1000;

export function SessionKeeper() {
  // React mounts twice in development; without this the second mount races the first and the
  // server sees a replayed proof for no reason at all
  const started = useRef(false);
  // The root layout does not remount when the router navigates, and somebody arriving at the
  // site is not signed in yet — so an effect that only ran on mount would look once, before
  // there was anything to look at, and never again. Watching the path is how it gets a second
  // chance the moment signing in takes them somewhere.
  const pathname = usePathname();

  useEffect(() => {
    if (started.current || readCookie(env.csrfCookie) === null) {
      return;
    }
    started.current = true;

    let timer: ReturnType<typeof setInterval> | undefined;
    let cancelled = false;

    void (async () => {
      const key = await deviceKey();
      if (key === null || cancelled) {
        return;
      }
      await apiPost("/auth/sessions/device-key", { public_key: key.publicKey });
      const renew = async () => {
        const url = `${env.apiUrl}${API_PREFIX}/auth/renew`;
        await apiPost("/auth/renew", {}, { "X-Device-Proof": await deviceProof(key, "POST", url) });
      };
      timer = setInterval(() => void renew(), RENEW_EVERY_MS);
    })();

    return () => {
      cancelled = true;
      if (timer !== undefined) {
        clearInterval(timer);
      }
    };
  }, [pathname]);

  return null;
}
