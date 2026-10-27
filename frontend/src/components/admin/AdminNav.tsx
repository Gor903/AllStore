import Link from "next/link";

import { LogoutButton } from "@/components/auth/LogoutButton";

type AdminNavProps = {
  current: "users" | "moderators" | "categories" | "audit";
};

const TABS = [
  { key: "users", href: "/admin", label: "Пользователи" },
  { key: "moderators", href: "/admin/moderators", label: "Модераторы" },
  { key: "categories", href: "/admin/categories", label: "Категории" },
  { key: "audit", href: "/admin/audit", label: "Журнал" },
] as const;

export function AdminNav({ current }: AdminNavProps) {
  const style = (active: boolean): string =>
    active
      ? "rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white"
      : "rounded-lg border border-ink-muted/30 px-3 py-1.5 text-sm font-medium";

  return (
    <header className="flex flex-wrap items-center gap-3">
      <h1 className="text-2xl font-semibold">Админка</h1>
      <nav className="flex flex-wrap gap-2">
        {TABS.map((tab) => (
          <Link key={tab.key} href={tab.href} className={style(current === tab.key)}>
            {tab.label}
          </Link>
        ))}
        <Link href="/moderation" className={style(false)}>
          Модерация
        </Link>
      </nav>
      <div className="ml-auto">
        <LogoutButton />
      </div>
    </header>
  );
}
