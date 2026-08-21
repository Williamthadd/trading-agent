# Copy-paste prompt: direct Firebase login and history for the React frontend

Copy everything below the horizontal rule into Codex while it is opened in the
existing standalone React frontend repository. This prompt intentionally keeps
the TradingAgents Python API as the analysis engine while removing it from the
login and history-read path.

---

## Role and objective

You are a senior React, TypeScript, Firebase, security-rules, and test engineer.
Work directly in this existing TradingAgents frontend repository. Inspect every
relevant source file, test, environment template, and build configuration before
editing anything. Then implement and verify the application; do not merely give
me a plan or code snippets.

Refactor the frontend into this hybrid architecture:

```text
Firebase Authentication ----> React login/session
Cloud Firestore -------------> React history, reports, decisions, live events
FastAPI TradingAgents -------> runtime options + POST new analysis only
Gemini/Ollama/agents --------> remain private behind FastAPI
```

The primary outcome is non-negotiable:

- I can start only the React dev server, leave FastAPI stopped, sign in through
  Firebase, and view Firestore-backed Daily History, events, generated reports,
  and final decisions.
- FastAPI is required only when I want to start a new TradingAgents analysis.
- A stopped FastAPI process must never block Firebase initialization, login,
  logout, history navigation, archived-run selection, report rendering, or
  decision rendering.
- When FastAPI is unavailable, preserve the complete Bloomberg-terminal UI and
  enter a clear read-only `HISTORY ONLY` mode; disable only analysis-engine
  controls.

Do not modify the Python backend from this repository. Do not copy Python code,
the service-account JSON, `.env`, Gemini keys, Ollama credentials, or any other
server secret into the frontend.

## Scope and known limitations

This design can work without FastAPI for login and history because Firebase
Authentication and the Cloud Firestore Web SDK are hosted Firebase services. It
does **not** make the application internet-independent.

When FastAPI is stopped, the frontend cannot:

- create or execute a new TradingAgents analysis;
- invoke Gemini or local Ollama/Llama;
- run LangGraph/LangChain agents or market-data integrations;
- retrieve current provider/model options, queue state, or backend health;
- read runs that exist only in the backend's local JSON fallback;
- repair a stale queued/running run after the backend was interrupted.

Only documents already stored in Cloud Firestore are available directly. The
current schema has no `owner_uid`, so history is shared among the small set of
Firebase UIDs explicitly approved by the Firestore membership rules below. Do
not label it as private per-user history. Per-user ownership requires a separate
backend schema change and migration and is outside this task.

## Preserve the existing application

Keep all current visual and behavioral functionality unless this prompt
explicitly replaces its data source:

- the Bloomberg-terminal dark palette, grid texture, typography, density,
  responsive breakpoints, logo, ticker ribbon, and three-panel workstation;
- Google and existing email/password login with no registration option;
- text-size slider from 85% to 160% and its current persistence behavior;
- Analysis Control, provider/model fields, crypto Fundamentals handling,
  keyboard shortcuts, Live Wire, Agent Matrix, Daily History, reports, and
  Final Trading Decision;
- safe Markdown formatting, financial colors, copy buttons, report accordions,
  accessibility, focus handling, responsive layout, and current XSS/DOM budgets;
- all existing tests that remain semantically valid.

Do not redesign the application into a generic SaaS dashboard. Do not replace
existing authored CSS with Tailwind, Bootstrap, Material UI, Chakra, Ant,
shadcn, or another visual system. Reuse the current types and components where
possible. Make the smallest coherent architectural refactor.

## Instructions that this prompt replaces

The older frontend specification may contain these requirements:

- "Firebase SDK for Authentication only";
- "Never access Firestore directly";
- fetch `/api/auth/config` before Firebase initialization;
- verify every login with `/api/auth/session` before showing the workspace;
- load history from `/api/history` and run detail from `/api/runs/{id}`;
- poll active runs from FastAPI every 1600 ms.

Replace those requirements. In the new architecture:

- the Firebase modular Web SDK handles both Authentication and read-only
  Firestore access;
- public Firebase Web config comes from `VITE_FIREBASE_*` build-time variables;
- Firebase auth state plus a successful Firestore-authorized query unlocks the
  history workspace;
