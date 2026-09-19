import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RegisterForm } from "@/components/auth/RegisterForm";

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

function mockResponse(status: number): Response {
  return { ok: status < 400, status, json: async () => ({}) } as Response;
}

beforeEach(() => {
  push.mockClear();
  refresh.mockClear();
});

describe("RegisterForm", () => {
  it("asks a buyer only for account fields", () => {
    render(<RegisterForm />);

    expect(screen.queryByLabelText("Юридическое название")).toBeNull();
  });

  it("asks a seller for the legal name, because it is required to register", async () => {
    const user = userEvent.setup();
    render(<RegisterForm />);

    await user.click(screen.getByRole("button", { name: "Продавец" }));

    expect(screen.getByLabelText("Юридическое название")).toBeInTheDocument();
    expect(screen.getByLabelText("Название магазина")).toBeInTheDocument();
  });

  it("posts to the seller endpoint with the business fields", async () => {
    const fetchMock = vi.fn<(url: string, init: RequestInit) => Promise<Response>>(async () =>
      mockResponse(201),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<RegisterForm />);

    await user.click(screen.getByRole("button", { name: "Продавец" }));
    await user.type(screen.getByLabelText("Email"), "seller@example.com");
    await user.type(screen.getByLabelText("Пароль"), "seller-password-1");
    await user.type(screen.getByLabelText("Юридическое название"), "ИП Тест");
    await user.type(screen.getByLabelText("Название магазина"), "Тест");
    await user.click(screen.getByRole("button", { name: "Зарегистрироваться" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    const call = fetchMock.mock.calls.at(0);
    if (!call) {
      throw new Error("fetch was never called");
    }
    const [url, init] = call;
    expect(url).toContain("/auth/register/seller");
    expect(JSON.parse(String(init.body))).toMatchObject({
      email: "seller@example.com",
      legal_name: "ИП Тест",
      display_name: "Тест",
    });
  });

  it("omits an empty phone instead of sending a blank string", async () => {
    const fetchMock = vi.fn<(url: string, init: RequestInit) => Promise<Response>>(async () =>
      mockResponse(201),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<RegisterForm />);

    await user.type(screen.getByLabelText("Email"), "buyer@example.com");
    await user.type(screen.getByLabelText("Пароль"), "buyer-password-1");
    await user.click(screen.getByRole("button", { name: "Зарегистрироваться" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    const call = fetchMock.mock.calls.at(0);
    if (!call) {
      throw new Error("fetch was never called");
    }
    const [, init] = call;
    expect(JSON.parse(String(init.body))).not.toHaveProperty("phone");
  });
});
