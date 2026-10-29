"use client";

/**
 * A key this browser holds and cannot hand over.
 *
 * Generated with `extractable: false`, so there is no call that returns the private half —
 * not to us, not to a script that gets injected into the page. What a script *can* do is ask
 * the browser to sign with it, which is why this is not a defence against cross-site
 * scripting; that is what the content security policy is for. It is a defence against a
 * cookie that has been copied somewhere else, which is the commoner way sessions are lost.
 *
 * Stored in IndexedDB because it is the only store that keeps a `CryptoKey` as a key rather
 * than as text. Putting it in `localStorage` would mean exporting it, which would mean it
 * could be exported.
 */

const DATABASE = "allstore-device";
const STORE = "keys";
const RECORD = "session-key";

export type DeviceKey = { publicKey: string; sign: (payload: string) => Promise<string> };

function base64url(bytes: ArrayBuffer): string {
  const binary = String.fromCharCode(...new Uint8Array(bytes));
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function transact<T>(
  db: IDBDatabase,
  mode: IDBTransactionMode,
  run: (s: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const request = run(db.transaction(STORE, mode).objectStore(STORE));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function stored(db: IDBDatabase): Promise<CryptoKeyPair | null> {
  const pair = await transact<CryptoKeyPair | undefined>(db, "readonly", (store) =>
    store.get(RECORD),
  );
  return pair ?? null;
}

async function generate(db: IDBDatabase): Promise<CryptoKeyPair> {
  const pair = await crypto.subtle.generateKey(
    { name: "ECDSA", namedCurve: "P-256" },
    // the whole point: there is no call that gets the private half back out
    false,
    ["sign", "verify"],
  );
  await transact(db, "readwrite", (store) => store.put(pair, RECORD));
  return pair;
}

/**
 * The key for this browser, made on first use and kept afterwards.
 *
 * Returns null wherever the pieces are missing — an old browser, a private window with
 * IndexedDB disabled, a context without `crypto.subtle`. That is a supported outcome, not a
 * failure: the session simply stays unbound, and the platform gives it a shorter life
 * instead. Binding is worth having and is not worth locking anybody out over.
 */
export async function deviceKey(): Promise<DeviceKey | null> {
  if (typeof indexedDB === "undefined" || typeof crypto?.subtle === "undefined") {
    return null;
  }
  try {
    const db = await openDatabase();
    const pair = (await stored(db)) ?? (await generate(db));
    const spki = await crypto.subtle.exportKey("spki", pair.publicKey);
    return {
      publicKey: base64url(spki),
      sign: async (payload: string) => {
        const signature = await crypto.subtle.sign(
          { name: "ECDSA", hash: "SHA-256" },
          pair.privateKey,
          new TextEncoder().encode(payload),
        );
        return base64url(signature);
      },
    };
  } catch {
    return null;
  }
}

/**
 * A short statement that this request came from the browser holding the key.
 *
 * Covers the method and the full address as well as the moment, so a signature captured from
 * one call cannot be presented on another. The server keeps the newest one it has accepted
 * and refuses anything not newer, which is what stops the captured one being worth keeping.
 */
export async function deviceProof(key: DeviceKey, method: string, url: string): Promise<string> {
  const claims = { htm: method, htu: url, iat: Math.floor(Date.now() / 1000) };
  const payload = base64url(new TextEncoder().encode(JSON.stringify(claims)).buffer as ArrayBuffer);
  return `${payload}.${await key.sign(payload)}`;
}
