// The top of every page: what it is, in plain words, and what to take away from it.
export default function PageHeader({ title, children, takeaway }: { title: string; children: React.ReactNode; takeaway?: React.ReactNode }) {
  return (
    <div className="max-w-3xl space-y-3">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="text-base leading-relaxed text-neutral-300">{children}</p>
      {takeaway && <p className="rounded-lg bg-neutral-900 px-4 py-3 text-sm leading-relaxed text-neutral-200">{takeaway}</p>}
    </div>
  );
}
