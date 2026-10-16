import { useState } from "react";
import { CheckForm } from "./components/CheckForm";
import { ItemSearch } from "./components/ItemSearch";
import { ResultCard } from "./components/ResultCard";
import type { CheckResult, Item } from "./types";

export default function App() {
  const [item, setItem] = useState<Item | null>(null);
  const [result, setResult] = useState<CheckResult | null>(null);
  return (
    <main className="mx-auto max-w-5xl space-y-4 p-6">
      <h1 className="text-2xl font-bold">迷你出口合规查询台</h1>
      <div className="grid gap-6 md:grid-cols-2">
        <ItemSearch
          selected={item}
          onSelect={(i) => {
            setItem(i);
            setResult(null);
          }}
        />
        <div className="space-y-4">
          <CheckForm item={item} onResult={setResult} />
          {result && <ResultCard result={result} />}
        </div>
      </div>
      <footer className="border-t pt-3 text-xs text-gray-500">
        简化子集，仅供演示，不构成法律意见。
      </footer>
    </main>
  );
}
