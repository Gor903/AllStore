"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Field } from "@/components/auth/Field";
import type { CategoryTree, Product } from "@/lib/api";
import { apiPatch, apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";

type ProductFormProps = {
  categories: CategoryTree[];
  /** Absent when the form creates a product rather than edits one. */
  product?: Product;
};

export function ProductForm({ categories, product }: ProductFormProps) {
  const router = useRouter();
  const [error, setError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const description = String(form.get("description") ?? "").trim();
    const body = {
      category_id: form.get("category_id"),
      name: form.get("name"),
      // an empty box means the description is cleared, and null is how the backend hears that
      description: description === "" ? null : description,
      price: form.get("price"),
      stock_quantity: Number(form.get("stock_quantity") ?? 0),
    };

    const result =
      product === undefined
        ? await apiPost<Product>("/products", body)
        : await apiPatch<Product>(`/products/${product.id}`, body);
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    // straight to the card of the product: photos are added there
    router.push(`/dashboard/products/${result.data.id}`);
    router.refresh();
  }

  const field = "rounded-lg border border-ink-muted/30 bg-surface px-3 py-2 outline-none";

  return (
    <form onSubmit={onSubmit} className="flex max-w-xl flex-col gap-4" noValidate>
      <Field
        label="Название"
        name="name"
        defaultValue={product?.name ?? ""}
        error={error?.fieldErrors["name"]}
      />

      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium">Категория</span>
        <select
          name="category_id"
          defaultValue={product?.category_id ?? ""}
          required
          className={field}
        >
          <option value="" disabled>
            Выберите категорию
          </option>
          {categories.map((root) => (
            <optgroup key={root.slug} label={root.name}>
              {root.children.map((child) => (
                <option key={child.slug} value={child.id}>
                  {child.name}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        {error?.fieldErrors["category_id"] ? (
          <span role="alert" className="text-danger">
            {error.fieldErrors["category_id"]}
          </span>
        ) : null}
      </label>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Цена, ֏"
          name="price"
          defaultValue={product?.price ?? ""}
          error={error?.fieldErrors["price"]}
        />
        <Field
          label="Остаток, шт."
          name="stock_quantity"
          type="number"
          required={false}
          defaultValue={product?.stock_quantity ?? 0}
          error={error?.fieldErrors["stock_quantity"]}
        />
      </div>

      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium">Описание</span>
        <textarea
          name="description"
          rows={6}
          maxLength={5000}
          defaultValue={product?.description ?? ""}
          className={field}
        />
      </label>

      {error && Object.keys(error.fieldErrors).length === 0 ? (
        <p role="alert" className="text-sm text-danger">
          {error.message}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={pending}
        className="self-start rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-60"
      >
        {pending ? "Сохраняем…" : product === undefined ? "Создать товар" : "Сохранить"}
      </button>
    </form>
  );
}
