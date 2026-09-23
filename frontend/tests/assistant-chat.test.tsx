import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CatalogProduct } from "@/lib/api";

vi.mock("@/lib/browser-api", () => ({ apiPostLines: vi.fn() }));

const { apiPostLines } = await import("@/lib/browser-api");
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

/** The answer arrives as lines; the tests script them the way the backend sends them. */
function streaming(...lines: unknown[]) {
  return async function* () {
    for (const line of lines) {
      yield line;
    }
  };
}

beforeEach(() => {
  vi.mocked(apiPostLines).mockReset();
});

describe("assistant", () => {
  it("shows the answer and the products behind it", async () => {
    vi.mocked(apiPostLines).mockImplementation(
      streaming(
        { type: "products", products: [VASE] },
        { type: "answer", text: "Нашёл вазу ручной работы." },
      ) as typeof apiPostLines,
    );

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

  it("shows the cards while the model is still writing", async () => {
    let releaseAnswer: () => void = () => {};
    const written = new Promise<void>((resolve) => {
      releaseAnswer = resolve;
    });
    vi.mocked(apiPostLines).mockImplementation(async function* () {
      yield { type: "products", products: [VASE] };
      await written;
      yield { type: "answer", text: "Нашёл вазу ручной работы." };
    } as typeof apiPostLines);

    render(<AssistantChat />);
    await userEvent.type(screen.getByLabelText(/Опишите/u), "ваза");
    await userEvent.click(screen.getByRole("button", { name: "Спросить" }));

    // this is the whole point: search takes a moment, the model takes twenty seconds
    await waitFor(() => expect(screen.getByRole("link", { name: /Ваза/u })).toBeInTheDocument());
    expect(screen.queryByText("Нашёл вазу ручной работы.")).not.toBeInTheDocument();
    expect(screen.getByText(/пишу ответ/u)).toBeInTheDocument();

    releaseAnswer();
    await waitFor(() => expect(screen.getByText("Нашёл вазу ручной работы.")).toBeInTheDocument());
    expect(screen.queryByText(/пишу ответ/u)).not.toBeInTheDocument();
  });

  it("sends the conversation back so a follow-up makes sense", async () => {
    vi.mocked(apiPostLines).mockImplementation(
      streaming({ type: "answer", text: "Вот вазы." }) as typeof apiPostLines,
    );

    render(<AssistantChat />);
    const field = screen.getByLabelText(/Опишите/u);
    await userEvent.type(field, "вазы");
    await userEvent.click(screen.getByRole("button", { name: "Спросить" }));
    await waitFor(() => expect(screen.getByText("Вот вазы.")).toBeInTheDocument());
    await userEvent.type(field, "а подешевле?");
    await userEvent.click(screen.getByRole("button", { name: "Спросить" }));

    await waitFor(() => expect(vi.mocked(apiPostLines)).toHaveBeenCalledTimes(2));
    const [, body] = vi.mocked(apiPostLines).mock.calls[1] ?? [];
    expect(body).toEqual({
      question: "а подешевле?",
      history: [
        { role: "user", content: "вазы" },
        { role: "assistant", content: "Вот вазы." },
      ],
    });
  });

  it("shows a failure that arrives in the middle of the stream", async () => {
    vi.mocked(apiPostLines).mockImplementation(
      streaming({
        type: "error",
        message: "Помощник сейчас не отвечает. Поиск по каталогу работает как обычно.",
      }) as typeof apiPostLines,
    );

    render(<AssistantChat />);
    await userEvent.type(screen.getByLabelText(/Опишите/u), "ваза");
    await userEvent.click(screen.getByRole("button", { name: "Спросить" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Поиск по каталогу работает");
  });

  it("keeps the question when the assistant is not available", async () => {
    vi.mocked(apiPostLines).mockImplementation(async function* () {
      // the stream never opens: the endpoint refused before the first line
      yield await Promise.reject({ message: "Помощник пока не подключён.", fieldErrors: {} });
    } as typeof apiPostLines);

    render(<AssistantChat />);
    await userEvent.type(screen.getByLabelText(/Опишите/u), "ваза");
    await userEvent.click(screen.getByRole("button", { name: "Спросить" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Помощник пока не подключён.");
    // retrying should not mean typing it again
    expect(screen.getByLabelText(/Опишите/u)).toHaveValue("ваза");
  });

  it("does not ask an empty question", async () => {
    render(<AssistantChat />);

    await userEvent.click(screen.getByRole("button", { name: "Спросить" }));

    expect(vi.mocked(apiPostLines)).not.toHaveBeenCalled();
  });
});
