import { TONE_CLASS, type ProductStatus } from "@/lib/product-status";

export function StatusPill({ status }: { status: ProductStatus }) {
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${TONE_CLASS[status.tone]}`}
    >
      {status.label}
    </span>
  );
}
