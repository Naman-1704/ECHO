"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { getLoginUrl } from "@/lib/api-client";
import { EchoWordmark } from "@/components/shared/EchoWordmark";

export default function LandingPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.replace("/dashboard");
    }
  }, [isLoading, isAuthenticated, router]);

  return (
    <main className="min-h-screen bg-paper flex flex-col">
      <div className="flex-1 flex items-center justify-center px-6 py-20">
        <div className="max-w-xl">
          <div className="mb-8">
            <EchoWordmark />
          </div>

          <p className="text-xs tracking-wide text-stone mb-1">
            Employee Context &amp; Handoff Orchestrator
          </p>

          <h1 className="font-serif text-2xl md:text-3xl text-ink leading-snug mt-6 mb-6 max-w-md">
            Every decision your predecessor made, still traceable to its source.
          </h1>

          <p className="text-base text-stone leading-relaxed mb-10 max-w-md">
            Sign in with the Google account you've inherited access to. Echo reads the
            inbox and Drive, builds a record of who was involved in what and why, and
            lets you ask it directly — every answer points back to the email it came from.
          </p>

          <a
            href={getLoginUrl()}
            className="inline-flex items-center gap-3 px-5 py-3 bg-ink text-paper text-sm rounded-sm hover:bg-ink/90 transition-colors"
          >
            Sign in with Google
          </a>

          <p className="text-xs text-stone-light mt-6 max-w-md leading-relaxed">
            Personal and HR-flagged content is filtered out before anything is read or stored.
          </p>
        </div>
      </div>

      <footer className="px-6 py-6 border-t border-line">
        <p className="text-xs text-stone-light text-center">Echo — a record for whoever comes next</p>
      </footer>
    </main>
  );
}
