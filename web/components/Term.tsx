import { GLOSSARY } from "@/lib/glossary";

// Marks a technical word and shows its plain-language meaning on hover. The same text is listed in full on the Overview page.
export default function Term({ k, children }: { k: keyof typeof GLOSSARY | string; children?: React.ReactNode }) {
  const def = GLOSSARY[k];
  if (!def) return <>{children ?? k}</>;
  return (
    <abbr title={def} className="cursor-help no-underline decoration-dotted underline-offset-4 hover:underline">
      {children ?? k}
    </abbr>
  );
}
