import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { fetchStorefront } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: PageProps<"/s/[subdomain]">): Promise<Metadata> {
  const { subdomain } = await params;
  const store = await fetchStorefront(subdomain);
  return { title: store?.display_name ?? "Магазин не найден" };
}

export default async function StorefrontPage({ params }: PageProps<"/s/[subdomain]">) {
  const { subdomain } = await params;
  const store = await fetchStorefront(subdomain);
  if (store === null) {
    notFound();
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-6 px-6">
      <div
        className="h-2 w-24 rounded-full bg-brand"
        style={store.primary_color === null ? undefined : { background: store.primary_color }}
      />
      <h1 className="text-4xl font-semibold tracking-tight">{store.display_name}</h1>
      {store.description === null ? null : <p className="text-ink-muted">{store.description}</p>}
      <p className="text-sm text-ink-muted">
        Витрина {store.subdomain}. Каталог товаров появится на следующем этапе.
      </p>
    </main>
  );
}
