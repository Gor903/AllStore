import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Activity, SystemState } from "@/lib/api";

/**
 * The machine and the platform, read at the moment of the request.
 *
 * No history is kept — no table of measurements, no background collector — and the page says so,
 * along with the thing that would otherwise read as a bug: inside a container the processor and
 * memory figures are the machine's, so under a quota they disagree with what the container
 * actually has.
 *
 * The activity table shares one scale across every column. Scaled per column, a quiet day of
 * registrations would draw the same bar as a busy day of logins, and the table would say the
 * opposite of the truth at a glance.
 */

vi.mock("@/lib/dal", () => ({
  requireRole: vi.fn(),
  getSystemState: vi.fn(),
  getActivity: vi.fn(),
}));

vi.mock("@/components/admin/AdminNav", () => ({
  AdminNav: ({ current }: { current: string }) => (
    <header data-testid="nav" data-current={current} />
  ),
}));

vi.mock("@/components/admin/SystemState", () => ({
  SystemStateCards: ({ initial }: { initial: SystemState | null }) => (
    <div data-testid="cards" data-empty={String(initial === null)} />
  ),
}));

const { requireRole, getSystemState, getActivity } = await import("@/lib/dal");
const { default: SystemPage } = await import("@/app/(admin)/admin/system/page");

function day(date: string, registrations: number, logins: number) {
  return { day: date, registrations, logins, products: 0, reports: 0 };
}

beforeEach(() => {
  vi.mocked(requireRole)
    .mockReset()
    .mockResolvedValue({ id: "1", role: "admin" } as never);
  vi.mocked(getSystemState)
    .mockReset()
    .mockResolvedValue({ cpu_percent: 4, users: 12 } as unknown as SystemState);
  vi.mocked(getActivity)
    .mockReset()
    .mockResolvedValue({
      days: [day("2026-11-12", 1, 20), day("2026-11-13", 0, 4)],
    } as unknown as Activity);
});

describe("the system screen", () => {
  it("is the administrator's screen and nobody else's", async () => {
    render(await SystemPage());

    expect(requireRole).toHaveBeenCalledWith("admin");
  });

  it("says nothing is stored and why the container figures look wrong", async () => {
    render(await SystemPage());

    expect(screen.getByText(/история не хранится/i)).toBeInTheDocument();
    expect(screen.getByText(/цифры разойдутся с настоящими/i)).toBeInTheDocument();
  });

  it("asks for a fortnight of activity", async () => {
    render(await SystemPage());

    expect(getActivity).toHaveBeenCalledWith(14);
  });

  it("hands a state it could not read straight through to the cards", async () => {
    vi.mocked(getSystemState).mockResolvedValue(null);

    render(await SystemPage());

    expect(screen.getByTestId("cards")).toHaveAttribute("data-empty", "true");
  });

  it("says there is no activity data rather than drawing an empty table", async () => {
    vi.mocked(getActivity).mockResolvedValue(null);

    render(await SystemPage());

    expect(screen.getByText("Данных пока нет.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("draws every day it was given, quiet ones included", async () => {
    render(await SystemPage());

    expect(screen.getAllByRole("row")).toHaveLength(3); // the head and two days
  });

  it("scales every column against one peak, so a quiet column stays quiet", async () => {
    const { container } = render(await SystemPage());

    const widths = [...container.querySelectorAll<HTMLElement>("span[style]")].map(
      (bar) => bar.style.width,
    );
    // twenty logins against one registration on the same scale: 100% and 5%
    expect(widths).toContain("100%");
    expect(widths).toContain("5%");
  });

  it("draws nothing wider than its track even on the busiest day", async () => {
    const { container } = render(await SystemPage());

    const widths = [...container.querySelectorAll<HTMLElement>("span[style]")].map((bar) =>
      parseFloat(bar.style.width),
    );
    expect(Math.max(...widths)).toBeLessThanOrEqual(100);
  });
});
