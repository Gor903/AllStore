import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CatalogProduct } from "@/lib/api";

vi.mock("@/lib/browser-api", () => ({ apiPost: vi.fn() }));

const { apiPost } = await import("@/lib/browser-api");
const { AssistantChat } = await import("@/components/assistant/AssistantChat");

const VASE: CatalogProduct = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "Ваза «Гюмри»",
  description: null,
  price: "12500.00",
  currency: "AMD",
  availability_status: "in_stock",
  category: { slug: "tableware", name: "Посуда" },
  store: { subdomain: "keramika", display_name: "Гончарная лавка" },
  images: [],
  created_at: "2026-09-21T00:00:00Z",
};

beforeEach(() => {
  vi.mocked(apiPost).mockReset();
});

describe("assistant", () => {
  it("shows the answer and the products behind it", async () => {
    vi.mocked(apiPost).mockResolvedValue({
      ok: true,
      data: { answer: "Нашёл вазу ручной работы.", products: [VASE] },
    });

    render(<AssistantChat />);
    await userEvent.type(screen.getByLabelText(/Опишите/u), "белая ваза для гостиной");
    await userEvent.click(screen.getByRole("button", { name: "Спросить" }));

    await waitFor(() => {
      expect(screen.getByText("Нашёл вазу ручной работы.")).toBeInTheDocument();
    });
    // the card leaves for the shop that sells it, exactly as in the catalogue
    expect(screen.getByRole("link", { name: /Ваза «Гюмри»/u })).toHaveAttribute(
      "href",
      `https://keramika.allstore.am/p/${VASE.id}`,
    );
  });

  it("sends the conversation back so a follow-up makes sense", async () => {
    vi.mocked(apiPost).mockResolvedValue({
      ok: true,
      data: { answer: "Вот вазы.", products: [] },
    });

    render(<AssistantChat />);
    const field = screen.getByLabelText(/Опишите/u);
    await userEvent.type(field, "вазы");
    await userEvent.click(screen.getByRole("button", { name: "Спросить" }));
    await waitFor(() => expect(screen.getByText("Вот вазы.")).toBeInTheDocument());
    await userEvent.type(field, "а подешевле?");
    await userEvent.click(screen.getByRole("button", { name: "Спросить" }));

    await waitFor(() => expect(vi.mocked(apiPost)).toHaveBeenCalledTimes(2));
    const [, body] = vi.mocked(apiPost).mock.calls[1] ?? [];
    expect(body).toEqual({
      question: "а подешевле?",
      history: [
        { role: "user", content: "вазы" },
        { role: "assistant", content: "Вот вазы." },
      ],
    });
  });

  it("keeps the question when the assistant is not available", async () => {
    vi.mocked(apiPost).mockResolvedValue({
      ok: false,
      error: { message: "Помощник пока не подключён.", fieldErrors: {} },
    });

    render(<AssistantChat />);
    await userEvent.type(screen.getByLabelText(/Опишите/u), "ваза");
    await userEvent.click(screen.getByRole("button", { name: "Спросить" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Помощник пока не подключён.");
    expect(screen.getByLabelText(/Опишите/u)).toHaveValue("ваза");
  });

  it("does not ask an empty question", async () => {
    render(<AssistantChat />);

    await userEvent.click(screen.getByRole("button", { name: "Спросить" }));

    expect(vi.mocked(apiPost)).not.toHaveBeenCalled();
  });
});
