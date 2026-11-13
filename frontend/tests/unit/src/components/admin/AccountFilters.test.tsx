import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AccountFilters } from "@/components/admin/AccountFilters";
import type { AccountQuery } from "@/lib/account-query";

/**
 * Narrowing the administrator's list of accounts.
 *
 * A plain GET form, so a narrowed list stays an address somebody can keep, send on, or open
 * tomorrow. The part that is easy to get wrong is how the tab and the filters compose: the tab
 * travels inside the form as a hidden field, or submitting a filter would quietly drop it, and
 * a tab link drops the paging, or page three of the buyers becomes page three of the sellers —
 * which usually means an empty screen with no explanation.
 */

function query(overrides: Partial<AccountQuery> = {}): AccountQuery {
  return {
    tab: null,
    q: null,
    status: null,
    hasBans: null,
    sort: "registered",
    offset: 0,
    ...overrides,
  };
}

describe("AccountFilters", () => {
  it("puts the filters in the address bar rather than in a click handler", () => {
    const { container } = render(<AccountFilters query={query()} />);

    expect(container.querySelector("form")).toHaveAttribute("method", "get");
  });

  it("offers every tab plus the whole list", () => {
    render(<AccountFilters query={query()} />);

    for (const name of ["Все", "Покупатели", "Продавцы", "Модераторы"]) {
      expect(screen.getByRole("link", { name })).toBeInTheDocument();
    }
  });

  it("marks the tab the administrator is on", () => {
    render(<AccountFilters query={query({ tab: "sellers" })} />);

    expect(screen.getByRole("link", { name: "Продавцы" })).toHaveClass("bg-brand");
    expect(screen.getByRole("link", { name: "Все" })).not.toHaveClass("bg-brand");
  });

  it("marks the whole list when no tab is chosen", () => {
    render(<AccountFilters query={query()} />);

    expect(screen.getByRole("link", { name: "Все" })).toHaveClass("bg-brand");
  });

  it("keeps the filters when the tab changes", () => {
    render(<AccountFilters query={query({ q: "ромашка", status: "blocked" })} />);

    const href = screen.getByRole("link", { name: "Продавцы" }).getAttribute("href") ?? "";
    expect(href).toContain("tab=sellers");
    expect(href).toContain("q=");
    expect(href).toContain("status=blocked");
  });

  it("drops the paging when the tab changes, because the pages are not the same pages", () => {
    render(<AccountFilters query={query({ tab: "buyers", offset: 40 })} />);

    expect(screen.getByRole("link", { name: "Продавцы" }).getAttribute("href")).not.toContain(
      "offset",
    );
  });

  it("leads to a bare address for the whole list with nothing filtered", () => {
    render(<AccountFilters query={query({ tab: "buyers" })} />);

    expect(screen.getByRole("link", { name: "Все" })).toHaveAttribute("href", "/admin");
  });

  it("carries the tab inside the form, or a filter would drop it", () => {
    const { container } = render(<AccountFilters query={query({ tab: "moderators" })} />);

    expect(container.querySelector('input[name="tab"]')).toHaveValue("moderators");
  });

  it("carries no tab at all when the list is not narrowed to one", () => {
    const { container } = render(<AccountFilters query={query()} />);

    expect(container.querySelector('input[name="tab"]')).toBeNull();
  });

  it("shows what was already asked for", () => {
    render(
      <AccountFilters
        query={query({ q: "ромашка", status: "suspended", hasBans: true, sort: "email" })}
      />,
    );

    expect(screen.getByLabelText("Почта или телефон")).toHaveValue("ромашка");
    expect(screen.getByLabelText("Статус")).toHaveValue("suspended");
    expect(screen.getByLabelText("Баны")).toHaveValue("true");
    expect(screen.getByLabelText("Порядок")).toHaveValue("email");
  });

  it("reads no preference about bans as neither yes nor no", () => {
    render(<AccountFilters query={query({ hasBans: null })} />);

    expect(screen.getByLabelText("Баны")).toHaveValue("");
  });

  it("sorts by registration unless something else was asked", () => {
    render(<AccountFilters query={query()} />);

    expect(screen.getByLabelText("Порядок")).toHaveValue("registered");
  });

  it("names every box for a screen reader without crowding the screen", () => {
    /* Four boxes in a row with four visible labels is a wall of words; four boxes with no
       names at all is a form nobody can fill in by voice. */
    render(<AccountFilters query={query()} />);

    for (const name of ["Почта или телефон", "Статус", "Баны", "Порядок"]) {
      expect(screen.getByText(name)).toHaveClass("sr-only");
    }
  });
});
