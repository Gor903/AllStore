import { BlockHistory } from "@/components/moderation/BlockHistory";
import { VerdictButtons, type Verdict } from "@/components/moderation/VerdictButtons";
import type { User } from "@/lib/api";

type AccountRowsProps = {
  items: User[];
  /** The account looking at the list, so it can be marked rather than acted on. */
  viewerId: string;
  /** Rendered between the name and the verdicts — the administrator's role select. */
  extra?: (item: User) => React.ReactNode;
};

const ROLE: Record<string, string> = {
  buyer: "покупатель",
  seller: "продавец",
  moderator: "модератор",
  admin: "админ",
};

const STATUS: Record<string, string> = {
  active: "активен",
  suspended: "приостановлен",
  blocked: "заблокирован",
};

const BLOCK: Verdict[] = [
  {
    label: "Заблокировать",
    action: "block",
    reasonPrompt: "За что? Причина останется в истории и в журнале.",
    danger: true,
  },
];

const UNBLOCK: Verdict[] = [
  { label: "Разблокировать", action: "unblock", reasonPrompt: "Почему снимаете? Необязательно." },
];

/**
 * One list of accounts, shared by the administrator's screen and the moderator's.
 *
 * The rows are identical because the action is: barring somebody is one decision in the
 * access matrix, and who may take it against whom is settled by the backend's ranks. The
 * panels differ in what else they may do — roles and appointments are the administrator's —
 * not in how a ban looks.
 */
export function AccountRows({ items, viewerId, extra }: AccountRowsProps) {
  return (
    <ul className="flex flex-col divide-y divide-ink-muted/15 rounded-card border border-ink-muted/20">
      {items.map((item) => (
        <li key={item.id} className="flex flex-wrap items-start gap-4 p-4">
          <div className="min-w-48 flex-1">
            <p className="font-medium">{item.email}</p>
            <p className="text-sm text-ink-muted">
              {ROLE[item.role] ?? item.role} · {STATUS[item.status] ?? item.status}
              {item.id === viewerId ? " — это вы" : ""}
            </p>
          </div>
          {extra?.(item)}
          {item.id === viewerId ? null : (
            <VerdictButtons
              basePath={`/accounts/${item.id}`}
              verdicts={item.status === "blocked" ? UNBLOCK : BLOCK}
            />
          )}
          <BlockHistory userId={item.id} email={item.email} />
        </li>
      ))}
    </ul>
  );
}
