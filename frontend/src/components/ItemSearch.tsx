import { useEffect, useState } from "react";
import { searchItems } from "../api";
import { EAR99_ITEM, type Item } from "../types";

export function ItemSearch(props: { selected: Item | null; onSelect: (item: Item) => void }) {
  const { selected, onSelect } = props;
  const [q, setQ] = useState("");
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stale = false;
    const timer = setTimeout(() => {
      searchItems(q.trim())
        .then((r) => {
          if (stale) return;
          setItems(r.filter((i) => i.eccn !== EAR99_ITEM.eccn));
          setError(null);
        })
        .catch((e: unknown) => {
          if (stale) return;
          setItems([]);
          setError(e instanceof Error ? e.message : "搜索失败");
        })
        .finally(() => {
          if (!stale) setLoading(false);
        });
    }, 300);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [q]);

  const list = [EAR99_ITEM, ...items];

  return (
    <div className="space-y-2">
      <label htmlFor="item-q" className="block text-sm font-medium">
        物项检索（ECCN、名称或关键词）
      </label>
      <input
        id="item-q"
        type="search"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setLoading(true);
        }}
        placeholder="例如 5a0、加密"
        className="w-full rounded border border-gray-300 px-3 py-2"
      />
      {loading && <p className="text-sm text-gray-500">加载中…</p>}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          搜索出错：{error}
        </p>
      )}
      {!loading && !error && items.length === 0 && (
        <p className="text-sm text-gray-500">无匹配物项</p>
      )}
      <ul className="space-y-1">
        {list.map((item) => {
          const active = selected?.eccn === item.eccn;
          return (
            <li key={item.eccn}>
              <button
                type="button"
                aria-pressed={active}
                onClick={() => onSelect(item)}
                className={`flex w-full flex-wrap items-center gap-2 rounded border px-3 py-2 text-left ${
                  active ? "border-blue-600 bg-blue-50" : "border-gray-200 hover:bg-gray-50"
                }`}
              >
                <span className="font-mono font-semibold">{item.eccn}</span>
                <span>{item.title_zh}</span>
                {item.controls.map((c) => (
                  <span key={c} className="rounded bg-gray-200 px-1.5 text-xs">
                    {c}
                  </span>
                ))}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
