import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProductCard } from "@/components/catalog/ProductCard";
import type { CatalogProduct } from "@/lib/api";

const PRODUCT: CatalogProduct = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "Кружка керамическая",
  description: "Ручная работа",
  price: "1500.00",
  currency: "AMD",
  availability_status: "in_stock",
  category: { slug: "tableware", name: "Посуда" },
  store: { subdomain: "cups", display_name: "Лавка кружек" },
  images: [{ image_url: "https://cdn.example/cup.jpg", alt_text: "Кружка спереди" }],
  created_at: "2026-09-21T00:00:00Z",
};

const HREF = `https://cups.allstore.am/p/${PRODUCT.id}`;

describe("ProductCard", () => {
  it("links where the page told it to", () => {
    render(<ProductCard product={PRODUCT} href={HREF} />);

    expect(screen.getByRole("link")).toHaveAttribute("href", HREF);
  });

  it("shows the name, the price and whose shop it is", () => {
    render(<ProductCard product={PRODUCT} href={HREF} />);

    expect(screen.getByRole("heading")).toHaveTextContent("Кружка керамическая");
    expect(screen.getByText(/1.500 ֏/u)).toBeInTheDocument();
    expect(screen.getByText("Лавка кружек")).toBeInTheDocument();
  });

  it("uses the alt text of the photo", () => {
    render(<ProductCard product={PRODUCT} href={HREF} />);

    expect(screen.getByRole("img")).toHaveAccessibleName("Кружка спереди");
  });

  it("falls back to the product name when the photo has no alt text", () => {
    render(
      <ProductCard
        product={{ ...PRODUCT, images: [{ ...PRODUCT.images[0]!, alt_text: null }] }}
        href={HREF}
      />,
    );

    expect(screen.getByRole("img")).toHaveAccessibleName("Кружка керамическая");
  });

  it("says so when there is no photo at all", () => {
    render(<ProductCard product={{ ...PRODUCT, images: [] }} href={HREF} />);

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("Без фото")).toBeInTheDocument();
  });
});
