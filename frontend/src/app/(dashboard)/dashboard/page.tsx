import type { Metadata } from "next";
import Link from "next/link";

import { LogoutButton } from "@/components/auth/LogoutButton";
import { StatusPill } from "@/components/dashboard/StatusPill";
import { StoreForm } from "@/components/dashboard/StoreForm";
import { getMyBusiness, getMyProducts, getMyStore, requireUser } from "@/lib/dal";
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
  suspended: "приостановлен",
  blocked: "заблокирован",
};

export default async function DashboardPage() {
  // the real check lives here, not in the layout: layouts do not re-render on navigation
  const user = await requireUser();
  const seller = user.role === "seller";
  const [business, store, products] = seller
    ? await Promise.all([getMyBusiness(), getMyStore(), getMyProducts()])
    : [null, null, null];

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-8 px-6 py-10">
      <header className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">Кабинет</h1>
        <LogoutButton />
      </header>

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

          {store === null ? (
            <StoreForm />
          ) : (
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
