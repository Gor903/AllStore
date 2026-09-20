import type { Metadata } from "next";
import Link from "next/link";

import { ProductForm } from "@/components/dashboard/ProductForm";
import { fetchCategories } from "@/lib/api";
import { requireRole } from "@/lib/dal";

export const metadata: Metadata = {
  title: "Новый товар",
  robots: { index: false, follow: false },
};

export default async function NewProductPage() {
  await requireRole("seller");
  const categories = await fetchCategories();

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-10">
      <nav className="text-sm text-ink-muted">
        <Link href="/dashboard" className="hover:text-brand">
          Кабинет
        </Link>
        {" / новый товар"}
      </nav>
      <h1 className="text-2xl font-semibold">Новый товар</h1>
      <p className="text-sm text-ink-muted">
        После сохранения добавьте фотографии и отправьте товар на проверку.
      </p>
      <ProductForm categories={categories} />
    </main>
  );
}
