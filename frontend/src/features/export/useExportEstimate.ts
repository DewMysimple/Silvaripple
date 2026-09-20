import { useEffect, useState } from "react";
import { invoke } from "../../bridge";
import type { ExportEstimate } from "../../types";
import type { ExportRequest } from "./model";

interface EstimateState {
  key: string;
  result?: ExportEstimate;
  error?: string;
  loading: boolean;
}

export function useExportEstimate(request?: ExportRequest) {
  // A serialized key also detects in-place draft changes and prevents an old
  // estimate flashing for one render before the effect has cleaned up.
  const key = request ? JSON.stringify(request) : "";
  const [state, setState] = useState<EstimateState>({
    key: "",
    loading: false,
  });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    if (!key) return;
    setState({ key, loading: true });
    const timer = window.setTimeout(() => {
      void invoke<ExportEstimate>("estimate_export", JSON.parse(key)).then(
        (result) => {
          if (current) setState({ key, result, loading: false });
        },
        (error) => {
          if (current)
            setState({
              key,
              error: error instanceof Error ? error.message : String(error),
              loading: false,
            });
        },
      );
    }, 500);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [key, attempt]);
  const visible = key && state.key === key ? state : undefined;
  return {
    estimate: visible?.result,
    estimateError: visible?.error,
    estimating: Boolean(key && (!visible || visible.loading)),
    retryEstimate: () => setAttempt((value) => value + 1),
  };
}
