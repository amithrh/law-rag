"use client";

import type { PassageEvent, SentenceEvent } from "../lib/types";
import { CitationChip } from "./citation-chip";

const STATUS_STYLE: Record<SentenceEvent["status"], string> = {
  ok: "text-stone-900",
  guidance: "text-stone-700 bg-stone-50 border-l-2 border-stone-300 pl-2",
  weak_support: "text-stone-900 bg-amber-50 px-1 rounded-sm",
  unsupported: "text-stone-500 bg-red-50 px-1 rounded-sm line-through decoration-red-400 decoration-1",
  unknown_citation: "text-stone-500 bg-red-50 px-1 rounded-sm line-through decoration-red-400 decoration-1",
  meta: "text-stone-500 italic",
};

const STATUS_BADGE: Partial<Record<SentenceEvent["status"], string>> = {
  guidance: "practical step",
  weak_support: "weak support",
  unsupported: "unsupported",
  unknown_citation: "bad citation",
};

// Renders one sentence with inline [n] citation chips replacing the bracket
// tokens, plus a status-tinted background. The model emits citations as
// "[1]", "[2,3]" etc — we replace each occurrence with a clickable chip so
// the prose still reads naturally.
export function SentenceLine({
  sentence,
  passagesByIndex,
}: {
  sentence: SentenceEvent;
  passagesByIndex: Map<number, PassageEvent>;
}) {
  const badge = STATUS_BADGE[sentence.status];
  return (
    <p className="my-2 leading-relaxed">
      <span className={STATUS_STYLE[sentence.status]}>
        {renderWithCitations(sentence.text, passagesByIndex)}
        {sentence.auto_cited && sentence.citations.length > 0 && (
          <CitationChip
            n={sentence.citations[0]}
            passage={passagesByIndex.get(sentence.citations[0])}
          />
        )}
      </span>
      {sentence.auto_cited && (
        <span
          className="ml-2 align-baseline rounded border border-sky-200 bg-sky-50 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-sky-700"
          title={sentence.reason ?? "Citation attached by lexical match — the model did not write one inline."}
        >
          auto-cite
        </span>
      )}
      {badge && (
        <span
          className="ml-2 align-baseline rounded border border-red-200 bg-red-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-red-700"
          title={sentence.reason ?? undefined}
        >
          {badge}
        </span>
      )}
    </p>
  );
}

function renderWithCitations(
  text: string,
  passagesByIndex: Map<number, PassageEvent>,
): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const re = /\[(\d+(?:\s*,\s*\d+)*)\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const numbers = m[1].split(",").map((s) => parseInt(s.trim(), 10));
    for (const n of numbers) {
      parts.push(
        <CitationChip key={`c-${key++}`} n={n} passage={passagesByIndex.get(n)} />,
      );
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}
