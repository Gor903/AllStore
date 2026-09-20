import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Pagination } from "@/components/catalog/Pagination";

const PAGE_SIZE = 24;

function renderPagination(offset: number, total: number, params = new URLSearchParams()) {
  render(
    <Pagination
      path="/catalog"
      params={params}
      offset={offset}
      pageSize={PAGE_SIZE}
      total={total}
    />,
  );
}

describe("Pagination", () => {
  it("shows nothing when everything fits on one page", () => {
    renderPagination(0, 10);

    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("offers the next page but not a previous one at the start", () => {
    renderPagination(0, 50);

    expect(screen.getByRole("link", { name: "Вперёд" })).toHaveAttribute(
      "href",
      "/catalog?offset=24",
    );
    expect(screen.queryByRole("link", { name: "Назад" })).not.toBeInTheDocument();
  });

  it("leaves the first page out of the address of the back link", () => {
    renderPagination(24, 50);

    expect(screen.getByRole("link", { name: "Назад" })).toHaveAttribute("href", "/catalog");
  });

  it("keeps the filters the visitor chose", () => {
    renderPagination(0, 50, new URLSearchParams({ q: "кружка", category: "tableware" }));

    expect(screen.getByRole("link", { name: "Вперёд" })).toHaveAttribute(
      "href",
      "/catalog?q=%D0%BA%D1%80%D1%83%D0%B6%D0%BA%D0%B0&category=tableware&offset=24",
    );
  });

  it("counts the pages for the visitor", () => {
    renderPagination(24, 50);

    expect(screen.getByText("Страница 2 из 3")).toBeInTheDocument();
  });
});
