import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * Where the browser and the server each think the API is, and what the session cookies are
 * called. Both of these have already cost a working stand once.
 *
 * `??` was not enough: it falls through on `undefined` and stops on an empty string, and an
 * empty string is exactly what a deploy produces when a variable is declared and left blank.
 * The consequence was quiet — `apiUrl` became "" and every browser request went to whatever
 * host served the page, which on a storefront subdomain is not the API.
 *
 * The cookie names are the other half: these are build-time values on the frontend and
 * run-time values on the backend, so nothing but agreement keeps them equal. When they were
 * left unset in the production image the frontend looked for un-prefixed cookies, found none,
 * and every mutating request answered 403.
 *
 * The module reads the environment once at import, so each test re-imports it.
 */

async function freshEnv(): Promise<typeof import("@/lib/env").env> {
  vi.resetModules();
  return (await import("@/lib/env")).env;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("an unset variable and a blank one", () => {
  it("falls back when the variable was left blank, not only when it is missing", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");

    expect((await freshEnv()).apiUrl).toBe("http://localhost:8080");
  });

  it("falls back on whitespace too, which is what a trailing space in a .env looks like", async () => {
    vi.stubEnv("NEXT_PUBLIC_BASE_DOMAIN", "   ");

    expect((await freshEnv()).baseDomain).toBe("allstore.am");
  });

  it("uses the value when there is one", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.allstore.am");

    expect((await freshEnv()).apiUrl).toBe("https://api.allstore.am");
  });
});

describe("two addresses, because there are two callers", () => {
  it("the browser goes through the public gateway", async () => {
    vi.stubEnv("INTERNAL_API_URL", "http://backend:8000");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.allstore.am");

    expect((await freshEnv()).apiUrl).toBe("https://api.allstore.am");
  });

  it("rendering on the server goes over the internal network", async () => {
    vi.stubGlobal("window", undefined);
    vi.stubEnv("INTERNAL_API_URL", "http://backend:8000");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.allstore.am");

    expect((await freshEnv()).apiUrl).toBe("http://backend:8000");
  });

  it("falls through to the public one when there is no internal address", async () => {
    vi.stubGlobal("window", undefined);
    vi.stubEnv("INTERNAL_API_URL", "");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.allstore.am");

    expect((await freshEnv()).apiUrl).toBe("https://api.allstore.am");
  });
});

describe("the address a crawler is given", () => {
  it("is built from the base domain when nothing says otherwise", async () => {
    vi.stubEnv("NEXT_PUBLIC_BASE_DOMAIN", "example.am");

    const env = await freshEnv();

    expect(env.siteUrl).toBe("https://example.am");
  });

  it("is the public address rather than the one the container answers on", async () => {
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "https://allstore.am");
    vi.stubEnv("NEXT_PUBLIC_BASE_DOMAIN", "internal.local");

    expect((await freshEnv()).siteUrl).toBe("https://allstore.am");
  });
});

describe("the cookie names", () => {
  it("default to the local ones, where plain http rules the prefix out", async () => {
    const env = await freshEnv();

    expect(env.sessionCookie).toBe("allstore_session");
    expect(env.csrfCookie).toBe("allstore_csrf");
  });

  it("take the __Host- prefixed names the backend sets outside local", async () => {
    vi.stubEnv("NEXT_PUBLIC_SESSION_COOKIE", "__Host-allstore_session");
    vi.stubEnv("NEXT_PUBLIC_CSRF_COOKIE", "__Host-allstore_csrf");

    const env = await freshEnv();

    expect(env.sessionCookie).toBe("__Host-allstore_session");
    expect(env.csrfCookie).toBe("__Host-allstore_csrf");
  });

  it("names the header the backend reads the token from", async () => {
    expect((await freshEnv()).csrfHeader).toBe("X-CSRF-Token");
  });
});
