# Setup Firebase Authentication untuk TradingAgents

TradingAgents menyediakan halaman **login saja** pada frontend React. Metode
login yang didukung adalah Google dan email/password; tidak ada tombol, route,
atau API register di aplikasi.

Authentication dan pembacaan history dilakukan langsung oleh frontend melalui
Firebase Web SDK. FastAPI tidak diperlukan untuk login, logout, mempertahankan
session Firebase, atau melihat Firestore history. Backend hanya diperlukan saat
user ingin mengambil options runtime dan memulai analisis baru.

Backend tetap memverifikasi Firebase ID token pada dua endpoint yang dapat
memakai resource server:

```text
GET  /api/options
POST /api/runs
```

Frontend mengirim `Authorization: Bearer <Firebase ID token>` hanya pada request
tersebut. Ini merupakan authorization untuk CPU, LLM, dan data-provider quota,
bukan implementasi halaman login atau session backend.

Endpoint berikut sudah tidak tersedia:

```text
/api/auth/config
/api/auth/session
/api/history
/api/history/{run_id}
GET /api/runs/{run_id}
```

History dan live run dibaca menggunakan listener Firestore pada frontend.

## Prasyarat

Selesaikan [`FIREBASE_SETUP.md`](FIREBASE_SETUP.md) sampai Anda memiliki:

- project Firebase dan Firestore database `(default)`;
- service-account backend yang tersimpan aman;
- `FIREBASE_PROJECT_ID`, `FIREBASE_CREDENTIALS_PATH`, dan konfigurasi storage
  lain di `.env` backend;
- repository React terpisah yang dibuat dari
  [`REACT_FRONTEND_PROMPT.md`](REACT_FRONTEND_PROMPT.md).

Repository frontend adalah satu-satunya pemilik `firebase.json`,
`firestore.rules`, dan `firestore.indexes.json`. Repository Python tidak
menyediakan file deployment Firebase tersebut.

## 1. Daftarkan Firebase Web App