- Firestore is authoritative for run documents, events, reports, decisions,
  archived history, and active-run observation;
- FastAPI remains authoritative only for runtime options and accepting the POST
  that launches a new analysis;
- the Firebase ID token is still sent to FastAPI when a backend call is made,
  and backend token verification must not be bypassed.

The backend no longer exposes `GET /api/auth/config`, `GET /api/auth/session`,
`GET /api/history`, `GET /api/history/{run_id}`, or
`GET /api/runs/{run_id}`. Treat those routes as permanently removed, not as a
fallback. The only application endpoints are public `GET /api/health` plus
Bearer-protected `GET /api/options` and `POST /api/runs`.

## Required dependencies

Use the current stable versions compatible with this project's Node LTS and
existing Vite/React versions. Keep current dependencies and add only what is
needed:

- `firebase` for the modular Web SDK;
- `@firebase/rules-unit-testing` as a development dependency;
- `firebase-tools` as a pinned development dependency so rules tests and deploy
  commands do not depend on an unpinned global installation.

Keep Vitest, React Testing Library, MSW, and Playwright already present in the
project. Do not add a second state-management or UI framework merely for this
change.

Add scripts equivalent to:

```json
{
  "firebase:emulators": "firebase emulators:start --only firestore",
  "test:rules": "firebase emulators:exec --only firestore \"vitest run src/test/firestore.rules.test.ts\"",
  "firebase:deploy:rules": "firebase deploy --only firestore:rules"
}
```

Make quoting portable across the project's supported shell. If the nested
quoted `test:rules` form is not portable on Windows, add a small Node runner or
use the existing test orchestration instead of leaving a broken script.

## Environment contract

Create or update `.env.example` with exactly the public configuration required
by the frontend:

```dotenv
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=
VITE_FIREBASE_PROJECT_ID=
VITE_FIREBASE_APP_ID=

# This frontend contract intentionally supports the default Firestore database.
VITE_FIREBASE_DATABASE_ID=(default)

# Optional values from the Firebase Web App config.
VITE_FIREBASE_MESSAGING_SENDER_ID=
VITE_FIREBASE_STORAGE_BUCKET=
VITE_FIREBASE_MEASUREMENT_ID=

# Needed only for starting a new analysis. Login/history work when it is offline.
VITE_TRADINGAGENTS_API_URL=http://127.0.0.1:8000
```

Use the default Firestore database and these fixed schema constants:

```ts
export const RUNS_COLLECTION = "trading_runs";
export const MEMBERS_COLLECTION = "tradingagents_members";
export const EVENTS_SUBCOLLECTION = "events";
```

Do not make security-sensitive collection paths freely user-editable at
runtime. If this existing frontend genuinely supports a non-default
`FIREBASE_COLLECTION`, centralize and validate the build-time value, update the
Security Rules and tests to the exact same literal, and document the coupling.
Never use a broad wildcard rule to simulate a configurable collection.

Validate the four required `VITE_FIREBASE_*` values before initializing
Firebase. Show a polished `FIREBASE SETUP REQUIRED` screen listing only missing
variable names. Never print their values. The Firebase Web config is public
client configuration, but it is not a substitute for Security Rules.

Fail fast unless `VITE_FIREBASE_DATABASE_ID` is exactly `(default)`. This
migration intentionally standardizes the frontend, Python backend, Emulator,
and Rules deployment on the default database. Verify this identity invariant:

```text
VITE_FIREBASE_PROJECT_ID
  == backend FIREBASE_PROJECT_ID
  == project_id inside the backend service-account JSON
```

Never let Firebase Auth/history use one project while the backend verifies
tokens or persists runs in another.

Ensure `.env.local`, `.env.*.local`, Firebase debug output, emulator exports,
and any App Check debug token are ignored by Git. Never introduce any
`VITE_FIREBASE_SERVICE_ACCOUNT`, private key, `GOOGLE_API_KEY`, or LLM key.

## Firebase initialization

Create one small module such as `src/firebase/client.ts` which:

1. reads and validates the Vite variables;
2. initializes exactly one Firebase app;
3. initializes Firebase Auth;
4. initializes the default Firestore database with memory-only cache and fails
   configuration validation for any named database ID;
