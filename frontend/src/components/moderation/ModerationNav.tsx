import Link from "next/link";

import { LogoutButton } from "@/components/auth/LogoutButton";

type ModerationNavProps = {
  current: "products" | "businesses" | "catalog";
  products: number;
  businesses: number;
};

export function ModerationNav({ current, products, businesses }: ModerationNavProps) {
  const style = (active: boolean): string =>
    active
      ? "rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white"
      : "rounded-lg border border-ink-muted/30 px-3 py-1.5 text-sm font-medium";

  return (
    <header className="flex flex-wrap items-center gap-3">
      <h1 className="text-2xl font-semibold">Модерация</h1>
      <nav className="flex gap-2">
        <Link href="/moderation" className={style(current === "products")}>
          Товары ({products})
        </Link>
        <Link href="/moderation/businesses" className={style(current === "businesses")}>
          Продавцы ({businesses})
        </Link>
        <Link href="/moderation/catalog" className={style(current === "catalog")}>
          Поиск по каталогу
        </Link>
      </nav>
      <div className="ml-auto">
        <LogoutButton />
      </div>
    </header>
  );
}
