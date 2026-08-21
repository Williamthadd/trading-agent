# Setup Cloud Firestore untuk TradingAgents

TradingAgents memakai Cloud Firestore sebagai penghubung data antara dua
aplikasi yang terpisah:

```text
React frontend -- Firebase Web SDK --> Authentication + read-only history
FastAPI backend -- Firebase Admin SDK -> run, progress, reports, dan decision
```

Login dan pembacaan history dilakukan langsung oleh frontend. Karena itu login
dan history tetap bekerja ketika FastAPI berhenti. Backend hanya diperlukan
untuk mengambil options runtime dan memulai analisis baru.

Repository Python ini tidak lagi memiliki `firebase.json`, `.firebaserc`, file
Security Rules, atau file indexes. Semua konfigurasi deployment Firestore
tersebut harus berada di repository frontend yang dibuat menggunakan
[`REACT_FRONTEND_PROMPT.md`](REACT_FRONTEND_PROMPT.md). Jangan membuat sumber
rules kedua di repository backend.

Struktur data yang dipakai adalah:

```text
trading_runs/{run_id}
`-- events/{event_id}

tradingagents_members/{firebase_uid}
```

- Dokumen run berisi ticker, status, `date_key`, progress, keputusan, dan
  timestamps.
- Subcollection `events` berisi progress, respons agent, dan report lengkap.
- Dokumen membership menentukan UID yang boleh membaca shared history.
- Browser hanya membaca. Seluruh create, update, dan delete dari browser
  ditolak oleh Security Rules.
- Backend memakai Admin SDK dan menulis melalui IAM, sehingga tidak bergantung
  pada izin client di Security Rules.

History yang ada sekarang bersifat bersama untuk semua UID yang menjadi member,
bukan history privat per user. Schema run belum memiliki `owner_uid`.

## 1. Buat project dan database Firestore

1. Buka [Firebase Console](https://console.firebase.google.com/) dan pilih
   **Add project**. Catat **Project ID**, bukan hanya nama tampilan project.
2. Buka **Build > Firestore Database**, lalu pilih **Create database**.
3. Pilih **Standard edition** dan database ID `(default)`.
4. Pilih lokasi yang dekat dengan laptop atau pengguna. Lokasi tidak dapat
   diubah setelah database dibuat. Lihat
   [Firestore locations](https://firebase.google.com/docs/firestore/locations).
5. Pilih **Production mode**, lalu selesaikan pembuatan database.

Collection tidak perlu dibuat sekarang. Backend akan membuat `trading_runs`
dan `events` pada analisis pertama. Collection membership dibuat pada langkah
Security Rules di bawah.

Gunakan database `(default)` kecuali backend dan frontend sengaja dikonfigurasi
untuk database bernama yang sama. Nilai database yang tidak sama menyebabkan
frontend melihat history kosong atau `permission-denied` walaupun project ID
benar.

## 2. Buat service-account key untuk backend

1. Di Firebase Console, buka **Project settings > Service accounts**.
2. Pada bagian **Firebase Admin SDK**, klik **Generate new private key**.
3. Konfirmasi, unduh JSON, lalu simpan sebagai:

   ```text
   W:\AI\Agent\TradingAgents\secrets\firebase-service-account.json
   ```

4. Verifikasi path dan Project ID tanpa mencetak private key:

   ```powershell
   Test-Path .\secrets\firebase-service-account.json
   (Get-Content .\secrets\firebase-service-account.json -Raw |
     ConvertFrom-Json).project_id
   ```

Perintah pertama harus menghasilkan `True`. Project ID dari perintah kedua
harus sama dengan project Firebase. Prosedur resminya tersedia di
[Firebase Admin SDK setup](https://firebase.google.com/docs/admin/setup#initialize_the_sdk_in_non-google_environments).

> Service-account JSON adalah private key server. Jangan menaruhnya di
> repository frontend, variabel `VITE_*`, JavaScript, browser, Git, Docker image,
> screenshot, log, atau chat.

Jika IAM service account pernah diubah dan backend mendapat `PermissionDenied`,
pastikan principal service account tersebut mempunyai izin Firestore yang
diperlukan pada project yang benar, misalnya role **Cloud Datastore User** untuk
operasi data backend. Security Rules browser tidak dapat memperbaiki kegagalan
IAM Admin SDK.

## 3. Konfigurasikan `.env` backend

Edit `.env` di repository Python, bukan `.env.example`:

```dotenv
FIREBASE_ENABLED=true
FIREBASE_PROJECT_ID=project-id-anda
FIREBASE_CREDENTIALS_PATH=secrets/firebase-service-account.json
FIREBASE_DATABASE_ID=(default)
FIREBASE_COLLECTION=trading_runs

