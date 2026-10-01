type StatBlockProps = {
  value: number;
  label: string;
};

export function StatBlock({ value, label }: StatBlockProps) {
  return (
    <div className="border-l-2 border-line pl-4">
      <p className="font-serif text-3xl text-ink leading-none">{value}</p>
      <p className="text-xs text-stone mt-2">{label}</p>
    </div>
  );
}
