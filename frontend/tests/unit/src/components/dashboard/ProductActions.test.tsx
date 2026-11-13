import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProductActions } from "@/components/dashboard/ProductActions";
import type { Product } from "@/lib/api";

/**
 * The two things a seller can do to one of their own products.
 *
 * Sending it for review is refused while a proposal is already in the queue — whether it is the
 * product's first look or an edit to a listing already on the shelf, there is nothing left to
 * press, and a button that cheerfully submits again would put a second proposal in a queue that
 * holds one.
 *
 * Archiving asks first. It takes the product off the shelf for good as far as the seller is
 * concerned, and that is not a thing to do on a mis-click.
 */

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const apiPost = vi.fn();
const apiDelete = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
  apiDelete: (path: string) => apiDelete(path),
}));

const PRODUCT = "11111111-1111-1111-1111-111111111111";

function product(overrides: Partial<Product> = {}): Product {
  return {
    id: PRODUCT,
    name: "Чашка",
    pending_change: null,
    ...overrides,
  } as Product;
}

beforeEach(() => {
  push.mockClear();
  refresh.mockClear();
  apiPost.mockReset().mockResolvedValue({ ok: true, data: undefined });
  apiDelete.mockReset().mockResolvedValue({ ok: true, data: undefined });
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("sending a product for review", () => {
  it("asks the backend to put it in the queue", async () => {
    render(<ProductActions product={product()} />);

    await userEvent.click(screen.getByRole("button", { name: "Отправить на проверку" }));

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(`/products/${PRODUCT}/submit`, {}));
  });

  it("reloads the page, because the status on it has just changed", async () => {
    render(<ProductActions product={product()} />);

    await userEvent.click(screen.getByRole("button", { name: "Отправить на проверку" }));

    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("is not offered while something is already waiting to be judged", () => {
    render(
      <ProductActions
        product={product({
          pending_change: {
            id: "22222222-2222-2222-2222-222222222222",
            name: "Чашка с блюдцем",
            description: null,
            category_id: "33333333-3333-3333-3333-333333333333",
            created_at: "2026-11-13T00:00:00Z",
          },
        })}
      />,
    );

    expect(screen.getByRole("button", { name: "Уже на проверке" })).toBeDisabled();
  });

  it("says why the backend refused rather than failing quietly", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "conflict", message: "Добавьте хотя бы одно фото", fieldErrors: {} },
    });
    render(<ProductActions product={product()} />);

    await userEvent.click(screen.getByRole("button", { name: "Отправить на проверку" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Добавьте хотя бы одно фото");
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("taking a product out of the shop", () => {
  it("asks first, and names the product it is about to remove", async () => {
    render(<ProductActions product={product()} />);

    await userEvent.click(screen.getByRole("button", { name: "Убрать из магазина" }));

    expect(window.confirm).toHaveBeenCalledWith("Убрать «Чашка» из магазина?");
  });

  it("does nothing at all when the question is answered no", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<ProductActions product={product()} />);

    await userEvent.click(screen.getByRole("button", { name: "Убрать из магазина" }));

    expect(apiDelete).not.toHaveBeenCalled();
  });

  it("sends the seller back to a page that still exists", async () => {
    render(<ProductActions product={product()} />);

    await userEvent.click(screen.getByRole("button", { name: "Убрать из магазина" }));

    await waitFor(() => expect(apiDelete).toHaveBeenCalledWith(`/products/${PRODUCT}`));
    expect(push).toHaveBeenCalledWith("/dashboard");
    expect(refresh).toHaveBeenCalled();
  });

  it("keeps the seller where they are when the backend refuses", async () => {
    apiDelete.mockResolvedValue({
      ok: false,
      error: { code: "conflict", message: "Товар уже убран", fieldErrors: {} },
    });
    render(<ProductActions product={product()} />);

    await userEvent.click(screen.getByRole("button", { name: "Убрать из магазина" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Товар уже убран");
    expect(push).not.toHaveBeenCalled();
  });
});

describe("while either is in flight", () => {
  it("nothing else can be pressed", async () => {
    apiPost.mockReturnValue(new Promise(() => {}));
    render(<ProductActions product={product()} />);

    await userEvent.click(screen.getByRole("button", { name: "Отправить на проверку" }));

    expect(screen.getByRole("button", { name: "Убрать из магазина" })).toBeDisabled();
  });
});
