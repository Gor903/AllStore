import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CategoryTree } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  fetchCategories: vi.fn(),
}));

vi.mock("@/lib/dal", () => ({
  requireRole: vi.fn(),
}));

// the form is a client component with its own router and network; what is under test is the
// page's decision to render it at all
vi.mock("@/components/dashboard/ProductForm", () => ({
  ProductForm: () => <form aria-label="Карточка товара" />,
}));

const { fetchCategories } = await import("@/lib/api");
const { default: NewProductPage } = await import("@/app/(dashboard)/dashboard/products/new/page");

const TREE: CategoryTree[] = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    slug: "home",
    name: "Для дома",
    children: [
      {
        id: "22222222-2222-2222-2222-222222222222",
        slug: "tableware",
        name: "Посуда",
        children: [],
      },
    ],
  },
];

beforeEach(() => {
  vi.mocked(fetchCategories).mockReset();
});

describe("новый товар без справочника категорий", () => {
  it("вместо формы говорит, что справочник недоступен", async () => {
    vi.mocked(fetchCategories).mockResolvedValue(null);

    render(await NewProductPage());

    expect(screen.getByText(/Справочник категорий сейчас недоступен/)).toBeInTheDocument();
    // the whole point: no form to fill in and fail on submit
    expect(screen.queryByRole("form", { name: "Карточка товара" })).not.toBeInTheDocument();
  });

  it("показывает форму, когда справочник прочитался", async () => {
    vi.mocked(fetchCategories).mockResolvedValue(TREE);

    render(await NewProductPage());

    expect(screen.getByRole("form", { name: "Карточка товара" })).toBeInTheDocument();
    expect(screen.queryByText(/Справочник категорий сейчас недоступен/)).not.toBeInTheDocument();
  });

  it("пустой справочник — это не сбой, форма остаётся", async () => {
    vi.mocked(fetchCategories).mockResolvedValue([]);

    render(await NewProductPage());

    expect(screen.getByRole("form", { name: "Карточка товара" })).toBeInTheDocument();
  });
});
