import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BusinessOnboardingForm } from "@/components/dashboard/BusinessOnboardingForm";

const replace = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
}));

function mockResponse(status: number, body: unknown = {}): Response {
  return { ok: status < 400, status, json: async () => body } as Response;
}

beforeEach(() => {
  replace.mockClear();
  refresh.mockClear();
});

async function fillIn(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.type(screen.getByLabelText("Юридическое название"), "ИП Петров");
  await user.type(screen.getByLabelText("Название магазина"), "Лавка");
}

describe("BusinessOnboardingForm", () => {
  it("asks for what a shop cannot exist without", () => {
    render(<BusinessOnboardingForm />);

    expect(screen.getByLabelText("Юридическое название")).toBeInTheDocument();
    expect(screen.getByLabelText("Название магазина")).toBeInTheDocument();
  });

  it("sends them to the account's own business endpoint", async () => {
    const fetchMock = vi.fn<(url: string, init: RequestInit) => Promise<Response>>(async () =>
      mockResponse(201),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<BusinessOnboardingForm />);

    await fillIn(user);
    await user.click(screen.getByRole("button", { name: "Отправить на проверку" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    const call = fetchMock.mock.calls.at(0);
    if (!call) {
      throw new Error("fetch was never called");
    }
    const [url, init] = call;
    expect(url).toContain("/users/me/business");
    expect(JSON.parse(String(init.body))).toEqual({
      legal_name: "ИП Петров",
      display_name: "Лавка",
    });
  });

  it("refreshes the cabinet, which reads the business on the server", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => mockResponse(201)),
    );
    const user = userEvent.setup();
    render(<BusinessOnboardingForm />);

    await fillIn(user);
    await user.click(screen.getByRole("button", { name: "Отправить на проверку" }));

    // without the refresh the cached page would send them straight back here
    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/dashboard");
    });
    expect(refresh).toHaveBeenCalled();
  });

  it("shows the refusal and stays put when the account already has one", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        mockResponse(409, {
          error: { code: "business_exists", message: "У этого аккаунта уже есть магазин" },
        }),
      ),
    );
    const user = userEvent.setup();
    render(<BusinessOnboardingForm />);

    await fillIn(user);
    await user.click(screen.getByRole("button", { name: "Отправить на проверку" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("уже есть магазин");
    expect(replace).not.toHaveBeenCalled();
  });
});
