import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AdminNav } from "@/components/admin/AdminNav";

/**
 * The administrator's tabs.
 *
 * Every screen behind them is one an administrator can lock themselves out of, so the thing
 * worth asserting is that each tab leads where its name says and that the current one is
 * marked — a navigation that does not say where you are is one where every page looks like the
 * same page, and the first list of accounts lives at /admin rather than at /admin/users.
 */

vi.mock("@/components/auth/LogoutButton", () => ({
  LogoutButton: () => <button type="button">Выйти</button>,
}));

const TABS: [string, string][] = [
  ["Состояние", "/admin/system"],
  ["Пользователи", "/admin"],
  ["Модераторы", "/admin/moderators"],
  ["Категории", "/admin/categories"],
  ["Инциденты", "/admin/incidents"],
  ["Журнал", "/admin/audit"],
  ["Акции", "/admin/promotions"],
  ["Доступ", "/admin/security"],
];

describe("AdminNav", () => {
  it.each(TABS)("leads to %s", (name, href) => {
    render(<AdminNav current="system" />);

    expect(screen.getByRole("link", { name })).toHaveAttribute("href", href);
  });

  it("leads to the moderation queues as well, because an admin works them too", () => {
    render(<AdminNav current="system" />);

    expect(screen.getByRole("link", { name: "Модерация" })).toHaveAttribute("href", "/moderation");
  });

  it("marks the tab the administrator is on", () => {
    render(<AdminNav current="categories" />);

    expect(screen.getByRole("link", { name: "Категории" })).toHaveClass("bg-brand");
  });

  it("marks exactly one of them", () => {
    render(<AdminNav current="audit" />);

    const marked = screen
      .getAllByRole("link")
      .filter((link) => link.className.includes("bg-brand"));
    expect(marked).toHaveLength(1);
    expect(marked[0]).toHaveTextContent("Журнал");
  });

  it("offers a way out from every screen", () => {
    render(<AdminNav current="system" />);

    expect(screen.getByRole("button", { name: "Выйти" })).toBeInTheDocument();
  });

  it("says where it is, so the page below does not have to", () => {
    render(<AdminNav current="system" />);

    expect(screen.getByRole("heading", { name: "Админка" })).toBeInTheDocument();
  });
});
