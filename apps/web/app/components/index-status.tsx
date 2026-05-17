"use client";

import { useEffect, useState } from "react";

interface Health {
  status: string;
  chunks: number;
  documents: number;
}

// Shows a small "X passages from Y documents indexed" pill so users can see
// the scale of the source corpus the answers are drawn from. Soft-fails if
// the API isn't reachable yet.
export function IndexStatus() {
  const [h, setH] = useState<Health | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    fetch("/api/healthz", { signal: ac.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: Health) => setH(j))
      .catch((e) => {
        if (!ac.signal.aborted) setErr(e instanceof Error ? e.message : String(e));
      });
    return () => ac.abort();
  }, []);

  if (err) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-2.5 py-0.5 text-[11px] text-amber-800">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
        API unavailable
      </span>
    );
  }
  if (!h) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-stone-300 bg-white px-2.5 py-0.5 text-[11px] text-stone-500">
        <span className="h-1.5 w-1.5 rounded-full bg-stone-400" />
        checking index…
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300 bg-emerald-50 px-2.5 py-0.5 text-[11px] text-emerald-800">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
      {fmt(h.chunks)} passages from {fmt(h.documents)} documents
    </span>
  );
}

function fmt(n: number): string {
  return n.toLocaleString("en-IN");
}
