import type { Product } from "@/lib/api";

export type StatusTone = "neutral" | "waiting" | "live" | "refused";

export type ProductStatus = {
  label: string;
  tone: StatusTone;
  /** What the seller is expected to do next, when there is anything to do. */
  hint: string | null;
};

/**
 * Two statuses live on a product — the moderator's verdict and where it stands on the
 * shelf — and a seller should not have to hold both in their head. This is the one
 * sentence that comes out of the pair.
 */
export function productStatus(product: Product): ProductStatus {
  if (product.moderation_status === "pending") {
    return { label: "На проверке", tone: "waiting", hint: "Модератор скоро посмотрит товар." };
  }
  if (product.moderation_status === "rejected") {
    return {
      label: "Отклонён",
      tone: "refused",
      hint: product.rejection_reason ?? "Причина не указана.",
    };
  }
  if (product.publication_status === "published") {
    return { label: "Опубликован", tone: "live", hint: null };
  }
  if (product.publication_status === "hidden") {
    return {
      label: "Скрыт модератором",
      tone: "refused",
      hint: "Исправьте товар и отправьте на повторную проверку.",
    };
  }
  return {
    label: "Одобрен, но не на полке",
    tone: "neutral",
    hint: "Отправьте товар на проверку, чтобы он снова появился в каталоге.",
  };
}

export const TONE_CLASS: Record<StatusTone, string> = {
  neutral: "bg-ink-muted/10 text-ink-muted",
  waiting: "bg-brand/10 text-brand",
  live: "bg-success/10 text-success",
  refused: "bg-danger/10 text-danger",
};
