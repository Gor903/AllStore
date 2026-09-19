/** The backend answers every failure in one envelope, see docs/AllStore_build_plan.md section 4.3. */
type ErrorEnvelope = {
  error: {
    code: string;
    message: string;
    details?: Array<{ loc?: Array<string | number>; msg?: string }>;
  };
};

export type FormError = {
  message: string;
  fieldErrors: Record<string, string>;
};

const FALLBACK = "Не удалось выполнить запрос, попробуйте ещё раз";

function isEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== "object" || value === null || !("error" in value)) {
    return false;
  }
  const { error } = value as { error: unknown };
  return typeof error === "object" && error !== null && "message" in error;
}

export function toFormError(body: unknown): FormError {
  if (!isEnvelope(body)) {
    return { message: FALLBACK, fieldErrors: {} };
  }
  const fieldErrors: Record<string, string> = {};
  for (const detail of body.error.details ?? []) {
    // loc looks like ["body", "email"]; the field name is the last segment
    const field = detail.loc?.at(-1);
    if (typeof field === "string" && detail.msg && field !== "body") {
      fieldErrors[field] = detail.msg;
    }
  }
  return { message: body.error.message || FALLBACK, fieldErrors };
}
