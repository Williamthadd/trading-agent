# Copy-paste prompt: build the standalone TradingAgents React frontend

Use everything below the horizontal rule as one self-contained implementation
prompt inside a **new, empty frontend repository**. The Python repository is an
API-only analysis engine; it does not provide authentication UI, history-read
endpoints, or frontend assets.

---

## Role and objective

You are a senior React, TypeScript, Firebase, Firestore Security Rules, testing,
accessibility, and UI-systems engineer. Build and verify a complete
production-quality **React + Vite + TypeScript** frontend. Do not merely provide
a plan or disconnected snippets: create every source file, configuration,
ruleset, test, asset integration, and README required to install and run it.

Reproduce the TradingAgents Bloomberg-terminal-style workstation as closely as
possible in layout, density, color, typography, copy, interaction, responsive
behavior, login, reports, and Final Trading Decision. It must not look like a
generic SaaS dashboard.

Use this architecture from the first commit:

```text
Firebase Authentication ----> React login and persisted session
Cloud Firestore -------------> Daily History, selected-run detail, live events,
                               reports, and Final Trading Decision
FastAPI TradingAgents -------> health, runtime options, and POST new analysis
Gemini/Ollama/agents --------> remain private behind FastAPI
```

The backend is a separate local project and process:

- Backend repository: `W:\AI\Agent\TradingAgents`
- Backend API: `http://127.0.0.1:8000`
- Frontend dev server: `http://localhost:5173`
- Never modify, embed, copy, or launch Python code from this repository.
- Login and Firestore history must work when FastAPI is stopped.
- FastAPI is required only for health/options and starting a new analysis.

The only asset to copy from the backend is
`W:\AI\Agent\TradingAgents\assets\logo.png`; place it at `public/logo.png`. If
that path is unavailable, stop and ask for the logo rather than inventing one.

## Scope and limitations

When FastAPI is offline, the signed-in user must still be able to browse every
authorized Firestore-backed run, event, report, and decision. Preserve the
complete workstation in a read-only `HISTORY ONLY` mode and disable only the
analysis-engine controls.

This does not make the application internet-independent. With FastAPI stopped,
the frontend cannot launch agents, invoke Gemini/Ollama, retrieve fresh runtime
options, read backend local-JSON fallback files, or repair a stale interrupted
run. Only documents already stored in Cloud Firestore are directly available.

The current schema has no `owner_uid`. History is shared among the small set of
Firebase UIDs explicitly approved through membership documents. Never label it
as private per-user history.

## Non-negotiable requirements

1. Use React, TypeScript strict mode, and Vite.
2. Use the modular Firebase Web SDK for both Authentication and read-only
   Firestore access.
3. Implement Google popup login and existing email/password login. Provide no
   registration, sign-up, create-user, anonymous-auth, or password-reset UI.
4. Initialize Firebase solely from public `VITE_FIREBASE_*` variables.
5. Login, logout, auth restoration, history, archived reports, and decisions
   must never depend on FastAPI.
6. Send a fresh Firebase ID token only to protected `GET /api/options` and
   `POST /api/runs`; the backend still authorizes analysis calls.
7. Read run documents and event subcollections directly through typed Firestore
   repositories and live listeners. Never poll FastAPI for run state.
8. Consume `/api/options`; never hardcode form providers, models, analysts,
   languages, depths, defaults, or storage state.
9. Preserve the exact dense dark terminal design. Do not use Tailwind,
   Bootstrap, Material UI, Chakra, Ant, shadcn, or another generic theme.
10. Use semantic HTML and fully accessible keyboard behavior.
11. Never use `dangerouslySetInnerHTML`, `innerHTML`, `eval`, raw-HTML Markdown
    plugins, or remotely loaded Markdown images.
12. Treat Firestore content, LLM output, and API error strings as untrusted.
13. Never place a Firebase service account, LLM key, Ollama credential, private
    key, or ID token in source, `VITE_*`, logs, analytics, or localStorage.
