import Link from "next/link";

/** The marketplace chrome. A storefront on its own subdomain does not wear it. */
export function SiteHeader() {
  return (
    <header className="border-b border-ink-muted/15">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-6 py-4">
        <Link href="/" className="text-xl font-semibold tracking-tight">
          AllStore.am
        </Link>
        <nav className="flex gap-4 text-sm">
          <Link href="/catalog" className="hover:text-brand">
            Каталог
          </Link>
          <Link href="/stores" className="hover:text-brand">
            Магазины
          </Link>
          <Link href="/assistant" className="hover:text-brand">
            Помощник
          </Link>
        </nav>
        <Link href="/login" className="ml-auto text-sm hover:text-brand">
          Войти
        </Link>
      </div>
    </header>
  );
}
