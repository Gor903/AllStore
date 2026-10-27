"use client";

import { useState } from "react";

import type { AccountBlockList } from "@/lib/api";
import { apiGet } from "@/lib/browser-api";

type BlockHistoryProps = {
  userId: string;
  email: string;
};

/**
 * Every ban this account has ever had, loaded when somebody asks for it.
 *
 * On demand rather than with the page: a list of twenty accounts would otherwise make twenty
 * requests for a history most of them do not have. Shown at all because a ban that has been
 * lifted still happened, and whoever is about to decide again needs to know it did.
 */
export function BlockHistory({ userId, email }: BlockHistoryProps) {
  const [page, setPage] = useState<AccountBlockList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onToggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (page !== null) {
      return;
    }
    setBusy(true);
    setError(null);
    const result = await apiGet<AccountBlockList>(`/accounts/${userId}/blocks`);
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setPage(result.data);
  }

  return (
    <div className="flex w-full flex-col gap-2">
      <button
        type="button"
        onClick={() => void onToggle()}
        aria-expanded={open}
        className="self-start text-sm text-brand underline-offset-2 hover:underline"
      >
        {open ? "Скрыть историю блокировок" : "История блокировок"}
      </button>

      {!open ? null : busy ? (
        <p className="text-sm text-ink-muted">Загружаем…</p>
      ) : error !== null ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : page === null || page.items.length === 0 ? (
        <p className="text-sm text-ink-muted">{email} ещё не блокировали.</p>
      ) : (
        <ul className="flex flex-col gap-2 rounded-lg border border-ink-muted/20 p-3 text-sm">
          {page.items.map((item) => (
            <li key={item.id} className="flex flex-col gap-0.5">
              <p>
                <span className="font-medium">{item.in_force ? "Действует" : "Снята"}</span> —{" "}
                {item.reason}
              </p>
              <p className="text-xs text-ink-muted">
                {new Date(item.created_at).toLocaleString("ru-RU")} ·{" "}
                {item.actor_email ?? "аккаунт удалён"}
                {item.revoked_at === null
                  ? ""
                  : ` · снял ${item.revoked_by_email ?? "аккаунт удалён"} ${new Date(
                      item.revoked_at,
                    ).toLocaleString("ru-RU")}`}
              </p>
              {item.revoke_reason === null ? null : (
                <p className="text-xs text-ink-muted">при снятии: {item.revoke_reason}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
