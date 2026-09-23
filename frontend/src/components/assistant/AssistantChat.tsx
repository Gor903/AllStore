"use client";

import { useState, type FormEvent } from "react";

import { ProductCard } from "@/components/catalog/ProductCard";
import type { AssistantAnswer, CatalogProduct } from "@/lib/api";
import { apiPost } from "@/lib/browser-api";
import { productUrl } from "@/lib/urls";

type Turn = { role: "user" | "assistant"; content: string };

type Exchange = {
  question: string;
  answer: string;
  products: CatalogProduct[];
};

/** How much of the conversation travels back — the backend trims it again on its side. */
const HISTORY_TURNS = 6;

export function AssistantChat() {
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const asked = question.trim();
    if (asked === "") {
      return;
    }
    setPending(true);
    setError(null);

    const history: Turn[] = exchanges
      .flatMap((exchange) => [
        { role: "user" as const, content: exchange.question },
        { role: "assistant" as const, content: exchange.answer },
      ])
      .slice(-HISTORY_TURNS);

    const result = await apiPost<AssistantAnswer>("/assistant/ask", { question: asked, history });
    setPending(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setExchanges((previous) => [
      ...previous,
      { question: asked, answer: result.data.answer, products: result.data.products },
    ]);
    setQuestion("");
  }

  return (
    <div className="flex flex-col gap-6">
      {exchanges.map((exchange, index) => (
        <section key={index} className="flex flex-col gap-3">
          <p className="font-medium">{exchange.question}</p>
          <p className="whitespace-pre-line text-ink-muted">{exchange.answer}</p>
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
        {error === null ? null : (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
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
