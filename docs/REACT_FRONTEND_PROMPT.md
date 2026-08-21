# Copy-paste prompt: build the standalone TradingAgents React frontend

Use the complete prompt below inside the **new, empty frontend repository**. It
is intentionally self-contained because the Python repository no longer ships
the legacy HTML/CSS/JavaScript application.

---

## Role and objective

You are a senior frontend engineer and UI systems designer. Build a complete,
production-quality **React + Vite + TypeScript** frontend for the TradingAgents
backend. Do not merely write a plan: create every source file, configuration,
test, and README needed to install and run it.

The result must reproduce the existing TradingAgents Bloomberg-terminal-style
workstation as closely as possible in layout, density, colors, typography,
copy, interaction, responsive behavior, authentication, reports, and final
decision rendering. It must not look like a generic SaaS dashboard.

The backend is a separate local project and process:

- Backend repository: `W:\AI\Agent\TradingAgents`
- Backend API: `http://127.0.0.1:8000`
- Frontend dev server: `http://localhost:5173`
- API environment variable: `VITE_TRADINGAGENTS_API_URL=http://127.0.0.1:8000`
- The backend already allows the exact local Vite origins through CORS.
- Never modify, embed, copy, or launch the Python backend from this repository.
- Never access Firestore directly. All application data goes through the API.

If the frontend repository is elsewhere, keep the API URL configurable rather
than hardcoding filesystem locations. The only asset to copy from the backend
is `W:\AI\Agent\TradingAgents\assets\logo.png`; place it at
`public/logo.png`. If that path is unavailable, stop and ask for the logo
instead of inventing a replacement.

## Non-negotiable requirements

1. Use React, TypeScript in strict mode, and Vite.
2. Use the npm Firebase modular SDK for Authentication only.
3. Implement Google popup login and existing email/password login. There is no
   registration, sign-up link, account creation call, or password-reset UI.
4. Verify the Firebase ID token with the Python backend before revealing the
   workstation.
5. Send `Authorization: Bearer <Firebase ID token>` on every protected request.
6. Consume `/api/options`; do not hardcode providers, models, analysts,
   languages, research depths, defaults, or storage state into form logic.
7. Poll active runs, display events/reports/final decision, and implement daily
   history with the contracts below.
8. Preserve the exact dense dark terminal design. No Tailwind, Bootstrap,
   Material UI, Chakra, Ant, shadcn, or generic component theme.
9. Use semantic HTML and accessible keyboard behavior.
10. Never use `dangerouslySetInnerHTML`, `innerHTML`, `eval`, raw-HTML Markdown
    plugins, or remotely loaded Markdown images.
11. LLM output and API error strings are untrusted input.
12. Do not put Firebase service-account JSON, Gemini keys, Ollama credentials,
    or any server secret in this project. The Firebase Web config returned by
    `/api/auth/config` is public client configuration and is the only Firebase
    config the app needs.
13. Keep the frontend and backend independently runnable and independently
    testable.

## Required stack and scripts

Use stable current releases compatible with the installed Node LTS:

- `react`, `react-dom`
- `firebase`
- either a carefully restricted `react-markdown` + `remark-gfm` integration or
  a small DOM-safe Markdown subset implemented in TypeScript; raw HTML must
  never be enabled
- `vite`, `typescript`, `@vitejs/plugin-react`
- ESLint with React/TypeScript rules
- Vitest, React Testing Library, `@testing-library/user-event`, MSW
- Playwright for desktop/mobile visual and end-to-end checks

Provide these scripts:

```json
{
  "dev": "vite",
  "build": "tsc -b && vite build",
  "preview": "vite preview",
  "lint": "eslint .",
  "test": "vitest run",
  "test:watch": "vitest",
  "test:e2e": "playwright test"
}
```

Create `.env.example`:

```dotenv
VITE_TRADINGAGENTS_API_URL=http://127.0.0.1:8000
```

