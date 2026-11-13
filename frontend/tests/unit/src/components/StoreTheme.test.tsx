import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StoreTheme } from "@/components/StoreTheme";

/**
 * A shop's own colours painted over the shared skeleton.
 *
 * Tailwind's utilities read the theme through CSS variables, so overriding the two brand
 * variables on a wrapper repaints everything inside it — buttons, links, borders — without a
 * single class changing. Which is why what matters here is the variables and the wrapper being
 * `display: contents`: a wrapper that took part in the layout would shift every page it is on.
 *
 * The fallbacks are the interesting part. A shop that chose one colour and not the other must
 * not have a hover that jumps from its own colour back to the platform blue.
 */

function wrapper(primary: string | null, secondary: string | null): HTMLElement {
  render(
    <StoreTheme primary={primary} secondary={secondary}>
      <span data-testid="inside">Чашки</span>
    </StoreTheme>,
  );
  return screen.getByTestId("inside").parentElement as HTMLElement;
}

describe("StoreTheme", () => {
  it("paints both brand variables from the shop's two colours", () => {
    const painted = wrapper("#aa0000", "#550000");

    expect(painted).toHaveStyle({ "--color-brand": "#aa0000", "--color-brand-dark": "#550000" });
  });

  it("follows the primary where no second colour was chosen", () => {
    const painted = wrapper("#aa0000", null);

    expect(painted).toHaveStyle({ "--color-brand": "#aa0000", "--color-brand-dark": "#aa0000" });
  });

  it("takes the secondary as the brand where that is the only colour there is", () => {
    const painted = wrapper(null, "#550000");

    expect(painted).toHaveStyle({ "--color-brand": "#550000", "--color-brand-dark": "#550000" });
  });

  it("adds no wrapper at all for a shop that chose nothing", () => {
    render(
      <StoreTheme primary={null} secondary={null}>
        <span data-testid="inside">Чашки</span>
      </StoreTheme>,
    );

    expect(screen.getByTestId("inside").parentElement?.tagName).toBe("DIV");
    expect(screen.getByTestId("inside").parentElement).not.toHaveAttribute("style");
  });

  it("takes no part in the layout it wraps", () => {
    /* `display: contents` — anything else would put a block between a grid and its cells and
       quietly break the page it was meant only to recolour. */
    expect(wrapper("#aa0000", null)).toHaveClass("contents");
  });

  it("shows what it wraps, whatever the colours are", () => {
    wrapper("#aa0000", "#550000");

    expect(screen.getByText("Чашки")).toBeInTheDocument();
  });
});
