import { ChangeEvent, useRef, useState } from "react";
import client from "../api/client";
import styles from "./ImportPage.module.css";

interface PreviewRow {
  ticker: string;
  quantity: string;
  average_cost: string;
  [key: string]: string;
}

interface ImportResult {
  imported: number;
  merged: number;
  row_errors: string[];
  total_holdings: number;
}

function parseCSV(text: string): { rows: PreviewRow[]; parseErrors: string[] } {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return { rows: [], parseErrors: ["File has no data rows."] };

  const raw = lines[0].split(",").map((h) => h.trim().replace(/^"|"$/g, "").toLowerCase());
  const required = ["ticker", "quantity", "average_cost"];
  const missing = required.filter((r) => !raw.includes(r));
  if (missing.length > 0) {
    return { rows: [], parseErrors: [`Missing required columns: ${missing.join(", ")}`] };
  }

  const rows: PreviewRow[] = [];
  const parseErrors: string[] = [];

  lines.slice(1).forEach((line, i) => {
    if (!line.trim()) return;
    const vals = line.split(",").map((v) => v.trim().replace(/^"|"$/g, ""));
    const row = Object.fromEntries(raw.map((h, j) => [h, vals[j] ?? ""])) as PreviewRow;
    if (!row.ticker) { parseErrors.push(`Row ${i + 2}: empty ticker`); return; }
    if (isNaN(parseFloat(row.quantity)) || parseFloat(row.quantity) <= 0) {
      parseErrors.push(`Row ${i + 2}: invalid quantity`); return;
    }
    if (isNaN(parseFloat(row.average_cost)) || parseFloat(row.average_cost) <= 0) {
      parseErrors.push(`Row ${i + 2}: invalid average_cost`); return;
    }
    rows.push(row);
  });

  return { rows, parseErrors };
}

const EXAMPLE_CSV = `ticker,quantity,average_cost
AAPL,10,175.50
MSFT,5,380.00
NVDA,3,820.00`;

