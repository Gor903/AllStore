import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusPill } from "@/components/dashboard/StatusPill";
import { TONE_CLASS, type ProductStatus } from "@/lib/product-status";

/**
 * The one line a seller reads about where their product stands.
 *
 * The pill shows the label and nothing else — the hint belongs to the row around it. What is
 * worth asserting is that the tone reaches the markup: a refused product and a published one
 * must not look alike, and "looks alike" is exactly what a wrong class name produces.
 */

function status(overrides: Partial<ProductStatus> = {}): ProductStatus {
  return { label: "Опубликован", tone: "live", hint: null, ...overrides };
}

describe("StatusPill", () => {
  it("says where the product stands", () => {
    render(<StatusPill status={status({ label: "На проверке", tone: "waiting" })} />);

    expect(screen.getByText("На проверке")).toBeInTheDocument();
  });

  it.each(["neutral", "waiting", "live", "refused"] as const)(
    "a %s product does not look like the others",
    (tone) => {
      render(<StatusPill status={status({ tone })} />);

      expect(screen.getByText("Опубликован")).toHaveClass(...TONE_CLASS[tone].split(" "));
    },
  );

  it("carries the label only, because the hint is a sentence and this is a badge", () => {
    render(<StatusPill status={status({ hint: "Модератор скоро посмотрит товар." })} />);

    expect(screen.queryByText(/Модератор/)).not.toBeInTheDocument();
  });
});