14. Keep frontend, backend, Firebase, and their tests independently runnable.

## Required stack and scripts

Use stable current releases compatible with the installed Node LTS:

- `react`, `react-dom`, `firebase`;
- either restricted `react-markdown` + `remark-gfm` or a small DOM-safe Markdown
  subset; never enable raw HTML;
- `vite`, `typescript`, `@vitejs/plugin-react`;
- ESLint with React/TypeScript rules;
- Vitest, React Testing Library, `@testing-library/user-event`, and MSW;
- `@firebase/rules-unit-testing` and pinned `firebase-tools` for rules tests;
- Playwright for desktop/mobile visual and end-to-end checks.

Provide at least these scripts, adapting only shell quoting for portability:

```json
{
  "dev": "vite",
  "build": "tsc -b && vite build",
  "preview": "vite preview",
  "lint": "eslint .",
  "test": "vitest run",
  "test:watch": "vitest",
  "test:e2e": "playwright test",
  "firebase:emulators": "firebase emulators:start --only firestore",
  "test:rules": "firebase emulators:exec --only firestore \"vitest run src/test/firestore.rules.test.ts\"",
  "firebase:deploy:rules": "firebase deploy --only firestore:rules"
}
```

If nested quoting is unreliable on Windows, add a small Node runner instead of
leaving a broken script.

## Environment contract

Create `.env.example`:

```dotenv
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=
VITE_FIREBASE_PROJECT_ID=
VITE_FIREBASE_APP_ID=

# This frontend contract intentionally supports the default Firestore database.
VITE_FIREBASE_DATABASE_ID=(default)

# Optional fields from the Firebase Web App config.
VITE_FIREBASE_MESSAGING_SENDER_ID=
VITE_FIREBASE_STORAGE_BUCKET=
VITE_FIREBASE_MEASUREMENT_ID=

# Needed only for health/options and launching a new analysis.
VITE_TRADINGAGENTS_API_URL=http://127.0.0.1:8000
```

Validate the four required Firebase values before initialization. If any are
missing, show a polished `FIREBASE SETUP REQUIRED` screen containing only the
missing variable names. Never print values. Web App config is public project
configuration; authorization still comes from Auth and Security Rules.

Fail fast unless `VITE_FIREBASE_DATABASE_ID` is exactly `(default)`. This
prompt deliberately standardizes both applications and Rules deployment on the
default Firestore database; do not silently connect to or deploy Rules for a
named database. Also document and verify this identity invariant before login
or deployment:

```text
VITE_FIREBASE_PROJECT_ID
  == backend FIREBASE_PROJECT_ID
  == project_id inside the backend service-account JSON
```

A mismatch means Auth/history can use one Firebase project while Bearer-token
verification and run persistence use another.

Validate the optional API URL once: require absolute HTTP(S), forbid
username/password/query/fragment, and remove one trailing slash. An invalid API
URL must not prevent Firebase login/history; treat only the analysis engine as
misconfigured.

Ensure `.env.local`, `.env.*.local`, emulator exports, Firebase debug logs,
service-account files, and secrets are ignored by Git.

Use these exact schema constants:

```ts
export const RUNS_COLLECTION = "trading_runs";
export const MEMBERS_COLLECTION = "tradingagents_members";
export const EVENTS_SUBCOLLECTION = "events";
```

Do not expose security-sensitive collection paths as runtime user settings.

## Suggested source structure

Use small cohesive modules close to:

```text
src/
  app/App.tsx
  app/AppProviders.tsx
  auth/AuthProvider.tsx
  auth/LoginPage.tsx
  firebase/client.ts
  firebase/schema.ts
  firebase/tradingHistoryRepository.ts
  api/client.ts
  api/types.ts
  api/errors.ts
  hooks/useOptions.ts
  hooks/useDailyHistory.ts
  hooks/useSelectedRun.ts
  hooks/useBackendAvailability.ts
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
firestore.rules
firestore.indexes.json
firebase.json
```