Validate and normalize the URL once at startup: it must be an absolute HTTP(S)
URL with no username/password/query/fragment. Remove one trailing slash. Show a
clear setup screen if it is invalid.

## Suggested source structure

Use small components and hooks with an organization close to:

```text
src/
  app/App.tsx
  app/AppProviders.tsx
  auth/AuthProvider.tsx
  auth/LoginPage.tsx
  auth/firebase.ts
  api/client.ts
  api/types.ts
  api/errors.ts
  hooks/useOptions.ts
  hooks/useRunPolling.ts
  hooks/useHistory.ts
  hooks/usePersistedSettings.ts
  hooks/useTextScale.ts
  components/TerminalHeader.tsx
  components/TickerRibbon.tsx
  components/AnalysisControl.tsx
  components/IntelligenceDesk.tsx
  components/LiveWire.tsx
  components/AgentMatrix.tsx
  components/Reports.tsx
  components/FinalDecision.tsx
  components/DailyHistory.tsx
  components/SafeMarkdown.tsx
  components/TerminalFooter.tsx
  components/ToastProvider.tsx
  styles/tokens.css
  styles/global.css
  styles/auth.css
  styles/workstation.css
  styles/markdown.css
  test/
```

Names may differ, but do not put the whole application in one component.

## Backend API contract

Create exact TypeScript interfaces for these responses. Preserve unknown fields
with safe optional types because backend run payloads can grow over time.

### Public endpoints

`GET /`

```json
{
  "service": "tradingagents-api",
  "status": "ok",
  "health": "/api/health",
  "docs": "/api/docs",
  "message": "The frontend is a separate application; this process serves the backend API only."
}
```

`GET /api/health`

```ts
interface HealthResponse {
  status: "ok" | "degraded";
  service: "tradingagents-api" | string;
  version: string;
  storage: StorageInfo;
  active_runs: number;
}
```

`GET /api/auth/config`

```ts
interface AuthConfigResponse {
  required: boolean;
  configured: boolean;
  firebase: {
    apiKey: string;
    authDomain: string;
    projectId: string;
    appId: string;
    messagingSenderId?: string;
    storageBucket?: string;
    measurementId?: string;
  } | Record<string, never>;
  missing: string[];
  access_restricted: boolean;
}
```

These endpoints are intentionally public. Do not mistake the Firebase Web
configuration for a service-account secret.

### Protected endpoints

Except when `AuthConfigResponse.required === false`, send the Firebase bearer
token to all endpoints below.

`GET /api/auth/session`

```ts
interface SessionResponse {
  authenticated: true;
  user: {
    uid: string;
    email: string | null;
    name?: string | null;
    picture?: string | null;
    email_verified?: boolean;
    auth_disabled?: boolean;
  };
}
```

`GET /api/options`

```ts
interface OptionItem {
  id: string;
  label: string;
  custom?: boolean;
}

interface ThinkingControl {
  key: "thinking_level" | "reasoning_effort" | "anthropic_effort" | string;
  label: string;
  default?: string | null;
  options: OptionItem[];
}

interface ProviderOption {
  id: string;
  label: string;
  quick_models: OptionItem[];
  deep_models: OptionItem[];
  default_quick_model?: string;
  default_deep_model?: string;
  supports_backend_url: boolean;
  requires_backend_url: boolean;
  backend_url?: string | null;
  backend_urls?: OptionItem[];
  thinking_control?: ThinkingControl;
}

interface StorageInfo {
  mode: "firebase" | "local" | "unavailable" | string;
  backend: string;
  configured: boolean;
  message: string;
}

interface OptionsResponse {
  analysts: OptionItem[];
  research_depths: Array<{
    id: 1 | 3 | 5;
    label: string;
    description: string;
  }>;
  providers: ProviderOption[];
  output_languages: OptionItem[];
  languages: OptionItem[];
  defaults: {
    ticker: string;
    analysis_date: string;
    output_language: string;
    analysts: string[];
    research_depth: 1 | 3 | 5;
    llm_provider: string;
    quick_model: string;
    deep_model: string;
    backend_url: string | null;
    thinking_level?: "high" | "minimal" | null;
  };
  storage: StorageInfo;
}
```

