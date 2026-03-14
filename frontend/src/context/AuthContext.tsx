import { createContext, useContext, useState, ReactNode } from "react";
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
    localStorage.setItem(TOKEN_KEY, access);
    setToken(access);
    navigate("/dashboard");
  }

  function logout(): void {
    localStorage.removeItem(TOKEN_KEY);
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
