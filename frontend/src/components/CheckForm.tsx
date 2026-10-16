import { useEffect, useState } from "react";
import { ApiError, check, getCountries } from "../api";
import type { CheckResult, Country, Item } from "../types";

export function CheckForm(props: { item: Item | null; onResult: (r: CheckResult) => void }) {
  const { item, onResult } = props;
  const [countries, setCountries] = useState<Country[]>([]);
  const [country, setCountry] = useState("");
  const [endUser, setEndUser] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCountries()
      .then(setCountries)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "国家列表加载失败"));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!item || !country) return;
    setBusy(true);
    setError(null);
    try {
      const eu = endUser.trim();
      onResult(await check({ eccn: item.eccn, country, end_user: eu || undefined }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "判定失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <p className="text-sm">
        已选物项：
        {item ? (
          <span className="font-mono font-semibold">
            {item.eccn} {item.title_zh}
          </span>
        ) : (
          <span className="text-gray-500">请先在左侧选择物项</span>
        )}
      </p>
      <div>
        <label htmlFor="country" className="block text-sm font-medium">
          目的国
        </label>
        <select
          id="country"
          value={country}
          onChange={(e) => setCountry(e.target.value)}
          className="w-full rounded border border-gray-300 px-3 py-2"
        >
          <option value="">请选择国家</option>
          {countries.map((c) => (
            <option key={c.code} value={c.code}>
              {c.name_zh}
              {c.embargoed ? "（禁运）" : ""}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="end-user" className="block text-sm font-medium">
          最终用户（可选）
        </label>
        <input
          id="end-user"
          value={endUser}
          maxLength={200}
          onChange={(e) => setEndUser(e.target.value)}
          className="w-full rounded border border-gray-300 px-3 py-2"
        />
      </div>
      <button
        type="submit"
        disabled={!item || !country || busy}
        className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
      >
        {busy ? "判定中…" : "开始判定"}
      </button>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </form>
  );
}
