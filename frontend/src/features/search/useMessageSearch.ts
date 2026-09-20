import { useEffect, useRef, useState } from "react";
import { invoke } from "../../bridge";
import { useWorkbench } from "../../store";
import type { Operation, SearchItem } from "../../types";
import { operationIsRunning } from "../../utils/labels";

export function useMessageSearch() {
  const { account, selected, operations, trackOperation, pollOperation } =
    useWorkbench();
  const [query, setQuery] = useState("");
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [messageType, setMessageType] = useState("all");
  const [selectedOnly, setSelectedOnly] = useState(false);
  const [operationId, setOperationId] = useState<string>();
  const [items, setItems] = useState<SearchItem[]>([]);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const pending = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    if (!selected.length) setSelectedOnly(false);
  }, [selected.length]);
  const operation = operationId ? operations[operationId] : undefined;
  const running = submitting || operationIsRunning(operation?.status);
  const dateError =
    startAt && endAt && startAt > endAt ? "结束日期不能早于开始日期" : "";

  const run = async () => {
    if (!account || !query.trim() || pending.current || running || dateError)
      return;
    const version = useWorkbench.getState().contextVersion;
    const current = () =>
      mounted.current && useWorkbench.getState().contextVersion === version;
    pending.current = true;
    setSubmitting(true);
    setItems([]);
    setError("");
    setOperationId(undefined);
    setSearchedQuery(query.trim());
    try {
      const first = await invoke<Operation>("search_messages", {
        account_id: account.account_id,
        query: query.trim(),
        limit: 300,
        start_at: startAt ? `${startAt}T00:00:00` : null,
        end_at: endAt ? `${endAt}T23:59:59` : null,
        message_types: messageType === "all" ? [] : [messageType],
        conversation_ids: selectedOnly ? [...selected] : [],
      });
      if (!current()) return;
      trackOperation(first);
      setOperationId(first.operation_id);
      const done = await pollOperation<{ items: SearchItem[] }>(
        first.operation_id,
      );
      if (!current()) return;
      setItems(done.status === "completed" ? done.result?.items || [] : []);
      if (done.status === "failed")
        setError(done.error || "读取聊天记录失败，请重试。");
    } catch (failure) {
      if (current())
        setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      pending.current = false;
      if (current()) setSubmitting(false);
    }
  };
  const cancel = async () => {
    if (!operationId) return;
    try {
      await invoke("cancel_operation", operationId);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };
  return {
    query,
    setQuery,
    startAt,
    setStartAt,
    endAt,
    setEndAt,
    messageType,
    setMessageType,
    selectedOnly,
    setSelectedOnly,
    items,
    searchedQuery,
    error,
    operation,
    running,
    dateError,
    run,
    cancel,
  };
}