Current options expose Google Gemini and `Llama 3.2 3B (Local / Ollama)`, whose
model ID is `tradingagents-llama3.2:16k`, but the UI must still hydrate them
dynamically from the response.

### Create and poll a run

`POST /api/runs` uses a JSON body with no API keys or other server credentials;
when authentication is enabled it still requires the Firebase Bearer header:

```ts
interface RunRequest {
  ticker: string;
  analysis_date: string; // YYYY-MM-DD
  output_language: string;
  analysts: Array<"market" | "social" | "news" | "fundamentals" | string>;
  research_depth: 1 | 3 | 5;
  llm_provider: string;
  quick_model: string;
  deep_model: string;
  backend_url?: string;
  thinking_level?: "high" | "minimal";
  reasoning_effort?: "low" | "medium" | "high";
  anthropic_effort?: "low" | "medium" | "high";
}
```

The response status is `202` and the body is a full run object. Do not expect
only an ID.

```ts
type RunStatus =
  | "queued" | "pending" | "running" | "processing" | "in_progress"
  | "completed" | "failed" | "error" | "cancelled" | "canceled"
  | string;

interface RunEvent {
  event_id?: string;
  id?: string;
  run_id?: string;
  created_at?: string;
  timestamp?: string;
  sequence?: number;
  agent?: string;
  type?: string;
  status?: string;
  message?: unknown;
  report_key?: string;
  content?: unknown;
  data?: unknown;
  [key: string]: unknown;
}

interface TradingRun {
  run_id: string; // 32 lowercase hex characters
  ticker: string;
  analysis_date: string;
  output_language?: string;
  analysts?: string[];
  research_depth?: 1 | 3 | 5;
  llm_provider?: string;
  quick_model?: string;
  deep_model?: string;
  asset_type?: string;
  status: RunStatus;
  progress?: number | { percent?: number; fraction?: number; value?: number };
  current_phase?: string | null;
  current_agent?: string | null;
  agent_status?: Record<string, string | { status?: string; state?: string }>;
  reports?: Record<string, unknown> | unknown[];
  decision?: unknown;
  final_decision?: unknown;
  final_trade_decision?: unknown;
  final_state?: Record<string, unknown>;
  result?: Record<string, unknown>;
  error?: unknown;
  created_at?: string;
  updated_at?: string;
  completed_at?: string;
  date_key?: string;
  events?: RunEvent[] | Record<string, RunEvent>;
  [key: string]: unknown;
}
```

Poll `GET /api/runs/{run_id}` every **1600 ms** until a terminal status.

### History

`GET /api/history?date=YYYY-MM-DD`

```ts
interface HistoryResponse {
  date: string | null;
  count: number;
  runs: TradingRun[];
}
```

`GET /api/history/{run_id}` returns the full `TradingRun`.

### API errors

Normalize all of these into readable messages:

- FastAPI string detail: `{ "detail": "message" }`
- validation detail array with `loc`, `msg`, `type`
- non-JSON response
- network failure
- `401`: invalidate auth state, sign out Firebase, show login
- `403`: show account-not-authorized state; do not reveal workspace data
- `422`: show form/API validation details near the form
- `429`: read exposed `Retry-After`, show queue-full message, do not auto-submit
- `503`: show safe configuration/storage/provider error

Use `AbortController` for stale options/history/poll requests. Never apply a
response after the selected run or history generation has changed.

## Authentication state machine

On startup:

1. Fetch `/api/auth/config` without a token.
2. If `required === false`, call `/api/auth/session` without a token and enter
   the workstation as local development.
3. If authentication is required but `configured === false`, show a polished
   `SETUP REQUIRED` state listing the safe environment variable names in
   `missing`. Never show a blank login form.