5. exports typed `firebaseApp`, `firebaseAuth`, and `firestoreDb` singletons;
6. has no React side effects and is safe under React StrictMode/HMR.

Use modular imports. Use Firestore's default memory cache or explicitly:

```ts
initializeFirestore(firebaseApp, {
  localCache: memoryLocalCache(),
});
```

Do not add named-database support implicitly. Supporting one later requires a
coordinated SDK, backend, Emulator, Firebase CLI deployment, Rules-test, and
operator-documentation change; until then, rejecting it is safer than silently
reading or securing the wrong database.

Do not silently enable persistent IndexedDB history caching. Firebase documents
that web persistence is not automatically cleared between sessions; these
reports are sensitive and may remain visible on a shared computer. Backend
offline mode does not require internet-offline persistence because Cloud
Firestore remains online.

If you choose to offer persistent history later, it must be an explicit
trusted-device opt-in with a warning, multi-user cache isolation, reliable cache
clearing on logout, and dedicated tests. It is not required now.

Optional Firebase App Check is defense in depth, not a prerequisite for this
task. If the project already uses it, preserve it. Otherwise document it as a
future reCAPTCHA Enterprise integration; do not enable enforcement or commit a
debug token without completing the Firebase Console setup and monitoring first.

## Authentication flow: frontend only

Remove all login/bootstrap dependencies on FastAPI:

- do not call `/api/auth/config`;
- do not call `/api/auth/session`;
- do not call `/api/health` before showing the login page;
- a network failure to `127.0.0.1:8000` must not be treated as an auth failure.

Implement this state machine:

1. Validate frontend Firebase config.
2. Call `setPersistence(firebaseAuth, browserLocalPersistence)` before a new
   sign-in operation, preserving the current remembered-login behavior.
3. Subscribe once with `onAuthStateChanged`.
4. Signed out: show the existing login page only.
5. Signed in: verify Firestore read membership using a minimal read query such
   as `query(collection(firestoreDb, RUNS_COLLECTION), limit(1))`.
6. Query succeeds, even when empty: enter the workspace and start the selected
   day's direct Firestore listener.
7. Query returns `permission-denied`: show `FIRESTORE ACCESS DENIED`, the safe
   Firebase UID with a Copy UID button, instructions to ask the administrator
   to add `tradingagents_members/{uid}`, and a Logout button. Do not reveal any
   run metadata.
8. Firebase unavailable: retain the signed-in identity, show a retryable data
   connection state, and do not confuse it with FastAPI offline status.
9. Logout: unsubscribe every Firestore listener first, clear protected
   in-memory state, call Firebase `signOut`, and return to login.

Login methods:

- Google: `GoogleAuthProvider`, custom parameter `{prompt: "select_account"}`,
  then `signInWithPopup`;
- email/password: `signInWithEmailAndPassword`;
- no `createUserWithEmailAndPassword`, registration link, sign-up route, or
  anonymous auth.

Map Firebase errors to safe English UI messages. Preserve the current login
copy and styling. Never persist raw ID tokens yourself; the Firebase SDK manages
its auth state.

The direct Firestore membership policy and backend
`WEB_AUTH_ALLOWED_EMAILS` are separate gates:

- membership permits shared history reads when FastAPI is offline;
- the backend allowlist permits analysis API calls when FastAPI is online.

An account may therefore read history but receive backend `403` when attempting
analysis. Treat that as `ANALYSIS ACCESS DENIED`; do not sign the Firebase user
out or hide Firestore history.

## Firestore schema to consume

The backend writes this hierarchy with Firebase Admin SDK:

```text
trading_runs/{run_id}
└── events/{event_id}
```

A run document can include:

