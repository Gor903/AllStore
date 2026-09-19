type FieldProps = {
  label: string;
  name: string;
  type?: string;
  required?: boolean;
  autoComplete?: string;
  error?: string | undefined;
};

export function Field({
  label,
  name,
  type = "text",
  required = true,
  autoComplete,
  error,
}: FieldProps) {
  const errorId = `${name}-error`;
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium">{label}</span>
      <input
        name={name}
        type={type}
        required={required}
        autoComplete={autoComplete}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2 outline-none focus:border-brand"
      />
      {error ? (
        <span id={errorId} role="alert" className="text-danger">
          {error}
        </span>
      ) : null}
    </label>
  );
}
