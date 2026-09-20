import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";
import { useWorkbench } from "../store";

export function ErrorBanner() {
  const { error, clearError } = useWorkbench();
  return (
    <AnimatePresence>
      {error && (
        <motion.div
          className="error-banner"
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          role="alert"
        >
          <span>{error}</span>
          <button onClick={clearError} aria-label="关闭错误">
            <X size={16} />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
