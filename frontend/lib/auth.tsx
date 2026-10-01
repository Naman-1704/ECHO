"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";

type AuthContextValue = {
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const STORAGE_KEY = "kt_session_token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // The backend's /auth/callback redirects to /dashboard?token=... after Google OAuth.
    // We capture it once here, persist it, then strip it out of the visible URL.
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get("token");

    if (urlToken) {
      localStorage.setItem(STORAGE_KEY, urlToken);
      setToken(urlToken);
      const cleanUrl = window.location.pathname;
      window.history.replaceState({}, "", cleanUrl);
    } else {
      const stored = localStorage.getItem(STORAGE_KEY);
      setToken(stored);
    }
    setIsLoading(false);
  }, []);

  const logout = () => {
    localStorage.removeItem(STORAGE_KEY);
    setToken(null);
    window.location.href = "/";
  };

  return (
    <AuthContext.Provider value={{ token, isAuthenticated: !!token, isLoading, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
