import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/urls";

/**
 * The cabinet and the admin area have nothing for a crawler and everything for a session;
 * login and registration are noise in a search result. Everything else is open.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/dashboard", "/admin", "/login", "/register"],
    },
    sitemap: siteUrl("/sitemap.xml"),
  };
}
