import { describe, expect, it, vi } from "vitest";

import { deviceKey, deviceProof, type DeviceKey } from "@/lib/device-key";

/**
 * The key this browser holds and cannot hand over, and the short statement it signs.
 *
 * Two things are worth asserting without a real IndexedDB. First, that a browser missing the
 * pieces gets null rather than an exception: an old browser or a private window with IndexedDB
 * switched off must still be able to sign in, with a shorter session instead of a bound one.
 * Binding is worth having and is not worth locking anybody out over.
 *
 * Second, what the proof covers. It names the method and the full address as well as the
 * moment, so a signature captured from one call cannot be presented on another — the server
 * keeps the newest it has accepted and refuses anything not newer.
 */

function decode(proof: string): Record<string, unknown> {
  const payload = proof.split(".")[0]!;
  const padded = payload.replaceAll("-", "+").replaceAll("_", "/");
  return JSON.parse(atob(padded)) as Record<string, unknown>;
}

const stub: DeviceKey = {
  publicKey: "a-public-key",
  sign: (payload: string) => Promise.resolve(`signed(${payload})`),
};

describe("deviceKey", () => {
  it("is null where the browser has no store to keep it in", async () => {
    // jsdom has no IndexedDB, which is the same shape as a private window with it switched off
    expect(await deviceKey()).toBeNull();
  });

  it("is null where there is no web crypto", async () => {
    vi.stubGlobal("indexedDB", {});
    vi.stubGlobal("crypto", {});

    expect(await deviceKey()).toBeNull();
  });

  it("is null rather than an exception when the store refuses to open", async () => {
    vi.stubGlobal("indexedDB", {
      open: () => {
        throw new Error("the store is not available");
      },
    });
    vi.stubGlobal("crypto", { subtle: {} });

    expect(await deviceKey()).toBeNull();
  });
});

describe("deviceProof", () => {
  it("names the method and the full address, so it cannot be replayed on another call", async () => {
    const claims = decode(
      await deviceProof(stub, "POST", "https://api.allstore.am/api/v1/auth/login"),
    );

    expect(claims["htm"]).toBe("POST");
    expect(claims["htu"]).toBe("https://api.allstore.am/api/v1/auth/login");
  });

  it("names the moment, which is what the server refuses to accept twice", async () => {
    const before = Math.floor(Date.now() / 1000);

    const claims = decode(await deviceProof(stub, "POST", "https://api.allstore.am/"));

    expect(claims["iat"]).toBeGreaterThanOrEqual(before);
    expect(claims["iat"]).toBeLessThanOrEqual(Math.floor(Date.now() / 1000));
  });

  it("is the signed payload and the signature over exactly that payload", async () => {
    const proof = await deviceProof(stub, "GET", "https://api.allstore.am/");
    const [payload, signature] = proof.split(".");

    expect(signature).toBe(`signed(${payload})`);
  });

  it("carries nothing that identifies the person", async () => {
    const claims = decode(await deviceProof(stub, "POST", "https://api.allstore.am/"));

    expect(Object.keys(claims).sort()).toEqual(["htm", "htu", "iat"]);
  });
});
