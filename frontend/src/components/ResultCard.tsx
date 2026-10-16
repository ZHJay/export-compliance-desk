import { useState } from "react";
import { downloadReport } from "../api";
import type { CheckResult, Decision } from "../types";

const BADGE: Record<Decision, { label: string; cls: string }> = {
  LICENSE_REQUIRED: { label: "需许可证", cls: "bg-red-100 text-red-800" },
  NEEDS_REVIEW: { label: "需人工复核", cls: "bg-yellow-100 text-yellow-800" },
  NLR: { label: "无需许可证", cls: "bg-green-100 text-green-800" },
};

function Badge({ d, big }: { d: Decision; big?: boolean }) {
  return (
    <span className={`rounded px-2 py-0.5 font-semibold ${big ? "text-lg" : "text-xs"} ${BADGE[d].cls}`}>
      {BADGE[d].label}
    </span>
  );
}

export function ResultCard({ result }: { result: CheckResult }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { eccn, country, end_user } = result.input;

  async function download() {
    setBusy(true);
    setError(null);
    try {
      await downloadReport({ eccn, country, end_user: end_user ?? undefined });
    } catch (e) {
      setError(e instanceof Error ? e.message : "导出失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-3 rounded border border-gray-200 p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm text-gray-600">
          {eccn} → {country}
        </span>
        <Badge d={result.decision} big />
      </div>
      <ul className="space-y-2">
        {result.findings.map((f, i) => (
          <li key={i} className="space-y-1 rounded bg-gray-50 p-2 text-sm">
            <Badge d={f.decision} />
            <p>{f.message}</p>
            <p className="text-xs text-gray-500">{f.citation}</p>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500">
        <span>
          规则版本 {result.ruleset_version} · {result.ruleset_digest}
        </span>
        <button
          type="button"
          onClick={download}
          disabled={busy}
          className="rounded border border-gray-300 px-3 py-1 text-sm text-gray-900 disabled:opacity-50"
        >
          {busy ? "导出中…" : "导出 PDF"}
        </button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </section>
  );
}
