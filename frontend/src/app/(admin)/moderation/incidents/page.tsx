import type { Metadata } from "next";

import { IncidentFeed } from "@/components/moderation/IncidentFeed";
import { ModerationNav } from "@/components/moderation/ModerationNav";
import { parseCatalogQuery, toSearchParams } from "@/lib/catalog-query";
import {
  ADMIN_PAGE_SIZE,
  getIncidents,
  getModerationBusinesses,
  getModerationProducts,
  requireRole,
} from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Инциденты",
  robots: { index: false, follow: false },
};

export default async function ModerationIncidentsPage({
  searchParams,
}: PageProps<"/moderation/incidents">) {
  const viewer = await requireRole("moderator", "admin");
  const { offset } = parseCatalogQuery(toSearchParams(await searchParams));
  const [page, queue, businesses] = await Promise.all([
    getIncidents(offset),
    getModerationProducts(),
    getModerationBusinesses(),
  ]);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <ModerationNav
        current="incidents"
        isAdmin={viewer.role === "admin"}
        products={queue?.total ?? 0}
        businesses={businesses?.total ?? 0}
      />
      <p className="text-sm text-ink-muted">
        Что произошло между покупателями и продавцами: жалобы и закрытые двери магазинов. События с
        участием другого модератора или администратора сюда не попадают.
      </p>

      <IncidentFeed
        page={page}
        path="/moderation/incidents"
        params={new URLSearchParams()}
        offset={offset}
        pageSize={ADMIN_PAGE_SIZE}
      />
    </main>
  );
}