```ts
interface FirestoreTradingRun {
  run_id?: string;
  ticker?: string;
  analysis_date?: string;
  output_language?: string;
  analysts?: string[];
  research_depth?: 1 | 3 | 5 | number;
  llm_provider?: string;
  quick_model?: string;
  deep_model?: string;
  backend_url?: string | null;
  thinking_level?: string | null;
  reasoning_effort?: string | null;
  anthropic_effort?: string | null;
  asset_type?: string;
  status?: string;
  progress?: unknown;
  current_phase?: string | null;
  current_agent?: string | null;
  agent_status?: Record<string, unknown>;
  reports?: Record<string, unknown>;
  decision?: unknown;
  error?: unknown;
  created_at?: unknown;
  updated_at?: unknown;
  started_at?: unknown;
  completed_at?: unknown;
  duration_seconds?: number;
  date_key?: string;
  [key: string]: unknown;
}
```

An event document can include:

```ts
interface FirestoreRunEvent {
  event_id?: string;
  id?: string;
  run_id?: string;
  created_at?: unknown;
  timestamp?: unknown;
  sequence?: unknown;
  agent?: string;
  type?: string;
  status?: string;
  message?: unknown;
  report_key?: string;
  content?: unknown;
  data?: unknown;
  [key: string]: unknown;
}
```

Backend timestamps are normally UTC ISO strings, but normalize Firestore
`Timestamp`, JavaScript `Date`, numeric epoch, and valid ISO strings defensively
without mutating SDK objects. Invalid values become `null`, not `Invalid Date`.

Never trust Firestore content merely because it came from this project. Keep
all LLM/error/event content treated as untrusted text.

## Direct history repository

Create a dedicated typed repository such as
`src/firebase/tradingHistoryRepository.ts`. UI components and hooks must not
construct Firestore paths or queries themselves.

The production repository may import only Firestore read/listen primitives. It
must not import or dynamically call `addDoc`, `setDoc`, `updateDoc`, `deleteDoc`,
`writeBatch`, `runTransaction`, `serverTimestamp`, or any REST write endpoint.

Expose operations equivalent to:

```ts
type Unsubscribe = () => void;

interface TradingHistoryRepository {
  verifyReadAccess(userUid: string): Promise<void>;
  subscribeDay(
    dateKey: string,
    onData: (runs: TradingRun[]) => void,
    onError: (error: HistoryError) => void,
  ): Unsubscribe;
  subscribeRun(
    runId: string,
    onData: (run: TradingRun | null) => void,
    onError: (error: HistoryError) => void,
  ): Unsubscribe;
}
```

Validate `dateKey` as a real `YYYY-MM-DD` calendar date. Validate `runId` as 32
lowercase hex characters before constructing a document path. Reject invalid
values locally.

Implement subscriptions with the modular SDK's `onSnapshot` and return its
unsubscribe callback. Use `getDocs(query(..., limit(1)))` only for the initial
membership/read-access check. Route listener errors through the typed error
normalizer; never allow an unhandled snapshot callback to tear down React.

### Daily query

Use a collection query containing only:

```ts
where("date_key", "==", selectedDate)
```

Then sort results client-side by normalized `created_at` descending and
`run_id` descending. Do not add `orderBy` merely for convenience: equality plus
server ordering usually requires a composite index. The client sort preserves
the current UI while keeping first-time Firebase setup simple.

Subscribe only to the currently selected date. Detach the old listener before
changing dates, on logout, and on unmount. Use a monotonically increasing
generation token so a late callback cannot overwrite a newer selected date.

Do not read every run's events to render history cards. A card uses run-document
summary fields only. This prevents an N+1 read pattern and unnecessary
Firestore cost.

### Selected-run detail

For one selected run, attach exactly two listeners:

1. `trading_runs/{runId}`;
2. `trading_runs/{runId}/events`.

No collection-group query is needed. Sort events client-side by:

1. finite numeric `sequence`, with missing/invalid sequence last;
2. normalized `created_at` ascending;
3. `event_id` ascending.

Deduplicate by `event_id`/document ID. Always inject the Firestore document ID
as a fallback `run_id` or `event_id`; never trust a conflicting path field to
select another document.

Combine independently arriving snapshots without flashing away the previous
valid half. If the run document is missing, distinguish not-found from
permission/network errors. Use `snapshot.metadata.fromCache` only as a status
hint, not proof that data is current.

Detach both listeners on selected-run change, logout, and unmount. React
StrictMode must never leave duplicate listeners.

### Reconstruct reports exactly

