import type { MetadataRoute } from "next";

import { fetchCatalogProducts, fetchCatalogStores } from "@/lib/api";
import { productUrl, siteUrl, storeUrl } from "@/lib/urls";

// the catalogue changes whenever a moderator approves something, so the file is built
// on request rather than pinned at build time
export const dynamic = "force-dynamic";

const PAGE = 100;
// at most this many addresses of one kind. Beyond it a sitemap has to be split into
// several files, and that is a job for the day the catalogue is actually that big
const MAX_ENTRIES = 5000;

type Page<T> = { items: T[]; total: number };

async function collect<T>(read: (offset: number) => Promise<Page<T> | null>): Promise<T[]> {
  const collected: T[] = [];
  let offset = 0;
  while (collected.length < MAX_ENTRIES) {
    const page = await read(offset);
    // a backend that cannot answer leaves the sitemap short rather than broken
    if (page === null || page.items.length === 0) {
      break;
    }
    collected.push(...page.items);
    offset += page.items.length;
    if (offset >= page.total) {
      break;
    }
  }
  return collected.slice(0, MAX_ENTRIES);
}

/** Only what the public catalogue already agrees to show — the same rules, one source. */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [products, stores] = await Promise.all([
    collect((offset) =>
      fetchCatalogProducts({ q: null, category: null, store: null, offset }, PAGE),
    ),
    collect((offset) => fetchCatalogStores(offset, PAGE)),
  ]);

  return [
    { url: siteUrl("/"), changeFrequency: "daily", priority: 1 },
    { url: siteUrl("/catalog"), changeFrequency: "daily", priority: 0.9 },
    { url: siteUrl("/stores"), changeFrequency: "weekly", priority: 0.7 },
    ...stores.map((store) => ({
      url: storeUrl(store.subdomain),
      changeFrequency: "weekly" as const,
      priority: 0.6,
    })),
    ...products.map((product) => ({
      url: productUrl(product.store.subdomain, product.id),
      // the public view carries no updated_at, and the day a product appeared is closer
      // to the truth than the day the file was built
      lastModified: product.created_at,
      changeFrequency: "weekly" as const,
      priority: 0.8,
    })),
  ];
}
