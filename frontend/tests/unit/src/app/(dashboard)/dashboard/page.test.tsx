import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Business, ContactList, ProductList, Store, User } from "@/lib/api";

/**
 * The cabinet: one page for a buyer, a seller, a moderator and the administrator.
 *
 * The check lives here rather than in the layout, because layouts do not re-render on
 * navigation — a gate in one would be a gate that stops being checked after the first page.
 *
 * A seller whose role was granted rather than registered has an account and no business, and
 * without the redirect they would be left on a page with nothing to do and nowhere to go. The
 * other pointed thing here is the contacts warning: a shop with no way to reach it cannot send
 * a product for review, and saying so here is what keeps that from looking like a broken button.
 */

const redirect = vi.fn((to: string) => {
  throw new Error(`redirect:${to}`);
});

vi.mock("next/navigation", () => ({ redirect: (to: string) => redirect(to) }));

vi.mock("@/lib/dal", () => ({
  requireUser: vi.fn(),
  getMyBusiness: vi.fn(),
  getMyStore: vi.fn(),
  getMyProducts: vi.fn(),
  getMyContacts: vi.fn(),
}));

vi.mock("@/components/auth/LogoutButton", () => ({
  LogoutButton: () => <button type="button">Выйти</button>,
}));

vi.mock("@/components/auth/VerifyEmailNotice", () => ({
  VerifyEmailNotice: ({ seller }: { seller: boolean }) => (
    <aside data-testid="verify-notice" data-seller={String(seller)} />
  ),
}));

vi.mock("@/components/dashboard/ResubmitBusiness", () => ({
  ResubmitBusiness: () => <button type="button">Отправить заявку снова</button>,
}));

vi.mock("@/components/dashboard/StoreForm", () => ({
  StoreForm: () => <form data-testid="store-form" />,
}));

const { requireUser, getMyBusiness, getMyStore, getMyProducts, getMyContacts } =
  await import("@/lib/dal");
const { default: DashboardPage } = await import("@/app/(dashboard)/dashboard/page");

function account(overrides: Partial<User> = {}): User {
  return {
    id: "1",
    email: "seller@example.am",
    role: "seller",
    email_verified_at: "2026-11-13T00:00:00Z",
    ...overrides,
  } as User;
}

function business(overrides: Partial<Business> = {}): Business {
  return {
    id: "b",
    legal_name: "ООО Ромашка",
    display_name: "Ромашка",
    description: null,
    status: "active",
    status_reason: null,
    created_at: "2026-11-13T00:00:00Z",
    ...overrides,
  } as Business;
}

function store(overrides: Partial<Store> = {}): Store {
  return {
    id: "s",
    business_id: "b",
    subdomain: "cups",
    description: null,
    logo_url: null,
    banner_url: null,
    primary_color: null,
    secondary_color: null,
    theme_id: "default",
    status: "active",
    created_at: "2026-11-13T00:00:00Z",
    ...overrides,
  } as Store;
}

const contacts = (count: number) =>
  ({ items: Array.from({ length: count }, () => ({ platform: "phone" })) }) as ContactList;

beforeEach(() => {
  redirect.mockClear();
  vi.mocked(requireUser).mockReset().mockResolvedValue(account());
  vi.mocked(getMyBusiness).mockReset().mockResolvedValue(business());
  vi.mocked(getMyStore).mockReset().mockResolvedValue(store());
  vi.mocked(getMyProducts)
    .mockReset()
    .mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 } as ProductList);
  vi.mocked(getMyContacts).mockReset().mockResolvedValue(contacts(1));
});

