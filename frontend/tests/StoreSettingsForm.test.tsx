import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StoreSettingsForm } from "@/components/dashboard/StoreSettingsForm";
import type { Store } from "@/lib/api";

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

const apiPatch = vi.fn();

vi.mock("@/lib/browser-api", () => ({
  apiPatch: (path: string, body: unknown) => apiPatch(path, body),
}));

const STORE = {
  id: "11111111-1111-1111-1111-111111111111",
  subdomain: "cups",
  description: null,
  logo_url: null,
  banner_url: null,
  primary_color: null,
  secondary_color: null,
  theme_id: "default",
} as Store;

beforeEach(() => {
  refresh.mockClear();
  apiPatch.mockReset().mockResolvedValue({ ok: true, data: STORE });
});

describe("store settings form", () => {
  it("sends an emptied description as null rather than as an empty string", async () => {
    // the two mean different things to the backend: clear it, or store a blank
    const user = userEvent.setup();
    render(<StoreSettingsForm store={{ ...STORE, description: "Было" }} />);

    await user.clear(screen.getByLabelText("Описание магазина"));
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    expect(apiPatch.mock.calls[0]?.[1]).toMatchObject({ description: null });
  });

  it("sends both colours of the pair the seller picked", async () => {
    const user = userEvent.setup();
    render(<StoreSettingsForm store={STORE} />);

    await user.click(screen.getByRole("button", { name: /Глина/u }));
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    expect(apiPatch.mock.calls[0]?.[1]).toMatchObject({
      primary_color: "#a85832",
      secondary_color: "#7d3f22",
    });
  });

  it("returns a shop to the platform look with a pair of nulls", async () => {
    const user = userEvent.setup();
    render(<StoreSettingsForm store={{ ...STORE, primary_color: "#a85832" }} />);

    await user.click(screen.getByRole("button", { name: /Как на площадке/u }));
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    expect(apiPatch.mock.calls[0]?.[1]).toMatchObject({
      primary_color: null,
      secondary_color: null,
    });
  });

  it("marks the pair the shop already wears", () => {
    render(
      <StoreSettingsForm
        store={{ ...STORE, primary_color: "#2f6fed", secondary_color: "#1e4fb8" }}
      />,
    );

    expect(screen.getByRole("button", { name: /Синий/u })).toHaveAttribute("aria-pressed", "true");
  });

  it("keeps a colour set outside the palette visible and selected", async () => {
    // otherwise the seller sees no swatch marked and cannot tell what the shop wears
    const user = userEvent.setup();
    render(
      <StoreSettingsForm
        store={{ ...STORE, primary_color: "#c4805c", secondary_color: "#eed6ba" }}
      />,
    );

    expect(screen.getByRole("button", { name: /Свой цвет/u })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // and it stays on offer after a detour through the palette
    await user.click(screen.getByRole("button", { name: /Глина/u }));

    expect(screen.getByRole("button", { name: /Свой цвет/u })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("shows what the backend refused and does not claim success", async () => {
    apiPatch.mockResolvedValue({
      ok: false,
      error: { message: "Неизвестная тема", fieldErrors: {} },
    });
    const user = userEvent.setup();
    render(<StoreSettingsForm store={STORE} />);

    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Неизвестная тема");
    expect(screen.queryByText("Сохранено.")).not.toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });
});