4. Initialize one Firebase app from the returned `firebase` object.
5. Set `browserLocalPersistence`.
6. Subscribe to `onAuthStateChanged`.
7. When a Firebase user exists, call `getIdToken(true)`, then verify it against
   `/api/auth/session` with a Bearer header.
8. Reveal the workstation only after the backend session succeeds.

Login methods:

- Google: `GoogleAuthProvider`, set `{ prompt: "select_account" }`, then
  `signInWithPopup`.
- Email/password: `signInWithEmailAndPassword`.
- Logout: Firebase `signOut`, clear protected in-memory state, return to login.
- Do not implement any create-user function.

Map common Firebase failures to friendly English messages without exposing raw
SDK objects: invalid credential, disabled user, too many attempts, popup
blocked/closed, network error, unauthorized domain, and configuration error.

## API client behavior

Build one typed client around `fetch`:

- Base URL comes from `VITE_TRADINGAGENTS_API_URL`.
- Always send `Accept: application/json`.
- Send `Content-Type: application/json` only when a body exists.
- Ask the auth provider for a fresh-enough ID token immediately before every
  protected request; do not save tokens in localStorage.
- Use `cache: "no-store"` for live polling and auth/session verification.
- Handle empty bodies safely.
- CORS uses exact origins; do not add `credentials: "include"` because the API
  uses a Bearer token rather than cookies.
- Do not retry POST automatically.
- Keep secrets out of logs, toasts, analytics, and persisted state.

## Page hierarchy and exact visible copy

This is a single conditional application shell, not a marketing site. Client
routing is optional and must not change the main UI.

### Login page

Before authentication, show only a full-screen login shell with subtle grid
texture and one terminal-style card.

- eyebrow: `SECURE MARKET INTELLIGENCE`
- brand: `TRADING` + orange `AGENTS`
- live status line initially: `INITIALIZING FIREBASE AUTH`
- panel code: `ACCESS // 01`
- heading: `Sign in to workstation`
- supporting copy: `Authentication is required before market analysis and Firestore history can be accessed.`
- Google button: `CONTINUE WITH GOOGLE`
- divider: `OR USE EMAIL`
- inputs: `Email address`, `Password`
- submit: `LOGIN TO TERMINAL` with a right arrow
- policy: `LOGIN ONLY · ACCOUNTS ARE MANAGED BY THE FIREBASE ADMINISTRATOR`

Do not show the workstation behind the login card. Disable controls while auth
is initializing or submitting. Use an assertive live error region.

### Authenticated workstation

Render in this order:

1. `TerminalHeader`
2. `TickerRibbon`
3. three-column `TerminalGrid`
4. `TerminalFooter`
5. global toast region

Header left:

- logo
- eyebrow `MULTI-AGENT MARKET INTELLIGENCE`
- `TRADINGAGENTS`, with `AGENTS` orange

Header system strip cells:

- Workstation: `WEB-01`
- Session: `INITIALIZING`, `READY`, `RUNNING`, or `OFFLINE`
- Data Store: Firebase/local/unavailable indicator and text
- Text Size slider and live percentage/base-pixel output
- Signed In email and `LOGOUT`
- local date, 24-hour clock with seconds, and local timezone abbreviation

Ticker ribbon:

- `TA SYSTEM`
- `MARKET MULTI-SOURCE`
- `RESEARCH AGENTIC`
- `RISK THREE-WAY DEBATE`
- right-aligned cyan `DATA IS FOR RESEARCH PURPOSES`

Main grid panels:

- left: `01 // INPUT` / `Analysis Control`
- center: `02 // INTELLIGENCE DESK` / `Live Analysis`
- right: `03 // ARCHIVE` / `Daily History`

Footer notice: `AI-GENERATED RESEARCH · VERIFY BEFORE TRADING`.

## Bloomberg visual system

Use CSS variables and plain authored CSS. Preserve these canonical tokens:

