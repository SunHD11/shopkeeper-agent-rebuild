import type { HealthReport } from "../types/health";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "";

function isHealthReport(value: unknown): value is HealthReport {
  if (!value || typeof value !== "object") return false;
  const report = value as Partial<HealthReport>;
  return (
    (report.status === "ok" || report.status === "unavailable") &&
    Boolean(report.checks) &&
    typeof report.checks === "object"
  );
}

export async function fetchReadiness(signal?: AbortSignal): Promise<HealthReport> {
  const response = await fetch(`${API_BASE_URL}/health/ready`, {
    headers: { Accept: "application/json" },
    signal,
  });
  const payload: unknown = await response.json();

  // readiness 在依赖异常时刻意返回 503，但响应体仍是有效的健康报告。
  if ((response.ok || response.status === 503) && isHealthReport(payload)) {
    return payload;
  }
  throw new Error(`健康检查返回了无效响应（HTTP ${response.status}）`);
}
