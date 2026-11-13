import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReportButton } from "@/components/ReportButton";

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

const PRODUCT_ID = "11111111-1111-1111-1111-111111111111";

beforeEach(() => {
  apiPost.mockReset().mockResolvedValue({ ok: true, data: { id: "x" } });
});

async function complain(text: string): Promise<void> {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /Пожаловаться/u }));
  await user.type(screen.getByLabelText("Что не так?"), text);
  await user.click(screen.getByRole("button", { name: "Отправить" }));
}

describe("report button", () => {
  it("does not ask for anything until it is clicked", () => {
    render(<ReportButton productId={PRODUCT_ID} label="Пожаловаться на товар" />);

    expect(screen.queryByLabelText("Что не так?")).not.toBeInTheDocument();
  });

  it("names a product by its id", async () => {
    render(<ReportButton productId={PRODUCT_ID} label="Пожаловаться на товар" />);

    await complain("Продаёт подделку");

    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(apiPost).toHaveBeenCalledWith("/reports", {
      product_id: PRODUCT_ID,
      reason: "Продаёт подделку",
    });
  });

  it("names a shop by the address a visitor sees", async () => {
    // the public storefront deliberately carries no internal identifiers
    render(<ReportButton subdomain="cups" label="Пожаловаться на магазин" />);

    await complain("Не отвечает неделю");

    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(apiPost).toHaveBeenCalledWith("/reports", {
      subdomain: "cups",
      reason: "Не отвечает неделю",
    });
  });

  it("says thank you and asks nothing more", async () => {
    render(<ReportButton productId={PRODUCT_ID} label="Пожаловаться на товар" />);

    await complain("Продаёт подделку");

    // what a moderator decides is not the reporter's business
    expect(await screen.findByText(/Жалоба отправлена/u)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Пожаловаться/u })).not.toBeInTheDocument();
  });

  it("keeps the form open and explains when the backend refuses", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { message: "Товар не найден", fieldErrors: {} },
    });
    render(<ReportButton productId={PRODUCT_ID} label="Пожаловаться на товар" />);

    await complain("Продаёт подделку");

    expect(await screen.findByRole("alert")).toHaveTextContent("Товар не найден");
    expect(screen.getByLabelText("Что не так?")).toBeInTheDocument();
    expect(screen.queryByText(/Жалоба отправлена/u)).not.toBeInTheDocument();
  });

  it("sends nothing when the reason is blank", async () => {
    const user = userEvent.setup();
    render(<ReportButton productId={PRODUCT_ID} label="Пожаловаться на товар" />);

    await user.click(screen.getByRole("button", { name: /Пожаловаться/u }));
    await user.type(screen.getByLabelText("Что не так?"), "   ");
    await user.click(screen.getByRole("button", { name: "Отправить" }));

    expect(apiPost).not.toHaveBeenCalled();
  });

  it("closes without sending when cancelled", async () => {
    const user = userEvent.setup();
    render(<ReportButton productId={PRODUCT_ID} label="Пожаловаться на товар" />);

    await user.click(screen.getByRole("button", { name: /Пожаловаться/u }));
    await user.click(screen.getByRole("button", { name: "Отмена" }));

    expect(apiPost).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Пожаловаться/u })).toBeInTheDocument();
  });
});
