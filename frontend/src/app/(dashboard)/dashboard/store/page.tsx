import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { BlockedBuyers } from "@/components/dashboard/BlockedBuyers";
import { ContactsForm } from "@/components/dashboard/ContactsForm";
import { StoreImageField } from "@/components/dashboard/StoreImageField";
import { StoreSettingsForm } from "@/components/dashboard/StoreSettingsForm";
import { getMyBlockedBuyers, getMyContacts, getMyStore, requireRole } from "@/lib/dal";
import { storeUrl } from "@/lib/urls";

export const metadata: Metadata = {
  title: "Настройки магазина",
  robots: { index: false, follow: false },
};

export default async function StoreSettingsPage() {
  await requireRole("seller");
  const [store, contacts, blocked] = await Promise.all([
    getMyStore(),
    getMyContacts(),
    getMyBlockedBuyers(),
  ]);
  // nothing to dress until the shop exists; the cabinet is where it gets created
  if (store === null) {
    redirect("/dashboard");
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-10">
      <header className="flex flex-col gap-2">
        <Link href="/dashboard" className="text-sm text-ink-muted hover:text-brand">
          ← Кабинет
        </Link>
        <h1 className="text-2xl font-semibold">Настройки магазина</h1>
        <p className="text-sm text-ink-muted">
          Как магазин выглядит покупателю на{" "}
          <a
            href={storeUrl(store.subdomain)}
            target="_blank"
            rel="noreferrer"
            className="hover:text-brand"
          >
            {storeUrl(store.subdomain)}
          </a>
        </p>
      </header>

      <section className="flex flex-col gap-4 rounded-card border border-ink-muted/20 p-4">
        <h2 className="font-medium">Оформление</h2>
        <StoreSettingsForm store={store} />
        <div className="grid gap-4 border-t border-ink-muted/15 pt-4 sm:grid-cols-2">
          <StoreImageField
            kind="logo"
            label="Логотип"
            hint="Квадратная картинка, стоит в шапке магазина и в списке магазинов."
            currentUrl={store.logo_url}
          />
          <StoreImageField
            kind="banner"
            label="Баннер"
            hint="Широкая картинка над витриной. Без неё витрина начинается сразу с названия."
            currentUrl={store.banner_url}
          />
        </div>
      </section>

      <section className="flex flex-col gap-4 rounded-card border border-ink-muted/20 p-4">
        <h2 className="font-medium">Контакты</h2>
        <ContactsForm contacts={contacts?.items ?? []} />
      </section>

      <BlockedBuyers items={blocked?.items ?? []} />
    </main>
  );
}
