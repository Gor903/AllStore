import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ContactList, CustomerBlockList, Store } from "@/lib/api";

/**
 * How a seller dresses their shop.
 *
 * There is nothing to dress until the shop exists, so a seller without one is sent to the
 * cabinet, which is where it gets created. The contacts and the barred buyers are read
 * alongside, and either of them failing to load must not take the page with it: a seller who
 * came to change a colour should be able to, even while another list is unreachable.
 */

const redirect = vi.fn((to: string) => {
  throw new Error(`redirect:${to}`);
});

vi.mock("next/navigation", () => ({ redirect: (to: string) => redirect(to) }));

vi.mock("@/lib/dal", () => ({
  requireRole: vi.fn(),
  getMyStore: vi.fn(),
  getMyContacts: vi.fn(),
  getMyBlockedBuyers: vi.fn(),
}));

vi.mock("@/components/dashboard/StoreSettingsForm", () => ({
  StoreSettingsForm: () => <form data-testid="settings-form" />,
}));

vi.mock("@/components/dashboard/StoreImageField", () => ({
  StoreImageField: ({ label }: { label: string }) => <div data-testid="image-field">{label}</div>,
}));

vi.mock("@/components/dashboard/ContactsForm", () => ({
  ContactsForm: ({ contacts }: { contacts: unknown[] }) => (
    <div data-testid="contacts-form">{contacts.length}</div>
  ),
}));

vi.mock("@/components/dashboard/BlockedBuyers", () => ({
  BlockedBuyers: ({ items }: { items: unknown[] }) => (
    <div data-testid="blocked-buyers">{items.length}</div>
  ),
}));

const { requireRole, getMyStore, getMyContacts, getMyBlockedBuyers } = await import("@/lib/dal");
const { default: StoreSettingsPage } = await import("@/app/(dashboard)/dashboard/store/page");

function store(): Store {
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
  } as Store;
}

beforeEach(() => {
  redirect.mockClear();
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue({ id: "1" } as never);
  vi.mocked(getMyStore).mockReset().mockResolvedValue(store());
  vi.mocked(getMyContacts)
    .mockReset()
    .mockResolvedValue({ items: [{ platform: "phone" }] } as unknown as ContactList);
  vi.mocked(getMyBlockedBuyers)
    .mockReset()
    .mockResolvedValue({ items: [] } as unknown as CustomerBlockList);
});

describe("store settings page", () => {
  it("is a seller's screen and nobody else's", async () => {
    render(await StoreSettingsPage());

    expect(requireRole).toHaveBeenCalledWith("seller");
  });

  it("shows the address a buyer would visit", async () => {
    render(await StoreSettingsPage());

    const link = screen.getByRole("link", { name: /cups\./ });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });

  it("offers the look, both pictures, the contacts and the shop's own door", async () => {
    render(await StoreSettingsPage());

    expect(screen.getByTestId("settings-form")).toBeInTheDocument();
    expect(screen.getAllByTestId("image-field").map((node) => node.textContent)).toEqual([
      "Логотип",
      "Баннер",
    ]);
    expect(screen.getByTestId("contacts-form")).toHaveTextContent("1");
    expect(screen.getByTestId("blocked-buyers")).toBeInTheDocument();
  });

  it("sends a seller with no shop to the cabinet, where one is created", async () => {
    vi.mocked(getMyStore).mockResolvedValue(null);

    await expect(StoreSettingsPage()).rejects.toThrow("redirect:/dashboard");
  });

  it("still renders when a list beside the shop could not be read", async () => {
    vi.mocked(getMyContacts).mockResolvedValue(null);
    vi.mocked(getMyBlockedBuyers).mockResolvedValue(null);

    render(await StoreSettingsPage());

    expect(screen.getByTestId("settings-form")).toBeInTheDocument();
    expect(screen.getByTestId("contacts-form")).toHaveTextContent("0");
  });

  it("offers the way back to the cabinet", async () => {
    render(await StoreSettingsPage());

    expect(screen.getByRole("link", { name: /Кабинет/ })).toHaveAttribute("href", "/dashboard");
  });
});
