import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { LogoutButton } from "@/components/auth/LogoutButton";
import { VerifyEmailNotice } from "@/components/auth/VerifyEmailNotice";
import { StatusPill } from "@/components/dashboard/StatusPill";
import { ResubmitBusiness } from "@/components/dashboard/ResubmitBusiness";
import { StoreForm } from "@/components/dashboard/StoreForm";
import { getMyBusiness, getMyContacts, getMyProducts, getMyStore, requireUser } from "@/lib/dal";
import { formatPrice } from "@/lib/format";
import { productStatus } from "@/lib/product-status";
import { storeUrl } from "@/lib/urls";

export const metadata: Metadata = {
  title: "Кабинет",
  robots: { index: false, follow: false },
};

const BUSINESS_STATUS: Record<string, string> = {
  pending: "на проверке модератором",
  active: "активен",
  rejected: "заявка отклонена",
  suspended: "приостановлен",
  blocked: "заблокирован",
};

export default async function DashboardPage() {
  // the real check lives here, not in the layout: layouts do not re-render on navigation
  const user = await requireUser();
  const seller = user.role === "seller";
  const [business, store, products, contacts] = seller
    ? await Promise.all([getMyBusiness(), getMyStore(), getMyProducts(), getMyContacts()])
    : [null, null, null, null];
  // A seller arriving through Google has an account and no business, because Google knows an
  // address and a shop needs a legal name. Without this the cabinet simply omits the shop
  // section and the person is left on a page with nothing to do and nowhere to go.
  if (seller && business === null) {
    redirect("/onboarding");
  }

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-8 px-6 py-10">
      <header className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">Кабинет</h1>
        <div className="flex items-center gap-3">
          <Link href="/devices" className="text-sm hover:text-brand">
            Устройства
          </Link>
          <LogoutButton />
        </div>
      </header>

      {user.email_verified_at === null ? (
        <VerifyEmailNotice email={user.email} seller={seller} />
      ) : null}

      <dl className="grid gap-2 text-sm">
        <div className="flex gap-2">
          <dt className="text-ink-muted">Email:</dt>
          <dd>{user.email}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-ink-muted">Роль:</dt>
          <dd>{user.role}</dd>
        </div>
      </dl>

      {user.role === "moderator" || user.role === "admin" ? (
        <Link
          href="/moderation"
          className="self-start rounded-lg bg-brand px-4 py-2 font-medium text-white"
        >
          Очередь модерации
        </Link>
      ) : null}

      {business === null ? null : (
        <section className="flex flex-col gap-3 rounded-card border border-ink-muted/20 p-4">
          <div>
            <h2 className="font-medium">{business.display_name}</h2>
            <p className="mt-1 text-sm text-ink-muted">
              {business.legal_name} — {BUSINESS_STATUS[business.status] ?? business.status}
            </p>
          </div>

          {business.status === "pending" ? (
            <p className="text-sm text-ink-muted">
              Пока заявка на проверке, магазин никому не виден. Товары можно готовить уже сейчас —
              их проверят отдельно.
            </p>
          ) : null}

          {business.status_reason === null ? null : (
            <p className="text-sm">
              <span className="text-ink-muted">Модератор написал: </span>
              {business.status_reason}
            </p>
          )}

          {business.status === "rejected" ? (
            <>
              <p className="text-sm text-ink-muted">
                Это не блокировка: исправьте то, что указано выше, и подайте заявку снова — она
                вернётся в очередь вместе с историей решений.
              </p>
              <ResubmitBusiness />
            </>
          ) : null}

          {store === null ? (
            <StoreForm />
          ) : (
            <>
              <p className="text-sm">
                Адрес магазина:{" "}
                <a
                  href={storeUrl(store.subdomain)}
                  className="font-medium hover:text-brand"
                  target="_blank"
                  rel="noreferrer"
                >
                  {storeUrl(store.subdomain)}
                </a>
                {store.status === "active" ? null : (
                  <span className="text-ink-muted"> — откроется после одобрения</span>
                )}
              </p>
              {contacts !== null && contacts.items.length === 0 ? (
                <p className="text-sm text-danger">
                  Не указан ни один способ связи. Пока его нет, товар не уходит на проверку —
                  покупателю некуда обратиться.
                </p>
              ) : null}
              <Link href="/dashboard/store" className="self-start text-sm hover:text-brand">
                Настройки магазина: оформление и контакты →
              </Link>
            </>
          )}
        </section>
      )}

      {seller ? (
        <section className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-xl font-semibold">Товары</h2>
            <Link
              href="/dashboard/products/new"
              className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white"
            >
              Добавить товар
            </Link>
          </div>

          {products === null || products.items.length === 0 ? (
            <p className="text-sm text-ink-muted">
              Товаров пока нет. Заведите первый — после проверки модератором он появится в каталоге.
            </p>
          ) : (
            <ul className="flex flex-col divide-y divide-ink-muted/15 rounded-card border border-ink-muted/20">
              {products.items.map((product) => {
                const status = productStatus(product);
                return (
                  <li key={product.id}>
                    <Link
                      href={`/dashboard/products/${product.id}`}
                      className="flex flex-wrap items-center gap-3 p-4 hover:bg-surface-muted"
                    >
                      <span className="font-medium">{product.name}</span>
                      <StatusPill status={status} />
                      <span className="ml-auto text-sm text-ink-muted">
                        {formatPrice(product.price, product.currency)}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      ) : null}
    </main>
  );
}
