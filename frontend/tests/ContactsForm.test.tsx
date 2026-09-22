import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ContactsForm } from "@/components/dashboard/ContactsForm";
import type { Contact } from "@/lib/api";

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

const apiPut = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPut: (path: string, body: unknown) => apiPut(path, body),
}));

const PHONE: Contact = { platform: "phone", value: "+37410123456", href: "tel:+37410123456" };
const TELEGRAM: Contact = {
  platform: "telegram",
  value: "mystore",
  href: "https://t.me/mystore",
};

beforeEach(() => {
  refresh.mockClear();
  apiPut.mockReset().mockResolvedValue({ ok: true, data: { items: [] } });
});

function sent(): { items: { platform: string; value: string }[] } {
  return apiPut.mock.calls[0]?.[1] as { items: { platform: string; value: string }[] };
}

describe("contacts form", () => {
  it("sends only the fields the seller filled in", async () => {
    const user = userEvent.setup();
    render(<ContactsForm contacts={[]} />);

    await user.type(screen.getByLabelText("Телефон"), "+374 10 123456");
    await user.click(screen.getByRole("button", { name: "Сохранить контакты" }));

    await waitFor(() => expect(apiPut).toHaveBeenCalled());
    expect(sent().items).toEqual([{ platform: "phone", value: "+374 10 123456" }]);
  });

  it("shows what the shop already has", () => {
    render(<ContactsForm contacts={[PHONE, TELEGRAM]} />);

    expect(screen.getByLabelText("Телефон")).toHaveValue("+37410123456");
    expect(screen.getByLabelText("Telegram")).toHaveValue("mystore");
    expect(screen.getByLabelText("WhatsApp")).toHaveValue("");
  });

  it("drops a contact the seller cleared", async () => {
    // the whole set is replaced, so an emptied field is a contact that is gone
    const user = userEvent.setup();
    render(<ContactsForm contacts={[PHONE, TELEGRAM]} />);

    await user.clear(screen.getByLabelText("Telegram"));
    await user.click(screen.getByRole("button", { name: "Сохранить контакты" }));

    await waitFor(() => expect(apiPut).toHaveBeenCalled());
    expect(sent().items).toEqual([{ platform: "phone", value: "+37410123456" }]);
  });

  it("lets the seller clear every contact", async () => {
    const user = userEvent.setup();
    render(<ContactsForm contacts={[PHONE]} />);

    await user.clear(screen.getByLabelText("Телефон"));
    await user.click(screen.getByRole("button", { name: "Сохранить контакты" }));

    await waitFor(() => expect(apiPut).toHaveBeenCalled());
    expect(sent().items).toEqual([]);
  });

  it("shows what the backend refused and does not claim success", async () => {
    apiPut.mockResolvedValue({
      ok: false,
      error: { message: "Телефон: номер нужен в международном формате", fieldErrors: {} },
    });
    const user = userEvent.setup();
    render(<ContactsForm contacts={[]} />);

    await user.type(screen.getByLabelText("Телефон"), "10123456");
    await user.click(screen.getByRole("button", { name: "Сохранить контакты" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("международном формате");
    expect(screen.queryByText("Сохранено.")).not.toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });
});
