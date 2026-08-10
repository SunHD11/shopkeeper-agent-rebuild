export type DependencyHealth = {
  status: "up" | "down";
  latency_ms: number;
  detail: string | null;
};

export type HealthReport = {
  status: "ok" | "unavailable";
  checks: Record<string, DependencyHealth>;
};

export type ServiceHealthState =
  | { phase: "checking"; report: null; message: string }
  | { phase: "ready"; report: HealthReport; message: string }
  | { phase: "unavailable"; report: HealthReport | null; message: string };