# Frontend yang boleh memanggil API options dan launch.
WEB_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Backend tetap memverifikasi Firebase ID token hanya untuk operasi analisis.
WEB_AUTH_REQUIRED=true
WEB_AUTH_ALLOWED_EMAILS=anda@gmail.com

# Opsional: lokasi persistence fallback backend.
# WEB_LOCAL_DATA_DIR=W:/AI/Agent/TradingAgents/.local/web_history
```

Catatan penting:

- Public Firebase Web App config tidak berada di `.env` backend. Nilai tersebut
  hanya ditaruh sebagai `VITE_FIREBASE_*` pada `.env.local` frontend.
- `FIREBASE_CREDENTIALS_PATH` dapat diganti dengan
  `GOOGLE_APPLICATION_CREDENTIALS`; gunakan satu saja. Aplikasi memprioritaskan
  `FIREBASE_CREDENTIALS_PATH`.
- Path relatif dihitung dari working directory backend. Gunakan path absolut
  bila backend dijalankan dari lokasi lain.
- `FIREBASE_COLLECTION` harus tetap `trading_runs`, sama dengan constant dan
  rules frontend.
- Jangan gunakan wildcard pada `WEB_CORS_ORIGINS`. CORS bukan authorization.
- Restart backend setelah `.env` diubah.

Pasang dependency backend dari environment Conda project:

```powershell
conda activate tradingagents
python -m pip install -e ".[api]"
```

Dependency `firebase-admin` tetap diperlukan untuk dua hal: menulis Firestore
dan memverifikasi Bearer token pada `GET /api/options` serta `POST /api/runs`.
Backend tidak menyediakan halaman login, session endpoint, atau public Web App
config.

## 4. Buat konfigurasi Firebase di repository frontend

Ikuti [`FIREBASE_AUTH_SETUP.md`](FIREBASE_AUTH_SETUP.md) untuk mendaftarkan Web
App dan mengaktifkan Google serta email/password. Public config ditempatkan di
`.env.local` repository React:

```dotenv
VITE_FIREBASE_API_KEY=nilai-firebaseConfig-apiKey
VITE_FIREBASE_AUTH_DOMAIN=project-id-anda.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=project-id-anda
VITE_FIREBASE_APP_ID=nilai-firebaseConfig-appId
VITE_FIREBASE_DATABASE_ID=(default)

# Opsional, bila tersedia pada firebaseConfig.
VITE_FIREBASE_MESSAGING_SENDER_ID=
VITE_FIREBASE_STORAGE_BUCKET=
VITE_FIREBASE_MEASUREMENT_ID=

# Hanya diperlukan untuk menjalankan analisis baru.
VITE_TRADINGAGENTS_API_URL=http://127.0.0.1:8000
```

Firebase Web config merupakan identifier publik, tetapi tetap tidak memberikan
izin membaca data. Firebase Authentication dan Security Rules menentukan akses.
Service-account JSON dan API key Gemini tidak boleh memakai prefix `VITE_`.

## 5. Buat dan uji Security Rules di frontend

Repository frontend adalah satu-satunya sumber rules. Buat `firestore.rules`
dengan policy berikut:

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

Rules pada parent document tidak otomatis berlaku pada subcollection. Karena
itu blok `events` harus ditulis secara eksplisit. Jangan mengganti membership
dengan hanya `request.auth != null`; itu akan memberi seluruh user Firebase
project akses ke shared trading history.

Buat `firestore.indexes.json`:

```json
{
  "indexes": [],
  "fieldOverrides": []
}
```

Query frontend memakai `where("date_key", "==", selectedDate)` lalu mengurutkan
hasil di client, sehingga automatic single-field index sudah cukup.

Buat atau gabungkan konfigurasi berikut ke `firebase.json` frontend:

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

Prompt frontend meminta test Rules Emulator untuk memastikan:

- user tanpa login tidak dapat membaca run atau events;
- user login tanpa membership juga tidak dapat membaca;
- member dapat membaca run dan events;
- bahkan member tidak dapat menulis run, events, atau membership.

Jalankan test sebelum deploy:

```powershell
cd W:\path\ke\repository-frontend
npm install
npx firebase login
npx firebase use --add
npm run test:rules
```

Pastikan Project ID CLI, `VITE_FIREBASE_PROJECT_ID`, backend
`FIREBASE_PROJECT_ID`, dan field `project_id` di service-account JSON semuanya
identik. Frontend dan backend juga harus sama-sama memakai database `(default)`
untuk kontrak yang didokumentasikan di sini. Kemudian deploy dari repository
frontend:

```powershell
npx firebase deploy --only firestore:rules,firestore:indexes `
  --project project-id-anda
```

