import { describe, expect, it } from "vitest";

import { subdomainFromHost } from "@/lib/hosts";

const BASE = "allstore.am";

describe("subdomainFromHost", () => {
  it.each([
    ["cups.allstore.am", "cups"],
    ["CUPS.AllStore.AM", "cups"],
    ["cups.allstore.am:8080", "cups"],
    ["my-shop.allstore.am", "my-shop"],
  ])("reads the storefront label of %s", (host, expected) => {
    expect(subdomainFromHost(host, BASE)).toBe(expected);
  });

  it.each([
    [null],
    [""],
    ["allstore.am"], // the marketplace itself
    ["www.allstore.am"], // serves the marketplace, not a storefront
    ["evil.com"],
    ["cups.evil.com"],
    ["notallstore.am"], // ends with the domain as text only
    ["a.b.allstore.am"],
    ["cups-.allstore.am"],
    ["my_shop.allstore.am"],
    ["ab.allstore.am"],
    ["[::1]:8080"],
  ])("does not read a storefront out of %s", (host) => {
    expect(subdomainFromHost(host, BASE)).toBeNull();
  });
});