Names may differ, but do not put the entire application in one component and do
not let UI components construct Firestore paths or queries.

## Firebase initialization and authentication

Create one Firebase client module which validates config, initializes exactly
one app, initializes Auth, initializes the default Firestore database, and
exports typed singletons. Use modular imports and memory-only Firestore cache:

```ts
initializeFirestore(firebaseApp, {
  localCache: memoryLocalCache(),
});
```

Do not silently persist sensitive trading history in IndexedDB. Do not install
multiple-tab persistent cache unless it becomes a separate explicit opt-in
feature with shared-device warnings and tested logout cache clearing.

Authentication state machine:

1. Validate frontend Firebase config.
2. Set `browserLocalPersistence` before initiating a new sign-in.
3. Subscribe exactly once with `onAuthStateChanged`.
4. Signed out: show only the login page.
5. Signed in: verify history membership with a minimal authorized read such as
   a `limit(1)` query on `trading_runs`.
6. Read succeeds, including an empty result: enter the workstation and attach
   the selected-day listener.
7. `permission-denied`: show `FIRESTORE ACCESS DENIED`, display the safe UID and
   a Copy UID button, explain the required membership document, and retain
   Logout. Never flash history metadata.
8. Firebase unavailable: keep the identity, show a retryable data-layer state,
   and do not mislabel FastAPI as the cause.
9. Logout: unsubscribe all listeners first, clear protected memory, call
   Firebase `signOut`, and return to login.

Login methods:

- Google: `GoogleAuthProvider`, `{ prompt: "select_account" }`, then
  `signInWithPopup`;
- email/password: `signInWithEmailAndPassword`;
- no registration or anonymous auth.

Map Firebase errors to concise safe English UI messages. Never manually persist
raw ID tokens; Firebase owns its auth state.

## Backend API contract

The frontend may call exactly these three endpoints. It must never call an auth
bootstrap/session route, history route, or run-detail GET route; those routes do
not exist in the backend contract.

### Public health endpoint

`GET /api/health`

```ts
interface StorageInfo {
  mode: "firebase" | "local" | "local-json" | "unavailable" | string;
  backend: string;
  configured: boolean;
  message: string;
}

interface HealthResponse {
  status: "ok" | "degraded";
  service: "tradingagents-api" | string;
  version: string;
  storage: StorageInfo;
  active_runs: number;
}
```

### Protected runtime options

`GET /api/options` requires `Authorization: Bearer <fresh Firebase ID token>`.

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

The current backend exposes Google Gemini and Llama 3.2 through local Ollama,
but hydrate every option dynamically. Never freeze current model IDs into form
logic.

### Protected run creation

`POST /api/runs` requires a fresh Firebase Bearer token and contains no API key
or server credential:

```ts
interface RunRequest {
  ticker: string;
  analysis_date: string;
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

The response is `202` and contains at least `run_id`; tolerate additional run
fields. Never automatically retry POST and guard rapid submit/React StrictMode
so one user action creates exactly one run.

## Firestore schema and normalization

The Python backend writes:

```text
trading_runs/{run_id}
└── events/{event_id}
```

Use safe optional fields because payloads can evolve:

```ts
type RunStatus =
  | "queued" | "pending" | "running" | "processing" | "in_progress"
  | "completed" | "failed" | "error" | "cancelled" | "canceled"
  | string;

