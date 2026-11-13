import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StoreHeader } from "@/components/StoreHeader";
import { env } from "@/lib/env";

/**
 * What a shop wears on its own subdomain: its name, its mark, and a way back.
 *
 * The way back is an `<a>` and not a `<Link>`, and that is the whole point of it: the
 * marketplace catalogue lives on another host, and a client-side navigation would look for
 * `/catalog` on the shop's own subdomain, where there is no such page.
 */

describe("StoreHeader", () => {
  it("is a header, so a screen reader can skip it", () => {
    render(<StoreHeader displayName="Ромашка" homeHref="/" />);

    expect(screen.getByRole("banner")).toBeInTheDocument();
  });

  it("leads back to the shop from its own name", () => {
    render(<StoreHeader displayName="Ромашка" homeHref="/" />);

    expect(screen.getByRole("link", { name: /Ромашка/ })).toHaveAttribute("href", "/");
  });

  it("takes an absolute way home where the shop root is somewhere else entirely", () => {
    /* On the marketplace host a storefront is rendered under /s/<subdomain>, so "home" is not
       the root of the host the page is being served from. */
    render(<StoreHeader displayName="Ромашка" homeHref="/s/cups" />);

    expect(screen.getByRole("link", { name: /Ромашка/ })).toHaveAttribute("href", "/s/cups");
  });

  it("leaves the shop's host to reach the whole catalogue", () => {
    render(<StoreHeader displayName="Ромашка" homeHref="/" />);

    const link = screen.getByRole("link", { name: /Весь каталог/ });
    expect(link).toHaveAttribute("href", `${env.siteUrl}/catalog`);
  });

  it("shows the shop's mark when it has one, with nothing to read out", () => {
    render(
      <StoreHeader displayName="Ромашка" homeHref="/" logoUrl="https://cdn.allstore.am/logo.png" />,
    );

    // decorative: the name is right next to it, and reading it twice is worse than once
    expect(screen.getByRole("presentation")).toHaveAttribute("alt", "");
  });

  it("is a header and not a hole for a shop with no mark", () => {
    render(<StoreHeader displayName="Ромашка" homeHref="/" />);

    expect(screen.queryByRole("presentation")).not.toBeInTheDocument();
    expect(screen.getByText("Ромашка")).toBeInTheDocument();
  });
});
