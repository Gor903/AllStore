import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ModerationNav } from "@/components/moderation/ModerationNav";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/lib/browser-api", () => ({
  apiPost: vi.fn(),
}));

describe("меню модерации", () => {
  it("показывает админу дорогу обратно в админку", () => {
    render(<ModerationNav current="products" products={3} businesses={1} isAdmin />);

    expect(screen.getByRole("link", { name: "Админка" })).toHaveAttribute("href", "/admin");
  });

  it("модератору про админку не говорит", () => {
    render(<ModerationNav current="products" products={3} businesses={1} />);

    // not a permission check — the server refuses him anyway — but a link that would only
    // bounce him back to the cabinet is worse than no link
    expect(screen.queryByRole("link", { name: "Админка" })).not.toBeInTheDocument();
  });

  it("считает очереди в заголовках вкладок", () => {
    render(<ModerationNav current="reports" products={177} businesses={11} reports={30} />);

    expect(screen.getByRole("link", { name: "Товары (177)" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Продавцы (11)" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Жалобы (30)" })).toBeInTheDocument();
  });
});
