import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Business, User } from "@/lib/api";

/**
 * The second half of becoming a seller, asked when the account came before the shop.
 *
 * A seller granted the role by `scripts.grant_role` has an account and nothing to sell from, so
 * this is the one place that asks the two questions a business cannot exist without. Everybody
 * else is sent away: a buyer has nothing to answer here, and a seller who already has a shop
 * would be filling in a form the backend would refuse.
 */

const redirect = vi.fn((to: string) => {
  throw new Error(`redirect:${to}`);
});

vi.mock("next/navigation", () => ({ redirect: (to: string) => redirect(to) }));

vi.mock("@/lib/dal", () => ({ requireUser: vi.fn(), getMyBusiness: vi.fn() }));

vi.mock("@/components/dashboard/BusinessOnboardingForm", () => ({
  BusinessOnboardingForm: () => <form data-testid="onboarding-form" />,
}));

const { requireUser, getMyBusiness } = await import("@/lib/dal");
const { default: OnboardingPage } = await import("@/app/(dashboard)/onboarding/page");

function account(role: User["role"]): User {
  return { id: "1", email: "person@example.am", role } as User;
}

beforeEach(() => {
  redirect.mockClear();
  vi.mocked(requireUser).mockReset().mockResolvedValue(account("seller"));
  vi.mocked(getMyBusiness).mockReset().mockResolvedValue(null);
});

describe("onboarding page", () => {
  it("asks the seller with no shop the two questions", async () => {
    render(await OnboardingPage());

    expect(screen.getByTestId("onboarding-form")).toBeInTheDocument();
    expect(screen.getByText(/ещё нет магазина/i)).toBeInTheDocument();
  });

  it("says what happens next, so nobody waits for a shop that is in a queue", async () => {
    render(await OnboardingPage());

    expect(screen.getByText(/заявка уйдёт модератору/i)).toBeInTheDocument();
  });

  it.each([
    ["buyer", "/dashboard"],
    ["moderator", "/moderation"],
    ["admin", "/admin"],
  ] as const)("sends a %s where they belong", async (role, home) => {
    vi.mocked(requireUser).mockResolvedValue(account(role));

    await expect(OnboardingPage()).rejects.toThrow(/redirect/);
    expect(redirect).toHaveBeenCalledWith(home);
  });

  it("sends a seller who already has a shop to the cabinet", async () => {
    vi.mocked(getMyBusiness).mockResolvedValue({ id: "b" } as Business);

    await expect(OnboardingPage()).rejects.toThrow("redirect:/dashboard");
  });
});
