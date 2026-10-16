export type Decision = "LICENSE_REQUIRED" | "NEEDS_REVIEW" | "NLR";

export interface Item {
  eccn: string;
  title: string;
  title_zh: string;
  keywords: string[];
  controls: string[];
  special_controls: { reason: string; citation: string }[];
}

export interface Country {
  code: string;
  name_zh: string;
  embargoed: boolean;
}

export interface Finding {
  rule: "embargo" | "country_chart" | "special_control" | "entity_list";
  decision: Decision;
  message: string;
  citation: string;
}

export interface CheckRequest {
  eccn: string;
  country: string;
  end_user?: string;
}

export interface CheckResult {
  decision: Decision;
  findings: Finding[];
  ruleset_version: string;
  ruleset_digest: string;
  input: { eccn: string; country: string; end_user: string | null };
}

export const EAR99_ITEM: Item = {
  eccn: "EAR99",
  title: "Not on the CCL",
  title_zh: "不在 CCL 上",
  keywords: [],
  controls: [],
  special_controls: [],
};
