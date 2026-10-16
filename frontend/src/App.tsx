import { useState } from "react";
import { ItemSearch } from "./components/ItemSearch";
import type { Item } from "./types";

export default function App() {
  const [item, setItem] = useState<Item | null>(null);
  return (
    <main className="mx-auto max-w-2xl space-y-4 p-6">
      <h1 className="text-2xl font-bold">迷你出口合规查询台</h1>
      <ItemSearch selected={item} onSelect={setItem} />
      {item && <p>已选：{item.eccn} {item.title_zh}</p>}
    </main>
  );
}
