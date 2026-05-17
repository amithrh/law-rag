"use client";

import type { CoverageEvent } from "../lib/types";

const SOURCE_LABEL: Record<string, string> = {
  act: "Acts",
  judgment: "Judgments",
  circular: "Circulars",
};

const SUBJECT_LABEL: Record<string, string> = {
  consumer: "Consumer",
  family: "Family",
  criminal: "Criminal",
  wages: "Wages",
  rti: "RTI",
  motor: "Motor accident",
  tax: "Tax",
  property: "Property",
  contract: "Contract",
  service: "Service",
  cyber: "Cyber",
  environment: "Environment",
  it: "IT",
  intellectual_property: "IP",
  banking: "Banking/Insurance",
  constitutional: "Constitutional",
};

export function CoverageChip({ coverage }: { coverage: CoverageEvent }) {
  const sources = coverage.sources_searched
    .map((s) => SOURCE_LABEL[s] ?? s)
    .join(", ");
  const subjects = coverage.subjects_in_results
    .map((s) => SUBJECT_LABEL[s] ?? s)
    .join(", ");
  return (
    <div className="mb-4 flex flex-wrap gap-2 text-xs text-stone-600">
      <span className="rounded-full border border-stone-300 bg-white px-3 py-1">
        {coverage.passages_used} passage{coverage.passages_used === 1 ? "" : "s"} used
      </span>
      {sources && (
        <span className="rounded-full border border-stone-300 bg-white px-3 py-1">
          Sources: {sources}
        </span>
      )}
      {subjects && (
        <span className="rounded-full border border-stone-300 bg-white px-3 py-1">
          Subjects: {subjects}
        </span>
      )}
    </div>
  );
}
