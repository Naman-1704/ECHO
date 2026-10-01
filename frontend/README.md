# Frontend — Setup & Run Guide

A Next.js app (TypeScript + Tailwind) that talks to your FastAPI backend. No separate
database or service to run — this is just a web app.

## Design notes
This isn't styled as a generic SaaS dashboard on purpose. The whole product's value is
traceability — every fact the successor sees should be checkable against a real source
email — so the visual language treats the app like a case file: hairline dividers instead
of card shadows, a serif for headings (Source Serif 4) paired with a plain sans (IBM Plex
Sans) for UI text, and small numbered source markers (the same pattern in dashboard rows
and chat) that expand to show the original text a fact came from. Color is deliberately
muted (paper/ink/stone) so the two meaningful accent colors — oxblood for pending/unresolved,
green for verified/decided — actually mean something when they appear, instead of competing
with decorative color elsewhere.

## 1. Prerequisites
- Node.js 18.18+ (Next.js 14 requirement)
- The backend running locally at `http://localhost:8000` (see backend README)

## 2. Install and configure
```bash
npm install
cp .env.local.example .env.local
```
`NEXT_PUBLIC_API_BASE_URL` in `.env.local` already defaults to `http://localhost:8000` —
only change it if your backend runs somewhere else.

## 3. Run it
```bash
npm run dev
```
Visit `http://localhost:3000`. You'll land on the sign-in page, which redirects to your
backend's `/auth/login` (Google OAuth) — after consent, the backend redirects back here
with a session token, which gets captured and stored automatically.

## What's built
| Route | What it does |
|---|---|
| `/` | Landing + "Sign in with Google" |
| `/dashboard` | Overview: stats, pending action items, recent decisions, a "Sync inbox" button that calls `/ingestion/sync` |
| `/dashboard/projects` | Every project extracted, most-referenced first |
| `/dashboard/people` | Every person extracted, most-mentioned first |
| `/chat` | Ask questions, grounded answers with clickable numbered source citations |

## How auth actually flows
1. `/` links straight to the backend's `/auth/login` (no frontend-side OAuth logic needed —
   the backend owns the whole Google OAuth exchange).
2. Backend redirects back to `/dashboard?token=...` after consent.
3. `lib/auth.tsx` captures that token on mount, stores it in `localStorage`, and strips it
   from the visible URL.
4. Every API call in `lib/api-client.ts` sends it as `Authorization: Bearer <token>`.

This matches what the backend README already flags: token-in-URL then localStorage is fine
for an MVP running locally, but swap for an httpOnly cookie before this touches real data —
that's a backend-side change (how `/auth/callback` responds), not a frontend one.

## Verified before handing this to you
I actually ran `npx tsc --noEmit` (clean, no type errors) and `npm run build` (clean
production build, all 5 routes compile and generate) against this exact code — not just
written it. The only build failure I hit was Next.js trying to fetch Google Fonts from a
network-restricted sandbox, which isn't a code issue and won't happen on your machine.

## Where this needs M3/design polish next
- No loading skeletons yet — loading states are a plain "Loading…" line. Fine for now,
  worth upgrading before a demo.
- The timeline view from the original directory structure isn't built yet — the backend's
  `/dashboard/summary` doesn't return date-ordered data yet either, so that's a two-sided
  addition (a `raw_item.item_date` sort + a new timeline component).
- No responsive/mobile layout pass — the sidebar is fixed-width and will look cramped
  under ~768px. Not a blocker for a desktop-first internal tool, but worth flagging.