```css
:root {
  --text-scale: 1.1;
  --black: #030405;
  --canvas: #07090a;
  --surface: #0c0f11;
  --surface-2: #111518;
  --surface-3: #171c1f;
  --line: #293036;
  --line-soft: #1b2226;
  --text: #e5e8e8;
  --muted: #8b969c;
  --dim: #626c71;
  --orange: #ff9f1a;
  --orange-2: #ffc15a;
  --cyan: #2cd9e8;
  --green: #52de86;
  --red: #ff5d64;
  --yellow: #f1d44c;
  --blue: #62a7ff;
  --shadow: 0 18px 60px rgb(0 0 0 / 35%);
  --mono: "Cascadia Mono", "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  --sans: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
}
```

Visual rules:

- Minimum supported viewport width: 320 px.
- Nearly black grid-textured canvas.
- Dense square-corner panels, 1 px hairlines, 2–3 px orange/cyan state rules.
- Uppercase monospaced micro-labels with tight letter spacing.
- Orange is the command/accent color; cyan means live/data; green/red/yellow
  communicate market/status semantics.
- Main prose is readable near-white, never low-contrast dim gray.
- Avoid large rounded cards, gradients typical of consumer SaaS, glassmorphism,
  oversized hero text, pastel colors, and excessive whitespace.
- Round only status dots, slider thumb, spinner, and Google mark.
- Every explicit font size must use `calc(Npx * var(--text-scale))` or an
  equivalent scale-aware formula. Do not scale layout dimensions globally.
- Provide visible 2 px focus rings and never remove focus outlines.
- Respect `prefers-reduced-motion`.

Desktop grid above 1180 px:

```css
grid-template-columns: minmax(270px, 310px) minmax(500px, 1fr) minmax(245px, 290px);
gap: 7px;
padding: 7px;
```

At viewport width >=1081 px and height >=720 px, target main-grid height:
`calc(100vh - 129px)` so the terminal fills the viewport and panels scroll
internally.

Responsive behavior:

- `<=1180px`: use 285 px + flexible center; History spans the full row and its
  run list becomes a responsive card grid.
- `<=1080px`: terminal header wraps; system strip occupies full width.
- `<=860px`: stack panels; center panel height about 680 px; history between
  300 and 520 px depending on viewport.
- `<=580px`: auth padding 16 px; hide Workstation and Session cells; storage,
  account, and clock form thirds; Text Size occupies the next full row; all
  two-column form fields become one column; Live view stacks Agent Matrix above
  Response Wire; phase items become two columns; tabs share equal width and
  hide `F1/F2/F3` labels; report/decision padding reduces to 12 px; footer
  shortcut list hides.
- At 390x844 and 160% text scale there must be no document-level horizontal
  overflow. Tables and code blocks scroll inside their own containers.

## Text-size slider

Exact behavior:

- min 85, max 160, step 5, default 110
- localStorage key: `tradingagents.web.textScale.v1`
- CSS variable: `--text-scale = value / 100`
- output text: `110% / 14.3px`, where base is 13 px
- update `aria-valuetext`
- visually fill the range track using `--range-progress`
- initialize the CSS variable in a tiny script in `index.html` before the main
  stylesheet loads, catching storage errors, to prevent a font-size flash

## Analysis Control form

Hydrate from `/api/options`, merge saved values only when still valid, and save
non-secret settings under `tradingagents.web.settings.v1`.

Sections:

1. `INSTRUMENT`
   - ticker/symbol with `$` prefix
   - as-of date
2. `RESEARCH PARAMETERS`
   - output language, including dynamic custom-language input
   - research depth
   - analyst checkboxes, at least one
3. `MODEL ROUTING`
   - provider
   - quick and deep model
   - dynamic custom model inputs
   - optional/required backend URL if the provider advertises it
   - dynamic thinking-control label/options/payload key

Validation parity:

- Uppercase ticker as the user types without moving the caret unexpectedly.
- Max length 32.
- Accepted ticker form:
  `^(?:[A-Z0-9._^=\-]{1,32}|[A-Z0-9._^=\-]{1,31}\+)$`.