interface FirestoreRunEvent {
  event_id?: string;
  id?: string;
  run_id?: string;
  created_at?: unknown;
  timestamp?: unknown;
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

interface FirestoreTradingRun {
  ticker?: unknown;
  analysis_date?: unknown;
  output_language?: unknown;
  analysts?: unknown;
  research_depth?: unknown;
  llm_provider?: unknown;
  quick_model?: unknown;
  deep_model?: unknown;
  asset_type?: unknown;
  status?: unknown;
  progress?: unknown;
  current_phase?: unknown;
  current_agent?: unknown;
  agent_status?: unknown;
  decision?: unknown;
  final_decision?: unknown;
  final_trade_decision?: unknown;
  error?: unknown;
  created_at?: unknown;
  updated_at?: unknown;
  completed_at?: unknown;
  date_key?: unknown;
  [key: string]: unknown;
}

interface TradingRun {
  run_id: string;
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
  reports: Record<string, string>;
  decision?: unknown;
  final_decision?: unknown;
  final_trade_decision?: unknown;
  error?: unknown;
  created_at?: string;
  updated_at?: string;
  completed_at?: string;
  date_key?: string;
  events: FirestoreRunEvent[];
  [key: string]: unknown;
}
```

Always inject Firestore document IDs as canonical `run_id`/`event_id`; never
trust colliding payload fields. Recursively normalize Firestore `Timestamp`,
JavaScript `Date`, and ISO strings without mutating snapshots. Convert malformed
values to safe fallbacks instead of crashing or rendering raw objects.

## Direct Firestore history repository

Create one typed repository. Production code may import read/listen operations
such as `collection`, `doc`, `query`, `where`, `limit`, `getDocs`, `onSnapshot`,
and `Timestamp`; it must not import Firestore write primitives.

The repository should expose behavior equivalent to:

```ts
interface TradingHistoryRepository {
  verifyAccess(): Promise<void>;
  subscribeToDay(
    dateKey: string,
    onData: (runs: TradingRun[]) => void,
    onError: (error: unknown) => void,
  ): () => void;
  subscribeToRun(
    runId: string,
    onData: (run: TradingRun | null) => void,
    onError: (error: unknown) => void,
  ): () => void;
}
```

For Daily History, query only `trading_runs` with
`where("date_key", "==", selectedDate)`, then normalize and sort client-side by
`created_at` descending with deterministic run-ID tie-breaking. This avoids a
composite index. Use a generation guard so late callbacks from an old date/user
cannot update the current UI. A history card uses only run-document metadata;
never read every event subcollection for the sidebar.

For one selected run, attach exactly two listeners:

1. `trading_runs/{runId}`;
2. `trading_runs/{runId}/events`.

Merge snapshots only after schema normalization. Deduplicate events by document
ID, then sort numeric `sequence`, normalized timestamp, and event ID. Tear down
both listeners when the selection/user changes, on logout, and on unmount.

Run documents normally do not contain complete reports. Reconstruct them from
sorted events where `type === "report"`, `report_key` is a safe non-empty key,
and `content` normalizes to text. The last sorted event for each report key wins:

```ts
const reports: Record<string, string> = {};
for (const event of sortedEvents) {
  if (event.type === "report" && validReportKey(event.report_key)) {
    reports[event.report_key] = normalizeText(event.content);
  }
}
```

Feed the canonical run into Reports and Final Decision. The short decision comes
from the run document; the complete portfolio narrative normally comes from
`reports.final_trade_decision`.

## Active analysis and backend availability

Model backend availability independently from Firebase Auth and Firestore:

```ts
type AnalysisEngineState =
  | "checking"
  | "ready"
  | "offline"
  | "forbidden"
  | "storage-local"
  | "misconfigured";
```

After Firestore history is usable, probe health with a short timeout, then fetch
fresh options with a fresh ID token. Retry only on an explicit Retry action,
throttled window focus, or conservative backoff; never block login/history or
create toast spam.

Before Launch, require a fresh successful options response and
`options.storage.mode === "firebase"`. On submit:

1. validate the form against current options;
2. POST once with a fresh Bearer token;
3. take the returned `run_id` as the selected run;
4. attach the same run/event Firestore listeners used for archived runs;
5. render Firestore updates until a terminal state;
6. rely on the day listener to refresh history.

Allow a short propagation grace period after `202`. If the document never
appears, explain that the backend may have fallen back to local JSON; never
fabricate progress. If backend storage is local, keep existing Firestore history
available but disable Launch with:

`BACKEND STORAGE IS LOCAL · NEW RUNS WOULD NOT APPEAR IN FIRESTORE HISTORY`

While the selected run is non-terminal, probe only `/api/health` at a modest
interval such as 30 seconds; never poll it for run state. If
`health.storage.mode` changes from `firebase` to `local`, stop presenting the
Firestore snapshot as live progress and show:

`RUN STORAGE DISCONNECTED · THE BACKEND FELL BACK TO LOCAL JSON`

Explain that the analysis may still be executing but its remaining local-only
updates cannot be displayed through the current API contract. Keep the last
confirmed Firestore data visible, disable another Launch, offer a health Retry,
and do not fabricate a terminal status. This covers a mid-run Firestore write
failure, not only a run document that never appears.

Expected state behavior:

- backend ready + Firestore ready: normal `READY` workstation;
- backend offline + Firestore ready: `HISTORY ONLY`, with
  `ANALYSIS ENGINE OFFLINE · LOGIN AND FIRESTORE HISTORY REMAIN AVAILABLE`;
- backend `403`: `ANALYSIS ACCESS DENIED`, while history/logout remain usable;
- backend `401`: refresh the token once and retry the analysis call once; if it
  still fails, show an analysis-session error without clearing Firestore state;
- Firestore denied/unavailable: a distinct data-layer error, never "backend
  offline".

Do not use `navigator.onLine` as proof of either service. Cache only validated
options and non-secret form preferences. Cached options must never enable Launch
while the backend is offline.

## API client and errors

Build one typed fetch client used only by health, options, and run creation:

- always send `Accept: application/json`;
- send `Content-Type: application/json` only for POST;
- obtain a fresh-enough token immediately before options/POST and never persist
  it yourself;
- use `cache: "no-store"` for health/options;
- do not use cookie credentials and never retry POST automatically;
- normalize FastAPI string/array validation errors, non-JSON responses, aborts,
  network errors, `401`, `403`, `422`, `429` with `Retry-After`, and `503`;
- never sign the user out solely because an analysis API call failed;
- keep raw exceptions, secrets, tokens, and response payloads out of logs.

Add a static test or explicit fetch-mock assertion proving production code never
calls removed backend surfaces: any `/api/auth/` path, any `/api/history` path,
or any GET run-detail path.

## Firestore Security Rules and Firebase files

Create `firestore.rules` with this exact read-only membership policy:

```javascript
rules_version = '2';

service cloud.firestore {
  match /databases/{database}/documents {
    function canReadTradingHistory() {
      return request.auth != null
        && exists(
          /databases/$(database)/documents/tradingagents_members/$(request.auth.uid)
        );
    }

    match /tradingagents_members/{memberUid} {
      allow read, write: if false;
    }

    match /trading_runs/{runId} {
      allow get, list: if canReadTradingHistory();
      allow create, update, delete: if false;

      match /events/{eventId} {
        allow get, list: if canReadTradingHistory();
        allow create, update, delete: if false;
      }
    }

    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

Do not weaken this to `request.auth != null`; arbitrary Google sign-in can
create a valid Firebase user. Parent rules do not cascade to subcollections, so
keep the explicit event rule. The browser must never enumerate membership or
write runs/events. Python Admin SDK writes bypass client rules and remain
governed by IAM.

Create `firestore.indexes.json`:

```json
{
  "indexes": [],
  "fieldOverrides": []
}
```

Create `firebase.json` without unrelated services:

```json
{
  "firestore": {
    "rules": "firestore.rules",
    "indexes": "firestore.indexes.json"
  },
  "emulators": {
    "firestore": {
      "host": "127.0.0.1",
      "port": 8080
    },
    "ui": {
      "enabled": true,
      "host": "127.0.0.1",
      "port": 4000
    },
    "singleProjectMode": true
  }
}
```

Use one canonical deployed rules source. Document that deploying a conflicting
rules file from another repository can revoke or overexpose direct history.

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
- Session: `INITIALIZING`, `READY`, `RUNNING`, `HISTORY ONLY`, or `DATA ERROR`
- Data Store: Firestore ready/denied/unavailable indicator and text; show
  backend storage-local as a separate Launch warning
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
- use an ARIA live region without announcing every listener snapshot verbosely

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
`run_id + raw report content` so an unchanged Firestore snapshot does not rebuild
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

- previous day;
- date input;
- next day, disabled past today;
- `TODAY`;
- refresh, implemented by cleanly replacing the selected-day listener;
- run count and localized date label.

The date uses the browser's local calendar and is never in the future. Convert
it to the exact `YYYY-MM-DD` value queried against backend-authored `date_key`.
Render cards with ticker, status, date/time, short run ID, provider/model or
phase summary, and active selection using `aria-current`.

Rules:

- do not read event subcollections until a run is selected;
- do not open another archived run while a different run is actively running;
- an archived terminal run renders all persisted events/reports/decision;
- an archived nonterminal run attaches live Firestore listeners and locks
  conflicting launch actions;
- when a run becomes terminal, the selected-day listener remains authoritative;
- an empty day is a valid zero-history state, not an error.

## Listener lifecycle and concurrency

Firestore listeners replace API run polling completely. Use monotonically
increasing generation IDs for auth, date, and selected-run subscriptions. Ignore
every callback whose generation/user/date/run no longer matches current state.

After successful POST, remember only the returned run ID, select it, and attach
the two listeners. React StrictMode must not create duplicate listeners or
duplicate POSTs. Cleanup must be idempotent. Do not automatically retry run
creation. Handle listener reconnect/error states without fabricating progress or
destroying the last validated in-memory snapshot.

## Storage and session status

Keep three independent concepts visible and correctly named:

- Firebase Auth: signed out, restoring, signed in;
- Firestore history: checking, ready/live, denied, unavailable;
- analysis backend: checking, ready, offline, forbidden, storage-local,
  misconfigured.

When Firestore reads work, display `FIREBASE` with a green/live treatment. A
backend local fallback is orange and disables Launch, but it must not hide
existing Firestore history. Never imply shared member history is private to the
current user.

The header Session values may include `INITIALIZING`, `READY`, `RUNNING`,
`HISTORY ONLY`, or `DATA ERROR`. Do not reduce all service failures to generic
`OFFLINE`.

## Accessibility and UX

- Include a skip link to the workspace after login.
- Use labels for every input and fieldset/legend for analysts.
- Use `aria-live` intentionally for auth, toasts, Live Wire, and status without
  duplicating speech on every Firestore snapshot.
- Support full keyboard operation and visible focus.
- Use native buttons, inputs, selects, details/summary, table semantics, and
  proper `time` elements.
- Announce copy success/failure through toast.
- Keep loading, empty, backend-offline, Firestore-error, configuration-error,
  API-error, and permission-denied states visually complete.
- Track browser online/offline events only as hints; never treat
  `navigator.onLine` as proof Firebase or FastAPI is reachable.
- Update the clock every second with localized 24-hour formatting.
- Never rely on color alone; include labels, icons, borders, and status text.

## Tests that must be created

### Unit/component tests with Vitest and Testing Library

Use a typed Firebase adapter/fake for component tests and MSW only for the three
FastAPI endpoints. Do not make tests pass by replacing production direct
Firestore history with an API repository.

Cover at minimum:

1. missing/invalid Firebase config setup screen;
2. Google and email/password login while FastAPI is unreachable;
3. auth restoration, login errors, signed-in Firestore denial, and logout;
4. no request to any auth/session/history/run-detail GET backend path;
5. history access verification success, empty collection success, and safe UID
   display on `permission-denied`;
6. daily `date_key` query, client-side descending sort, generation guards, and
   cleanup on date/user/unmount changes;
7. selected run-document/event dual listeners and cleanup;
8. document-ID injection, event de-duplication, sequence/time/ID sort, recursive
   Timestamp normalization, and malformed data fallbacks;
9. report reconstruction where the latest sorted event for a report key wins;
10. Final Decision receiving reconstructed `final_trade_decision` Markdown;
11. no event reads for unselected history cards;
12. backend state transitions among ready/offline/403/local storage without
    disturbing auth/history;
13. Bearer tokens only on options and POST, one refresh-and-retry for analysis
    `401`, and no token in localStorage/logs;
14. exact POST payload, custom fields, crypto Fundamentals rule, validation, and
    no duplicate submit under StrictMode;
15. propagation grace, mid-run health/storage fallback warning, and Launch
    disabling;
16. unchanged listener data preserving report accordions, decision DOM, and
    scroll state;
17. logout tearing down all listeners and clearing protected in-memory data;
18. a static/import-boundary test proving production code imports no Firestore
    write primitive;
19. text-scale persistence/clamping from 85–160 in increments of 5;
20. F1/F2/F3, tab arrows/Home/End, Ctrl+Enter, copy, and focus behavior.

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

Assert that no script/img/svg/iframe/form/style node or event-handler/style/src
attribute is created. Only the valid HTTPS link may be interactive with exact
target/rel safeguards. Add stress cases for 60,000 unmatched `[`, a pipe-heavy
table, huge signal repetition, malformed fences, Windows paths, and headings
containing `C#`.

### Firestore Rules emulator tests

Use `@firebase/rules-unit-testing` against the actual production rules text.
Seed only inside `withSecurityRulesDisabled`. Test that:

- unauthenticated and authenticated non-member users cannot get/list runs or
  events;
- a member can run the exact `date_key` query, get one run, and list its events;
- members cannot create/update/delete runs or events;
- no browser client can read, enumerate, create, update, or delete membership;
- members cannot read unrelated collections;
- removing a membership document revokes later reads;
- membership is UID-based rather than email-based;
- the production daily query succeeds without a composite index.

Use distinct users and reliably clean up the emulator environment.

### Playwright

Use deterministic Firebase emulator/adapters and MSW. Capture screenshots at:

- 1440x1000, 110% text;
- 1024x900, 110% text;
- 390x844, 110% text;
- 390x844, 160% text.

Acceptance scenarios:

1. With no FastAPI, login succeeds, history loads, an archived run opens,
   Reports/Final Decision format correctly, and Launch is disabled in
   `HISTORY ONLY`.
2. FastAPI becomes available; Retry hydrates options and enables Launch without
   re-authentication.
3. Firestore membership denial shows UID/Logout without flashing history.
4. Backend `403` leaves history and logout usable.
5. Logout with active listeners produces no post-logout render or warning.

Also assert no page-level horizontal overflow, internal table/code scrolling,
non-colliding hero/badge/header/tabs, pre-paint slider application, stable focus
order/rings, and reduced-motion support.

## Administrator setup documentation

Create a frontend README with these exact concepts and concrete commands.

### Firebase Console

1. Register a Firebase Web App and copy its public config fields into
   `.env.local` using the `VITE_FIREBASE_*` mapping above.
2. Enable Google and Email/Password in **Authentication > Sign-in method**.
3. Add `localhost` to **Authentication > Settings > Authorized domains** for
   local development; do not include scheme or port.
4. Create email/password accounts through **Authentication > Users** because
   the application intentionally has no registration page.
5. Obtain the exact authorized user's UID.
6. In Firestore Data, create `tradingagents_members/{UID}`. The document can be
   empty or contain harmless admin metadata; authorization depends only on its
   existence and the browser must never create it.
7. Remove that membership document to revoke history access.
8. If backend analysis authorization uses `WEB_AUTH_ALLOWED_EMAILS`, keep the
   same account there for users who may launch analyses. Firestore membership
   and backend analysis authorization are separate gates.

Explain that a Security Rules `exists()` check is a dependent document access
and can contribute to billed reads. Never instruct anyone to place service
account JSON, a private key, Gemini key, or Ollama credential in the frontend.

### Rules validation and deployment

```powershell
npm install
npx firebase login
npx firebase use --add
npm run test:rules
npx firebase deploy --only firestore:rules --project YOUR_PROJECT_ID
```

Require the operator to confirm that the CLI project ID equals
`VITE_FIREBASE_PROJECT_ID`, backend `FIREBASE_PROJECT_ID`, and the
`project_id` inside the backend service-account JSON. Also require
`VITE_FIREBASE_DATABASE_ID=(default)` and backend
`FIREBASE_DATABASE_ID=(default)` before deployment. The supplied
`firebase.json`, Rules, tests, and SDK initialization all target that database.

### Login and history only

```powershell
npm install
Copy-Item .env.example .env.local
npm run dev
```

Open `http://localhost:5173`. FastAPI may remain stopped; Firebase services and
internet connectivity are still required.

### Full analysis mode

Backend terminal:

```powershell
cd W:\AI\Agent\TradingAgents
conda activate tradingagents
python -m pip install -e ".[api]"
tradingagents-api
```

Backend `.env` must allow the exact frontend origin and must use working
Firestore Admin credentials so new runs appear to listeners:

```dotenv
WEB_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
WEB_AUTH_REQUIRED=true
# WEB_AUTH_ALLOWED_EMAILS=owner@example.com
FIREBASE_ENABLED=true
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_CREDENTIALS_PATH=secrets/firebase-service-account.json
FIREBASE_DATABASE_ID=(default)
FIREBASE_COLLECTION=trading_runs
```

The frontend `VITE_FIREBASE_PROJECT_ID`, backend `FIREBASE_PROJECT_ID`, and
service-account JSON `project_id` must all equal `your-project-id`.

Frontend terminal:

```powershell
npm run dev
```

Ollama must also run when the local model is selected. Document lint, unit
tests, rules tests, Playwright, build, preview, the two run modes, shared-history
limitation, local-JSON limitation, and listener cleanup behavior.

Use official Firebase references in the README:

- [Add Firebase to a web app](https://firebase.google.com/docs/web/setup)
- [Firebase Auth state observer](https://firebase.google.com/docs/auth/web/start)
- [Auth persistence](https://firebase.google.com/docs/auth/web/auth-state-persistence)
- [Google sign-in](https://firebase.google.com/docs/auth/web/google-signin)
- [Email/password sign-in](https://firebase.google.com/docs/auth/web/password-auth)
- [Listen to Firestore updates](https://firebase.google.com/docs/firestore/query-data/listen)
- [Security Rules conditions](https://firebase.google.com/docs/firestore/security/rules-conditions)
- [Rules are not filters](https://firebase.google.com/docs/firestore/security/rules-query)
- [Rules Emulator](https://firebase.google.com/docs/firestore/security/test-rules-emulator)
- [Offline cache behavior](https://firebase.google.com/docs/firestore/manage-data/enable-offline)

## Definition of done

Do not stop at scaffolding or TODOs. The task is complete only when:

- the frontend starts independently on port 5173;
- Firebase initializes entirely from `VITE_FIREBASE_*`;
- login and authorized Firestore history work with FastAPI stopped;
- reports and Final Decision reconstruct from event documents;
- backend outage yields `HISTORY ONLY`, not logout or a blank application;
- analysis works when FastAPI is available and uses Bearer authorization only
  for options and POST;
- production code never calls removed backend auth/history/run-read routes and
  contains no Firestore write capability;
- read-only membership rules and emulator tests exist and pass;
- the Bloomberg workstation, safe Markdown, text slider, responsiveness,
  accessibility, keyboard behavior, and copy behavior match this specification;
- lint, strict TypeScript build, unit tests, rules tests, Playwright, and the
  production Vite build pass;
- no backend code or secret file is copied into the frontend repository;
- README contains exact Firebase membership, rules deployment, history-only,
  and full-analysis setup;
- the final response lists every created/changed file, commands run, test
  results, and genuine remaining limitations.

Do not claim local JSON runs are directly readable. Do not claim shared legacy
history is user-private. Do not weaken Security Rules to make a demo pass, and
do not replace implementation with placeholders or a prose-only plan.

---
