"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { HandedOverPassword } from "@/components/admin/HandedOverPassword";
import { useStepUp } from "@/components/auth/useStepUp";
import type { HandedOver } from "@/lib/api";
import { apiPost } from "@/lib/browser-api";

/**
 * Hands a moderator a new temporary password.
 *
 * There is no recovery link to send and nothing to wait for: the administrator already
 * decides who moderates, so letting them restore access is no new authority. The replacement
 * is generated like the first one, shown once, and expires on first use exactly as it did.
 *
 * Nothing to fill in, so nothing to confirm beyond the press: the moderator's sessions end
 * either way, and a password they could no longer use is not one worth keeping.
 */
export function ResetModeratorPassword({ userId, email }: { userId: string; email: string }) {
  const router = useRouter();
  const { attempt, prompt } = useStepUp();
  const [issued, setIssued] = useState<HandedOver | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onIssue() {
    setPending(true);
    setMessage(null);
    const result = await attempt(() =>
      apiPost<HandedOver>(`/admin/moderators/${userId}/password`, {}),
    );
    setPending(false);
    if (!result.ok) {
      setMessage(result.error.message);
      return;
    }
    setIssued(result.data);
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={() => void onIssue()}
        disabled={pending}
        className="w-fit rounded-lg border border-ink-muted/30 px-3 py-1.5 text-sm font-medium disabled:opacity-60"
      >
        {pending ? "Выдаём…" : "Выдать новый пароль"}
      </button>

      {prompt}

      {issued === null ? null : <HandedOverPassword email={email} password={issued.password} />}

      {message === null ? null : (
        <p role="alert" className="text-sm text-danger">
          {message}
        </p>
      )}
    </div>
  );
}
