import { createContext, useContext, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

const TOKEN_KEY = "token";

interface AuthContextValue {
  token: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem(TOKEN_KEY)
  );
  const navigate = useNavigate();

  async function login(username: string, password: string): Promise<void> {
    const res = await axios.post<{ access: string; refresh: string }>(
      "/api/auth/token/",
      { username, password }
    );
    const access = res.data.access;
    if (!access) throw new Error("No access token in response");
    // Store in localStorage so the API client interceptor picks it up immediately.
    localStorage.setItem(TOKEN_KEY, access);
    // Also set on the raw axios default so any non-client calls are covered.
    axios.defaults.headers.common["Authorization"] = `Bearer ${access}`;
    setToken(access);
    navigate("/overview");
  }

  function logout(): void {
    localStorage.removeItem(TOKEN_KEY);
    delete axios.defaults.headers.common["Authorization"];
    setToken(null);
    navigate("/login");
  }

  return (
    <AuthContext.Provider
      value={{ token, isAuthenticated: !!token, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
