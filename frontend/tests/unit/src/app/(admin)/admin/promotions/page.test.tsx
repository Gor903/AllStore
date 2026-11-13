import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * A section that does not exist yet.
 *
 * The page is here so the question has a place to land rather than to pretend at an answer: the
 * tab exists in the navigation, and a tab leading to a 404 reads as something broken. What it
 * says is that nothing has been decided and that guessing would mean building something to throw
 * away — and the only thing it actually asserts about the platform is that the permission is
 * already in place.
 */

vi.mock("@/lib/dal", () => ({ requireRole: vi.fn() }));

vi.mock("@/components/admin/AdminNav", () => ({
  AdminNav: ({ current }: { current: string }) => (
    <header data-testid="nav" data-current={current} />
  ),
}));

const { requireRole } = await import("@/lib/dal");
const { default: PromotionsPage } = await import("@/app/(admin)/admin/promotions/page");

beforeEach(() => {
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue({ id: "1", role: "admin" } as never);
});

describe("the promotions section", () => {
  it("is already shut to everybody but the administrator", async () => {
    render(await PromotionsPage());

    expect(requireRole).toHaveBeenCalledWith("admin");
  });

  it("says plainly that there is nothing here yet", async () => {
    render(await PromotionsPage());

    expect(screen.getByText(/раздел пока пуст/i)).toBeInTheDocument();
  });

  it("says why it is empty rather than looking unfinished", async () => {
    render(await PromotionsPage());

    expect(screen.getByText(/ещё не описано/i)).toBeInTheDocument();
  });

  it("stands on its own tab, so the navigation does not lead to a 404", async () => {
    render(await PromotionsPage());

    expect(screen.getByTestId("nav")).toHaveAttribute("data-current", "promotions");
  });
});
