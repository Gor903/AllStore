import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StoreImageField } from "@/components/dashboard/StoreImageField";

/**
 * One picture per slot: uploading a second replaces the first, so there is no gallery here.
 *
 * The detail worth a test is the input being cleared after every attempt. A file input does not
 * fire `change` when the same file is picked again, so a failed upload followed by a second try
 * with the same file would do nothing at all — the seller presses, nothing happens, and there is
 * nothing on screen to explain why.
 */

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

const apiUploadPut = vi.fn();
const apiDelete = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiUploadPut: (path: string, form: FormData) => apiUploadPut(path, form),
  apiDelete: (path: string) => apiDelete(path),
}));

function picture(): File {
  return new File(["bytes"], "logo.png", { type: "image/png" });
}

function show(currentUrl: string | null) {
  render(
    <StoreImageField
      kind="logo"
      label="Логотип"
      hint="Квадратная картинка, её видно в карточке магазина."
      currentUrl={currentUrl}
    />,
  );
}

beforeEach(() => {
  refresh.mockClear();
  apiUploadPut.mockReset().mockResolvedValue({ ok: true, data: {} });
  apiDelete.mockReset().mockResolvedValue({ ok: true, data: {} });
});

describe("StoreImageField", () => {
  it("says what the picture is for while there is none", () => {
    show(null);

    expect(screen.getByText(/квадратная картинка/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Удалить" })).not.toBeInTheDocument();
  });

  it("shows the picture there is, and offers to remove it", () => {
    show("https://cdn.allstore.am/logo.png");

    expect(screen.getByRole("presentation")).toHaveAttribute("alt", "");
    expect(screen.getByRole("button", { name: "Удалить" })).toBeInTheDocument();
  });

  it("uploads what was picked to the slot it belongs to", async () => {
    show(null);

    await userEvent.upload(screen.getByLabelText("Логотип"), picture());

    await waitFor(() =>
      expect(apiUploadPut).toHaveBeenCalledWith("/stores/me/images/logo", expect.any(FormData)),
    );
    expect(apiUploadPut.mock.calls[0]?.[1].get("file")).toBeInstanceOf(File);
  });

  it("reloads the page, which now shows the new picture", async () => {
    show(null);

    await userEvent.upload(screen.getByLabelText("Логотип"), picture());

    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("lets the same file be picked again after a failure", async () => {
    apiUploadPut.mockResolvedValue({
      ok: false,
      error: { code: "payload_too_large", message: "Файл слишком большой", fieldErrors: {} },
    });
    show(null);
    const input = screen.getByLabelText("Логотип") as HTMLInputElement;

    await userEvent.upload(input, picture());

    expect(await screen.findByRole("alert")).toHaveTextContent("Файл слишком большой");
    expect(input.value).toBe("");
  });

  it("removes the picture that is there", async () => {
    show("https://cdn.allstore.am/logo.png");

    await userEvent.click(screen.getByRole("button", { name: "Удалить" }));

    await waitFor(() => expect(apiDelete).toHaveBeenCalledWith("/stores/me/images/logo"));
    expect(refresh).toHaveBeenCalled();
  });

  it("says why a removal did not happen", async () => {
    apiDelete.mockResolvedValue({
      ok: false,
      error: { code: "offline", message: "Сервер недоступен", fieldErrors: {} },
    });
    show("https://cdn.allstore.am/logo.png");

    await userEvent.click(screen.getByRole("button", { name: "Удалить" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Сервер недоступен");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("accepts the kinds of picture the backend accepts, and says so", () => {
    /* The browser's own filter, so that a .pdf is never uploaded only to be refused. */
    show(null);

    expect(screen.getByLabelText("Логотип")).toHaveAttribute(
      "accept",
      "image/jpeg,image/png,image/gif,image/webp",
    );
    expect(screen.getByText(/до 5 МБ/)).toBeInTheDocument();
  });

  it("names the box differently once there is a picture to replace", () => {
    show("https://cdn.allstore.am/logo.png");

    expect(screen.getByLabelText("Заменить: Логотип")).toBeInTheDocument();
  });

  it("takes nothing while it is working", async () => {
    apiUploadPut.mockReturnValue(new Promise(() => {}));
    show("https://cdn.allstore.am/logo.png");

    await userEvent.upload(screen.getByLabelText("Заменить: Логотип"), picture());

    expect(screen.getByLabelText("Заменить: Логотип")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Удалить" })).toBeDisabled();
  });
});