Full reports are intentionally persisted as event documents because a Firestore
run document has a size limit. `run.reports` is commonly empty.

Rebuild canonical detail data as follows:

```ts
const reports = {...safeRecord(run.reports)};

for (const event of sortedEvents) {
  if (
    event.type === "report" &&
    typeof event.report_key === "string" &&
    event.report_key.trim() !== ""
  ) {
    reports[event.report_key] = normalizeText(event.content);
  }
}

const canonicalRun = {
  ...run,
  run_id: runDocumentId,
  events: sortedEvents,
  reports,
};
```

The latest sorted event for each `report_key` wins. Feed this canonical
`TradingRun` into the existing Reports and Final Decision components so their
safe Markdown, raw Copy, report de-duplication, financial signal coloring, and
memoization behavior remain unchanged.

The short decision comes from the run document. The full portfolio-manager
narrative normally comes from the reconstructed
`reports.final_trade_decision` event.

## Active analysis behavior

FastAPI remains necessary to start an analysis, but all subsequent run data
should come from the same Firestore listeners used for archived detail.

When the backend is ready:

1. fetch a fresh `/api/options` with the current Firebase ID token;
2. require `options.storage.mode === "firebase"` before enabling Launch in this
   direct-history architecture;
3. validate the form using the current dynamic options;
4. POST `/api/runs` once with a fresh `Authorization: Bearer <ID token>`;
5. use the returned `run_id` immediately as the selected run;
6. attach the run-document and events listeners;
7. display Firestore updates instead of polling `GET /api/runs/{run_id}`;
8. refresh/rely on the selected-day listener when status becomes terminal.

Do not automatically retry POST. Guard double submit and React StrictMode as
the current app does.

Allow a short Firestore propagation grace period after the `202` response. If
the run document still does not appear, show a precise error explaining that
the backend may have fallen back to local JSON. Do not fabricate progress.

If `/api/options` reports `local`/`local-json` storage, keep login and existing
Firestore history working but disable Launch with:

`BACKEND STORAGE IS LOCAL · NEW RUNS WOULD NOT APPEAR IN FIRESTORE HISTORY`

Do not silently combine local JSON and Firestore archives. The browser cannot
read the machine's local fallback file under this API contract, even while
FastAPI is running, because all backend history/run-detail endpoints have been
removed.

While a selected run remains non-terminal, probe only `/api/health` at a modest
interval such as 30 seconds; do not use it as a run-state polling endpoint. If
`health.storage.mode` changes from `firebase` to `local`, stop presenting the
last Firestore snapshot as current and show:

`RUN STORAGE DISCONNECTED · THE BACKEND FELL BACK TO LOCAL JSON`

The analysis may still execute, but later local-only updates cannot be shown by
this frontend. Keep the last confirmed Firestore data visible, disable another
Launch, provide a health Retry, and never invent completion/failure. This is
distinct from the short initial propagation grace.

## Backend availability must be independent

Create a backend availability state separate from Firebase Auth and Firestore:

```ts
type AnalysisEngineState =
  | "checking"
  | "ready"
  | "offline"
  | "forbidden"
  | "storage-local"
  | "misconfigured";
```

After Firestore history is usable, probe `/api/health` with a short timeout and
then fetch `/api/options` with a Firebase token. Repeat only on explicit Retry,
window focus with reasonable throttling, or conservative backoff. Do not create
toast spam.

Expected behavior:

- Backend ready + Firestore ready: normal `READY` workstation.
- Backend offline + Firestore ready: show
  `ANALYSIS ENGINE OFFLINE · LOGIN AND FIRESTORE HISTORY REMAIN AVAILABLE`, set
  session state to `HISTORY ONLY`, and disable Launch/model-runtime controls.
- Backend `403`: show `ANALYSIS ACCESS DENIED`; retain login/history/logout.
- Backend `401`: refresh the Firebase token once and retry once. If still 401,
  show an analysis-session error; do not delete Firestore history state unless
  Firebase itself reports the user signed out.
- Backend storage local: use the explicit storage warning above.
- Firestore denied/unavailable: this is a data-layer failure and must not be
  mislabeled as backend offline.

Do not use `navigator.onLine` as proof that either service is available.

