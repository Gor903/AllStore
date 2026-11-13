import { describe, expect, it } from "vitest";

import robots from "@/app/robots";

describe("robots.txt", () => {
  it("keeps crawlers out of the cabinet and the admin area", () => {
    const { rules } = robots();

    expect(rules).toMatchObject({
      userAgent: "*",
      allow: "/",
      disallow: ["/dashboard", "/admin", "/login", "/register"],
    });
  });

  it("points at the sitemap", () => {
    expect(robots().sitemap).toBe("https://allstore.am/sitemap.xml");
  });
});
