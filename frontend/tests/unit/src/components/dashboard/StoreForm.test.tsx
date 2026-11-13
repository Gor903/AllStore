import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StoreForm } from "@/components/dashboard/StoreForm";
import { env } from "@/lib/env";

/**
 * Opening a shop: one field, and the one field that cannot be changed afterwards.
 *
 * The form says so in words, because the address is what the seller will print on a card and
 * what their buyers will type. The rules are said out loud too, so a refusal is something the
 * seller could have avoided rather than something they discover by being told no.
 *
 * `noValidate` is deliberate: the browser's own bubble would refuse the form before the backend
 * ever sees it, and the backend's refusals are the ones with the useful wording.
 */

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

const apiPost = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}));

async function open(address: string): Promise<void> {
  await userEvent.type(screen.getByLabelText("Адрес магазина"), address);
  await userEvent.click(screen.getByRole("button", { name: "Создать магазин" }));
}

beforeEach(() => {
  refresh.mockClear();
  apiPost.mockReset().mockResolvedValue({ ok: true, data: { subdomain: "cups" } });
});

describe("StoreForm", () => {
  it("asks for the address and nothing else", () => {
    render(<StoreForm />);

    expect(screen.getByLabelText("Адрес магазина")).toBeInTheDocument();
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
  });

  it("says what the address will become and that it is final", () => {
    render(<StoreForm />);

    expect(screen.getByText(new RegExp(`имя\\.${env.baseDomain}`))).toBeInTheDocument();
    expect(screen.getByText(/изменить адрес потом нельзя/i)).toBeInTheDocument();
  });

  it("sends the address the seller typed", async () => {
    render(<StoreForm />);

    await open("cups");

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith("/stores", { subdomain: "cups" }));
  });

  it("reloads the page, which now has a shop on it", async () => {
    render(<StoreForm />);

    await open("cups");

    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("puts a refusal about the address next to the address", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: {
        code: "conflict",
        message: "Проверьте форму",
        fieldErrors: { subdomain: "Этот адрес уже занят" },
      },
    });
    render(<StoreForm />);

    await open("cups");

    expect(await screen.findByRole("alert")).toHaveTextContent("Этот адрес уже занят");
    expect(screen.getByLabelText("Адрес магазина")).toBeInvalid();
  });

  it("shows a refusal that belongs to no field at all", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: { code: "offline", message: "Сервер недоступен", fieldErrors: {} },
    });
    render(<StoreForm />);

    await open("cups");

    expect(await screen.findByRole("alert")).toHaveTextContent("Сервер недоступен");
  });

  it("does not say it twice when the refusal is about the field", async () => {
    apiPost.mockResolvedValue({
      ok: false,
      error: {
        code: "conflict",
        message: "Проверьте форму",
        fieldErrors: { subdomain: "Этот адрес уже занят" },
      },
    });
    render(<StoreForm />);

    await open("cups");

    await waitFor(() => expect(screen.getAllByRole("alert")).toHaveLength(1));
    expect(screen.queryByText("Проверьте форму")).not.toBeInTheDocument();
  });

  it("cannot be submitted twice while the first one is in flight", async () => {
    apiPost.mockReturnValue(new Promise(() => {}));
    render(<StoreForm />);

    await open("cups");

    expect(screen.getByRole("button", { name: "Создаём…" })).toBeDisabled();
  });

  it("leaves the refusing to the backend rather than to the browser's own bubble", async () => {
    const { container } = render(<StoreForm />);

    expect(container.querySelector("form")).toHaveAttribute("novalidate");
  });
});
