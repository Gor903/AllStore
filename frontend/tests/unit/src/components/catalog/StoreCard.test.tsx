import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StoreCard } from "@/components/catalog/StoreCard";
import type { CatalogStore } from "@/lib/api";
import { env } from "@/lib/env";

/**
 * A shop in the listing of shops.
 *
 * The link is the part with a reason behind it: a shop lives on its own subdomain, so the
 * card has to leave this host — a Next.js `<Link>` would navigate on the client and land on a
 * route that does not exist here. The card also has to survive a shop that has filled in
 * nothing but its name, because that is what a shop looks like on its first day.
 */

function store(overrides: Partial<CatalogStore> = {}): CatalogStore {
  return {
    subdomain: "cups",
    display_name: "Ромашка",
    description: null,
    logo_url: null,
    banner_url: null,
    contacts: [],
    ...overrides,
  };
}

describe("StoreCard", () => {
  it("leaves this host, because the shop answers on its own", () => {
    render(<StoreCard store={store()} />);

    const link = screen.getByRole("link", { name: /Ромашка/ });
    expect(link).toHaveAttribute("href", expect.stringContaining(`cups.${env.baseDomain}`));
  });

  it("shows the address a visitor would type", () => {
    render(<StoreCard store={store()} />);

    expect(screen.getByText(`cups.${env.baseDomain}`)).toBeInTheDocument();
  });

  it("shows what the shop says about itself when it has said anything", () => {
    render(<StoreCard store={store({ description: "Чашки ручной работы" })} />);

    expect(screen.getByText("Чашки ручной работы")).toBeInTheDocument();
  });

  it("is a card and not a hole when the shop has only a name", () => {
    render(<StoreCard store={store()} />);

    expect(screen.getByRole("heading", { name: "Ромашка" })).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("shows the logo when there is one, with no alt text to read out", () => {
    render(<StoreCard store={store({ logo_url: "https://cdn.allstore.am/logo.png" })} />);

    // decorative: the shop's name is right beside it, and a screen reader saying it twice
    // is worse than it saying it once
    expect(screen.getByRole("presentation")).toHaveAttribute("alt", "");
  });
});
