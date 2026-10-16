import type { CheckRequest, CheckResult, Country, Item } from "./types";

export class ApiError extends Error {}

async function request(url: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let msg = `请求失败（${res.status}）`;
    try {
      const { detail } = await res.json();
      if (typeof detail === "string") msg = detail;
      else if (Array.isArray(detail) && typeof detail[0]?.msg === "string") msg = detail[0].msg;
    } catch {
      // non-JSON error body: keep the generic message
    }
    throw new ApiError(msg);
  }
  return res;
}

const post = (url: string, body: CheckRequest) =>
  request(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export async function searchItems(q: string): Promise<Item[]> {
  return (await request(`/api/items?q=${encodeURIComponent(q)}`)).json();
}

export async function getCountries(): Promise<Country[]> {
  return (await request("/api/countries")).json();
}

export async function check(req: CheckRequest): Promise<CheckResult> {
  return (await post("/api/check", req)).json();
}

export async function downloadReport(req: CheckRequest): Promise<void> {
  const blob = await (await post("/api/report", req)).blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `compliance-report-${req.eccn}-${req.country}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}
