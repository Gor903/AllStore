import type { User } from "@/lib/api";

export type AccountSort = "registered" | "last_login" | "email";

/** The three tabs of the administrator's list, and what each asks the backend for. */
export const ACCOUNT_TABS = [
  { key: "buyers", label: "Покупатели", roles: ["buyer"] },
  { key: "sellers", label: "Продавцы", roles: ["seller"] },
  { key: "moderators", label: "Модераторы", roles: ["moderator"] },
] as const;

export type AccountTab = (typeof ACCOUNT_TABS)[number]["key"];

export type AccountQuery = {
  tab: AccountTab | null;
  q: string | null;
  status: User["status"] | null;
  hasBans: boolean | null;
  sort: AccountSort;
  offset: number;
};

const STATUSES: readonly User["status"][] = ["active", "suspended", "blocked"];
const SORTS: readonly AccountSort[] = ["registered", "last_login", "email"];

function tabOf(value: string | null): AccountTab | null {
  return ACCOUNT_TABS.find((tab) => tab.key === value)?.key ?? null;
}

/**
 * What the address bar carries, with anything it cannot make sense of dropped.
 *
 * A tab nobody defined, a status that is not one, a sort that does not exist — all read as
 * "not asked", because a typed address should narrow the list or leave it alone, never fail.
 */
export function parseAccountQuery(params: URLSearchParams): AccountQuery {
  const offset = Number(params.get("offset"));
  const status = params.get("status");
  const sort = params.get("sort");
  const bans = params.get("has_bans");
  return {
    tab: tabOf(params.get("tab")),
    q: params.get("q")?.trim() || null,
    status: STATUSES.find((known) => known === status) ?? null,
    hasBans: bans === "true" ? true : bans === "false" ? false : null,
    sort: SORTS.find((known) => known === sort) ?? "registered",
    offset: Number.isSafeInteger(offset) && offset > 0 ? offset : 0,
  };
}

/** The backend's half: the same question, in the words `GET /admin/users` answers to. */
export function accountApiParams(query: AccountQuery, limit: number): URLSearchParams {
  const params = new URLSearchParams({ limit: String(limit), offset: String(query.offset) });
  const tab = ACCOUNT_TABS.find((known) => known.key === query.tab);
  for (const role of tab?.roles ?? []) {
    params.append("role", role);
  }
  if (query.q !== null) {
    params.set("q", query.q);
  }
  if (query.status !== null) {
    params.set("status", query.status);
  }
  if (query.hasBans !== null) {
    params.set("has_bans", String(query.hasBans));
  }
  params.set("sort", query.sort);
  return params;
}

/** The address bar's half, so a filtered list is a link somebody can keep or share. */
export function accountSearchParams(query: AccountQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.tab !== null) {
    params.set("tab", query.tab);
  }
  if (query.q !== null) {
    params.set("q", query.q);
  }
  if (query.status !== null) {
    params.set("status", query.status);
  }
  if (query.hasBans !== null) {
    params.set("has_bans", String(query.hasBans));
  }
  if (query.sort !== "registered") {
    params.set("sort", query.sort);
  }
  return params;
}
