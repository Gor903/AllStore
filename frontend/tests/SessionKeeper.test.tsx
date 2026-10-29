import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionKeeper } from "@/components/auth/SessionKeeper";

const apiPost = vi.fn();
vi.mock("@/lib/browser-api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/browser-api")>("@/lib/browser-api");
  return { ...actual, apiPost: (path: string, body: unknown) => apiPost(path, body) };
});

const deviceKey = vi.fn();
vi.mock("@/lib/device-key", () => ({
  deviceKey: () => deviceKey(),
  deviceProof: async () => "proof",
}));

vi.mock("next/navigation", () => ({ usePathname: () => "/dashboard" }));

beforeEach(() => {
  apiPost.mockReset().mockResolvedValue({ ok: true, data: undefined });
  deviceKey.mockReset().mockResolvedValue({ publicKey: "a-public-key", sign: async () => "sig" });
});

afterEach(() => {
  document.cookie = "allstore_csrf=; max-age=0";
});

describe("SessionKeeper", () => {
  it("does nothing at all for a visitor who is not signed in", async () => {
    render(<SessionKeeper />);

    await waitFor(() => {
      expect(deviceKey).not.toHaveBeenCalled();
    });
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("registers the key once somebody is signed in", async () => {
    document.cookie = "allstore_csrf=csrf-token-value";

    render(<SessionKeeper />);

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith("/auth/sessions/device-key", {
        public_key: "a-public-key",
      });
    });
  });

  it("stays quiet when the browser cannot hold a key", async () => {
    // a private window, an old browser: an unbound session is a supported outcome
    document.cookie = "allstore_csrf=csrf-token-value";
    deviceKey.mockResolvedValue(null);

    render(<SessionKeeper />);

    await waitFor(() => {
      expect(deviceKey).toHaveBeenCalled();
    });
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("renders nothing", () => {
    document.cookie = "allstore_csrf=csrf-token-value";

    const { container } = render(<SessionKeeper />);

    expect(container).toBeEmptyDOMElement();
  });
});
