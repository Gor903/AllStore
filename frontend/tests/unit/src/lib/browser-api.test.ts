import { afterEach, describe, expect, it, vi } from "vitest";

import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  apiPostLines,
  apiPut,
  apiUpload,
  readCookie,
} from "@/lib/browser-api";
import { env } from "@/lib/env";

/**
 * Every request the browser makes goes through here, so what it puts on the wire is a contract
 * with the backend rather than an implementation detail: the CSRF token echoed from a cookie
 * into a header, the cookies sent at all, and a refusal arriving as a form error instead of an
 * exception. A missing CSRF header is a 403 on every mutating request — that has happened, and
 * what it took to find was a reverse-built image, not a test.
 */

type Call = { url: string; init: RequestInit };

function answering(response: unknown): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return response instanceof Error ? Promise.reject(response) : Promise.resolve(response);
  });
  return calls;
}

function json(status: number, payload: unknown): unknown {
  return {
    ok: status < 400,
    status,
    json: () => Promise.resolve(payload),
  };
}

function headerOf(init: RequestInit, name: string): string | undefined {
  return (init.headers as Record<string, string> | undefined)?.[name];
}

afterEach(() => {
  document.cookie = `${env.csrfCookie}=; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
});

describe("readCookie", () => {
  it("reads the value the browser kept", () => {
    document.cookie = "allstore_csrf=a-token";

    expect(readCookie("allstore_csrf")).toBe("a-token");
  });

  it("decodes what the browser encoded", () => {
    document.cookie = `greeting=${encodeURIComponent("привет, мир")}`;

    expect(readCookie("greeting")).toBe("привет, мир");
  });

  it("does not answer with a cookie whose name merely ends the same way", () => {
    document.cookie = "not_allstore_csrf=somebody-elses";

    expect(readCookie("allstore_csrf")).toBeNull();
  });

  it("is null when there is no such cookie", () => {
    expect(readCookie("nothing-here")).toBeNull();
  });
});

describe("what goes on the wire", () => {
  it("echoes the readable CSRF cookie back in the header", async () => {
    document.cookie = `${env.csrfCookie}=a-token`;
    const calls = answering(json(200, {}));

    await apiPost("/auth/login", { email: "a@b.am" });

    expect(headerOf(calls[0]!.init, env.csrfHeader)).toBe("a-token");
  });

  it("sends no header when there is no cookie to echo", async () => {
    const calls = answering(json(200, {}));

    await apiPost("/auth/login", {});

    expect(headerOf(calls[0]!.init, env.csrfHeader)).toBeUndefined();
  });

  it("always sends the cookies, because the session lives in one", async () => {
    const calls = answering(json(200, {}));

    await apiGet("/auth/me");

    expect(calls[0]!.init.credentials).toBe("include");
  });

  it("addresses the API rather than whatever host served the page", async () => {
    const calls = answering(json(200, {}));

    await apiGet("/auth/me");

    expect(calls[0]!.url).toBe(`${env.apiUrl}/api/v1/auth/me`);
  });

  it.each([
    ["GET", (): Promise<unknown> => apiGet("/path")],
    ["POST", (): Promise<unknown> => apiPost("/path", {})],
    ["PATCH", (): Promise<unknown> => apiPatch("/path", {})],
    ["PUT", (): Promise<unknown> => apiPut("/path", {})],
    ["DELETE", (): Promise<unknown> => apiDelete("/path")],
  ])("sends %s as %s", async (method, call) => {
    const calls = answering(json(200, {}));

    await call();

    expect(calls[0]!.init.method).toBe(method);
  });

  it("leaves Content-Type to the browser when the body is a form", async () => {
    const calls = answering(json(200, {}));

    await apiUpload("/products/1/images", new FormData());

    expect(headerOf(calls[0]!.init, "Content-Type")).toBeUndefined();
  });

  it("carries a per-request header through, which is where the device proof travels", async () => {
    const calls = answering(json(200, {}));

    await apiPost("/auth/login", {}, { "X-Device-Proof": "a-proof" });

    expect(headerOf(calls[0]!.init, "X-Device-Proof")).toBe("a-proof");
    expect(headerOf(calls[0]!.init, "Content-Type")).toBe("application/json");
  });
});

describe("what comes back", () => {
  it("gives the payload when the answer is good", async () => {
    answering(json(200, { id: 7 }));

    const result = await apiGet<{ id: number }>("/path");

    expect(result).toEqual({ ok: true, data: { id: 7 } });
  });

  it("treats an empty answer as success with nothing in it", async () => {
    answering({ ok: true, status: 204, json: () => Promise.reject(new Error("no body")) });

    const result = await apiDelete("/devices/1");

    expect(result).toEqual({ ok: true, data: undefined });
  });

  it("turns a refusal into a form error rather than an exception", async () => {
    answering(
      json(409, { error: { code: "conflict", message: "Этот email уже занят", details: [] } }),
    );

    const result = await apiPost("/auth/register", {});

    expect(result).toEqual({
      ok: false,
      error: { code: "conflict", message: "Этот email уже занят", fieldErrors: {} },
    });
  });

  it("survives a refusal with no readable body at all", async () => {
    answering({ ok: false, status: 502, json: () => Promise.reject(new Error("not json")) });

    const result = await apiGet("/path");

    expect(result.ok).toBe(false);
  });

  it("says the server is unreachable instead of throwing at the screen", async () => {
    answering(new Error("network down"));

    const result = await apiGet("/path");

    expect(result).toEqual({
      ok: false,
      error: { code: "offline", message: "Сервер недоступен, попробуйте позже", fieldErrors: {} },
    });
  });
});

/**
 * The halves of an assistant's answer become ready at very different times, so they arrive as
 * lines and are yielded as each one lands. A chunk boundary falls wherever the network put it,
 * which is the part worth testing: a line split across two reads must not be read as two.
 */
describe("an answer that arrives in lines", () => {
  function streaming(chunks: string[], status = 200): void {
    const encoder = new TextEncoder();
    let next = 0;
    vi.stubGlobal("fetch", () =>
      Promise.resolve({
        ok: status < 400,
        status,
        json: () => Promise.resolve({ error: { code: "boom", message: "нет", details: [] } }),
        body:
          status < 400
            ? {
                getReader: () => ({
                  read: () =>
                    Promise.resolve(
                      next < chunks.length
                        ? { done: false, value: encoder.encode(chunks[next++]!) }
                        : { done: true, value: undefined },
                    ),
                }),
              }
            : null,
      }),
    );
  }

  async function collect<T>(source: AsyncGenerator<T>): Promise<T[]> {
    const seen: T[] = [];
    for await (const item of source) {
      seen.push(item);
    }
    return seen;
  }

  it("yields each line as it lands", async () => {
    streaming(['{"step":1}\n', '{"step":2}\n']);

    expect(await collect(apiPostLines("/assistant", {}))).toEqual([{ step: 1 }, { step: 2 }]);
  });

  it("keeps a line split across two chunks whole", async () => {
    streaming(['{"st', 'ep":1}\n{"step":2}\n']);

    expect(await collect(apiPostLines("/assistant", {}))).toEqual([{ step: 1 }, { step: 2 }]);
  });

  it("reads a last line that never got its break", async () => {
    streaming(['{"step":1}\n{"step":2}']);

    expect(await collect(apiPostLines("/assistant", {}))).toEqual([{ step: 1 }, { step: 2 }]);
  });

  it("ignores the blank lines between them", async () => {
    streaming(['\n{"step":1}\n\n\n']);

    expect(await collect(apiPostLines("/assistant", {}))).toEqual([{ step: 1 }]);
  });

  it("throws the form error when the answer never started", async () => {
    streaming([], 500);

    await expect(collect(apiPostLines("/assistant", {}))).rejects.toMatchObject({ code: "boom" });
  });
});