Deployment dari Console atau CLI dapat saling menimpa. Gunakan file frontend
sebagai satu-satunya sumber kebenaran. Lihat
[Manage and deploy Security Rules](https://firebase.google.com/docs/rules/manage-deploy)
dan [Rules Emulator](https://firebase.google.com/docs/firestore/security/test-rules-emulator).

## 6. Tambahkan UID yang boleh membaca history

Membership dibuat oleh administrator, bukan oleh browser:

1. Aktifkan provider dan buat user mengikuti
   [`FIREBASE_AUTH_SETUP.md`](FIREBASE_AUTH_SETUP.md).
2. Untuk email/password, UID langsung tersedia di **Authentication > Users**.
   Untuk Google, minta user login satu kali agar record user dibuat, lalu buka
   halaman Users.
3. Salin nilai **User UID** secara persis.
4. Buka **Firestore Database > Data**.
5. Buat collection `tradingagents_members`.
6. Buat document dengan **Document ID sama persis dengan UID**. Tambahkan field
   administratif opsional, misalnya `email` dan `added_at`. Rules hanya
   memeriksa keberadaan document, bukan nilai email di dalamnya.
7. Pastikan email user yang sama juga ada pada `WEB_AUTH_ALLOWED_EMAILS` di
   `.env` backend bila user boleh menjalankan analisis.
8. Refresh frontend. User sekarang dapat membaca history.

Untuk mencabut akses history, hapus document membership tersebut. Untuk
mencabut kemampuan launch juga, hapus email dari backend allowlist, disable user
di Authentication, lalu restart backend.

## 7. Jalankan dan verifikasi

Backend:

```powershell
cd W:\AI\Agent\TradingAgents
conda activate tradingagents
tradingagents-api
```

Frontend, pada terminal dan repository terpisah:

```powershell
npm run dev
```

Login dan history dapat diuji tanpa backend: hentikan FastAPI, buka
`http://localhost:5173`, login, lalu pilih tanggal history. Firebase dan koneksi
internet tetap diperlukan.

Untuk full analysis, jalankan backend dan cek health publik:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health |
  ConvertTo-Json -Depth 5
```

Storage yang benar menunjukkan nilai ekuivalen dengan:

```json
{
  "storage": {
    "mode": "firebase",
    "backend": "firestore",
    "configured": true
  }
}
```

Sesudah login, frontend mengambil token Firebase untuk `GET /api/options` dan
`POST /api/runs`. Backend tidak lagi menyediakan:

```text
/api/auth/config
/api/auth/session
/api/history
/api/history/{run_id}
GET /api/runs/{run_id}
```

Run document dan events dipantau langsung oleh listener Firestore frontend.
Sesudah satu analisis, verifikasi `trading_runs/{run_id}` dan subcollection
`events` pada Firebase Console.

## Local JSON fallback

Jika Firebase Admin tidak terkonfigurasi atau koneksi Firestore gagal, backend
dapat beralih ke `local-json`. File tersebut berada di `WEB_LOCAL_DATA_DIR` atau
`~/.tradingagents/web_history`.

Browser tidak dapat membaca file lokal backend secara langsung. Akibatnya:

- history local JSON tidak muncul pada frontend;
- listener Firestore tidak dapat melihat progress run lokal;
- tidak ada migrasi otomatis dari local JSON ke Firestore;
- frontend harus menonaktifkan **Launch** ketika `/api/options` melaporkan
  storage selain `firebase`.

Perbaiki koneksi Firebase dan restart backend sebelum membuat analisis baru.
Jangan menggabungkan archive local JSON dan Firestore secara diam-diam.

## Keamanan dan biaya

- Frontend boleh membaca hanya karena Firebase Auth + membership Rules. Semua
  browser write tetap ditolak.
- Backend Admin SDK melewati Rules dan dilindungi oleh IAM. Jangan menaruh
  service-account key di frontend.
- Backend tetap memverifikasi Firebase ID token pada options dan launch karena
  kedua operasi dapat menghabiskan CPU, LLM quota, dan data-provider quota.
- Gunakan HTTPS bila API diakses melalui jaringan. CORS bukan authorization.
- Isi `WEB_AUTH_ALLOWED_EMAILS`. Tidak menyediakan tombol register tidak cukup
  untuk mencegah pembuatan user melalui Firebase API.
- Jangan aktifkan `WEB_ALLOW_CUSTOM_BACKEND_URLS=true` pada host bersama kecuali
  seluruh user dan endpoint dipercaya.
- Gunakan satu backend worker. Rekonsiliasi startup menganggap satu process
  memiliki run aktif; untuk beberapa instance gunakan job ownership eksternal.
- Firestore mengenakan biaya untuk document reads, writes, deletes, storage,
  bandwidth, dan sebagian access calls pada Rules. Periksa
  [Firestore pricing](https://firebase.google.com/docs/firestore/pricing).
- Listener history harus dibatasi ke tanggal aktif dan events hanya dibaca untuk
  run yang dipilih agar penggunaan read tidak tumbuh tanpa batas.

## Troubleshooting

### Health masih menunjukkan `local-json`

Periksa secara berurutan:

1. backend sudah direstart setelah `.env` berubah;
2. `FIREBASE_ENABLED` bukan `false`;
3. `Test-Path .\secrets\firebase-service-account.json` menghasilkan `True`;
4. `firebase-admin` terpasang pada Conda environment yang menjalankan backend;
5. Project ID di `.env`, JSON key, dan Firebase Console sama;
6. database `(default)` sudah dibuat;
7. IAM service account mengizinkan operasi Firestore;
8. firewall atau proxy tidak memblokir Google APIs.

Saat memeriksa `.env` melalui `python -`, berikan path eksplisit agar versi
`python-dotenv` tertentu tidak menghasilkan `AssertionError`:

```powershell
@'
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path.cwd() / ".env")

from tradingagents.webapp.storage import build_run_store

store = build_run_store()
print({"backend": store.backend_name, "configured": store.configured})
'@ | python -
```

### `ModuleNotFoundError: firebase_admin`

```powershell
conda activate tradingagents
python -m pip install -e ".[api]"
python -c "import firebase_admin; print(firebase_admin.__version__)"
```

### Backend `PermissionDenied` / `403` dari Firestore

Pastikan service account berasal dari project yang sama, key masih aktif, dan
IAM role-nya benar. Admin SDK memakai IAM, bukan browser Security Rules. Lihat
[Secure data in Cloud Firestore](https://firebase.google.com/docs/firestore/security/overview).

### Login berhasil tetapi history mendapat `permission-denied`

Periksa bahwa:

1. rules read-only membership sudah di-deploy ke project yang benar;
2. document `tradingagents_members/{UID}` memakai UID, bukan email;
3. UID berasal dari Firebase project yang sama;
4. `VITE_FIREBASE_PROJECT_ID`, backend `FIREBASE_PROJECT_ID`, dan service-account
   `project_id` identik; database frontend/backend sama-sama `(default)`;
5. listener juga diizinkan pada subcollection `events`.

### History kosong setelah run baru

Cek `/api/health` dan status storage saat launch. Jika backend failover ke
`local-json`, run tersebut hanya ada di mesin backend dan tidak dapat diambil
langsung oleh frontend. Jika storage tetap Firestore, cek `date_key`, project,
database ID, listener error, dan Firebase Console.

### Rules deploy ke project yang salah

Jalankan dari repository frontend:

```powershell
npx firebase projects:list
npx firebase use
npx firebase deploy --only firestore:rules,firestore:indexes `
  --project project-id-anda
```

Selalu cocokkan Project ID CLI dengan `VITE_FIREBASE_PROJECT_ID` sebelum
menyetujui deployment.
