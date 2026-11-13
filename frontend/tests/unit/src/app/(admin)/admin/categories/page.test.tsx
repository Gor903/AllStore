import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AdminCategory } from "@/lib/api";

/**
 * The reference book both sides read.
 *
 * There is no deletion here, and the page says why: deleting a category would drag the products
 * filed under it along with it, so hiding exists instead — a hidden category leaves the buyer's
 * filter and the products stay exactly where they were.
 *
 * The tree is two levels deep, because two is what the catalogue has, and the new-category form
 * is given the roots as the sections something can be filed under.
 */

vi.mock("@/lib/dal", () => ({ requireRole: vi.fn(), getAdminCategories: vi.fn() }));

vi.mock("@/components/admin/AdminNav", () => ({
  AdminNav: () => <header data-testid="nav" />,
}));

vi.mock("@/components/admin/CategoryEditor", () => ({
  CategoryCreateForm: ({ parents }: { parents: AdminCategory[] }) => (
    <form data-testid="create-form" data-parents={parents.length} />
  ),
  CategoryRow: ({ category, nested }: { category: AdminCategory; nested?: boolean }) => (
    <li data-testid="row" data-nested={String(Boolean(nested))}>
      {category.name}
    </li>
  ),
}));

const { requireRole, getAdminCategories } = await import("@/lib/dal");
const { default: CategoriesPage } = await import("@/app/(admin)/admin/categories/page");

function tree(): AdminCategory[] {
  return [
    {
      id: "c1",
      name: "Посуда",
      slug: "dishes",
      status: "active",
      children: [{ id: "c2", name: "Чашки", slug: "cups", status: "active", children: [] }],
    },
  ];
}

beforeEach(() => {
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue({ id: "1", role: "admin" } as never);
  vi.mocked(getAdminCategories).mockReset().mockResolvedValue(tree());
});

describe("the categories screen", () => {
  it("is the administrator's screen and nobody else's", async () => {
    render(await CategoriesPage());

    expect(requireRole).toHaveBeenCalledWith("admin");
  });

  it("says hiding is what there is instead of deleting, and why", async () => {
    render(await CategoriesPage());

    expect(screen.getByText(/товары под ней остаются на месте/i)).toBeInTheDocument();
    expect(screen.getByText(/утащило бы товары за собой/i)).toBeInTheDocument();
  });

  it("shows both levels, and marks the nested one", async () => {
    render(await CategoriesPage());

    const rows = screen.getAllByTestId("row");
    expect(rows.map((row) => row.textContent)).toEqual(["Посуда", "Чашки"]);
    expect(rows[1]).toHaveAttribute("data-nested", "true");
  });

  it("offers the roots as the sections a new category can go under", async () => {
    render(await CategoriesPage());

    expect(screen.getByTestId("create-form")).toHaveAttribute("data-parents", "1");
  });

  it("says the reference book could not be read, and offers no form over nothing", async () => {
    vi.mocked(getAdminCategories).mockResolvedValue(null);

    render(await CategoriesPage());

    expect(screen.getByText(/справочник сейчас недоступен/i)).toBeInTheDocument();
    expect(screen.queryByTestId("create-form")).not.toBeInTheDocument();
  });

  it("is still a usable screen for an empty reference book", async () => {
    vi.mocked(getAdminCategories).mockResolvedValue([]);

    render(await CategoriesPage());

    expect(screen.getByTestId("create-form")).toHaveAttribute("data-parents", "0");
    expect(screen.queryAllByTestId("row")).toHaveLength(0);
  });
});
