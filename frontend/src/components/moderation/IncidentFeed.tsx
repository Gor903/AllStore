import { Pagination } from "@/components/catalog/Pagination";
import type { IncidentList } from "@/lib/api";

type IncidentFeedProps = {
  page: IncidentList | null;
  path: string;
  params: URLSearchParams;
  offset: number;
  pageSize: number;
};

const KIND: Record<string, string> = {
  report: "жалоба",
  customer_block: "магазин закрыт покупателю",
};

/**
 * One list, both panels. What differs between a moderator's feed and an administrator's is
 * which events the backend puts in it, not how they look — so there is one component and one
 * place to change if the shape of an incident changes.
 */
export function IncidentFeed({ page, path, params, offset, pageSize }: IncidentFeedProps) {
  if (page === null) {
    return <p className="text-danger">Лента сейчас недоступна, попробуйте обновить страницу.</p>;
  }
  if (page.items.length === 0) {
    return <p className="text-ink-muted">Ничего не происходило.</p>;
  }

  return (
    <>
      <p className="text-sm text-ink-muted">Всего: {page.total}</p>
      <ul className="flex flex-col divide-y divide-ink-muted/15 rounded-card border border-ink-muted/20">
        {page.items.map((item) => (
          <li
            key={`${item.kind}-${item.happened_at}-${item.counterpart_email ?? ""}`}
            className="flex flex-col gap-1 p-4"
          >
            <p className="text-sm">
              <span className="font-medium">{item.initiator_email ?? "аккаунт удалён"}</span>
              {" → "}
              <span className="font-medium">{item.counterpart_email ?? "аккаунт удалён"}</span>
              {" · "}
              {KIND[item.kind] ?? item.kind}
              {item.subject === "" ? "" : ` (${item.subject})`}
            </p>
            {item.reason === null ? null : (
              <p className="text-sm text-ink-muted">«{item.reason}»</p>
            )}
            <p className="text-xs text-ink-muted">
              {new Date(item.happened_at).toLocaleString("ru-RU")}
            </p>
          </li>
        ))}
      </ul>
      <Pagination
        path={path}
        params={params}
        offset={offset}
        pageSize={pageSize}
        total={page.total}
      />
    </>
  );
}