Cache only schema-validated `/api/options` and non-secret form preferences for
display continuity. A cached options object must never enable Launch while the
backend is offline; require a fresh successful options response before POST.

## Firestore Security Rules to generate

Direct history returns `permission-denied` until the frontend-owned read-only
ruleset below is tested and deliberately deployed.

Create `firestore.rules` in this frontend repository with this exact policy:

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

    // Membership is managed only by a trusted administrator in Firebase
    // Console/Admin SDK. Browser clients cannot enumerate or change it.
    match /tradingagents_members/{memberUid} {
      allow read, write: if false;
    }

    match /trading_runs/{runId} {
      allow get, list: if canReadTradingHistory();
      allow create, update, delete: if false;

      // Parent rules do not automatically cover subcollections.
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

Do not weaken this to `request.auth != null`. Google sign-in may create a
Firebase Authentication user the first time an arbitrary Google account signs
in. Without explicit membership, that would expose all shared trading history.

Do not permit browser writes, even for members. The Python backend uses Firebase
Admin SDK and continues writing because trusted server SDKs bypass Firestore
Security Rules and are governed by IAM.

Create `firestore.indexes.json`:

```json
{
  "indexes": [],
  "fieldOverrides": []
}
```

The specified date-only query and client-side sort need only Firestore's
automatic field index. If you deliberately switch to
`where(date_key) + orderBy(created_at)`, add and test the exact composite index
instead of telling the user to click an opaque production error link.

Create or update `firebase.json` without overwriting unrelated existing
Firebase configuration:

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

This frontend repository is the sole source of truth for deployed Firestore
Rules and indexes. The Python backend intentionally contains no `firebase.json`,
`.firebaserc`, or rules deployment files. Do not recreate a second rules source
there, and never weaken this ruleset merely to make a demo pass.

## Administrator setup documentation

Write exact README instructions for the administrator:

1. In Firebase Console, open **Project settings > General > Your apps** and
   copy the public Web App `firebaseConfig` fields into frontend `.env.local`.
2. In **Authentication > Sign-in method**, enable Google and Email/Password.
3. In **Authentication > Settings > Authorized domains**, add `localhost` for
   local development. Do not include scheme or port.
4. In **Authentication > Users**, create email/password users manually as
   needed; the frontend intentionally has no register button.
5. Sign in once or locate the user in **Authentication > Users**, then copy the
   exact UID.
6. In **Firestore Database > Data**, create collection
   `tradingagents_members` and a document whose document ID is exactly that UID.
   The document may contain harmless admin metadata such as
   `{email: "owner@example.com", added_at: "..."}`, but authorization depends
   only on document existence. Do not let the browser create it.
7. Remove that membership document to revoke direct history access.
8. Keep the same email in backend `WEB_AUTH_ALLOWED_EMAILS` if that user should
   also be allowed to launch analyses.
9. Install dependencies, authenticate Firebase CLI, choose the exact project,
   run rules tests, and only then deploy:

   ```powershell
   npm install
   npx firebase login
   npx firebase use --add
   npm run test:rules
   npx firebase deploy --only firestore:rules --project YOUR_PROJECT_ID
   ```

10. Verify that the Firebase CLI project ID, `VITE_FIREBASE_PROJECT_ID`, backend
    `FIREBASE_PROJECT_ID`, and the service-account JSON `project_id` all match.
    Also verify that frontend `VITE_FIREBASE_DATABASE_ID` and backend
    `FIREBASE_DATABASE_ID` are both exactly `(default)`; the supplied SDK
    initialization, `firebase.json`, Rules, and tests target that database.

Explain that a Security Rules `exists()` lookup is a dependent document access
and can contribute to billed Firestore reads. This is acceptable for a small
personal application, but it should be monitored.

Never tell the administrator to paste a service-account JSON into the frontend,
Firebase Web config, browser console, localStorage, or a `VITE_*` variable.

Use these official references when implementing and documenting the feature:

- [Add Firebase to a web app](https://firebase.google.com/docs/web/setup)
- [Firebase Auth state observer](https://firebase.google.com/docs/auth/web/start)
- [Auth persistence](https://firebase.google.com/docs/auth/web/auth-state-persistence)
- [Google sign-in](https://firebase.google.com/docs/auth/web/google-signin)
- [Email/password sign-in](https://firebase.google.com/docs/auth/web/password-auth)
- [Listen to Firestore updates](https://firebase.google.com/docs/firestore/query-data/listen)
- [Security Rules conditions and access calls](https://firebase.google.com/docs/firestore/security/rules-conditions)
- [Rules are not filters](https://firebase.google.com/docs/firestore/security/rules-query)
- [Test Rules with the Emulator](https://firebase.google.com/docs/firestore/security/test-rules-emulator)
- [Web cache and persistence behavior](https://firebase.google.com/docs/firestore/manage-data/enable-offline)
- [Firestore index management](https://firebase.google.com/docs/firestore/query-data/indexing)

## Error and status handling

Define a safe error normalization layer for Firebase and API errors. Do not
render raw objects or stack traces.

At minimum distinguish:

- `permission-denied`: membership/rules/project mismatch; show signed-in UID
  and setup guidance, no history;
- `unauthenticated`: wait for/refresh Firebase auth, then sign out only if the
  Firebase session is actually gone;
- `unavailable`, `deadline-exceeded`, network failure: retryable Firestore
  connection state;
- `resource-exhausted`: quota warning without retry storm;
- `failed-precondition`: configuration/index error with safe instructions;
- empty day: valid zero-history state, not an error;
- missing run: archived run no longer exists;
- backend connection failure: `HISTORY ONLY`, not Firebase logout;
- backend `403`: analysis access denied, history remains;
- backend `429`: queue full and exposed `Retry-After` behavior remains;
- backend `503`: safe runtime/storage/provider message.

Report whether a snapshot came from cache where useful, but do not claim
`FIREBASE LIVE` until a server-backed snapshot or successful query is observed.

## Security requirements

- Firestore Web config is public; data protection comes from Auth, Rules, and
  optional App Check. Still restrict Firebase API keys to the intended Firebase
  APIs and web origins in Google Cloud Console according to Firebase guidance.
- No service-account secret, private key, LLM key, or ID token in source,
  browser logs, analytics, errors, localStorage, screenshots, or persisted form
  state.
- Never base authorization on an email stored in localStorage or a Vite
  allowlist. Only deployed Security Rules decide Firestore access.
- Do not implement client writes to runs, events, or membership.
- Do not use Firestore rules as filters. This shared-membership design allows
  every approved UID to see all runs; say so explicitly.
- Preserve the existing safe Markdown renderer. Never use
  `dangerouslySetInnerHTML`, raw HTML plugins, eval, remote Markdown images, or
  unsafe URL schemes.
- Cap visible event nodes and Markdown parser work as the current frontend does,
  even though the full event set is retained for report reconstruction.
- Unsubscribe all listeners before clearing authenticated data.
- Avoid logging Firestore document contents in production.

## Required source-level tests

Update or add Vitest/Testing Library/MSW tests covering:

1. Firebase config missing/invalid setup state.
2. Google and email/password login with FastAPI completely unreachable.
3. No calls to `/api/auth/config` or `/api/auth/session`.
   Also assert that no frontend module calls `/api/history` or
   `GET /api/runs/{run_id}`.
4. Backend offline still renders signed-in workspace and Firestore history.
5. Firestore access verification success, empty collection success, and
   membership `permission-denied` state with safe UID display.
6. Daily direct query by `date_key`, client-side descending sort, stale callback
   guard, and listener cleanup on date/user/unmount changes.
7. Selected-run run/event dual listeners and cleanup.
8. Event ID fallback, de-duplication, sequence/time sorting, and malformed data.
9. Recursive Timestamp/date normalization.
10. Report reconstruction where multiple events update the same report key and
    the latest sorted event wins.
11. Final Decision receives reconstructed `final_trade_decision` Markdown.
12. No event-subcollection reads for history cards until a run is selected.
13. Backend state changes independently among ready/offline/403/local storage.
14. Launch disabled with backend offline or local storage, while history controls
    remain enabled.
15. Fresh Firebase Bearer token on `/api/options` and `POST /api/runs` only.
16. No automatic POST retry or duplicate launch under StrictMode.
17. Firestore propagation grace plus mid-run health/storage-fallback warning.
18. Logout tears down listeners and clears protected in-memory data.
19. A static/import-boundary test proving production `src` does not import
    Firestore write functions.
20. Existing Markdown adversarial, responsive, keyboard, copy, slider, polling
    replacement, and visual tests remain green.

Mocks must preserve the behavior boundary: MSW mocks FastAPI only; use a typed
Firestore adapter/fake or Firebase Emulator for Firestore behavior. Do not make
tests pass by replacing the production direct repository with API history.

## Firestore Rules emulator tests

Use `@firebase/rules-unit-testing` with the Firestore Emulator. Seed data only
inside `withSecurityRulesDisabled`. Test actual SDK operations against the
deployed rule text.

Required cases:

- unauthenticated client cannot get/list runs or events;
- authenticated non-member cannot get/list runs or events;
- authenticated member can list the `date_key` query, get one run, and list its
  events;
- member cannot create, update, or delete a run;
- member cannot create, update, or delete an event;
- no client can create/read/update/delete/enumerate membership documents;
- member cannot read unrelated collections;
- removing the member document revokes subsequent reads;
- the exact production daily query succeeds without a composite index.

Use distinct users and prove membership is UID-based, not email-based. Clean up
the test environment reliably.

## Playwright acceptance scenarios

Keep the current screenshot/accessibility coverage and add:

1. Start Firebase emulators/mocks but no FastAPI. Login succeeds, Daily History
   loads, an archived run opens, reports and Final Decision format correctly,
   and Launch is disabled under `HISTORY ONLY`.
2. FastAPI becomes available. Retry changes only analysis-engine state, hydrates
   fresh options, and enables Launch without re-authentication.
3. Firestore membership is denied. No history metadata flashes; the setup state
   shows UID and Logout.
4. Backend returns 403. History remains visible and usable.
5. Logout while listeners are active causes no post-logout render or console
   warning.

Retain the existing 1440x1000, 1024x900, 390x844, and 390x844-at-160% visual
checks. The new offline/history banners must not introduce global horizontal
overflow or collide with the terminal header.

## README run modes

Document these two modes clearly.

### Login and history only — backend not required

```powershell
npm install
Copy-Item .env.example .env.local
npm run dev
```

Open `http://localhost:5173`. Firebase services and internet connectivity are
still required. FastAPI may remain stopped.

### Full analysis mode

Backend terminal:

```powershell
cd W:\AI\Agent\TradingAgents
conda activate tradingagents
python -m pip install -e ".[api]"
tradingagents-api
```

Frontend terminal:

```powershell
npm run dev
```

The backend must have valid Firebase Admin/Firestore credentials and must report
Firebase storage. It still verifies the Firebase ID token before accepting a
run. Ollama must also be running when the local model is selected.

Document the corresponding backend `.env` requirements explicitly:

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

The frontend project ID and service-account JSON `project_id` must both equal
the backend `FIREBASE_PROJECT_ID`.

## Definition of done

Do not stop at scaffolding or TODOs. The task is complete only when:

- React can initialize Firebase entirely from `VITE_FIREBASE_*`;
- login works while FastAPI is stopped;
- authorized Firestore history works while FastAPI is stopped;
- reports and Final Decision are reconstructed from event documents;
- backend outage produces `HISTORY ONLY`, not logout or a blank app;
- analysis still works when FastAPI returns and uses Firebase Bearer auth;
- production frontend code has no Firestore write capability;
- read-only membership Security Rules and emulator tests are present and pass;
- all existing visual, responsive, Markdown-security, accessibility, and
  interaction behavior is preserved;
- lint, strict TypeScript build, unit tests, rules tests, Playwright tests, and
  production Vite build pass;
- README includes exact Firebase membership, rules deploy, backend-offline, and
  full-analysis setup;
- no secret or protected history payload is written to logs/localStorage;
- the final response lists all changed files, commands run, test results, and
  genuine remaining limitations.

Do not claim that local JSON runs are available directly. Do not claim that
shared legacy history is user-private. Do not weaken Security Rules merely to
make a demo pass.
