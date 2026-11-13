import { describe, expect, it } from "vitest";

import { toFormError } from "@/lib/errors";

describe("toFormError", () => {
  it("takes the message from the error envelope", () => {
    const result = toFormError({
      error: { code: "invalid_credentials", message: "Неверный email или пароль", details: [] },
    });

    expect(result.message).toBe("Неверный email или пароль");
    expect(result.fieldErrors).toEqual({});
  });

  it("maps validation details onto fields", () => {
    const result = toFormError({
      error: {
        code: "validation_failed",
        message: "Request validation failed",
        details: [
          { loc: ["body", "email"], msg: "value is not a valid email address" },
          { loc: ["body", "password"], msg: "String should have at least 10 characters" },
        ],
      },
    });

    expect(result.fieldErrors["email"]).toContain("email address");
    expect(result.fieldErrors["password"]).toContain("at least 10");
  });

  it("falls back when the body is not an envelope", () => {
    expect(toFormError("<html>502</html>").message).toBe(
      "Не удалось выполнить запрос, попробуйте ещё раз",
    );
    expect(toFormError(null).fieldErrors).toEqual({});
  });
});
