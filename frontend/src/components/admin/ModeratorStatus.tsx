import type { User } from "@/lib/api";

/**
 * Whether the handover worked, which is the one thing this list could not say before.
 *
 * All three states are read off what the account already carries: a password somebody else
 * handed over, and whether it has ever been used. Nothing here decides anything — the server
 * refuses a stale password on its own, and it owns the clock that makes it stale.
 *
 * That clock is deliberately not copied here. The date the password was handed over is shown
 * instead, which is what an administrator judges "this is going nowhere" by, and it cannot
 * drift away from a setting it does not duplicate.
 */
export function ModeratorStatus({ user }: { user: User }) {
  if (!user.must_change_password) {
    return <span className="text-ink-muted">пароль свой</span>;
  }
  const handed =
    user.password_handed_over_at === null
      ? null
      : new Date(user.password_handed_over_at).toLocaleDateString("ru-RU");
  const waiting = user.last_login_at === null;
  return (
    <span className="text-ink-muted">
      {waiting ? "ждёт первого входа" : "вошёл, пароль ещё не сменил"}
      {handed === null ? null : ` · пароль выдан ${handed}`}
    </span>
  );
}