1. Buka [Firebase Console](https://console.firebase.google.com/) dan pilih
   project yang sama dengan service account backend.
2. Buka **Project settings > General**.
3. Pada **Your apps**, klik ikon Web `</>` atau **Add app > Web**.
4. Isi nickname, misalnya `TradingAgents React`. Firebase Hosting tidak wajib.
5. Klik **Register app**.
6. Firebase menampilkan object `firebaseConfig`. Simpan nilai field-nya untuk
   `.env.local` frontend.

Panduan resminya tersedia di
[Add Firebase to your JavaScript project](https://firebase.google.com/docs/web/setup).
Web App config berisi identifier publik dan bukan service-account private key;
lihat [Firebase config object](https://firebase.google.com/docs/web/learn-more#config-object).

## 2. Aktifkan metode login

1. Buka **Build > Authentication** dan klik **Get started** bila diminta.
2. Buka tab **Sign-in method**.
3. Pilih **Email/Password**, aktifkan **Email/Password**, lalu **Save**. Email
   link tidak diperlukan.
4. Pilih **Google**, aktifkan provider, pilih **Project support email**, lalu
   **Save**.

Referensi resmi:

- [Email/password sign-in](https://firebase.google.com/docs/auth/web/password-auth)
- [Google sign-in](https://firebase.google.com/docs/auth/web/google-signin)

Frontend hanya menggunakan `signInWithEmailAndPassword` dan
`signInWithPopup`. Jangan menambahkan `createUserWithEmailAndPassword`, login
anonymous, atau halaman sign-up.

## 3. Tambahkan Authorized Domains

1. Buka **Authentication > Settings > Authorized domains**.
2. Tambahkan `localhost` untuk development lokal bila belum ada. Project yang
   dibuat setelah 28 April 2025 tidak selalu menambahkannya otomatis.
3. Jika frontend menggunakan domain lain, tambahkan hostname frontend tanpa
   scheme, port, atau path, misalnya `trading.example.com`.
4. Jangan menambahkan domain yang tidak Anda kontrol.

Untuk setup lokal, buka UI melalui `http://localhost:5173`. Daftar Authorized
Domains berisi `localhost`, bukan `http://localhost:5173`. Host backend
`127.0.0.1` tidak perlu ditambahkan kecuali halaman login benar-benar disajikan
dari sana. Lihat
[Firebase Authentication FAQ](https://firebase.google.com/support/faq#auth-allowed-domains).

## 4. Isi `.env.local` frontend

Di repository React, copy `.env.example` menjadi `.env.local`, lalu isi public
Web App config:

```dotenv
VITE_FIREBASE_API_KEY=nilai-firebaseConfig-apiKey
VITE_FIREBASE_AUTH_DOMAIN=project-id-anda.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=project-id-anda
VITE_FIREBASE_APP_ID=nilai-firebaseConfig-appId
VITE_FIREBASE_DATABASE_ID=(default)

# Opsional, isi jika field tersedia pada firebaseConfig.
VITE_FIREBASE_MESSAGING_SENDER_ID=
VITE_FIREBASE_STORAGE_BUCKET=
VITE_FIREBASE_MEASUREMENT_ID=

# Hanya diperlukan untuk options dan membuat analisis baru.
VITE_TRADINGAGENTS_API_URL=http://127.0.0.1:8000
```

Setelah mengubah `.env.local`, restart Vite. Jangan menaruh public config ini di
`.env` backend dan jangan mengharapkan `/api/auth/config`, karena endpoint
tersebut telah dihapus.

Yang tidak boleh berada di frontend atau memiliki prefix `VITE_`:

- service-account JSON atau private key;
- `FIREBASE_CREDENTIALS_PATH`;
- API key Gemini atau provider data;
- raw Firebase ID token yang disalin manual.

Firebase SDK mengelola token dan auth state. Frontend menggunakan
`browserLocalPersistence`, sehingga session bertahan setelah reload. Pada laptop
bersama, selalu logout setelah selesai. Jangan menyimpan protected history atau
raw token sendiri di localStorage.

## 5. Buat user tanpa halaman register

### Email/password

1. Buka **Authentication > Users**.
2. Klik **Add user**.
3. Isi email dan password awal, lalu simpan.
4. Tambahkan email yang sama ke `WEB_AUTH_ALLOWED_EMAILS` backend.
5. Buat membership UID seperti pada langkah berikut.
6. Bagikan credential melalui kanal aman, bukan Git atau chat publik.

Firebase Console mendukung pembuatan user administratif; lihat
[Manage Users](https://firebase.google.com/docs/auth/web/manage-users#create_a_user).

### Google

1. Tambahkan email Google yang disetujui ke `WEB_AUTH_ALLOWED_EMAILS` backend.
2. Minta user menekan **Continue with Google** satu kali.
3. Setelah record user muncul pada **Authentication > Users**, copy UID dan
   buat membership.

Tidak adanya tombol register bukan security boundary. Jika
`WEB_AUTH_ALLOWED_EMAILS` kosong, setiap user valid pada Firebase project dapat
memanggil endpoint analisis yang terlindungi. Gunakan allowlist untuk backend
privat.

## 6. Buat membership UID untuk akses history

Firebase Authentication dan Firestore membership adalah dua gate terpisah:

- Authentication membuktikan identitas user.
- `tradingagents_members/{UID}` mengizinkan shared history read.
- `WEB_AUTH_ALLOWED_EMAILS` mengizinkan options dan launch pada backend.

Langkah menambahkan member:

1. Buka **Authentication > Users**.
2. Copy **User UID** secara persis. Jangan menggunakan email sebagai document
   ID.
3. Buka **Firestore Database > Data**.
4. Buat collection `tradingagents_members` bila belum ada.
5. Buat document baru dengan Document ID sama persis dengan UID.
6. Tambahkan metadata administratif opsional seperti:

   ```text
   email: "anda@gmail.com"
   added_at: "2026-08-21"
   ```

7. Refresh frontend dan login kembali bila perlu.

Rules hanya memeriksa keberadaan document. Browser tidak perlu dan tidak boleh
membaca document membership itu sendiri. Frontend menguji izin dengan query
minimal ke `trading_runs`; query yang berhasil tetapi kosong berarti akses sah
dan belum ada history.

Untuk mencabut akses:

1. hapus `tradingagents_members/{UID}` agar history langsung ditolak;
2. hapus email dari `WEB_AUTH_ALLOWED_EMAILS` dan restart backend agar launch
   ditolak;
3. disable atau delete user di Authentication bila seluruh login harus dicabut.

## 7. Buat, uji, dan deploy read-only Rules

Di repository frontend, `firestore.rules` harus berisi:

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

Jangan menggantinya dengan `request.auth != null`. Semua approved member akan
membaca history bersama karena run saat ini belum memiliki `owner_uid`.

Prompt frontend juga menghasilkan test Rules Emulator. Jalankan dan deploy dari
repository frontend, bukan backend:

```powershell
npm install
npx firebase login
npx firebase use --add
npm run test:rules
npx firebase deploy --only firestore:rules,firestore:indexes `
  --project project-id-anda
```

Sebelum deploy, pastikan `project-id-anda`, `VITE_FIREBASE_PROJECT_ID`, backend
`FIREBASE_PROJECT_ID`, dan field `project_id` di service-account JSON semuanya
identik. Pastikan database frontend/backend sama-sama `(default)`. Repository
frontend merupakan satu-satunya sumber kebenaran rules dan indexes.

## 8. Konfigurasikan authorization backend

Public Web App config tidak diperlukan backend. `.env` Python hanya memerlukan
Admin credentials, CORS, dan policy API:

```dotenv
FIREBASE_ENABLED=true
FIREBASE_PROJECT_ID=project-id-anda
FIREBASE_CREDENTIALS_PATH=secrets/firebase-service-account.json
FIREBASE_DATABASE_ID=(default)
FIREBASE_COLLECTION=trading_runs

WEB_AUTH_REQUIRED=true
WEB_AUTH_ALLOWED_EMAILS=anda@gmail.com,analyst@perusahaan.com
WEB_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

`WEB_AUTH_ALLOWED_EMAILS` bersifat case-insensitive. Membership UID dan email
allowlist sengaja terpisah: user dapat diberi akses history tanpa izin memakai
quota analisis, atau sebaliknya. Untuk pengalaman normal, tambahkan user pada
keduanya.

Backend memakai service account yang sama untuk menulis Firestore dan
memverifikasi ID token. Lihat
[Verify Firebase ID tokens](https://firebase.google.com/docs/auth/admin/verify-id-tokens).

`WEB_AUTH_REQUIRED=false` hanya untuk development lokal darurat. Jangan gunakan
nilai tersebut ketika API tersedia melalui LAN, reverse proxy, tunnel, atau
internet.

## 9. Jalankan dua mode aplikasi

### Login dan history saja

FastAPI boleh berhenti. Jalankan hanya frontend:

```powershell
cd W:\path\ke\repository-frontend
npm install
npm run dev
```

Buka `http://localhost:5173`. Hasil yang benar:

1. login page tampil tanpa halaman register;
2. Google dan user email/password Console dapat login;
3. non-member melihat `FIRESTORE ACCESS DENIED`, bukan metadata history;
4. member dapat membuka Daily History, reports, events, dan final decision;
5. backend offline menghasilkan mode `HISTORY ONLY`, bukan logout.

Firebase Authentication, Firestore, dan internet masih harus tersedia.

### Full analysis

Jalankan backend pada terminal lain:

```powershell
cd W:\AI\Agent\TradingAgents
conda activate tradingagents
python -m pip install -e ".[api]"
tradingagents-api
```

Frontend mengambil fresh ID token untuk `/api/options` dan `POST /api/runs`.
Backend harus melaporkan storage `firebase`; bila storage `local-json`, Launch
harus tetap disabled karena frontend tidak dapat membaca hasilnya.

Request options tanpa token harus menghasilkan `401`:

```powershell
try {
  Invoke-RestMethod http://127.0.0.1:8000/api/options
} catch {
  $_.Exception.Response.StatusCode.value__
}
```

Root API, `/api/health`, OpenAPI docs, dan CORS preflight tetap publik. Options
dan POST run memerlukan Bearer token. Frontend tidak boleh meminta user menyalin
token secara manual atau menulis token ke log.

## Keamanan

- Gunakan HTTPS bila frontend atau backend diakses melalui jaringan. ID token
  tidak boleh melintasi jaringan dalam plaintext.
- Batasi `WEB_CORS_ORIGINS` secara exact-match. CORS bukan authorization.
- Browser hanya memiliki read access untuk member. Semua write dilakukan Admin
  SDK backend dan dikendalikan IAM.
- Batasi Firebase Web API key sesuai
  [Firebase API keys](https://firebase.google.com/docs/projects/api-keys), tetapi
  jangan memperlakukannya sebagai password user.
- Jangan menambahkan frontend write untuk runs, events, atau membership.
- Hentikan listener Firestore sebelum logout dan bersihkan data protected dari
  React state.
- Persistent Firestore IndexedDB cache tidak diaktifkan secara default karena
  history dapat sensitif pada perangkat bersama. Auth persistence tidak sama
  dengan menyimpan isi history secara offline.
- User yang sah tetap dapat menghabiskan quota. Pertahankan queue limit dan
  tambahkan rate limiting bila backend diekspos di luar laptop pribadi.
- App Check dapat ditambahkan sebagai defense in depth, tetapi bukan pengganti
  Authentication, Rules, atau backend authorization.

## Troubleshooting

### `SETUP REQUIRED` sebelum login

Periksa seluruh `VITE_FIREBASE_*` pada `.env.local` frontend. Pastikan tidak ada
tanda kutip yang salah, Project ID sama, lalu restart `npm run dev`. Backend
tidak menyediakan `/api/auth/config` untuk mengisi nilai tersebut.

### `auth/unauthorized-domain`

Tambahkan hostname frontend pada **Authentication > Settings > Authorized
domains**. Untuk Vite lokal, tambahkan `localhost` lalu buka
`http://localhost:5173`.

### Popup Google tidak muncul

Pastikan provider Google enabled, izinkan popup pada browser, gunakan authorized
domain yang benar, dan cek firewall dapat menjangkau Firebase Authentication.

### Email/password selalu ditolak

Pastikan provider enabled, user dibuat di **Authentication > Users**, password
benar, dan user tidak disabled. Email allowlist backend tidak memengaruhi proses
login frontend; allowlist baru diperiksa saat options atau launch.

### Login berhasil tetapi `FIRESTORE ACCESS DENIED`

Periksa:

1. rules membership telah di-deploy ke project yang benar;
2. document ID `tradingagents_members/{UID}` berisi UID persis, bukan email;
3. frontend memakai project dan database ID yang sama;
4. user tidak berpindah akun Google;
5. rule `events` juga ada secara eksplisit.

Tidak adanya run bukan error: query sah pada collection kosong tetap berhasil.

### Login dan history berhasil tetapi Launch mendapat `401`

Frontend harus mengambil ID token Firebase terbaru dan mengirim header Bearer
ke `/api/options` serta `POST /api/runs`. Pastikan request bukan memakai cached
token string buatan sendiri dan jam sistem laptop benar.

### Launch mendapat `403`

Tambahkan email login ke `WEB_AUTH_ALLOWED_EMAILS`, pastikan ejaannya benar,
lalu restart backend. Membership Firestore tidak otomatis memberi izin launch.

### Launch mendapat `503` authorization configuration error

Pastikan `FIREBASE_CREDENTIALS_PATH`, `FIREBASE_PROJECT_ID`, service-account
JSON, dependency `firebase-admin`, jam sistem, dan jaringan ke public keys Google
benar. Web App, service account, dan Firestore harus berasal dari project yang
sama.

### Backend offline menyebabkan logout

Itu adalah bug frontend. Auth state dan history tidak boleh bergantung pada
`/api/health`, `/api/options`, atau endpoint FastAPI lainnya. Saat backend tidak
tersedia, pertahankan user Firebase dan history lalu tampilkan `HISTORY ONLY`.

### History tidak menampilkan run dari local JSON

Ini memang batas arsitektur. Browser hanya membaca Cloud Firestore. Data di
`WEB_LOCAL_DATA_DIR` atau `~/.tradingagents/web_history` tidak tersedia tanpa
API pembaca, dan endpoint history backend sudah dihapus. Perbaiki Firestore,
restart backend, dan pastikan storage `firebase` sebelum launch berikutnya.
