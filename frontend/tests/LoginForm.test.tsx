import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/auth/LoginForm";

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

function mockResponse(status: number, body: unknown): Response {
  return {
    ok: status < 400,
    status,
    json: async () => body,
  } as Response;
}

beforeEach(() => {
  push.mockClear();
  refresh.mockClear();
  document.cookie = "allstore_csrf=csrf-token-value";
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function submit(email: string, password: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Пароль"), password);
  await user.click(screen.getByRole("button", { name: "Войти" }));
}

describe("LoginForm", () => {
  it("shows the backend message when credentials are wrong", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        mockResponse(401, {
          error: { code: "invalid_credentials", message: "Неверный email или пароль", details: [] },
        }),
      ),
    );
    render(<LoginForm next="/dashboard" />);

    await submit("buyer@example.com", "wrong-password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Неверный email или пароль");
    expect(push).not.toHaveBeenCalled();
  });

  it("shows validation errors next to the field", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        mockResponse(422, {
          error: {
            code: "validation_failed",
            message: "Request validation failed",
            details: [{ loc: ["body", "email"], msg: "не похоже на email" }],
          },
        }),
      ),
    );
    render(<LoginForm next="/dashboard" />);

    await submit("not-an-email", "some-password-1");

    expect(await screen.findByRole("alert")).toHaveTextContent("не похоже на email");
  });

  it("navigates to the requested page after a successful login", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => mockResponse(200, { id: "1", email: "buyer@example.com", role: "buyer" })),
    );
    render(<LoginForm next="/dashboard/orders" />);

    await submit("buyer@example.com", "buyer-password-1");

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/dashboard/orders");
    });
    expect(refresh).toHaveBeenCalled();
  });

  it("sends the session cookie and the CSRF header", async () => {
    const fetchMock = vi.fn<(url: string, init: RequestInit) => Promise<Response>>(async () =>
      mockResponse(200, { id: "1" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<LoginForm next="/dashboard" />);

    await submit("buyer@example.com", "buyer-password-1");

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    const call = fetchMock.mock.calls.at(0);
    if (!call) {
      throw new Error("fetch was never called");
    }
    const [, init] = call;
    expect(init.credentials).toBe("include");
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-token-value");
  });
});
