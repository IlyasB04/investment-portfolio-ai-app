import { ChangeEvent, useRef, useState } from "react";
import client from "../api/client";
import styles from "./ImportModal.module.css";

interface ImportResult {
  imported: number;
  merged: number;
  row_errors: string[];
  total_holdings: number;
}

interface Props {
  onClose: () => void;
  onSuccess: () => void;
}

export default function ImportModal({ onClose, onSuccess }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleFile(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setResult(null);
    setError(null);
  }

  async function handleImport() {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);

    const form = new FormData();
    form.append("file", file);

    try {
      const res = await client.post<ImportResult>("/portfolio/import/", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(res.data);
    } catch (err: unknown) {
      if (
        typeof err === "object" &&
        err !== null &&
        "response" in err &&
        typeof (err as { response?: { data?: { error?: string } } }).response?.data?.error === "string"
      ) {
        setError((err as { response: { data: { error: string } } }).response.data.error);
      } else {
        setError("Import failed. Please check your file and try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  function handleDone() {
    onSuccess();
    onClose();
  }

  return (
    <div className={styles.overlay} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={styles.card} role="dialog" aria-modal="true">
        <div className={styles.cardHeader}>
          <h2 className={styles.title}>Import Portfolio</h2>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        <p className={styles.hint}>
          Upload a CSV file with columns: <code>ticker</code>, <code>quantity</code>, <code>average_cost</code>.
          Existing positions will be merged using weighted average cost.
        </p>

        <div
          className={`${styles.dropzone} ${file ? styles.dropzoneActive : ""}`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const f = e.dataTransfer.files?.[0];
            if (f) { setFile(f); setResult(null); setError(null); }
          }}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".csv"
            className={styles.fileInput}
            onChange={handleFile}
          />
          {file ? (
            <div className={styles.fileInfo}>
              <span className={styles.fileIcon}>📄</span>
              <span className={styles.fileName}>{file.name}</span>
              <span className={styles.fileSize}>{(file.size / 1024).toFixed(1)} KB</span>
            </div>
          ) : (
            <div className={styles.dropHint}>
              <span className={styles.dropIcon}>↑</span>
              <span>Click or drag a CSV file here</span>
            </div>
          )}
        </div>

        {error && <p className={styles.error}>{error}</p>}

        {result && (
          <div className={styles.result}>
            <div className={styles.resultStats}>
              <div className={styles.statItem}>
                <span className={styles.statNum}>{result.imported}</span>
                <span className={styles.statLabel}>New positions</span>
              </div>
              <div className={styles.statItem}>
                <span className={styles.statNum}>{result.merged}</span>
                <span className={styles.statLabel}>Merged</span>
              </div>
              <div className={styles.statItem}>
                <span className={styles.statNum}>{result.total_holdings}</span>
                <span className={styles.statLabel}>Total holdings</span>
              </div>
            </div>
            {result.row_errors.length > 0 && (
              <div className={styles.rowErrors}>
                <p className={styles.rowErrorsTitle}>Skipped rows:</p>
                {result.row_errors.map((e, i) => (
                  <p key={i} className={styles.rowError}>{e}</p>
                ))}
              </div>
            )}
          </div>
        )}

        <div className={styles.actions}>
          <button className={styles.cancelBtn} onClick={onClose} disabled={loading}>
            Cancel
          </button>
          {result ? (
            <button className={styles.doneBtn} onClick={handleDone}>
              Done
            </button>
          ) : (
            <button
              className={styles.importBtn}
              onClick={handleImport}
              disabled={!file || loading}
            >
              {loading ? "Importing…" : "Import"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
