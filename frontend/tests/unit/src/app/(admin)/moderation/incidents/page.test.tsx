import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { IncidentList } from "@/lib/api";

/**
 * A moderator's feed of what passed between buyers and sellers.
 *
 * The same component renders the administrator's feed; what differs is which events the backend
 * puts in it. A moderator does not see events involving another moderator or the administrator,
 * and the screen says so — otherwise an empty feed reads as a feed that is broken.
 */

vi.mock("@/lib/dal", () => ({
  ADMIN_PAGE_SIZE: 20,
  requireRole: vi.fn(),
  getIncidents: vi.fn(),
  getModerationProducts: vi.fn(),
  getModerationBusinesses: vi.fn(),
}));

vi.mock("@/components/moderation/ModerationNav", () => ({
  ModerationNav: ({ current }: { current: string }) => (
    <header data-testid="nav" data-current={current} />
  ),
}));

vi.mock("@/components/moderation/IncidentFeed", () => ({
  IncidentFeed: ({ page, path }: { page: unknown; path: string }) => (
    <div data-testid="feed" data-path={path} data-empty={String(page === null)} />
  ),
}));

const { requireRole, getIncidents, getModerationProducts, getModerationBusinesses } =
  await import("@/lib/dal");
const { default: ModerationIncidentsPage } =
  await import("@/app/(admin)/moderation/incidents/page");

const props = { params: Promise.resolve({}), searchParams: Promise.resolve({}) };

beforeEach(() => {
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue({ id: "1", role: "moderator" } as never);
  vi.mocked(getIncidents)
    .mockReset()
    .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 } as unknown as IncidentList);
  vi.mocked(getModerationProducts)
    .mockReset()
    .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 } as never);
  vi.mocked(getModerationBusinesses)
    .mockReset()
    .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 } as never);
});

describe("the moderator's incident feed", () => {
  it("is open to a moderator and to the administrator", async () => {
    render(await ModerationIncidentsPage(props));

    expect(requireRole).toHaveBeenCalledWith("moderator", "admin");
  });

  it("says what is in the feed and what is deliberately not", async () => {
    render(await ModerationIncidentsPage(props));

    expect(screen.getByText(/между покупателями и продавцами/i)).toBeInTheDocument();
    expect(screen.getByText(/сюда не попадают/i)).toBeInTheDocument();
  });

  it("stands on the moderation side of the navigation", async () => {
    render(await ModerationIncidentsPage(props));

    expect(screen.getByTestId("nav")).toHaveAttribute("data-current", "incidents");
  });

  it("pages against its own address", async () => {
    render(await ModerationIncidentsPage(props));

    expect(screen.getByTestId("feed")).toHaveAttribute("data-path", "/moderation/incidents");
  });

  it("hands a feed it could not read straight through, rather than inventing an empty one", async () => {
    vi.mocked(getIncidents).mockResolvedValue(null);

    render(await ModerationIncidentsPage(props));

    expect(screen.getByTestId("feed")).toHaveAttribute("data-empty", "true");
  });
});
