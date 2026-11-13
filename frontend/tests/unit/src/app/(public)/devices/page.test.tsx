import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The list of devices an account is signed in on.
 *
 * Outside the role groups on purpose: a buyer, a seller, a moderator and the administrator all
 * have devices, and none of them should have to go through somebody else's cabinet to find the
 * list. It is also the one page a staff account still owing a second factor has to reach —
 * `owingASecondFactor` is what keeps that from being a redirect to itself.
 *
 * A list that cannot be read says so. The second-factor panel simply disappears, because its
 * absence is not a failure anybody can act on.
 */

vi.mock("@/lib/dal", () => ({
  requireUser: vi.fn(),
  getMyDevices: vi.fn(),
  getSecondFactor: vi.fn(),
}));

vi.mock("@/components/auth/DeviceList", () => ({
  DeviceList: ({ devices }: { devices: unknown[] }) => (
    <div data-testid="devices">{devices.length}</div>
  ),
}));

vi.mock("@/components/auth/SecondFactor", () => ({
  SecondFactor: () => <div data-testid="second-factor" />,
}));

const { requireUser, getMyDevices, getSecondFactor } = await import("@/lib/dal");
const { default: DevicesPage } = await import("@/app/(public)/devices/page");

beforeEach(() => {
  vi.mocked(requireUser)
    .mockReset()
    .mockResolvedValue({ id: "1" } as never);
  vi.mocked(getMyDevices)
    .mockReset()
    .mockResolvedValue({ items: [{ id: "a" }] } as never);
  vi.mocked(getSecondFactor)
    .mockReset()
    .mockResolvedValue({ enabled: false, required: true, recovery_codes_left: 0 });
});

describe("devices page", () => {
  it("lets through a staff account that still owes a second factor", async () => {
    render(await DevicesPage());

    expect(requireUser).toHaveBeenCalledWith({ owingASecondFactor: true });
  });

  it("lists the devices", async () => {
    render(await DevicesPage());

    expect(screen.getByTestId("devices")).toHaveTextContent("1");
  });

  it("says what to do about a line nobody recognises", async () => {
    render(await DevicesPage());

    expect(screen.getByText(/выйдите на всех/i)).toBeInTheDocument();
    expect(screen.getByText(/смените пароль/i)).toBeInTheDocument();
  });

  it("says the list could not be read rather than showing an empty one", async () => {
    vi.mocked(getMyDevices).mockResolvedValue(null);

    render(await DevicesPage());

    expect(screen.getByText(/список устройств сейчас недоступен/i)).toBeInTheDocument();
    expect(screen.queryByTestId("devices")).not.toBeInTheDocument();
  });

  it("offers the second factor where there is something to say about it", async () => {
    render(await DevicesPage());

    expect(screen.getByTestId("second-factor")).toBeInTheDocument();
  });

  it("says nothing about it where its state could not be read", async () => {
    vi.mocked(getSecondFactor).mockResolvedValue(null);

    render(await DevicesPage());

    expect(screen.queryByTestId("second-factor")).not.toBeInTheDocument();
    expect(screen.getByTestId("devices")).toBeInTheDocument();
  });
});
