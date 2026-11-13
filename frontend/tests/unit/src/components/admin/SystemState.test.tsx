import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SystemStateCards } from "@/components/admin/SystemState";
import type { SystemState } from "@/lib/api";

/**
 * The machine and the platform as they are right now.
 *
 * Nothing is stored, so the screen refreshes itself — often enough to watch, rarely enough that
 * watching costs nothing. The failure that matters is the one in the middle: a refresh that does
 * not come back must keep the last numbers and say they are old. Blanking the page would turn a
 * hiccup into an outage on the one screen meant to report outages.
 */

const apiGet = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiGet: (path: string) => apiGet(path),
}));

const REFRESH_MS = 15_000;

function state(overrides: Partial<SystemState> = {}): SystemState {
  return {
    cpu_percent: 4.5,
    memory_percent: 31,
    memory_total_mb: 16000,
    memory_used_mb: 5000,
    disk_percent: 42,
    disk_total_gb: 500,
    disk_free_gb: 290,
    uptime_seconds: 3600,
    users: 12,
    sellers: 3,
    products: 40,
    businesses_pending: 1,
    reports_open: 2,
    live_sessions: 5,
    database_size_mb: 64,
    ...overrides,
  };
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  apiGet.mockReset().mockResolvedValue({ ok: true, data: state() });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("SystemStateCards", () => {
  it("shows what the server rendered, without asking again first", () => {
    render(<SystemStateCards initial={state()} />);

    expect(screen.getByText("Процессор")).toBeInTheDocument();
    expect(apiGet).not.toHaveBeenCalled();
  });

  it("says the state could not be read when there is nothing to show", () => {
    render(<SystemStateCards initial={null} />);

    expect(screen.getByText(/состояние сейчас недоступно/i)).toBeInTheDocument();
  });

  it("reads the machine, the platform and the database in one place", () => {
    render(<SystemStateCards initial={state()} />);

    expect(screen.getByText("5000 из 16000 МБ")).toBeInTheDocument();
    expect(screen.getByText("290 ГБ свободно из 500")).toBeInTheDocument();
    expect(screen.getByText("64 МБ")).toBeInTheDocument();
    expect(screen.getByText("Жалоб открыто")).toBeInTheDocument();
  });

  it("says an uptime in hours, and in days once there are days of it", () => {
    render(<SystemStateCards initial={state({ uptime_seconds: 3600 * 5 })} />);
    expect(screen.getByText("5 ч")).toBeInTheDocument();

    render(<SystemStateCards initial={state({ uptime_seconds: 86_400 * 2 + 3600 * 3 })} />);
    expect(screen.getByText("2 д 3 ч")).toBeInTheDocument();
  });

  it("refreshes itself", async () => {
    render(<SystemStateCards initial={state()} />);

    apiGet.mockResolvedValue({ ok: true, data: state({ users: 13 }) });
    await vi.advanceTimersByTimeAsync(REFRESH_MS);

    await waitFor(() => expect(screen.getByText("13")).toBeInTheDocument());
  });

  it("keeps the last numbers when a refresh does not come back, and says they are old", async () => {
    render(<SystemStateCards initial={state()} />);

    apiGet.mockResolvedValue({
      ok: false,
      error: { code: "offline", message: "Сервер недоступен", fieldErrors: {} },
    });
    await vi.advanceTimersByTimeAsync(REFRESH_MS);

    expect(await screen.findByRole("status")).toHaveTextContent(/могли устареть/i);
    expect(screen.getByText("5000 из 16000 МБ")).toBeInTheDocument();
  });

  it("stops saying so once a refresh gets through again", async () => {
    render(<SystemStateCards initial={state()} />);
    apiGet.mockResolvedValue({
      ok: false,
      error: { code: "offline", message: "Сервер недоступен", fieldErrors: {} },
    });
    await vi.advanceTimersByTimeAsync(REFRESH_MS);
    await screen.findByRole("status");

    apiGet.mockResolvedValue({ ok: true, data: state() });
    await vi.advanceTimersByTimeAsync(REFRESH_MS);

    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
  });

  it("stops asking once the screen is gone", async () => {
    const { unmount } = render(<SystemStateCards initial={state()} />);

    unmount();
    await vi.advanceTimersByTimeAsync(REFRESH_MS * 3);

    expect(apiGet).not.toHaveBeenCalled();
  });

  it("colours a bar red once it is nearly full", () => {
    const { container } = render(<SystemStateCards initial={state({ disk_percent: 95 })} />);

    expect(container.querySelector(".bg-danger")).not.toBeNull();
  });

  it("does not let a bar run past the end of its track", () => {
    /* `psutil` can report over a hundred on a busy multi-core machine, and a bar wider than
       its box paints over the tile next to it. */
    const { container } = render(<SystemStateCards initial={state({ cpu_percent: 140 })} />);

    const bars = [...container.querySelectorAll<HTMLElement>("div[style]")];
    expect(bars.every((bar) => parseInt(bar.style.width, 10) <= 100)).toBe(true);
  });
});
