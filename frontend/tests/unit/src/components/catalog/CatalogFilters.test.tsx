import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CatalogFilters } from "@/components/catalog/CatalogFilters";
import type { CategoryTree } from "@/lib/api";
import type { CatalogQuery } from "@/lib/catalog-query";

/**
 * A plain GET form.
 *
 * Submitting it reloads the page with the filters in the address bar, so search works with no
 * JavaScript at all and every result is a link a visitor can keep, send, or come back to. That
 * is why the test asserts the method and action rather than a click handler: an `onSubmit` here
 * would be a quietly nicer search that nobody can bookmark.
 *
 * The hidden `store` field is the other thing with a reason: a visitor searching inside a shop
 * must stay inside it, and the filter they did not touch has to survive the ones they did.
 */

function query(overrides: Partial<CatalogQuery> = {}): CatalogQuery {
  return { q: null, category: null, store: null, offset: 0, ...overrides };
}

const CATEGORIES: CategoryTree[] = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    slug: "dishes",
    name: "Посуда",
    children: [
      {
        id: "22222222-2222-2222-2222-222222222222",
        slug: "cups",
        name: "Чашки",
        children: [],
      },
    ],
  },
];

describe("CatalogFilters", () => {
  it("puts the filters in the address bar rather than in a click handler", () => {
    const { container } = render(<CatalogFilters categories={[]} query={query()} />);

    const form = container.querySelector("form");
    expect(form).toHaveAttribute("method", "get");
    expect(form).toHaveAttribute("action", "/catalog");
  });

  it("keeps what the visitor searched for", () => {
    render(<CatalogFilters categories={[]} query={query({ q: "ваза" })} />);

    expect(screen.getByLabelText("Поиск товаров")).toHaveValue("ваза");
  });

  it("keeps the category they chose", () => {
    render(<CatalogFilters categories={CATEGORIES} query={query({ category: "cups" })} />);

    expect(screen.getByLabelText("Категория")).toHaveValue("cups");
  });

  it("offers the whole reference book, both levels of it", () => {
    render(<CatalogFilters categories={CATEGORIES} query={query()} />);

    expect(screen.getByRole("option", { name: "Все категории" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Посуда" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Весь раздел" })).toHaveValue("dishes");
    expect(screen.getByRole("option", { name: "Чашки" })).toHaveValue("cups");
  });

  it("keeps the visitor inside the shop they were searching in", () => {
    const { container } = render(
      <CatalogFilters categories={[]} query={query({ store: "cups" })} />,
    );

    expect(container.querySelector('input[name="store"]')).toHaveValue("cups");
  });

  it("adds no shop to a search of the whole catalogue", () => {
    const { container } = render(<CatalogFilters categories={[]} query={query()} />);

    expect(container.querySelector('input[name="store"]')).toBeNull();
  });

  it("bounds what can be typed into the search box", () => {
    /* The backend bounds it too; this is so the refusal never has to happen. */
    render(<CatalogFilters categories={[]} query={query()} />);

    expect(screen.getByLabelText("Поиск товаров")).toHaveAttribute("maxlength", "100");
  });

  it("names both boxes without a visible label on either", () => {
    /* The placeholder is not a label: it disappears the moment somebody types. */
    render(<CatalogFilters categories={[]} query={query()} />);

    expect(screen.getByLabelText("Поиск товаров")).toBeInTheDocument();
    expect(screen.getByLabelText("Категория")).toBeInTheDocument();
  });
});