- Date is local `YYYY-MM-DD`, required, and cannot exceed today.
- Select one or more unique analysts.
- Crypto suffixes `-USD`, `-USDT`, `-USDC`, `-BTC`, `-ETH` disable and uncheck
  Fundamentals. Remember its previous selection and restore it when returning
  to an equity symbol.
- If language/model option ID is `custom`, send the actual custom value, never
  the literal word `custom`.
- Backend URL, when present, is absolute HTTP(S), with no credentials, query,
  or fragment.
- Remove provider-specific controls from the payload when switching provider.
- Never accept API keys in this form.

Launch button:

- key block `GO`
- title `Run Intelligence Cycle`
- dynamic subtitle
- right chevron
- disabled while config is loading, invalid, submitting, or another run is
  active
- `Ctrl+Enter` submits from anywhere in the authenticated workstation
- display inline form error and toast on failure

## Intelligence Desk

Header includes selected ticker/date, run state dot/status, horizontal progress
bar, short run ID, phase, and rounded numeric percentage.

Tabs are a semantic ARIA tablist:

- `F1 Live Wire`
- `F2 Reports`
- `F3 Decision`

Support click, F1/F2/F3, ArrowLeft/ArrowRight, Home/End, roving tabindex, and
correct `aria-selected`, `aria-controls`, and panel `hidden` state.

### F1 Live Wire

Split desktop panel into:

- Agent Matrix rail
- Response Wire

Agent order comes from `agent_status`. Backend names include selected analyst
nodes plus Bull Researcher, Bear Researcher, Research Manager, Trader,
Aggressive Analyst, Conservative Analyst, Neutral Analyst, and Portfolio
Manager. Do not hardcode this as the only possible list.

Normalize common statuses for display while retaining unknown values:

- active: queued/pending/running/processing/in_progress
- completed aliases: done/success/succeeded/complete
- failed aliases: failure/errored
- cancelled/canceled

Events:

- normalize event object/string variants defensively
- show time, agent/source, and message
- cap visual feed to the newest 500 events
- use text nodes/React escaping, never Markdown or HTML in the live wire
- show an error banner when the run contains an error
- auto-scroll while the run is active or when the user was within 80 px of the
  bottom; do not yank a user who scrolled upward to read
- use an ARIA live region without making every polling render overly verbose

Empty states must distinguish standby, initializing, and archived runs with no
events.

### F2 Reports

Collect and de-duplicate reports using `(label + NUL + content)` from:

- canonical `run.reports` object or array
- result reports
- `market_report`, `sentiment_report`, `news_report`, `fundamentals_report`
- `trader_investment_plan`
- investment debate `bull_history`, `bear_history`, `judge_decision`
- risk debate `aggressive_history`, `conservative_history`, `neutral_history`

Use native `<details>` report cards. On a changed report set, open only the
newest card. Each summary shows the humanized label and word count. Memoize by
`run_id + raw report content` so an unchanged polling response does not rebuild
the DOM, close accordions, or reset scroll.

`COPY ALL` writes raw text in this exact structure:

```text
UPPERCASE LABEL
raw markdown content

------------------------------------------------------------

NEXT LABEL
raw markdown content
```

### F3 Final Decision

Combine the short signal from `decision`/`final_decision` with the full
narrative, preferring `reports.final_trade_decision`, then top-level/result/
final-state decision fields, then risk judge decision.

Display:

- toolbar `PORTFOLIO DESK` / `Final Trading Decision`
- hero label `PORTFOLIO MANAGER VERDICT`
- action headline
- `FINAL` badge
- up to 12 other scalar structured fields in a definition-list grid
- full narrative through the same safe Markdown renderer as reports

Signal colors:

- BUY / STRONG BUY / OVERWEIGHT / BULLISH / UPSIDE: green
- SELL / STRONG SELL / UNDERWEIGHT / BEARISH / DOWNSIDE: red
- HOLD / NEUTRAL: yellow

