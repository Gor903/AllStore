import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SiteHeader } from "@/components/SiteHeader";

/**
 * The marketplace chrome. A storefront on its own subdomain does not wear it — the shop's
 * header is its own, so a buyer inside a shop is not shown somebody else's navigation.
 */

describe("SiteHeader", () => {
  it("is a header, so a screen reader can skip it", () => {
    render(<SiteHeader />);

    expect(screen.getByRole("banner")).toBeInTheDocument();
  });

  it("leads home from the name", () => {
    render(<SiteHeader />);

    expect(screen.getByRole("link", { name: "AllStore.am" })).toHaveAttribute("href", "/");
  });

  it.each([
    ["Каталог", "/catalog"],
    ["Магазины", "/stores"],
    ["Помощник", "/assistant"],
  ])("leads to %s", (name, href) => {
    render(<SiteHeader />);

    expect(screen.getByRole("link", { name })).toHaveAttribute("href", href);
  });

  it("offers a way in", () => {
    render(<SiteHeader />);

    expect(screen.getByRole("link", { name: "Войти" })).toHaveAttribute("href", "/login");
  });

  it("keeps the three sections in one navigation rather than scattered links", () => {
    render(<SiteHeader />);

    expect(screen.getAllByRole("link", { name: /Каталог|Магазины|Помощник/ })).toHaveLength(3);
    expect(screen.getByRole("navigation")).toBeInTheDocument();
  });
});
