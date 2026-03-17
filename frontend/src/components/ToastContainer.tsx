import { useToast } from "../context/ToastContext";
import styles from "./ToastContainer.module.css";

export default function ToastContainer() {
  const { toasts, removeToast } = useToast();

  if (toasts.length === 0) return null;

  return (
    <div className={styles.container} aria-live="polite" aria-atomic="false">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`${styles.toast} ${styles[t.variant]}`}
          role="alert"
        >
          <span className={styles.icon}>
            {t.variant === "success" ? "✓" : t.variant === "error" ? "✕" : "ℹ"}
          </span>
          <span className={styles.message}>{t.message}</span>
          <button
            className={styles.close}
            onClick={() => removeToast(t.id)}
            aria-label="Dismiss"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
