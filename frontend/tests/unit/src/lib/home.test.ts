import { describe, expect, it } from "vitest";

import { homeFor } from "@/lib/home";

describe("куда роль попадает по умолчанию", () => {
  it("администратор — в админку", () => {
    expect(homeFor("admin")).toBe("/admin");
  });

  it("модератор — в очередь", () => {
    expect(homeFor("moderator")).toBe("/moderation");
  });

  it("покупатель и продавец — в кабинет", () => {
    // there they have something of their own; the two roles above do not
    expect(homeFor("buyer")).toBe("/dashboard");
    expect(homeFor("seller")).toBe("/dashboard");
  });
});
