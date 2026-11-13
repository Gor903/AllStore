import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AuditLogList } from "@/lib/api";

/**
 * The journal: who did what and when, moderators' decisions included.
 *
 * Entries are not edited and not deleted — that is the point of a journal — so there is no button
 * here that would remove one, for anybody.
 *
 * The filters have to survive a page turn, or page two of a filtered journal quietly means
 * something else: the same offset against a different set of rows. That is what the carried
 * parameters are for, and it is the part of this page a test can actually hold on to.
 */

vi.mock("@/lib/dal", () => ({
  ADMIN_PAGE_SIZE: 20,
  requireRole: vi.fn(),
  getAuditLogs: vi.fn(),
}));

vi.mock("@/components/admin/AdminNav", () => ({
  AdminNav: () => <header data-testid="nav" />,
}));

vi.mock("@/components/catalog/Pagination", () => ({
  Pagination: ({ params, total }: { params: URLSearchParams; total: number }) => (
    <nav data-testid="pagination" data-params={params.toString()} data-total={total} />
  ),
}));

const { requireRole, getAuditLogs } = await import("@/lib/dal");
const { default: AuditLogPage } = await import("@/app/(admin)/admin/audit/page");

function entry(overrides: Record<string, unknown> = {}) {
  return {
    id: "e1",
    action: "user.role_changed",
    entity_type: "user",
    entity_id: "u1",
    details: { from: "buyer", to: "moderator" },
    created_at: "2026-11-13T10:00:00Z",
    actor_email: "admin@allstore.am",
    ...overrides,
  };
}

function page(items: unknown[], total = items.length): AuditLogList {
  return { items, total, limit: 20, offset: 0 } as unknown as AuditLogList;
}

const props = (search: Record<string, string> = {}) => ({
  params: Promise.resolve({}),
  searchParams: Promise.resolve(search),
});

beforeEach(() => {
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue({ id: "1", role: "admin" } as never);
  vi.mocked(getAuditLogs)
    .mockReset()
    .mockResolvedValue(page([entry()]));
});

describe("the journal", () => {
  it("is the administrator's screen and nobody else's", async () => {
    render(await AuditLogPage(props()));

    expect(requireRole).toHaveBeenCalledWith("admin");
  });

  it("says entries cannot be edited or removed, and offers no way to", async () => {
    render(await AuditLogPage(props()));

    expect(screen.getByText(/не редактируются и не удаляются/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /удалить/i })).not.toBeInTheDocument();
  });

  it("names who did it and spells out what was done, in words", async () => {
    render(await AuditLogPage(props()));

    expect(screen.getByText("admin@allstore.am")).toBeInTheDocument();
    expect(screen.getByText(/сменил роль/)).toBeInTheDocument();
    expect(screen.getByText("было: buyer, стало: moderator")).toBeInTheDocument();
  });

  it("says nothing where an entry carries no details", async () => {
    vi.mocked(getAuditLogs).mockResolvedValue(page([entry({ details: {} })]));

    render(await AuditLogPage(props()));

    expect(screen.queryByText(/было:/)).not.toBeInTheDocument();
  });

  it("says an account is gone rather than leaving the author blank", async () => {
    vi.mocked(getAuditLogs).mockResolvedValue(page([entry({ actor_email: null })]));

    render(await AuditLogPage(props()));

    expect(screen.getByText(/аккаунт удалён|площадка/i)).toBeInTheDocument();
  });

  it("asks the backend for what was filtered", async () => {
    render(await AuditLogPage(props({ actor_id: "u1", action: "user.role_changed" })));

    expect(getAuditLogs).toHaveBeenCalledWith(0, { actorId: "u1", action: "user.role_changed" });
  });

  it("carries the filters into the paging, so page two still means the same thing", async () => {
    render(await AuditLogPage(props({ actor_id: "u1", action: "user.role_changed" })));

    const carried = screen.getByTestId("pagination").getAttribute("data-params") ?? "";
    expect(carried).toContain("actor_id=u1");
    expect(carried).toContain("action=user.role_changed");
  });

  it("carries nothing when nothing was filtered", async () => {
    render(await AuditLogPage(props()));

    expect(screen.getByTestId("pagination")).toHaveAttribute("data-params", "");
  });

  it("offers to clear the filters only when there are some", async () => {
    render(await AuditLogPage(props({ actor_id: "u1" })));
    expect(screen.getByRole("link", { name: "Сбросить" })).toHaveAttribute("href", "/admin/audit");

    render(await AuditLogPage(props()));
    expect(screen.queryAllByRole("link", { name: "Сбросить" })).toHaveLength(1);
  });

  it("says nothing has happened yet rather than that the journal broke", async () => {
    vi.mocked(getAuditLogs).mockResolvedValue(page([]));

    render(await AuditLogPage(props()));

    expect(screen.getByText(/пока ничего не происходило/i)).toBeInTheDocument();
  });

  it("says the journal could not be read when it could not", async () => {
    vi.mocked(getAuditLogs).mockResolvedValue(null);

    render(await AuditLogPage(props()));

    expect(screen.getByText(/журнал сейчас недоступен/i)).toBeInTheDocument();
  });

  it("names both filter boxes without a visible label", async () => {
    render(await AuditLogPage(props()));

    expect(screen.getByLabelText("Кто")).toBeInTheDocument();
    expect(screen.getByLabelText("Действие")).toBeInTheDocument();
  });
});