Memoize decision rendering by `run_id + raw decision text`. `COPY` must preserve
the original raw decision representation rather than rendered DOM text.

## Safe Markdown renderer

Render Reports and Final Decision with one shared, memoized component.

Supported subset:

- ATX headings `#` through `######`
- paragraphs
- strong, emphasis, strike-through, inline code
- fenced code with safe language label
- unordered and ordered lists, including wrapped item continuation
- blockquotes
- horizontal rules
- pipe tables with alignment
- links

Security requirements:

- no `dangerouslySetInnerHTML`
- do not enable raw HTML parsing
- raw `<script>`, `<img onerror>`, SVG, iframe, form, style, and other HTML is
  displayed harmlessly as literal text or ignored; it is never mounted
- never render Markdown images or trigger remote image requests
- links only for exact `http:` or `https:` URLs
- reject URLs with username/password
- reject javascript/data/vbscript/file, relative, and protocol-relative URLs
- valid links use `target="_blank"` and
  `rel="noopener noreferrer nofollow"`
- code contents always remain text
- tables are wrapped in an internally scrollable, keyboard-focusable element
  with `aria-label="Scrollable analysis table"`

Financial signal tokens outside code blocks become compact bordered color
chips. Generic bold text remains near-white so reports do not become an orange
wall.

Protect the main thread from adversarial or malformed 200k-character agent
output. Preserve these budgets or stricter equivalents:

- 1000 blocks
- 1000 styled inline tokens
- 500 list items
- 1200 table cells
- 24 table columns
- 512-character link label
- 2048-character URL

When a budget is exhausted, show the remaining source as one literal
preformatted block rather than silently dropping it. Avoid regexes with
quadratic behavior on tens of thousands of unmatched `[` or `*` characters.

Typography inside Markdown:

- prose: sans, readable near-white, 12 px base times text scale, line height
  about 1.72
- headings: mono; H1 18, H2 16, H3 14, H4 13 px times text scale
- H1 orange with rule; H2 cyan; lower headings cyan/blue
- blockquote cyan left rule and subtle cyan background
- code dark inset with green/orange terminal accent
- table header orange, alternating nearly-black rows
- internal code/table horizontal scrolling, never page overflow

## Daily History

Controls:

- previous day
- date input
- next day (disabled past today)
- `TODAY`
- refresh button
- run count and localized date label

The date is based on the browser’s local calendar and is never in the future.
Fetch the selected day with a generation guard. Render archived run cards with
ticker, status, date/time, short run ID, provider/model or phase summary, and
active selection using `aria-current`.

Rules:

- Do not allow opening another archived run while a different run is active.
- Loading an archived terminal run renders all persisted events/reports/
  decision.
- Loading an archived nonterminal run locks launch and resumes polling it.
- Refresh the selected history day when a run reaches terminal state.

## Polling and concurrency

After successful POST:

1. store the full returned run
2. lock launch/history conflict actions
3. render immediately
4. poll every 1600 ms

Use a monotonically increasing generation ID and selected run ID. Ignore every
stale response. On poll network failure, retry with approximately
`min(10 seconds, 2.5 seconds + failureCount * 1 second)`. Toast the first and
every fifth consecutive failure, then reset the counter after success. Stop on
completed/failed/error/cancelled/canceled.

Clean timers and abort controllers on logout and unmount. React StrictMode must
not create duplicate poll loops or duplicate POSTs.

## Storage status

Use `options.storage` and health storage data:

- Firestore configured: green/online indicator, `FIREBASE`
- local fallback: orange/local indicator, `LOCAL`, display backend message
- unavailable: red/error indicator

Do not connect to Firestore from the browser. All authenticated users currently
see the backend’s shared run history; do not pretend history is user-private.

## Accessibility and UX

- Include a skip link to the workspace after login.
- Use labels for every input and fieldset/legend for analysts.
- Use `aria-live` intentionally for auth, toasts, live wire, and status without
  duplicating speech on each poll.
