"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { getSessionToken } from "../lib/session";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    if (getSessionToken()) {
      router.replace("/dashboard");
    }
  }, [router]);

  return (
    <main className="auth-shell">
      <div className="card hero-card">
        <div className="eyebrow">ECHO</div>
        <h1>Employee Context &amp; Handoff Orchestrator</h1>
        <p>
          Sign in with Google to sync your inbox, ground answers in your context, and keep
          knowledge transfer aligned with your team.
        </p>

        <a className="primary-button" href={`${API_BASE_URL}/auth/login`}>
          Continue with Google
        </a>
      </div>
    </main>
  );
}
