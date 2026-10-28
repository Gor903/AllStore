import Link from "next/link";

import { ACCOUNT_TABS, accountSearchParams, type AccountQuery } from "@/lib/account-query";

type AccountFiltersProps = {
  query: AccountQuery;
};

const STATUSES = [
  { value: "", label: "Любой статус" },
  { value: "active", label: "Активные" },
  { value: "suspended", label: "Приостановленные" },
  { value: "blocked", label: "Заблокированные" },
];

const SORTS = [
  { value: "registered", label: "Сначала новые" },
  { value: "last_login", label: "По последнему входу" },
  { value: "email", label: "По адресу" },
];

const BANS = [
  { value: "", label: "Неважно" },
  { value: "true", label: "Были баны" },
  { value: "false", label: "Банов не было" },
];

/** A plain GET form: a narrowed list stays an address somebody can keep or send on. */
export function AccountFilters({ query }: AccountFiltersProps) {
  const tabStyle = (active: boolean): string =>
    active
      ? "rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white"
      : "rounded-lg border border-ink-muted/30 px-3 py-1.5 text-sm font-medium";

  const withTab = (tab: string | null): string => {
    const params = accountSearchParams({ ...query, tab: null, offset: 0 });
    if (tab !== null) {
      params.set("tab", tab);
    }
    const search = params.toString();
    return search === "" ? "/admin" : `/admin?${search}`;
  };

  return (
    <div className="flex flex-col gap-3">
      <nav className="flex flex-wrap gap-2">
        <Link href={withTab(null)} className={tabStyle(query.tab === null)}>
          Все
        </Link>
        {ACCOUNT_TABS.map((tab) => (
          <Link key={tab.key} href={withTab(tab.key)} className={tabStyle(query.tab === tab.key)}>
            {tab.label}
          </Link>
        ))}
      </nav>

      <form method="get" className="flex flex-wrap items-end gap-2">
        {/* the tab travels in the form too, or submitting a filter would drop it */}
        {query.tab === null ? null : <input type="hidden" name="tab" value={query.tab} />}
        <label className="flex flex-col gap-1 text-sm">
          <span className="sr-only">Почта или телефон</span>
          <input
            name="q"
            defaultValue={query.q ?? ""}
            placeholder="Почта или телефон"
            className="min-w-56 rounded-lg border border-ink-muted/30 bg-surface px-3 py-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="sr-only">Статус</span>
          <select
            name="status"
            defaultValue={query.status ?? ""}
            className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2"
          >
            {STATUSES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="sr-only">Баны</span>
          <select
            name="has_bans"
            defaultValue={query.hasBans === null ? "" : String(query.hasBans)}
            className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2"
          >
            {BANS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="sr-only">Порядок</span>
          <select
            name="sort"
            defaultValue={query.sort}
            className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2"
          >
            {SORTS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="rounded-lg bg-brand px-4 py-2 font-medium text-white">
          Показать
        </button>
      </form>
    </div>
  );
}
