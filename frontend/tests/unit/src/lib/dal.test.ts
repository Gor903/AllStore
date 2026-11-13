import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Every read a signed-in screen makes, and the two gates in front of them.
 *
 * The gates are what is worth asserting. `redirect` is how a person is told what is in their
 * way, and the order of the two is the server's order — a password owed is dealt with before a
 * second factor owed, or the owner lands on a screen they are refused. The one page that
 * attaches an authenticator has to be exempt from the second gate, or it redirects to itself.
 *
 * `backendGet` asks nothing at all without cookies: an anonymous request to a route that needs
 * a session is a 401 nobody learns anything from.
 */

const jar = vi.hoisted(() => ({ value: "" }));

class Redirected extends Error {
  constructor(readonly to: string) {
    super(`redirect to ${to}`);
  }
}

vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({ toString: () => jar.value }),
}));

vi.mock("next/navigation", () => ({
  // the real one throws too: nothing after a redirect is meant to run
  redirect: (to: string) => {
    throw new Redirected(to);
  },
}));

vi.mock("react", async (original) => ({
  ...(await original<typeof import("react")>()),
  // per-request memoisation has no meaning outside a request
  cache: <T>(fn: T): T => fn,
}));

type Call = { url: string; init: RequestInit };

function answering(...responses: unknown[]): Call[] {
  const calls: Call[] = [];
  let next = 0;
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return Promise.resolve(responses[Math.min(next++, responses.length - 1)]);
  });
  return calls;
}

function json(status: number, payload: unknown): unknown {
  return { ok: status < 400, status, json: () => Promise.resolve(payload) };
}

function account(overrides: Record<string, unknown> = {}): unknown {
  return {
    id: "1",
    email: "person@example.am",
    role: "buyer",
    must_change_password: false,
    ...overrides,
  };
}

beforeEach(() => {
  jar.value = "allstore_session=a-token";
});

describe("asking the backend on behalf of a signed-in person", () => {
  it("asks nothing when there are no cookies to ask with", async () => {
    jar.value = "";
    const calls = answering(json(200, account()));
    const { getCurrentUser } = await import("@/lib/dal");

    expect(await getCurrentUser()).toBeNull();
    expect(calls).toEqual([]);
  });

  it("sends the cookies and reads no cache", async () => {
    const calls = answering(json(200, account()));
    const { getCurrentUser } = await import("@/lib/dal");

    await getCurrentUser();

    expect((calls[0]!.init.headers as Record<string, string>)["cookie"]).toBe(
      "allstore_session=a-token",
    );
    expect(calls[0]!.init.cache).toBe("no-store");
  });

  it("is null when the backend refuses, so a screen renders its empty state", async () => {
    answering(json(403, {}));
    const { getMyStore } = await import("@/lib/dal");

    expect(await getMyStore()).toBeNull();
  });
});

describe("the gate in front of a signed-in screen", () => {
  it("sends somebody who is not signed in to the sign-in screen", async () => {
    jar.value = "";
    answering(json(200, account()));
    const { requireUser } = await import("@/lib/dal");

    await expect(requireUser()).rejects.toMatchObject({ to: "/login" });
  });

  it("sends an account owing a password change to the form that takes one", async () => {
    answering(json(200, account({ must_change_password: true })));
    const { requireUser } = await import("@/lib/dal");

    await expect(requireUser()).rejects.toMatchObject({ to: "/password" });
  });

  it("deals with the password before the second factor, as the server does", async () => {
    answering(
      json(200, account({ role: "moderator", must_change_password: true })),
      json(200, { enabled: false, required: true, recovery_codes_left: 0 }),
    );
    const { requireUser } = await import("@/lib/dal");

    await expect(requireUser()).rejects.toMatchObject({ to: "/password" });
  });

  it("sends staff with no authenticator to the screen that attaches one", async () => {
    answering(
      json(200, account({ role: "moderator" })),
      json(200, { enabled: false, required: true, recovery_codes_left: 0 }),
    );
    const { requireUser } = await import("@/lib/dal");

    await expect(requireUser()).rejects.toMatchObject({ to: "/devices" });
  });

  it("lets that very screen through, or it would redirect to itself", async () => {
    answering(
      json(200, account({ role: "moderator" })),
      json(200, { enabled: false, required: true, recovery_codes_left: 0 }),
    );
    const { requireUser } = await import("@/lib/dal");

    await expect(requireUser({ owingASecondFactor: true })).resolves.toMatchObject({
      role: "moderator",
    });
  });

  it("does not hold a buyer to a second factor nobody asks them for", async () => {
    const calls = answering(json(200, account({ role: "buyer" })));
    const { requireUser } = await import("@/lib/dal");

    await requireUser();

    expect(calls).toHaveLength(1);
  });

  it("lets staff through once the authenticator is attached", async () => {
    answering(
      json(200, account({ role: "admin" })),
      json(200, { enabled: true, required: true, recovery_codes_left: 8 }),
    );
    const { requireUser } = await import("@/lib/dal");

    await expect(requireUser()).resolves.toMatchObject({ role: "admin" });
  });
});

