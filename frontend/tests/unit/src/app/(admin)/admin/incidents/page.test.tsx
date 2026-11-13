import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { IncidentList } from "@/lib/api";

/**
 * The administrator's feed of what happened between people.
 *
 * The same component as the moderator's, with a wider feed behind it: the administrator sees
 * everything, moderators' own actions included. The page says what is in it and — just as
 * usefully — what is not: there are no orders and no messaging on the platform yet, so there are
 * no feeds about them either, and an empty feed is not a feed that broke.
 *
 * The filter has to survive a page turn, or page two of one person's history quietly becomes page
 * two of everybody's.
 */

vi.mock("@/lib/dal", () => ({
  ADMIN_PAGE_SIZE: 20,
  requireRole: vi.fn(),
  getIncidents: vi.fn(),
}));

vi.mock("@/components/admin/AdminNav", () => ({
  AdminNav: () => <header data-testid="nav" />,
}));

vi.mock("@/components/moderation/IncidentFeed", () => ({
  IncidentFeed: ({ path, params }: { path: string; params: URLSearchParams }) => (
    <div data-testid="feed" data-path={path} data-params={params.toString()} />
  ),
}));

const { requireRole, getIncidents } = await import("@/lib/dal");
const { default: AdminIncidentsPage } = await import("@/app/(admin)/admin/incidents/page");

const props = (search: Record<string, string> = {}) => ({
  params: Promise.resolve({}),
  searchParams: Promise.resolve(search),
});

beforeEach(() => {
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue({ id: "1", role: "admin" } as never);
  vi.mocked(getIncidents)
    .mockReset()
    .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 } as unknown as IncidentList);
});

describe("the administrator's incident feed", () => {
  it("is the administrator's screen and nobody else's", async () => {
    render(await AdminIncidentsPage(props()));

    expect(requireRole).toHaveBeenCalledWith("admin");
  });

  it("says the administrator sees everything, moderators included", async () => {
    render(await AdminIncidentsPage(props()));

    expect(screen.getByText(/включая действия модераторов/i)).toBeInTheDocument();
  });

  it("says which feeds do not exist yet, so their absence is not a bug", async () => {
    render(await AdminIncidentsPage(props()));

    expect(screen.getByText(/заказов и переписки на площадке пока нет/i)).toBeInTheDocument();
  });

  it("narrows the feed to one person when asked", async () => {
    render(await AdminIncidentsPage(props({ user_id: "u1" })));

    expect(getIncidents).toHaveBeenCalledWith(0, { userId: "u1" });
  });

  it("carries that filter into the paging", async () => {
    render(await AdminIncidentsPage(props({ user_id: "u1" })));

    expect(screen.getByTestId("feed")).toHaveAttribute("data-params", "user_id=u1");
  });

  it("carries nothing when the feed is not narrowed", async () => {
    render(await AdminIncidentsPage(props()));

    expect(screen.getByTestId("feed")).toHaveAttribute("data-params", "");
    expect(getIncidents).toHaveBeenCalledWith(0, { userId: "" });
  });

  it("pages against its own address rather than the moderator's", async () => {
    render(await AdminIncidentsPage(props()));

    expect(screen.getByTestId("feed")).toHaveAttribute("data-path", "/admin/incidents");
  });

  it("names the filter box without a visible label", async () => {
    render(await AdminIncidentsPage(props()));

    expect(screen.getByLabelText("Участник")).toBeInTheDocument();
  });
});
