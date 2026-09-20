import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProductForm } from "@/components/dashboard/ProductForm";
import type { CategoryTree, Product } from "@/lib/api";

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const apiPost = vi.fn();
const apiPatch = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
  apiPatch: (path: string, body: unknown) => apiPatch(path, body),
}));

const CATEGORY_ID = "44444444-4444-4444-4444-444444444444";

const CATEGORIES: CategoryTree[] = [
  {
    id: "55555555-5555-5555-5555-555555555555",
    slug: "home-and-garden",
    name: "Дом и сад",
    children: [{ id: CATEGORY_ID, slug: "tableware", name: "Посуда", children: [] }],
  },
];

const PRODUCT = {
  id: "11111111-1111-1111-1111-111111111111",
  category_id: CATEGORY_ID,
  name: "Кружка",
  description: "Была",
  price: "1500.00",
  stock_quantity: 3,
} as Product;

beforeEach(() => {
  push.mockClear();
  refresh.mockClear();
  apiPost.mockReset().mockResolvedValue({ ok: true, data: { id: PRODUCT.id } });
  apiPatch.mockReset().mockResolvedValue({ ok: true, data: { id: PRODUCT.id } });
});

async function fillAndSubmit(description: string | null): Promise<void> {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Название"), "Кружка");
  await user.selectOptions(screen.getByLabelText("Категория"), CATEGORY_ID);
  await user.type(screen.getByLabelText("Цена, ֏"), "1500.00");
  if (description !== null) {
    await user.type(screen.getByLabelText("Описание"), description);
  }
  await user.click(screen.getByRole("button", { name: "Создать товар" }));
}

describe("ProductForm", () => {
  it("creates a product and opens its card, where photos are added", async () => {
    render(<ProductForm categories={CATEGORIES} />);

    await fillAndSubmit("Ручная работа");

    await waitFor(() => expect(apiPost).toHaveBeenCalledOnce());
    expect(apiPost).toHaveBeenCalledWith("/products", {
      category_id: CATEGORY_ID,
      name: "Кружка",
      description: "Ручная работа",
      price: "1500.00",
      stock_quantity: 0,
    });
    expect(push).toHaveBeenCalledWith(`/dashboard/products/${PRODUCT.id}`);
  });

  it("clears the description rather than sending an empty string", async () => {
    render(<ProductForm categories={CATEGORIES} />);

    await fillAndSubmit(null);

    await waitFor(() => expect(apiPost).toHaveBeenCalledOnce());
    expect(apiPost.mock.calls[0]?.[1]).toMatchObject({ description: null });
  });

  it("edits an existing product instead of creating a second one", async () => {
    const user = userEvent.setup();
    render(<ProductForm categories={CATEGORIES} product={PRODUCT} />);

    expect(screen.getByLabelText("Название")).toHaveValue("Кружка");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(apiPatch).toHaveBeenCalledOnce());
    expect(apiPatch.mock.calls[0]?.[0]).toBe(`/products/${PRODUCT.id}`);
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("shows what the backend refused", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { message: "Категория не найдена", fieldErrors: { category_id: "Не найдена" } },
    });
    render(<ProductForm categories={CATEGORIES} />);

    await fillAndSubmit("Ручная работа");

    expect(await screen.findByRole("alert")).toHaveTextContent("Не найдена");
  });
});
