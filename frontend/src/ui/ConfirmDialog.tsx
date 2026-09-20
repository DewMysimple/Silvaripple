import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { AlertTriangle } from "lucide-react";

export type ConfirmRequest = {
  title: string;
  description: string;
  count?: number;
  confirmLabel: string;
  notes?: string[];
  onConfirm(): Promise<void>;
};

export function ConfirmDialog({
  request,
  onClose,
}: {
  request?: ConfirmRequest;
  onClose(): void;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const submitting = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!request) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    setError("");
    setBusy(false);
    submitting.current = false;
    cancelRef.current?.focus();
    return () => previousFocus?.focus();
  }, [request]);
  useEffect(() => {
    if (!request) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !submitting.current) onClose();
      if (event.key === "Tab") {
        const buttons = Array.from(
          dialogRef.current?.querySelectorAll<HTMLButtonElement>(
            "button:not(:disabled)",
          ) || [],
        );
        if (!buttons.length) {
          event.preventDefault();
          return;
        }
        const first = buttons[0];
        const last = buttons[buttons.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [request, onClose]);
  const notes = request?.notes || [
    "只删除任务历史元数据，导出文件仍会保留。",
    "正在运行的任务和记录不会被清除。",
  ];
  return (
    <AnimatePresence initial={false}>
      {request && (
        <motion.div
          className="dialog-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !submitting.current)
              onClose();
          }}
        >
          <motion.section
            className="confirm-dialog"
            ref={dialogRef}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-dialog-title"
            aria-describedby="confirm-dialog-description"
            aria-busy={busy}
            initial={{ opacity: 0, scale: 0.98, y: 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 4 }}
            transition={{ type: "spring", duration: 0.3, bounce: 0 }}
          >
            <span className="confirm-dialog-icon">
              <AlertTriangle size={22} />
            </span>
            <div>
              <span className="eyebrow">谨慎操作</span>
              <h3 id="confirm-dialog-title">{request.title}</h3>
              {request.count != null && (
                <strong className="confirm-count">
                  {request.count.toLocaleString()} 条记录
                </strong>
              )}
              <p id="confirm-dialog-description">{request.description}</p>
              <ul>
                {notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
              {error && (
                <p className="error-text" role="alert">
                  {error}
                </p>
              )}
            </div>
            <footer>
              <button
                ref={cancelRef}
                className="secondary"
                disabled={busy}
                onClick={onClose}
              >
                取消
              </button>
              <button
                className="primary danger-solid"
                disabled={busy}
                onClick={async () => {
                  if (submitting.current) return;
                  submitting.current = true;
                  setBusy(true);
                  setError("");
                  try {
                    await request.onConfirm();
                    onClose();
                  } catch (failure) {
                    setError(
                      failure instanceof Error
                        ? failure.message
                        : String(failure),
                    );
                  } finally {
                    submitting.current = false;
                    setBusy(false);
                  }
                }}
              >
                {busy ? "正在处理…" : request.confirmLabel}
              </button>
            </footer>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
