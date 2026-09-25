import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ECHO Dashboard",
  description: "Employee Context & Handoff Orchestrator",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