describe("the gate in front of somebody else's screens", () => {
  it("sends a moderator who wandered into the admin panel back to their queue", async () => {
    answering(
      json(200, account({ role: "moderator" })),
      json(200, { enabled: true, required: true, recovery_codes_left: 8 }),
    );
    const { requireRole } = await import("@/lib/dal");

    await expect(requireRole("admin")).rejects.toMatchObject({ to: "/moderation" });
  });

  it("lets through the role the screen is for", async () => {
    answering(
      json(200, account({ role: "admin" })),
      json(200, { enabled: true, required: true, recovery_codes_left: 8 }),
    );
    const { requireRole } = await import("@/lib/dal");

    await expect(requireRole("admin")).resolves.toMatchObject({ role: "admin" });
  });
});

describe("the queues are paged", () => {
  it("asks for one page rather than a hundred rows", async () => {
    const calls = answering(json(200, { items: [], total: 0 }));
    const { getModerationProducts, ADMIN_PAGE_SIZE } = await import("@/lib/dal");

    await getModerationProducts();

    expect(calls[0]!.url).toContain(`limit=${ADMIN_PAGE_SIZE}`);
    expect(calls[0]!.url).toContain("offset=0");
  });

  it("asks for the page it was sent to", async () => {
    const calls = answering(json(200, { items: [], total: 0 }));
    const { getModerationBusinesses } = await import("@/lib/dal");

    await getModerationBusinesses(40);

    expect(calls[0]!.url).toContain("offset=40");
  });

  it("leaves out an empty search term rather than sending one", async () => {
    const calls = answering(json(200, { items: [], total: 0 }));
    const { getReachableAccounts } = await import("@/lib/dal");

    await getReachableAccounts("", 0);

    expect(calls[0]!.url).not.toContain("q=");
  });

  it("carries the search term when there is one", async () => {
    const calls = answering(json(200, { items: [], total: 0 }));
    const { getModerators } = await import("@/lib/dal");

    await getModerators("анна", 0);

    expect(calls[0]!.url).toContain("q=%D0%B0%D0%BD%D0%BD%D0%B0");
  });

  it("leaves out a filter nobody filled in", async () => {
    const calls = answering(json(200, { items: [], total: 0 }));
    const { getAuditLogs } = await import("@/lib/dal");

    await getAuditLogs(0, { actorId: "", action: "role_granted" });

    expect(calls[0]!.url).not.toContain("actor_id");
    expect(calls[0]!.url).toContain("action=role_granted");
  });

  it("carries the account an incident feed was narrowed to", async () => {
    const calls = answering(json(200, { items: [], total: 0 }));
    const { getIncidents } = await import("@/lib/dal");

    await getIncidents(0, { userId: "7" });

    expect(calls[0]!.url).toContain("user_id=7");
  });
});

describe("an empty query is not a search", () => {
  it("answers an empty page without asking, because the backend refuses it", async () => {
    const calls = answering(json(200, { items: [], total: 0 }));
    const { searchModerationCatalog, ADMIN_PAGE_SIZE } = await import("@/lib/dal");

    const result = await searchModerationCatalog("", 20);

    expect(result).toEqual({ items: [], total: 0, limit: ADMIN_PAGE_SIZE, offset: 20 });
    expect(calls).toEqual([]);
  });

  it("asks when there is something to search for", async () => {
    const calls = answering(json(200, { items: [], total: 0 }));
    const { searchModerationCatalog } = await import("@/lib/dal");

    await searchModerationCatalog("ваза", 0);

    expect(calls[0]!.url).toContain("q=%D0%B2%D0%B0%D0%B7%D0%B0");
  });
});

describe("an identifier that came from the address bar", () => {
  it("is escaped before it reaches the path", async () => {
    const calls = answering(json(200, account()));
    const { getAdminUser } = await import("@/lib/dal");

    await getAdminUser("../moderators");

    expect(calls[0]!.url).toContain("/admin/users/..%2Fmoderators");
  });
});
