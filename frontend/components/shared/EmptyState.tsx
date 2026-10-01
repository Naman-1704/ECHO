type EmptyStateProps = {
  title: string;
  description: string;
  action?: { label: string; onClick: () => void; loading?: boolean };
};

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="border border-dashed border-line rounded-sm px-8 py-12 text-center max-w-prose mx-auto">
      <p className="font-serif text-lg text-ink mb-2">{title}</p>
      <p className="text-sm text-stone mb-6">{description}</p>
      {action && (
        <button
          onClick={action.onClick}
          disabled={action.loading}
          className="px-4 py-2 text-sm bg-ink text-paper rounded-sm hover:bg-ink/90 disabled:opacity-50 transition-colors"
        >
          {action.loading ? "Working…" : action.label}
        </button>
      )}
    </div>
  );
}