describe("the cabinet", () => {
  it("names the account and offers the way out", async () => {
    render(await DashboardPage());

    expect(screen.getByText("seller@example.am")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Выйти" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Устройства" })).toHaveAttribute("href", "/devices");
  });

  it("asks nothing of the shop for somebody who has none", async () => {
    vi.mocked(requireUser).mockResolvedValue(account({ role: "buyer" }));

    render(await DashboardPage());

    expect(getMyBusiness).not.toHaveBeenCalled();
    expect(screen.queryByRole("heading", { name: "Товары" })).not.toBeInTheDocument();
  });

  it("sends a seller with no business to answer for one", async () => {
    vi.mocked(getMyBusiness).mockResolvedValue(null);

    await expect(DashboardPage()).rejects.toThrow("redirect:/onboarding");
  });

  it("offers the queue to staff who arrived here", async () => {
    vi.mocked(requireUser).mockResolvedValue(account({ role: "moderator" }));

    render(await DashboardPage());

    expect(screen.getByRole("link", { name: /очередь модерации/i })).toHaveAttribute(
      "href",
      "/moderation",
    );
  });

  it("nags about an unconfirmed address, and says whether a shop depends on it", async () => {
    vi.mocked(requireUser).mockResolvedValue(account({ email_verified_at: null }));

    render(await DashboardPage());

    expect(screen.getByTestId("verify-notice")).toHaveAttribute("data-seller", "true");
  });

  it("says a shop awaiting review is invisible, and that products can be made meanwhile", async () => {
    vi.mocked(getMyBusiness).mockResolvedValue(business({ status: "pending" }));

    render(await DashboardPage());

    expect(screen.getByText(/магазин никому не виден/i)).toBeInTheDocument();
  });

  it("shows a refusal with what the moderator wrote, and the way to answer it", async () => {
    vi.mocked(getMyBusiness).mockResolvedValue(
      business({ status: "rejected", status_reason: "Нет документов" }),
    );

    render(await DashboardPage());

    expect(screen.getByText("Нет документов")).toBeInTheDocument();
    expect(screen.getByText(/это не блокировка/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /отправить заявку снова/i })).toBeInTheDocument();
  });

  it("offers to open a storefront to a shop that has none", async () => {
    vi.mocked(getMyStore).mockResolvedValue(null);

    render(await DashboardPage());

    expect(screen.getByTestId("store-form")).toBeInTheDocument();
  });

  it("shows the address, and says when it will start answering", async () => {
    vi.mocked(getMyStore).mockResolvedValue(store({ status: "draft" }));

    render(await DashboardPage());

    expect(screen.getByText(/откроется после одобрения/i)).toBeInTheDocument();
  });

  it("warns a shop with no way to reach it, because that blocks every product", async () => {
    vi.mocked(getMyContacts).mockResolvedValue(contacts(0));

    render(await DashboardPage());

    expect(screen.getByText(/не указан ни один способ связи/i)).toBeInTheDocument();
  });

  it("says nothing about contacts it could not read", async () => {
    vi.mocked(getMyContacts).mockResolvedValue(null);

    render(await DashboardPage());

    expect(screen.queryByText(/не указан ни один способ связи/i)).not.toBeInTheDocument();
  });

  it("invites the first product rather than showing an empty list", async () => {
    render(await DashboardPage());

    expect(screen.getByText(/товаров пока нет/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Добавить товар" })).toHaveAttribute(
      "href",
      "/dashboard/products/new",
    );
  });

  it("lists the products with where each one stands", async () => {
    vi.mocked(getMyProducts).mockResolvedValue({
      items: [
        {
          id: "p1",
          name: "Чашка",
          price: "1500.00",
          currency: "AMD",
          moderation_status: "pending",
          publication_status: "draft",
          pending_change: null,
          change_rejection_reason: null,
          rejection_reason: null,
        },
      ],
      total: 1,
      limit: 100,
      offset: 0,
    } as unknown as ProductList);

    render(await DashboardPage());

    expect(screen.getByRole("link", { name: /Чашка/ })).toHaveAttribute(
      "href",
      "/dashboard/products/p1",
    );
    expect(screen.getByText("На проверке")).toBeInTheDocument();
  });
});
