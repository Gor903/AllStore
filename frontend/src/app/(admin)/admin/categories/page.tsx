import type { Metadata } from "next";

import { AdminNav } from "@/components/admin/AdminNav";
import { CategoryCreateForm, CategoryRow } from "@/components/admin/CategoryEditor";
import { getAdminCategories, requireRole } from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Категории",
  robots: { index: false, follow: false },
};

export default async function AdminCategoriesPage() {
  await requireRole("admin");
  const tree = await getAdminCategories();

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-10">
      <AdminNav current="categories" />

      {tree === null ? (
        <p className="text-danger">Справочник сейчас недоступен, попробуйте обновить страницу.</p>
      ) : (
        <>
          <section className="flex flex-col gap-3 rounded-card border border-ink-muted/20 p-4">
            <h2 className="font-medium">Новая категория</h2>
            <CategoryCreateForm parents={tree} />
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="font-medium">Справочник</h2>
            <p className="text-sm text-ink-muted">
              Скрытая категория уходит из фильтра покупателя, но товары под ней остаются на месте.
              Удаления нет: оно утащило бы товары за собой.
            </p>
            <ul className="flex flex-col divide-y divide-ink-muted/15 rounded-card border border-ink-muted/20">
              {tree.map((root) => (
                <li key={root.id}>
                  <ul className="flex flex-col divide-y divide-ink-muted/10">
                    <CategoryRow category={root} />
                    {root.children.map((child) => (
                      <CategoryRow key={child.id} category={child} nested />
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </main>
  );
}
