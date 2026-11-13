import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Which storefront the visitor is on, read from the host of the request being rendered.
 *
 * A page uses it to decide whether a link has to leave the host it is rendered on: on
 * `shop.allstore.am` a link to another shop must be absolute, and on the marketplace itself it
 * must not be. Reading the wrong one sends a buyer to a 404 on a stranger's subdomain.
 */

const host = vi.hoisted(() => ({ value: null as string | null }));

vi.mock("next/headers", () => ({
  headers: () => Promise.resolve(new Headers(host.value === null ? {} : { host: host.value })),
}));

async function subdomainOn(value: string | null): Promise<string | null> {
  host.value = value;
  const { currentSubdomain } = await import("@/lib/request-host");
  return currentSubdomain();
}

beforeEach(() => {
  vi.resetModules();
});

describe("currentSubdomain", () => {
  it("is the storefront when the request arrived on one", async () => {
    expect(await subdomainOn("shop.allstore.am")).toBe("shop");
  });

  it("is null on the marketplace itself", async () => {
    expect(await subdomainOn("allstore.am")).toBeNull();
  });

  it("is null on www, which is the marketplace under another name", async () => {
    expect(await subdomainOn("www.allstore.am")).toBeNull();
  });

  it("ignores the port a development host carries", async () => {
    expect(await subdomainOn("shop.allstore.am:3000")).toBe("shop");
  });

  it("is null on a host that is not ours at all", async () => {
    expect(await subdomainOn("example.com")).toBeNull();
  });

  it("is null when the request carried no host", async () => {
    expect(await subdomainOn(null)).toBeNull();
  });
});
