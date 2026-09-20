import { describe, expect, it } from "vitest";

import type { Product } from "@/lib/api";
import { productStatus } from "@/lib/product-status";

function product(fields: Partial<Product>): Product {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    business_id: "22222222-2222-2222-2222-222222222222",
    category_id: "33333333-3333-3333-3333-333333333333",
    name: "Кружка",
    description: null,
    price: "1500.00",
    currency: "AMD",
    stock_quantity: 3,
    availability_status: "in_stock",
    moderation_status: "pending",
    publication_status: "draft",
    rejection_reason: null,
    images: [],
    created_at: "2026-09-21T00:00:00Z",
    updated_at: "2026-09-21T00:00:00Z",
    ...fields,
  };
}

describe("productStatus", () => {
  it("says the product is waiting for a moderator", () => {
    expect(productStatus(product({}))).toMatchObject({ label: "На проверке", tone: "waiting" });
  });

  it("hands the seller the reason of a refusal", () => {
    const status = productStatus(
      product({ moderation_status: "rejected", rejection_reason: "Фото не то" }),
    );

    expect(status).toMatchObject({ label: "Отклонён", tone: "refused", hint: "Фото не то" });
  });

  it("survives a refusal that lost its reason", () => {
    const status = productStatus(product({ moderation_status: "rejected" }));

    expect(status.hint).toBe("Причина не указана.");
  });

  it("says nothing is left to do once the product is on the shelf", () => {
    const status = productStatus(
      product({ moderation_status: "approved", publication_status: "published" }),
    );

    expect(status).toMatchObject({ label: "Опубликован", tone: "live", hint: null });
  });

  it("tells the seller what to do with a product a moderator hid", () => {
    const status = productStatus(
      product({ moderation_status: "approved", publication_status: "hidden" }),
    );

    expect(status.label).toBe("Скрыт модератором");
    expect(status.hint).toContain("повторную проверку");
  });

  it("covers the approved product that never reached the shelf", () => {
    const status = productStatus(
      product({ moderation_status: "approved", publication_status: "draft" }),
    );

    expect(status.tone).toBe("neutral");
    expect(status.hint).toContain("Отправьте товар на проверку");
  });
});
