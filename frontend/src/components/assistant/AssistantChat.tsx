"use client";

import { useState, type FormEvent } from "react";

import { ProductCard } from "@/components/catalog/ProductCard";
import type { CatalogProduct } from "@/lib/api";
import { apiPostLines } from "@/lib/browser-api";
import { productUrl } from "@/lib/urls";

type Turn = { role: "user" | "assistant"; content: string };

type Line =
  | { type: "products"; products: CatalogProduct[] }
  | { type: "answer"; text: string }
  | { type: "error"; message: string };

type Exchange = {
  question: string;
  answer: string;
  products: CatalogProduct[];
  error: string | null;
  pending: boolean;
};

/** How much of the conversation travels back — the backend trims it again on its side. */
const HISTORY_TURNS = 6;

const OFFLINE = "Сервер недоступен, попробуйте позже";

export function AssistantChat() {
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);

  function update(index: number, change: Partial<Exchange>) {
    setExchanges((previous) =>
      previous.map((exchange, at) => (at === index ? { ...exchange, ...change } : exchange)),
    );
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const asked = question.trim();
    if (asked === "") {
      return;
    }
    setPending(true);
    setQuestion("");

    const history: Turn[] = exchanges
      .flatMap((exchange) => [
        { role: "user" as const, content: exchange.question },
        { role: "assistant" as const, content: exchange.answer },
      ])
      .slice(-HISTORY_TURNS);

    let index = 0;
    setExchanges((previous) => {
      index = previous.length;
      return [
        ...previous,
        { question: asked, answer: "", products: [], error: null, pending: true },
      ];
    });

    try {
      for await (const line of apiPostLines<Line>("/assistant/ask", {
        question: asked,
        history,
      })) {
        if (line.type === "products") {
          // cards land while the model is still writing: the search was ready long before it
          setExchanges((previous) =>
            previous.map((exchange, at) =>
              at === index
                ? { ...exchange, products: [...exchange.products, ...line.products] }
                : exchange,
            ),
          );
        } else if (line.type === "answer") {
          update(index, { answer: line.text });
        } else {
          update(index, { error: line.message });
        }
      }
    } catch (error) {
      const message = (error as { message?: string }).message;
      update(index, { error: message ?? OFFLINE });
      // nothing came of it, so the question goes back into the field — unless a new one is there
      setQuestion((current) => (current === "" ? asked : current));
    } finally {
      update(index, { pending: false });
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {exchanges.map((exchange, index) => (
        <section key={index} className="flex flex-col gap-3">
          <p className="font-medium">{exchange.question}</p>

          {exchange.error === null ? null : (
            <p role="alert" className="text-sm text-danger">
              {exchange.error}
            </p>
          )}

          {exchange.answer === "" ? null : (
            <p className="whitespace-pre-line text-ink-muted">{exchange.answer}</p>
          )}

          {exchange.pending && exchange.error === null ? (
            <p className="text-sm text-ink-muted" aria-live="polite">
              {exchange.products.length === 0 ? "Ищу по каталогу…" : "Нашёл, пишу ответ…"}
            </p>
          ) : null}

          {exchange.products.length === 0 ? null : (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              {exchange.products.map((product) => (
                <ProductCard
                  key={product.id}
                  product={product}
                  // the assistant is on the marketplace, so every card leaves for its shop
                  href={productUrl(product.store.subdomain, product.id)}
                />
              ))}
            </div>
          )}
        </section>
      ))}

      <form onSubmit={onSubmit} className="flex flex-col gap-3" noValidate>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Опишите, что вы ищете</span>
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            maxLength={500}
            placeholder="например: небольшая белая ваза для гостиной"
            className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2 outline-none focus:border-brand"
          />
        </label>
        <button
          type="submit"
          disabled={pending}
          className="self-start rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-60"
        >
          {pending ? "Ищу…" : "Спросить"}
        </button>
      </form>
    </div>
  );
}
