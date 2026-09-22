"use client";

import { useRouter } from "next/navigation";
import { useState, type ChangeEvent } from "react";

import type { User } from "@/lib/api";
import { apiPost } from "@/lib/browser-api";

type RoleSelectProps = {
  userId: string;
  role: User["role"];
};

const ROLES: { value: User["role"]; label: string }[] = [
  { value: "buyer", label: "покупатель" },
  { value: "seller", label: "продавец" },
  { value: "moderator", label: "модератор" },
  { value: "admin", label: "админ" },
];

/**
 * Appointing a moderator used to mean a direct write to the database. The refusals the
 * backend can answer with — the last administrator, an account that runs a shop — are
 * shown next to the row rather than swallowed: the administrator has to learn why.
 */
export function RoleSelect({ userId, role }: RoleSelectProps) {
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onPick(event: ChangeEvent<HTMLSelectElement>) {
    const next = event.target.value as User["role"];
    if (next === role) {
      return;
    }
    setBusy(true);
    setMessage(null);
    const result = await apiPost<User>(`/admin/users/${userId}/role`, { role: next });
    setBusy(false);
    if (!result.ok) {
      // the select snaps back: the role on screen must be the role in the database
      event.target.value = role;
      setMessage(result.error.message);
      return;
    }
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-1">
      <label className="sr-only" htmlFor={`role-${userId}`}>
        Роль
      </label>
      <select
        id={`role-${userId}`}
        defaultValue={role}
        onChange={(event) => void onPick(event)}
        disabled={busy}
        className="rounded-lg border border-ink-muted/30 bg-surface px-2 py-1 text-sm disabled:opacity-60"
      >
        {ROLES.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {message === null ? null : (
        <p role="alert" className="max-w-xs text-xs text-danger">
          {message}
        </p>
      )}
    </div>
  );
}
