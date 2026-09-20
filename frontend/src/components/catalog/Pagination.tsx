import Link from "next/link";

type PaginationProps = {
  path: string;
  params: URLSearchParams;
  offset: number;
  pageSize: number;
  total: number;
};

/** Plain links, so a page of the catalogue is an address a visitor can keep. */
export function Pagination({ path, params, offset, pageSize, total }: PaginationProps) {
  const hasPrevious = offset > 0;
  const hasNext = offset + pageSize < total;
  if (!hasPrevious && !hasNext) {
    return null;
  }

  const href = (value: number): string => {
    const next = new URLSearchParams(params);
    if (value > 0) {
      next.set("offset", String(value));
    } else {
      next.delete("offset");
    }
    const query = next.toString();
    return query === "" ? path : `${path}?${query}`;
  };

  const style = "rounded-lg border border-ink-muted/30 px-4 py-2 text-sm font-medium";
  const page = Math.floor(offset / pageSize) + 1;
  const pages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <nav className="flex items-center justify-center gap-3" aria-label="Страницы каталога">
      {hasPrevious ? (
        <Link href={href(offset - pageSize)} className={style} rel="prev">
          Назад
        </Link>
      ) : null}
      <span className="text-sm text-ink-muted">
        Страница {page} из {pages}
      </span>
      {hasNext ? (
        <Link href={href(offset + pageSize)} className={style} rel="next">
          Вперёд
        </Link>
      ) : null}
    </nav>
  );
}
