"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { STATIC } from "@/lib/api";

const PAGES = [
  { name: "Overview", href: "/" },
  { name: "Analytics", href: "/analytics" },
  { name: "Model", href: "/model" },
  { name: "Business", href: "/business" },
  { name: "Agent", href: "/agent" },
  { name: "Evals", href: "/evals" },
  { name: "Pipeline", href: "/pipeline" },
  { name: "Export", href: "/export" },
  { name: "Upload", href: "/upload" },
];

export default function Nav() {
  const path = (usePathname() ?? "/").replace(/\/$/, "") || "/";
  return (
    <header className="border-b border-neutral-800">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-6 py-3">
        <span className="text-lg font-semibold tracking-tight">Argus</span>
        <nav aria-label="Pages" className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {PAGES.map((p) => {
            const here = p.href === path;
            return (
              <Link
                key={p.name}
                href={p.href}
                aria-current={here ? "page" : undefined}
                className={here ? "font-medium text-sky-300 underline decoration-sky-500 underline-offset-8" : "text-neutral-200 hover:text-sky-400"}
              >
                {p.name}
              </Link>
            );
          })}
        </nav>
        <span className="ml-auto rounded-full bg-amber-500/10 px-3 py-1 text-xs text-amber-300">
          {STATIC ? "Static snapshot of a real run" : "Real 2008 benchmark data, local AI model"}
        </span>
      </div>
    </header>
  );
}
