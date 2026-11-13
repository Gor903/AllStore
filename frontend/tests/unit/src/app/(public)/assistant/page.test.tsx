import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

/**
 * The assistant's page.
 *
 * Rendered per request, which the page does not otherwise need: the Content-Security-Policy
 * carries a fresh nonce and Next.js can only attach it while rendering. Prerendered at build
 * time there would be no nonce to attach, and the page's own scripts would be the ones the
 * policy refused — so `dynamic` is asserted here as the load-bearing line it is.
 */

vi.mock("@/components/assistant/AssistantChat", () => ({
  AssistantChat: () => <div data-testid="chat" />,
}));

vi.mock("@/components/SiteHeader", () => ({
  SiteHeader: () => <header data-testid="site-header" />,
}));

const page = await import("@/app/(public)/assistant/page");
const AssistantPage = page.default;

describe("assistant page", () => {
  it("is rendered per request, because the nonce is attached while rendering", () => {
    expect(page.dynamic).toBe("force-dynamic");
  });

  it("wears the marketplace chrome", () => {
    render(AssistantPage());

    expect(screen.getByTestId("site-header")).toBeInTheDocument();
  });

  it("says what the assistant is for and what it will not do", () => {
    render(AssistantPage());

    expect(screen.getByRole("heading", { name: "Помощник", level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/только о товарах, которые есть на площадке/i)).toBeInTheDocument();
  });

  it("puts the conversation on the page", () => {
    render(AssistantPage());

    expect(screen.getByTestId("chat")).toBeInTheDocument();
  });
});
