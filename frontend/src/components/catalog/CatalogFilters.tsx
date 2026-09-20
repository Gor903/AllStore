import type { CategoryTree } from "@/lib/api";
import type { CatalogQuery } from "@/lib/catalog-query";

type CatalogFiltersProps = {
  categories: CategoryTree[];
  query: CatalogQuery;
};

/**
 * A plain GET form: submitting it reloads the page with the filters in the address bar,
 * so search works with no JavaScript and every result is a link a visitor can keep.
 */
export function CatalogFilters({ categories, query }: CatalogFiltersProps) {
  const field = "rounded-lg border border-ink-muted/30 bg-surface px-3 py-2";

  return (
    <form method="get" action="/catalog" className="flex flex-wrap items-center gap-2">
      <input
        type="search"
        name="q"
        defaultValue={query.q ?? ""}
        placeholder="Поиск товаров"
        aria-label="Поиск товаров"
        maxLength={100}
        className={`${field} min-w-56 flex-1`}
      />
      <select
        name="category"
        defaultValue={query.category ?? ""}
        aria-label="Категория"
        className={field}
      >
        <option value="">Все категории</option>
        {categories.map((root) => (
          <optgroup key={root.slug} label={root.name}>
            <option value={root.slug}>Весь раздел</option>
            {root.children.map((child) => (
              <option key={child.slug} value={child.slug}>
                {child.name}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      {/* the shop the visitor came from survives a search inside it */}
      {query.store === null ? null : <input type="hidden" name="store" value={query.store} />}
      <button type="submit" className="rounded-lg bg-brand px-4 py-2 font-medium text-white">
        Найти
      </button>
    </form>
  );
}
