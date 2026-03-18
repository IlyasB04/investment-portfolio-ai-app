import { type FormEvent, useState } from "react";
import axios from "axios";
import { useAuth } from "../context/AuthContext";
import styles from "./Login.module.css";

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
    } catch (err) {
      if (axios.isAxiosError(err)) {
        const status = err.response?.status;
        console.error("[Login] API error", status, err.response?.data);
        if (status === 401) {
          setError("Incorrect username or password.");
        } else if (!err.response) {
          setError("Cannot reach server. Make sure the backend is running.");
        } else {
          setError(`Sign-in failed (${status ?? "unknown"}). Please try again.`);
        }
      } else {
        console.error("[Login] unexpected error", err);
        setError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.logo}>
            <svg viewBox="0 0 40 40" fill="none" width="48" height="48">
              <rect x="1" y="1" width="38" height="38" rx="10" fill="rgba(79,142,255,0.12)"/>
              <rect x="1" y="1" width="38" height="38" rx="10" stroke="rgba(79,142,255,0.35)" strokeWidth="1.5"/>
              <path d="M9 29L15 16L20 23L25 10L31 29" stroke="#4F8EFF" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
              <circle cx="31" cy="10" r="3" fill="#22D46A" opacity="0.9"/>
            </svg>
          </div>
          <h1 className={styles.title}>PortfolioAI</h1>
          <p className={styles.subtitle}>Sign in to your investment account</p>
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="username">
              Username
            </label>
            <input
              id="username"
              className={styles.input}
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="password">
              Password
            </label>
            <input
              id="password"
              className={styles.input}
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {error && <p className={styles.error}>{error}</p>}

          <button className={styles.button} type="submit" disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
