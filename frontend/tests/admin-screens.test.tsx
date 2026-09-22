import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CategoryRow } from "@/components/admin/CategoryEditor";
import { RoleSelect } from "@/components/admin/RoleSelect";
import type { AdminCategory } from "@/lib/api";

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

const apiPost = vi.fn();
const apiPatch = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPost: (path: string, body: unknown) => apiPost(path, body),
  apiPatch: (path: string, body: unknown) => apiPatch(path, body),
}));

const USER_ID = "11111111-1111-1111-1111-111111111111";

const CATEGORY: AdminCategory = {
  id: "22222222-2222-2222-2222-222222222222",
  name: "Электроника",
  slug: "electronics",
  status: "active",
  children: [],
};

beforeEach(() => {
  refresh.mockClear();
  apiPost.mockReset().mockResolvedValue({ ok: true, data: {} });
  apiPatch.mockReset().mockResolvedValue({ ok: true, data: {} });
});

describe("role select", () => {
  it("appoints a moderator without a trip to the database", async () => {
    const user = userEvent.setup();
    render(<RoleSelect userId={USER_ID} role="buyer" />);

    await user.selectOptions(screen.getByLabelText("Роль"), "moderator");

    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(apiPost).toHaveBeenCalledWith(`/admin/users/${USER_ID}/role`, { role: "moderator" });
    expect(refresh).toHaveBeenCalled();
  });

  it("snaps back and explains when the backend refuses", async () => {
    // the last administrator, or an account that runs a shop
    apiPost.mockResolvedValue({
      ok: false,
      error: { message: "Это последний администратор", fieldErrors: {} },
    });
    const user = userEvent.setup();
    render(<RoleSelect userId={USER_ID} role="admin" />);

    await user.selectOptions(screen.getByLabelText("Роль"), "buyer");

    expect(await screen.findByRole("alert")).toHaveTextContent("Это последний администратор");
    // the role on screen must be the role in the database
    expect(screen.getByLabelText("Роль")).toHaveValue("admin");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("asks for nothing when the role did not change", async () => {
    const user = userEvent.setup();
    render(<RoleSelect userId={USER_ID} role="buyer" />);

    await user.selectOptions(screen.getByLabelText("Роль"), "buyer");

    expect(apiPost).not.toHaveBeenCalled();
  });
});

describe("category row", () => {
  it("renames a category and leaves its address alone", async () => {
    const user = userEvent.setup();
    render(<CategoryRow category={CATEGORY} />);

    const field = screen.getByLabelText("Название категории electronics");
    await user.clear(field);
    await user.type(field, "Электроника и техника");
    await user.click(screen.getByRole("button", { name: "Переименовать" }));

    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    expect(apiPatch).toHaveBeenCalledWith(`/admin/categories/${CATEGORY.id}`, {
      name: "Электроника и техника",
    });
  });

  it("does not offer to rename what has not been retyped", () => {
    render(<CategoryRow category={CATEGORY} />);

    expect(screen.getByRole("button", { name: "Переименовать" })).toBeDisabled();
  });

  it("hides a visible category and brings back a hidden one", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<CategoryRow category={CATEGORY} />);

    await user.click(screen.getByRole("button", { name: "Скрыть" }));
    await waitFor(() =>
      expect(apiPatch).toHaveBeenCalledWith(expect.any(String), {
        status: "hidden",
      }),
    );

    rerender(<CategoryRow category={{ ...CATEGORY, status: "hidden" }} />);
    await user.click(screen.getByRole("button", { name: "Вернуть в каталог" }));

    expect(apiPatch).toHaveBeenLastCalledWith(expect.any(String), { status: "active" });
  });

  it("says a hidden category is hidden", () => {
    render(<CategoryRow category={{ ...CATEGORY, status: "hidden" }} />);

    expect(screen.getByText("скрыта от покупателя")).toBeInTheDocument();
  });

  it("shows what the backend refused", async () => {
    apiPatch.mockResolvedValue({
      ok: false,
      error: { message: "Категория не найдена", fieldErrors: {} },
    });
    const user = userEvent.setup();
    render(<CategoryRow category={CATEGORY} />);

    await user.click(screen.getByRole("button", { name: "Скрыть" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Категория не найдена");
    expect(refresh).not.toHaveBeenCalled();
  });
});
