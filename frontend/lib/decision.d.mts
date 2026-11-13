export type Validation = {
  execution_allowed: boolean;
  proposal: { policy: "reactive" | "anticipatory" } | null;
  explanation: string;
  mode: "offline" | "llm" | "fallback";
  audit?: { source: string; status: string; reasons?: string[] }[];
};
export type Decision = {
  status: "approved" | "abstained" | "unavailable";
  policy: string | null;
  title: string;
  reason: string;
};
export type Source = { tone: "approved" | "abstained"; text: string };
export function explanationSource(validation: Validation | null): Source | null;
export function interpretDecision(validation: Validation | null): Decision;
