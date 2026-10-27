"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import type { CustomerBlock } from "@/lib/api";
import { apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";

type BlockedBuyersProps = {
  items: CustomerBlock[];
};

const BLOCKED_BUYERS = "/stores/me/blocked-buyers";

/**
 * The shop's own door. A seller may decide who they will not serve here, and that is as far
 * as it goes: the buyer keeps their account, keeps browsing every other shop, and keeps the
 * ability to complain about this one. Barring somebody from the platform is a moderator's
 * decision and has no button on this screen.
 */
export function BlockedBuyers({ items }: BlockedBuyersProps) {
  const router = useRouter();
  const [error, setError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    const result = await apiPost(BLOCKED_BUYERS, {
      email: data.get("email"),
      reason: data.get("reason"),
    });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    form.reset();
    router.refresh();
  }

  async function onRevoke(blockId: string) {
    setPending(true);
    setError(null);
    const result = await apiPost(`${BLOCKED_BUYERS}/${blockId}/revoke`, {});
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    router.refresh();
  }

  const inForce = items.filter((item) => item.in_force);
  const lifted = items.filter((item) => !item.in_force);

  return (
    <section className="flex flex-col gap-4 rounded-card border border-ink-muted/20 p-4">
      <div className="flex flex-col gap-1">
        <h2 className="font-medium">Закрыть магазин покупателю</h2>
        <p className="text-sm text-ink-muted">
          Ограничение действует только в вашем магазине. Аккаунт покупателя остаётся обычным: он
          пользуется площадкой дальше и может пожаловаться на вас модератору. Снять ограничение
          можно в любой момент, запись о нём останется.
        </p>
      </div>

      <form onSubmit={onSubmit} className="flex flex-col gap-3" noValidate>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Email покупателя</span>
          <input
            name="email"
            type="email"
            required
            autoComplete="off"
            className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2 outline-none focus:border-brand"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Причина</span>
          <textarea
            name="reason"
            required
            rows={2}
            maxLength={1000}
            className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2 outline-none focus:border-brand"
          />
        </label>
        <button
          type="submit"
          disabled={pending}
          className="self-start rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-60"
        >
          {pending ? "Сохраняем…" : "Закрыть доступ"}
        </button>
      </form>

      {error === null ? null : (
        <p role="alert" className="text-sm text-danger">
          {error.message}
        </p>
      )}

      {inForce.length === 0 ? (
        <p className="text-sm text-ink-muted">Сейчас магазин никому не закрыт.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-ink-muted/15 rounded-lg border border-ink-muted/20">
          {inForce.map((item) => (
            <li key={item.id} className="flex flex-wrap items-start gap-3 p-3 text-sm">
              <div className="min-w-48 flex-1">
                <p className="font-medium">{item.buyer_email}</p>
                <p className="text-ink-muted">{item.reason}</p>
                <p className="text-xs text-ink-muted">
                  {new Date(item.created_at).toLocaleString("ru-RU")}
                </p>
              </div>
              <button
                type="button"
                onClick={() => void onRevoke(item.id)}
                disabled={pending}
                className="rounded-lg border border-ink-muted/30 px-3 py-1.5 font-medium disabled:opacity-60"
              >
                Открыть доступ
              </button>
            </li>
          ))}
        </ul>
      )}

      {lifted.length === 0 ? null : (
        <details className="text-sm">
          <summary className="cursor-pointer text-ink-muted">
            Снятые ограничения ({lifted.length})
          </summary>
          <ul className="mt-2 flex flex-col gap-2">
            {lifted.map((item) => (
              <li key={item.id} className="text-ink-muted">
                {item.buyer_email} — {item.reason} · снято{" "}
                {item.revoked_at === null ? "" : new Date(item.revoked_at).toLocaleString("ru-RU")}
                {item.revoked_by_email === null ? "" : ` (${item.revoked_by_email})`}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
