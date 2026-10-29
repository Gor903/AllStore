import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DeviceList } from "@/components/auth/DeviceList";
import type { Device } from "@/lib/api";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh }),
}));

const apiDelete = vi.fn();
vi.mock("@/lib/browser-api", () => ({
  apiDelete: (path: string) => apiDelete(path),
}));

function device(overrides: Partial<Device> = {}): Device {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    user_agent: "Mozilla/5.0 (Macintosh)",
    ip: "203.0.113.9",
    created_at: "2026-10-01T10:00:00Z",
    last_seen_at: "2026-10-29T10:00:00Z",
    current: false,
    ...overrides,
  };
}

beforeEach(() => {
  refresh.mockReset();
  apiDelete.mockReset().mockResolvedValue({ ok: true, data: undefined });
});

describe("DeviceList", () => {
  it("marks the device being used, so nobody signs themselves out by mistake", () => {
    render(<DeviceList devices={[device({ current: true })]} />);

    expect(screen.getByText("это устройство")).toBeInTheDocument();
  });

  it("says something when a browser did not introduce itself", () => {
    render(<DeviceList devices={[device({ user_agent: null })]} />);

    expect(screen.getByText(/Устройство не представилось/)).toBeInTheDocument();
  });

  it("signs out one device by its own identifier", async () => {
    const user = userEvent.setup();
    render(<DeviceList devices={[device({ id: "abc", current: false })]} />);

    await user.click(screen.getByRole("button", { name: "Выйти здесь" }));

    await waitFor(() => {
      expect(apiDelete).toHaveBeenCalledWith("/auth/sessions/abc");
    });
    expect(refresh).toHaveBeenCalled();
  });

  it("offers the everywhere-else button only when there is an everywhere else", () => {
    const { rerender } = render(<DeviceList devices={[device({ current: true })]} />);

    expect(screen.queryByRole("button", { name: /на всех остальных/ })).not.toBeInTheDocument();

    rerender(<DeviceList devices={[device({ current: true }), device({ id: "other" })]} />);

    expect(screen.getByRole("button", { name: /на всех остальных/ })).toBeInTheDocument();
  });

  it("keeps the current device when signing out everywhere else", async () => {
    const user = userEvent.setup();
    render(<DeviceList devices={[device({ current: true }), device({ id: "other" })]} />);

    await user.click(screen.getByRole("button", { name: /на всех остальных/ }));

    await waitFor(() => {
      expect(apiDelete).toHaveBeenCalledWith("/auth/sessions");
    });
  });

  it("shows why nothing happened when the server refuses", async () => {
    apiDelete.mockResolvedValue({
      ok: false,
      error: { message: "Такого устройства нет", fieldErrors: {} },
    });
    const user = userEvent.setup();
    render(<DeviceList devices={[device({ id: "gone" })]} />);

    await user.click(screen.getByRole("button", { name: "Выйти здесь" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Такого устройства нет");
    expect(refresh).not.toHaveBeenCalled();
  });
});
