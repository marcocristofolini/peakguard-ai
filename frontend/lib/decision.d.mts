export type Validation = {
  execution_allowed: boolean;
  proposal: { policy: "reactive" | "anticipatory" } | null;
  explanation: string;
  mode: "offline" | "llm" | "fallback";
};
export type Decision = {
  status: "approved" | "abstained" | "unavailable";
  policy: string | null;
  title: string;
  reason: string;
};
export function interpretDecision(validation: Validation | null): Decision;