- Support full keyboard operation and visible focus.
- Use native buttons, inputs, selects, details/summary, table semantics, and
  proper time elements.
- Announce copy success/failure through toast.
- Keep loading, empty, offline, configuration-error, API-error, and forbidden
  states visually complete.
- Track `online`/`offline` browser events for session display, but do not treat
  `navigator.onLine` as proof the API is reachable.
- Clock updates every second and uses a localized 24-hour format.
- Never rely on color alone; include labels/icons/borders/status text.

## Tests that must be created

### Unit/component tests with Vitest + Testing Library + MSW

Cover at minimum:

1. auth-required/configured, auth-disabled, setup-required, Google/email error,
   forbidden user, expired/401 session, and logout
2. bearer token on every protected API request and no token in localStorage
3. dynamic options hydration and stale saved-setting fallback
4. exact run POST payload, custom fields, crypto Fundamentals rule, and form
   validation
5. no duplicate POST on rapid submit/StrictMode
6. polling interval, retry backoff, terminal stop, stale response cancellation,
   and unmount cleanup
7. daily history navigation, active-run conflict, archived nonterminal resume
8. raw Copy All and Copy Decision output
9. unchanged polling content preserving report accordion and decision DOM/scroll
10. text scale persistence and clamping 85–160 in steps of 5
11. keyboard F1/F2/F3, tab arrows/Home/End, Ctrl+Enter

Markdown adversarial fixtures must include:

```text
<script>alert(1)</script>
<img src=x onerror=alert(1)>
<svg><a xlink:href="javascript:alert(1)">x</a></svg>
[bad](javascript:alert(1))
[bad](data:text/html,boom)
[bad](https://trusted.example@evil.example/path)
[good](https://example.com/research)
```

Assert no script/img/svg/iframe/form/style node or event-handler/style/src
attribute is created; only the valid HTTPS link is interactive with the exact
target/rel safety attributes. Add stress cases for 60,000 unmatched `[`, a
pipe-heavy table, huge signal repetition, malformed fences, Windows paths, and
headings containing `C#`.

### Playwright

Use deterministic MSW or a local mock layer and capture screenshots at:

- 1440x1000, 110% text
- 1024x900, 110% text
- 390x844, 110% text
- 390x844, 160% text

Cover login, idle workstation, active live wire, formatted reports, formatted
decision, and populated history. Assert:

- no document-level horizontal overflow
- tables/code scroll internally
- hero/badge/header/tabs do not collide
- slider applies before the main app paint and survives reload
- focus order and focus rings work
- reduced motion is respected

## README and operator instructions

Create a frontend README containing exact local startup steps.

Backend terminal:

```powershell
cd W:\AI\Agent\TradingAgents
conda activate tradingagents
python -m pip install -e ".[api]"
tradingagents-api
```

The backend `.env` must allow the actual frontend origin:

```dotenv
WEB_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Frontend terminal:

```powershell
npm install
Copy-Item .env.example .env.local
npm run dev
```

Open `http://localhost:5173`. Firebase Authentication Authorized Domains must
contain `localhost` for Google login. Do not add a port to Firebase’s domain
list.

Document how to run lint, tests, Playwright, production build, and preview.
Explain that both processes must remain running locally.

## Definition of done

Do not stop at scaffolding. The task is complete only when:

- the frontend starts independently on port 5173
- it communicates with the backend on port 8000
- Firebase login and auth-disabled development both work
- the authenticated Bloomberg workstation closely matches this specification
- run creation, polling, reports, decision, and daily history are functional
- Markdown is modern, colored, and adversarially safe
- desktop/mobile/160% layouts have no global overflow
- lint, TypeScript build, unit tests, and Playwright tests pass
- no backend or secret file was copied into the frontend repository
- the final response lists created files, commands run, test results, and any
  genuine remaining limitation

Do not replace missing implementation with TODOs, placeholders, mock-only UI,
or a prose plan. Implement and verify the working application.

---
