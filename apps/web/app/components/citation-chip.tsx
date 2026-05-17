"use client";

import { useState } from "react";
import type { PassageEvent } from "../lib/types";

export function CitationChip({
  n,
  passage,
}: {
  n: number;
  passage: PassageEvent | undefined;
}) {
  const [open, setOpen] = useState(false);
  const known = !!passage;
  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className={
          known
            ? "mx-0.5 inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded border border-stone-300 bg-stone-100 px-1 text-[11px] font-medium leading-none text-stone-700 hover:bg-stone-200"
            : "mx-0.5 inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded border border-red-300 bg-red-50 px-1 text-[11px] font-medium leading-none text-red-700"
        }
        title={known ? passage!.title : `Citation [${n}] not found in passages`}
      >
        {n}
      </button>
      {open && known && passage && (
        <span
          className="absolute left-1/2 top-6 z-10 w-72 -translate-x-1/2 rounded-md border border-stone-200 bg-white p-3 text-left text-xs shadow-lg"
          role="tooltip"
        >
          <span className="block font-semibold text-stone-900">
            {passage.title}
          </span>
          {passage.court && (
            <span className="mt-1 block text-stone-600">{passage.court}</span>
          )}
          {passage.citation && (
            <span className="mt-1 block text-stone-600">{passage.citation}</span>
          )}
          <span className="mt-1 block font-mono text-[10px] text-stone-500">
            {passage.anchor}
          </span>
          {passage.as_at && (
            <span className="mt-1 block text-[10px] text-stone-400">
              as-at {passage.as_at}
            </span>
          )}
        </span>
      )}
    </span>
  );
}
