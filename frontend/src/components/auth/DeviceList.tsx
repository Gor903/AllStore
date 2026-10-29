"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Device } from "@/lib/api";
import { apiDelete } from "@/lib/browser-api";

/**
 * The screen exists for one question — "is somebody else in my account?" — so the answer has
 * to be actionable without knowing which line is the intruder. Hence the single button that
 * ends everything except the device being used to press it.
 */
export function DeviceList({ devices }: { devices: Device[] }) {
  const router = useRouter();
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function revoke(id: string) {
    setPending(id);
    setError(null);
    const result = await apiDelete(`/auth/sessions/${encodeURIComponent(id)}`);
    setPending(null);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    router.refresh();
  }

  async function revokeOthers() {
    setPending("others");
    setError(null);
    const result = await apiDelete("/auth/sessions");
    setPending(null);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-3">
        {devices.map((device) => (
          <li
            key={device.id}
            className="flex flex-wrap items-center gap-3 rounded-card border border-ink-muted/20 p-4"
          >
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <p className="truncate text-sm">
                {/* the browser's own description of itself: ugly, and the only thing a person
                    has to recognise their own laptop by */}
                {device.user_agent ?? "Устройство не представилось"}
                {device.current ? (
                  <span className="ml-2 rounded-full bg-brand/10 px-2 py-0.5 text-xs text-brand">
                    это устройство
                  </span>
                ) : null}
              </p>
              <p className="text-xs text-ink-muted">
                Последний раз: {new Date(device.last_seen_at).toLocaleString("ru-RU")}
                {device.ip === null ? "" : ` · ${device.ip}`}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void revoke(device.id)}
              disabled={pending !== null}
              className="rounded-lg border border-ink-muted/30 px-3 py-1.5 text-sm disabled:opacity-60"
            >
              {pending === device.id ? "Выходим…" : device.current ? "Выйти" : "Выйти здесь"}
            </button>
          </li>
        ))}
      </ul>

      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}

      {devices.length > 1 ? (
        <button
          type="button"
          onClick={() => void revokeOthers()}
          disabled={pending !== null}
          className="self-start rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {pending === "others" ? "Выходим…" : "Выйти на всех остальных устройствах"}
        </button>
      ) : null}
    </div>
  );
}
