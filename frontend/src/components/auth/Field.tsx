type FieldProps = {
  label: string;
  name: string;
  type?: string;
  required?: boolean;
  autoComplete?: string;
  defaultValue?: string | number;
  error?: string | undefined;
};

export function Field({
  label,
  name,
  type = "text",
  required = true,
  autoComplete,
  defaultValue,
  error,
}: FieldProps) {
  const errorId = `${name}-error`;
  return (
    <div className="flex flex-col gap-1 text-sm">
      {/* The refusal sits outside the label: inside it, the text became part of the input's
          own name, so a screen reader announced the field as "Почта Этот адрес уже занят"
          and then read the same words again as its description. */}
      <label className="flex flex-col gap-1">
        <span className="font-medium">{label}</span>
        <input
          name={name}
          type={type}
          required={required}
          autoComplete={autoComplete}
          defaultValue={defaultValue}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2 outline-none focus:border-brand"
        />
      </label>
      {error ? (
        <span id={errorId} role="alert" className="text-danger">
          {error}
        </span>
      ) : null}
    </div>
  );
}
