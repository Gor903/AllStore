type StatusBadgeProps = {
  label: string;
  healthy: boolean;
};

export function StatusBadge({ label, healthy }: StatusBadgeProps) {
  return (
    <span
      data-testid="status-badge"
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm ${
        healthy ? "bg-success/10 text-success" : "bg-danger/10 text-danger"
      }`}
    >
      <span
        aria-hidden="true"
        className={`size-2 rounded-full ${healthy ? "bg-success" : "bg-danger"}`}
      />
      {label}: {healthy ? "доступен" : "недоступен"}
    </span>
  );
}
