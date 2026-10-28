import type { Metadata } from "next";

import { AdminNav } from "@/components/admin/AdminNav";
import { IncidentFeed } from "@/components/moderation/IncidentFeed";
import { parseCatalogQuery, toSearchParams } from "@/lib/catalog-query";
import { ADMIN_PAGE_SIZE, getIncidents, requireRole } from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Инциденты",
  robots: { index: false, follow: false },
};

export default async function AdminIncidentsPage({ searchParams }: PageProps<"/admin/incidents">) {
  await requireRole("admin");
  const params = toSearchParams(await searchParams);
  const { offset } = parseCatalogQuery(params);
  const userId = params.get("user_id") ?? "";
  const page = await getIncidents(offset, { userId });
  const carried = new URLSearchParams(userId === "" ? {} : { user_id: userId });

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-10">
      <AdminNav current="incidents" />
      <p className="text-sm text-ink-muted">
        Жалобы и блокировки покупателей магазинами — то, что между людьми действительно произошло и
        осталось в базе. Заказов и переписки на площадке пока нет, и ленты про них тоже.
        Администратор видит всё, включая действия модераторов.
      </p>

      <form method="get" className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-sm">
          <span className="sr-only">Участник</span>
          <input
            name="user_id"
            defaultValue={userId}
            placeholder="Идентификатор участника"
            className="min-w-72 rounded-lg border border-ink-muted/30 bg-surface px-3 py-2"
          />
        </label>
        <button type="submit" className="rounded-lg bg-brand px-4 py-2 font-medium text-white">
          Показать
        </button>
      </form>

      <IncidentFeed
        page={page}
        path="/admin/incidents"
        params={carried}
        offset={offset}
        pageSize={ADMIN_PAGE_SIZE}
      />
    </main>
  );
}
