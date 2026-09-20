import { describe, expect, it } from "vitest";

import { productHref, productUrl, siteUrl, storeHref, storeUrl } from "@/lib/urls";

const PRODUCT = "11111111-1111-1111-1111-111111111111";

describe("canonical addresses", () => {
  it("puts a shop on its own subdomain", () => {
    expect(storeUrl("cups")).toBe("https://cups.allstore.am/");
  });

  it("puts a product inside the shop that sells it", () => {
    expect(productUrl("cups", PRODUCT)).toBe(`https://cups.allstore.am/p/${PRODUCT}`);
  });

  it("makes an absolute address out of a path on the marketplace", () => {
    expect(siteUrl("/sitemap.xml")).toBe("https://allstore.am/sitemap.xml");
  });
});

describe("links from the host the visitor is on", () => {
  it("leaves the marketplace for the shop", () => {
    expect(productHref("cups", PRODUCT, null)).toBe(`https://cups.allstore.am/p/${PRODUCT}`);
    expect(storeHref("cups", null)).toBe("https://cups.allstore.am/");
  });

  it("stays put inside the shop it is already in", () => {
    expect(productHref("cups", PRODUCT, "cups")).toBe(`/p/${PRODUCT}`);
    expect(storeHref("cups", "cups")).toBe("/");
  });

  it("crosses over from one shop to another", () => {
    expect(productHref("mugs", PRODUCT, "cups")).toBe(`https://mugs.allstore.am/p/${PRODUCT}`);
    expect(storeHref("mugs", "cups")).toBe("https://mugs.allstore.am/");
  });
});
