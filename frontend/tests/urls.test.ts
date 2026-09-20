import { describe, expect, it } from "vitest";

import { productUrl, siteUrl, storeUrl } from "@/lib/urls";

describe("canonical addresses", () => {
  it("points a shop at its own subdomain", () => {
    expect(storeUrl("cups")).toBe("https://cups.allstore.am/");
  });

  it("keeps a product on the marketplace domain", () => {
    expect(productUrl("11111111-1111-1111-1111-111111111111")).toBe(
      "https://allstore.am/p/11111111-1111-1111-1111-111111111111",
    );
  });

  it("makes an absolute address out of a path", () => {
    expect(siteUrl("/sitemap.xml")).toBe("https://allstore.am/sitemap.xml");
  });
});
