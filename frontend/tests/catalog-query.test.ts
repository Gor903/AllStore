import { describe, expect, it } from "vitest";

import { catalogSearchParams, parseCatalogQuery, toSearchParams } from "@/lib/catalog-query";

const EMPTY = { q: null, category: null, store: null, offset: 0 };

describe("toSearchParams", () => {
  it("keeps what Next hands over", () => {
    const params = toSearchParams({ q: "кружка", category: "cups" });

    expect(params.get("q")).toBe("кружка");
    expect(params.get("category")).toBe("cups");
  });

  it("takes the first value of a repeated key", () => {
    expect(toSearchParams({ category: ["cups", "mugs"] }).get("category")).toBe("cups");
  });

  it("drops what is not there", () => {
    expect(toSearchParams({ q: undefined, category: [] }).toString()).toBe("");
  });
});

describe("parseCatalogQuery", () => {
  it("reads the filters out of the address bar", () => {
    const query = parseCatalogQuery(
      new URLSearchParams({ q: "  кружка ", category: "cups", store: "shop", offset: "48" }),
    );

    expect(query).toEqual({ q: "кружка", category: "cups", store: "shop", offset: 48 });
  });

  it("treats an empty search box as no search at all", () => {
    expect(parseCatalogQuery(new URLSearchParams({ q: "   " }))).toEqual(EMPTY);
  });

  it.each(["-1", "abc", "1.5", "", "9007199254740993"])(
    "falls back to the first page on offset=%s",
    (offset) => {
      expect(parseCatalogQuery(new URLSearchParams({ offset })).offset).toBe(0);
    },
  );
});

describe("catalogSearchParams", () => {
  it("survives a round trip", () => {
    const query = { q: "кружка", category: "cups", store: "shop", offset: 24 };

    expect(parseCatalogQuery(catalogSearchParams(query))).toEqual(query);
  });

  it("writes nothing when nothing is chosen", () => {
    expect(catalogSearchParams(EMPTY).toString()).toBe("");
  });

  it("leaves the first page out of the address", () => {
    expect(catalogSearchParams({ ...EMPTY, q: "кружка" }).has("offset")).toBe(false);
  });
});
