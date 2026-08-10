import { useCallback, useEffect, useRef, useState } from "react";
import { fetchReadiness } from "../lib/healthApi";
import type { ServiceHealthState } from "../types/health";

const initialState: ServiceHealthState = {
  phase: "checking",
  report: null,
  message: "正在检查基础服务",
};

export function useServiceHealth() {
  const [state, setState] = useState<ServiceHealthState>(initialState);
  const controllerRef = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState(initialState);

    try {
      const report = await fetchReadiness(controller.signal);
      if (report.status === "ok") {
        setState({ phase: "ready", report, message: "基础服务已就绪" });
      } else {
        const downCount = Object.values(report.checks).filter(
          (check) => check.status === "down",
        ).length;
        setState({
          phase: "unavailable",
          report,
          message: `${downCount} 项基础服务不可用`,
        });
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setState({
        phase: "unavailable",
        report: null,
        message: error instanceof Error ? error.message : "无法检查基础服务",
      });
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
    }
  }, []);

  useEffect(() => {
    void refresh();
    return () => controllerRef.current?.abort();
  }, [refresh]);

  return { state, refresh };
}
