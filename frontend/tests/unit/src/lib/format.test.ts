import { describe, expect, it } from "vitest";

import { formatPrice } from "@/lib/format";

// the grouping separator of the ru-RU locale is a narrow no-break space, not a plain one
const SPACE = " ";

describe("formatPrice", () => {
  it("drops the zeroes of a round price", () => {
    expect(formatPrice("1500.00", "AMD")).toBe(`1${SPACE}500 ֏`);
  });

  it("keeps the lepton when there is one", () => {
    expect(formatPrice("1500.50", "AMD")).toBe(`1${SPACE}500,50 ֏`);
  });

  it("falls back to the code of a currency it has no sign for", () => {
    expect(formatPrice("10.00", "GBP")).toBe("10 GBP");
  });

  it("shows what it was given when that is not a number", () => {
    expect(formatPrice("не число", "AMD")).toBe("не число AMD");
  });
});