export default function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewRow[] | null>(null);
  const [parseErrors, setParseErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function processFile(f: File) {
    setFile(f);
    setResult(null);
    setUploadError(null);
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = (e.target?.result as string) ?? "";
      const { rows, parseErrors: errs } = parseCSV(text);
      setPreview(rows);
      setParseErrors(errs);
    };
    reader.readAsText(f);
  }

  function handleFile(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) processFile(f);
  }

  async function handleImport() {
    if (!file) return;
    setLoading(true);
    setUploadError(null);

    const form = new FormData();
    form.append("file", file);

    try {
      const res = await client.post<ImportResult>("/portfolio/import/", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(res.data);
      setPreview(null);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { error?: string } } };
      setUploadError(e?.response?.data?.error ?? "Import failed. Please check your file.");
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setFile(null);
    setPreview(null);
    setParseErrors([]);
    setResult(null);
    setUploadError(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  const canImport = !!file && (preview?.length ?? 0) > 0 && parseErrors.length === 0;

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Import Portfolio</h1>
          <p className={styles.pageSubtitle}>Upload a CSV file to bulk-add or merge positions</p>
        </div>
      </div>

      <div className={styles.layout}>
        {/* ── Left: upload zone ── */}
        <div className={styles.leftCol}>
          <div className={styles.card}>
            <h2 className={styles.cardTitle}>Upload File</h2>

            {!result ? (
              <>
                <div
                  className={`${styles.dropzone} ${file ? styles.dropzoneHasFile : ""}`}
                  onClick={() => inputRef.current?.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    const f = e.dataTransfer.files?.[0];
                    if (f) processFile(f);
                  }}
                >
                  <input ref={inputRef} type="file" accept=".csv" className={styles.fileInput} onChange={handleFile} />
                  {file ? (
                    <div className={styles.fileInfo}>
                      <span className={styles.fileIcon}>📄</span>
                      <div>
                        <p className={styles.fileName}>{file.name}</p>
                        <p className={styles.fileSize}>{(file.size / 1024).toFixed(1)} KB</p>
                      </div>
                    </div>
                  ) : (
                    <div className={styles.dropHint}>
                      <div className={styles.dropIconWrap}>↑</div>
                      <p className={styles.dropText}>Click or drag a CSV file here</p>
                      <p className={styles.dropSub}>Supports UTF-8 encoded .csv files</p>
                    </div>
                  )}
                </div>

                {uploadError && <p className={styles.error}>{uploadError}</p>}

                {parseErrors.length > 0 && (
                  <div className={styles.warningBlock}>
                    <p className={styles.warningTitle}>⚠ Parse warnings ({parseErrors.length} rows skipped)</p>
                    {parseErrors.map((e, i) => <p key={i} className={styles.warningLine}>{e}</p>)}
                  </div>
                )}

                <div className={styles.formActions}>
                  {file && (
                    <button className={styles.secondaryBtn} onClick={handleReset}>
                      Clear
                    </button>
                  )}
                  <button
                    className={styles.primaryBtn}
                    onClick={handleImport}
                    disabled={!canImport || loading}
                  >
                    {loading ? "Importing…" : `Import ${preview?.length ?? 0} rows`}
                  </button>
                </div>
              </>
            ) : (
              <div className={styles.resultBlock}>
                <div className={styles.resultStats}>
                  <div className={styles.statItem}>
                    <p className={styles.statNum}>{result.imported}</p>
                    <p className={styles.statLabel}>New positions</p>
                  </div>
                  <div className={styles.statItem}>
                    <p className={styles.statNum}>{result.merged}</p>
                    <p className={styles.statLabel}>Merged</p>
                  </div>
                  <div className={styles.statItem}>
                    <p className={styles.statNum}>{result.total_holdings}</p>
                    <p className={styles.statLabel}>Total holdings</p>
                  </div>
                </div>
                {result.row_errors.length > 0 && (
                  <div className={styles.warningBlock}>
                    <p className={styles.warningTitle}>⚠ Rows skipped</p>
                    {result.row_errors.map((e, i) => <p key={i} className={styles.warningLine}>{e}</p>)}
                  </div>
                )}
                <button className={styles.secondaryBtn} onClick={handleReset}>
                  Import another file
                </button>
              </div>
            )}
          </div>

          {/* Format guide */}
          <div className={styles.card}>
            <h2 className={styles.cardTitle}>Expected Format</h2>
            <p className={styles.guideText}>
              Your CSV must include these columns (in any order):
            </p>
            <div className={styles.colList}>
              <div className={styles.colItem}><code>ticker</code><span>Stock symbol (e.g. AAPL)</span></div>
              <div className={styles.colItem}><code>quantity</code><span>Number of shares</span></div>
              <div className={styles.colItem}><code>average_cost</code><span>Cost per share in USD</span></div>
            </div>
            <p className={styles.guideNote}>
              Existing positions with the same ticker will be merged using weighted average cost. Additional columns are ignored.
            </p>
            <div className={styles.exampleBlock}>
              <p className={styles.exampleLabel}>Example</p>
              <pre className={styles.exampleCode}>{EXAMPLE_CSV}</pre>
            </div>
          </div>
        </div>

        {/* ── Right: preview table ── */}
        <div className={styles.rightCol}>
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Preview</h2>
              {preview && <span className={styles.previewCount}>{preview.length} valid rows</span>}
            </div>

            {!preview && !result && (
              <div className={styles.previewEmpty}>
                <p>Upload a CSV to preview rows before importing</p>
              </div>
            )}

            {result && (
              <div className={styles.previewEmpty}>
                <span className={styles.successTick}>✓</span>
                <p>Import complete — <a className={styles.link} href="/portfolio">view portfolio</a></p>
              </div>
            )}

            {preview && preview.length > 0 && (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Ticker</th>
                      <th className={styles.right}>Quantity</th>
                      <th className={styles.right}>Avg Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.map((row, i) => (
                      <tr key={i}>
                        <td className={styles.rowNum}>{i + 1}</td>
                        <td className={styles.ticker}>{row.ticker.toUpperCase()}</td>
                        <td className={`${styles.right} ${styles.mono}`}>{row.quantity}</td>
                        <td className={`${styles.right} ${styles.mono}`}>${row.average_cost}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {preview && preview.length === 0 && (
              <p className={styles.previewError}>No valid rows found in this file.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
