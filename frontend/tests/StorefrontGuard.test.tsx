import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StorefrontGuard } from "@/components/StorefrontGuard";

const apiGet = vi.fn();
vi.mock("@/lib/browser-api", () => ({
  apiGet: (path: string) => apiGet(path),
}));

function refused(code: string) {
  return { ok: false, error: { message: "нет", fieldErrors: {}, code } };
}

beforeEach(() => {
  apiGet.mockReset().mockResolvedValue({ ok: true, data: {} });
});

describe("StorefrontGuard", () => {
  it("shows the shop to somebody it was never closed to", async () => {
    render(
      <StorefrontGuard subdomain="cups">
        <p>Витрина</p>
      </StorefrontGuard>,
    );

    await waitFor(() => {
      expect(apiGet).toHaveBeenCalledWith("/storefront/cups");
    });
    expect(screen.getByText("Витрина")).toBeInTheDocument();
  });

  it("withdraws it from the buyer the seller shut out", async () => {
    apiGet.mockResolvedValue(refused("store_access_blocked"));

    render(
      <StorefrontGuard subdomain="cups">
        <p>Витрина</p>
      </StorefrontGuard>,
    );

    expect(await screen.findByText("Магазин ограничил вам доступ")).toBeInTheDocument();
    expect(screen.queryByText("Витрина")).not.toBeInTheDocument();
  });

  it("leaves the shop alone when the answer is some other refusal", async () => {
    apiGet.mockResolvedValue(refused("not_found"));

    render(
      <StorefrontGuard subdomain="cups">
        <p>Витрина</p>
      </StorefrontGuard>,
    );

    await waitFor(() => {
      expect(apiGet).toHaveBeenCalled();
    });
    expect(screen.getByText("Витрина")).toBeInTheDocument();
  });

  it("leaves the shop alone when the network hiccups", async () => {
    // a shop must not disappear because a request failed on the way out
    apiGet.mockResolvedValue(refused("offline"));

    render(
      <StorefrontGuard subdomain="cups">
        <p>Витрина</p>
      </StorefrontGuard>,
    );

    await waitFor(() => {
      expect(apiGet).toHaveBeenCalled();
    });
    expect(screen.getByText("Витрина")).toBeInTheDocument();
  });

  it("asks about the shop it is actually showing", async () => {
    render(
      <StorefrontGuard subdomain="my-shop">
        <p>Витрина</p>
      </StorefrontGuard>,
    );

    await waitFor(() => {
      expect(apiGet).toHaveBeenCalledWith("/storefront/my-shop");
    });
  });
});
