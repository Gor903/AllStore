"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiPost } from "@/lib/browser-api";

export function LogoutButton() {
  const router = useRouter();
  const [pending, setPending] = useState(false);

  async function onClick() {
    setPending(true);
    await apiPost("/auth/logout", {});
    setPending(false);
    router.push("/login");
    router.refresh();
  }

  return (
    <button
      type="button"
      onClick={() => void onClick()}
      disabled={pending}
      className="rounded-lg border border-ink-muted/30 px-3 py-1.5 text-sm disabled:opacity-60"
    >
      {pending ? "Выходим…" : "Выйти"}
    </button>
  );
}
