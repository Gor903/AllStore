import { describe, expect, it } from "vitest";

import { PALETTE, swatchOf } from "@/lib/palette";

/** WCAG relative luminance, the ingredient of the contrast ratio below. */
function luminance(hex: string): number {
  const channels = [1, 3, 5].map((start) => {
    const value = parseInt(hex.slice(start, start + 2), 16) / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrastWithWhite(hex: string): number {
  return 1.05 / (luminance(hex) + 0.05);
}

describe("palette", () => {
  it("carries white text on every colour it offers", () => {
    // this is the whole reason the palette exists instead of a free colour picker:
    // the shared skeleton puts white text on bg-brand, and pale yellow would hide it
    for (const swatch of PALETTE) {
      for (const colour of [swatch.primary, swatch.secondary]) {
        if (colour !== null) {
          expect(contrastWithWhite(colour), `${swatch.name} ${colour}`).toBeGreaterThanOrEqual(4.5);
        }
      }
    }
  });

  it("offers the platform look first, as a pair of nulls", () => {
    expect(PALETTE[0]).toMatchObject({ primary: null, secondary: null });
  });

  it("names every colour once", () => {
    const names = PALETTE.map((swatch) => swatch.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it("finds the pair a shop is already wearing", () => {
    expect(swatchOf("#2f6fed", "#1e4fb8").name).toBe("Синий");
    expect(swatchOf(null, null).name).toBe("Как на площадке");
  });

  it("keeps a pair set outside this screen instead of losing it", () => {
    // set through the API before the screen existed, or left behind by a palette change
    const kept = swatchOf("#123456", "#654321");

    expect(kept).toEqual({ name: "Свой цвет", primary: "#123456", secondary: "#654321" });
  });
});
