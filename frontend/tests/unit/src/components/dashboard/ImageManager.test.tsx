import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ImageManager } from "@/components/dashboard/ImageManager";
import type { ProductImage } from "@/lib/api";

/**
 * The photographs of one product: a gallery with a ceiling.
 *
 * The ceiling is the backend's, and the box goes dead at it rather than letting somebody pick a
 * file and be refused afterwards. The input is cleared after every attempt for the same reason
 * it is in StoreImageField: a file input does not fire `change` for the same file twice, so a
 * failed upload followed by a second try with the same file would do nothing visible at all.
 */

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

const apiUpload = vi.fn();
const apiDelete = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiUpload: (path: string, form: FormData) => apiUpload(path, form),
  apiDelete: (path: string) => apiDelete(path),
}));

const PRODUCT = "11111111-1111-1111-1111-111111111111";

function image(id: string, altText: string | null = null): ProductImage {
  return { id, image_url: `https://cdn.allstore.am/${id}.png`, sort_order: 0, alt_text: altText };
}

function picture(name = "cup.png"): File {
  return new File(["bytes"], name, { type: "image/png" });
}

beforeEach(() => {
  refresh.mockClear();
  apiUpload.mockReset().mockResolvedValue({ ok: true, data: {} });
  apiDelete.mockReset().mockResolvedValue({ ok: true, data: {} });
});

describe("ImageManager", () => {
  it("says a product without a photograph looks like nothing at all", () => {
    render(<ImageManager productId={PRODUCT} images={[]} max={5} />);

    expect(screen.getByText(/выглядит пустым местом/i)).toBeInTheDocument();
  });

  it("says how many there are of how many allowed", () => {
    render(<ImageManager productId={PRODUCT} images={[image("a"), image("b")]} max={5} />);

    expect(screen.getByText("2 из 5")).toBeInTheDocument();
  });

  it("uploads what was picked, with the file name as the alt text", async () => {
    render(<ImageManager productId={PRODUCT} images={[]} max={5} />);

    await userEvent.upload(screen.getByLabelText("Добавить фото"), picture("чашка.png"));

    await waitFor(() => expect(apiUpload).toHaveBeenCalled());
    const [path, form] = apiUpload.mock.calls[0] as [string, FormData];
    expect(path).toBe(`/products/${PRODUCT}/images`);
    expect(form.get("alt_text")).toBe("чашка.png");
    expect(refresh).toHaveBeenCalled();
  });

  it("goes dead at the ceiling rather than letting a file be refused afterwards", () => {
    render(<ImageManager productId={PRODUCT} images={[image("a"), image("b")]} max={2} />);

    expect(screen.getByLabelText("Добавить фото")).toBeDisabled();
  });

  it("lets the same file be picked again after a failure", async () => {
    apiUpload.mockResolvedValue({
      ok: false,
      error: { code: "payload_too_large", message: "Файл слишком большой", fieldErrors: {} },
    });
    render(<ImageManager productId={PRODUCT} images={[]} max={5} />);
    const input = screen.getByLabelText("Добавить фото") as HTMLInputElement;

    await userEvent.upload(input, picture());

    expect(await screen.findByRole("alert")).toHaveTextContent("Файл слишком большой");
    expect(input.value).toBe("");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("removes the photograph that was pointed at", async () => {
    render(<ImageManager productId={PRODUCT} images={[image("a"), image("b")]} max={5} />);

    await userEvent.click(screen.getAllByRole("button", { name: "Удалить" })[1]!);

    await waitFor(() => expect(apiDelete).toHaveBeenCalledWith(`/products/${PRODUCT}/images/b`));
  });

  it("says why a removal did not happen", async () => {
    apiDelete.mockResolvedValue({
      ok: false,
      error: { code: "offline", message: "Сервер недоступен", fieldErrors: {} },
    });
    render(<ImageManager productId={PRODUCT} images={[image("a")]} max={5} />);

    await userEvent.click(screen.getByRole("button", { name: "Удалить" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Сервер недоступен");
  });

  it("describes a photograph by what it was called, or by nothing", () => {
    /* An alt text invented here would be worse than none: a screen reader reading
       "image 33333333-3333" has learnt nothing it did not know. */
    render(<ImageManager productId={PRODUCT} images={[image("a", "чашка"), image("b")]} max={5} />);

    expect(screen.getByRole("img", { name: "чашка" })).toBeInTheDocument();
    expect(screen.getByRole("presentation")).toHaveAttribute("alt", "");
  });

  it("takes nothing while it is working", async () => {
    apiUpload.mockReturnValue(new Promise(() => {}));
    render(<ImageManager productId={PRODUCT} images={[image("a")]} max={5} />);

    await userEvent.upload(screen.getByLabelText("Добавить фото"), picture());

    expect(screen.getByLabelText("Добавить фото")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Удалить" })).toBeDisabled();
  });

  it("accepts the kinds of picture the backend accepts, and says so", () => {
    render(<ImageManager productId={PRODUCT} images={[]} max={5} />);

    expect(screen.getByLabelText("Добавить фото")).toHaveAttribute(
      "accept",
      "image/jpeg,image/png,image/gif,image/webp",
    );
    expect(screen.getByText(/до 5 МБ/)).toBeInTheDocument();
  });
});
