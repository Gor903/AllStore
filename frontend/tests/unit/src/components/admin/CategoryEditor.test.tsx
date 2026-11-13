import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CategoryCreateForm, CategoryRow } from "@/components/admin/CategoryEditor";
import type { AdminCategory } from "@/lib/api";

/**
 * The reference book both sides read, edited in place.
 *
 * Nothing here deletes. A deleted category would take the products filed under it with it,
 * which is the whole reason hiding exists — so the test asserts there is no way to delete one
 * and that hiding is offered instead, both ways round.
 *
 * The address cannot be changed afterwards and the form says so: it is what a buyer sees in a
 * filter link, and somebody may have that link saved. An empty choice of section means a
 * top-level category, which the backend spells as `null` rather than as an empty string.
 */

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

const apiPatch = vi.fn();
const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPatch: (path: string, body: unknown) => apiPatch(path, body),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

const CATEGORY = "11111111-1111-1111-1111-111111111111";

function category(overrides: Partial<AdminCategory> = {}): AdminCategory {
  return {
    id: CATEGORY,
    name: "Посуда",
    slug: "dishes",
    status: "active",
    children: [],
    ...overrides,
  };
}

beforeEach(() => {
  refresh.mockClear();
  apiPatch.mockReset().mockResolvedValue({ ok: true, data: category() });
  apiPost.mockReset().mockResolvedValue({ ok: true, data: category() });
});

describe("one row of the reference book", () => {
  it("offers no way to delete a category", () => {
    render(<CategoryRow category={category()} />);

    expect(screen.queryByRole("button", { name: /удалить/i })).not.toBeInTheDocument();
  });

  it("offers to hide one instead, which keeps the products filed under it", async () => {
    render(<CategoryRow category={category()} />);

    await userEvent.click(screen.getByRole("button", { name: "Скрыть" }));

    await waitFor(() =>
      expect(apiPatch).toHaveBeenCalledWith(`/admin/categories/${CATEGORY}`, {
        status: "hidden",
      }),
    );
  });

  it("offers to bring a hidden one back, and says it is hidden", async () => {
    render(<CategoryRow category={category({ status: "hidden" })} />);

    expect(screen.getByText(/скрыта от покупателя/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Вернуть в каталог" }));

    await waitFor(() =>
      expect(apiPatch).toHaveBeenCalledWith(`/admin/categories/${CATEGORY}`, {
        status: "active",
      }),
    );
  });

  it("renames it to what was typed", async () => {
    render(<CategoryRow category={category()} />);

    const box = screen.getByLabelText("Название категории dishes");
    await userEvent.clear(box);
    await userEvent.type(box, "Кухня");
    await userEvent.click(screen.getByRole("button", { name: "Переименовать" }));

    await waitFor(() =>
      expect(apiPatch).toHaveBeenCalledWith(`/admin/categories/${CATEGORY}`, { name: "Кухня" }),
    );
  });

  it("will not rename it to what it is already called", () => {
    render(<CategoryRow category={category()} />);

    expect(screen.getByRole("button", { name: "Переименовать" })).toBeDisabled();
  });

  it("will not rename it to nothing", async () => {
    render(<CategoryRow category={category()} />);

    await userEvent.clear(screen.getByLabelText("Название категории dishes"));

    expect(screen.getByRole("button", { name: "Переименовать" })).toBeDisabled();
  });

  it("shows the address, because it is the thing that cannot change", () => {
    render(<CategoryRow category={category()} />);

    expect(screen.getByText("dishes")).toBeInTheDocument();
  });

  it("names the box after the category, because a page has many of them", () => {
    render(<CategoryRow category={category()} />);

    expect(screen.getByLabelText("Название категории dishes")).toHaveValue("Посуда");
  });

  it("says why a change did not happen", async () => {
    apiPatch.mockResolvedValue({
      ok: false,
      error: { code: "conflict", message: "Под категорией есть товары", fieldErrors: {} },
    });
    render(<CategoryRow category={category()} />);

    await userEvent.click(screen.getByRole("button", { name: "Скрыть" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Под категорией есть товары");
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("adding a category", () => {
  it("sends the name, the address and the section", async () => {
    render(<CategoryCreateForm parents={[category()]} />);

    await userEvent.type(screen.getByLabelText("Название"), "Чашки");
    await userEvent.type(screen.getByLabelText("Адрес"), "cups");
    await userEvent.selectOptions(screen.getByLabelText("Раздел"), CATEGORY);
    await userEvent.click(screen.getByRole("button", { name: "Добавить категорию" }));

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/admin/categories", {
        name: "Чашки",
        slug: "cups",
        parent_id: CATEGORY,
      }),
    );
  });

  it("spells an empty section as null, which is how the backend says top level", async () => {
    render(<CategoryCreateForm parents={[category()]} />);

    await userEvent.type(screen.getByLabelText("Название"), "Посуда");
    await userEvent.type(screen.getByLabelText("Адрес"), "dishes");
    await userEvent.click(screen.getByRole("button", { name: "Добавить категорию" }));

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/admin/categories", {
        name: "Посуда",
        slug: "dishes",
        parent_id: null,
      }),
    );
  });

  it("says the address is final and what it is for", () => {
    render(<CategoryCreateForm parents={[]} />);

    expect(screen.getByText(/поменять его потом нельзя/i)).toBeInTheDocument();
  });

  it("empties the form once the category is added", async () => {
    render(<CategoryCreateForm parents={[]} />);

    await userEvent.type(screen.getByLabelText("Название"), "Чашки");
    await userEvent.type(screen.getByLabelText("Адрес"), "cups");
    await userEvent.click(screen.getByRole("button", { name: "Добавить категорию" }));

    await waitFor(() => expect(screen.getByLabelText("Название")).toHaveValue(""));
    expect(refresh).toHaveBeenCalled();
  });

  it("says why a category was not added", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "conflict", message: "Такой адрес уже занят", fieldErrors: {} },
    });
    render(<CategoryCreateForm parents={[]} />);

    await userEvent.type(screen.getByLabelText("Название"), "Чашки");
    await userEvent.type(screen.getByLabelText("Адрес"), "dishes");
    await userEvent.click(screen.getByRole("button", { name: "Добавить категорию" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Такой адрес уже занят");
    expect(screen.getByLabelText("Название")).toHaveValue("Чашки");
  });

  it("cannot be submitted twice while the first one is in flight", async () => {
    apiPost.mockReturnValue(new Promise(() => {}));
    render(<CategoryCreateForm parents={[]} />);

    await userEvent.type(screen.getByLabelText("Название"), "Чашки");
    await userEvent.type(screen.getByLabelText("Адрес"), "cups");
    await userEvent.click(screen.getByRole("button", { name: "Добавить категорию" }));

    expect(screen.getByRole("button", { name: "Добавляем…" })).toBeDisabled();
  });
});
