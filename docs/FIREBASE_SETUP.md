# Setup Firebase untuk history TradingAgents

Backend API menyimpan run dan respons agent ke Cloud Firestore jika kredensial
server valid tersedia. Frontend React membaca data tersebut hanya melalui API.
Jika Firebase belum disiapkan atau gagal diakses, backend tetap berjalan dan
otomatis memakai JSON lokal di
`~/.tradingagents/web_history` (atau lokasi `WEB_LOCAL_DATA_DIR`).

Frontend juga mewajibkan Firebase Authentication sebelum options, analisis,
respons agent, atau history dapat diakses. Setiap request yang dilindungi harus
mengirim Firebase ID token sebagai Bearer token ke backend. Setelah database dan
service account di dokumen ini siap, lanjutkan ke
[`FIREBASE_AUTH_SETUP.md`](FIREBASE_AUTH_SETUP.md) untuk mengaktifkan login
Google dan email/password.

Backend FastAPI dan Bloomberg-style React UI adalah dua aplikasi terpisah.
Backend berjalan di `http://127.0.0.1:8000`, sedangkan frontend development
berjalan di `http://localhost:5173`. Gunakan
[`REACT_FRONTEND_PROMPT.md`](REACT_FRONTEND_PROMPT.md) untuk membuat frontend
React + Vite di repository terpisah.

Arsitektur datanya:

```text
trading_runs/{run_id}
└── events/{event_id}
```

Dokumen run menyimpan metadata seperti ticker, status, `date_key`, dan waktu.
Subcollection `events` menyimpan progres serta respons tiap agent. History per
hari menggunakan field `date_key` dalam format `YYYY-MM-DD`.

## 1. Buat project dan database

1. Buka [Firebase Console](https://console.firebase.google.com/) dan pilih
   **Add project**. Catat **Project ID**; ini berbeda dari nama tampilan
   project.
2. Di project tersebut, buka **Databases & Storage > Firestore** (pada beberapa
   tampilan: **Build > Firestore Database**), lalu klik **Create database** atau
   **Add database**.
3. Pilih **Standard edition** dan gunakan database ID `(default)`.
4. Pilih lokasi yang dekat dengan server/pengguna. Lokasi database tidak dapat
   diubah setelah database dibuat, jadi tentukan dengan hati-hati. Lihat
   [panduan lokasi Firestore resmi](https://firebase.google.com/docs/firestore/locations).
5. Pilih **Production mode**, kemudian klik **Create**. Production mode menolak
   akses mobile/web client, tetapi server terautentikasi tetap dapat mengakses
   Firestore. Langkah console terbaru dijelaskan pada
   [Manage databases](https://firebase.google.com/docs/firestore/manage-databases#console).

Tidak perlu membuat collection secara manual. Collection `trading_runs` dan
subcollection `events` dibuat ketika run pertama disimpan.

## 2. Buat service-account key

1. Di Firebase Console, buka ikon roda gigi **Project settings**.
2. Buka tab **Service accounts**, lalu bagian **Firebase Admin SDK**.
3. Klik **Generate new private key**, konfirmasi **Generate key**, dan simpan
   file JSON yang diunduh dengan aman. Ini adalah prosedur resmi pada
   [Firebase Admin SDK setup](https://firebase.google.com/docs/admin/setup#initialize_the_sdk_in_non-google_environments).
4. Ubah nama dan pindahkan file itu ke lokasi berikut dari root repository:

   ```text
   W:\AI\Agent\TradingAgents\secrets\firebase-service-account.json
   ```

5. Pastikan file ada tanpa menampilkan isi rahasianya:

   ```powershell
   Test-Path .\secrets\firebase-service-account.json
   (Get-Content .\secrets\firebase-service-account.json -Raw |
     ConvertFrom-Json).project_id
   ```

Perintah pertama harus menghasilkan `True`; perintah kedua harus menampilkan
Project ID yang sama dengan Firebase Console.

> Service-account JSON adalah kunci privat server. Jangan pernah menaruhnya di
> JavaScript/browser, folder `static`, Git, Docker image, screenshot, atau chat.
> Firebase merekomendasikan environment variable untuk menunjuk file key dan
> meminta key disimpan secara aman; lihat
> [Add the Firebase Admin SDK to your server](https://firebase.google.com/docs/admin/setup#set-up-project-and-service-account).

## 3. Isi `.env`

Edit file `.env` yang sudah ada, bukan `.env.example`, lalu tambahkan:

```dotenv
FIREBASE_ENABLED=true
FIREBASE_PROJECT_ID=project-id-anda
FIREBASE_CREDENTIALS_PATH=secrets/firebase-service-account.json
FIREBASE_DATABASE_ID=(default)
FIREBASE_COLLECTION=trading_runs

# Origin frontend yang diizinkan memanggil backend API secara exact-match.
WEB_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Opsional: pindahkan fallback history lokal.
# WEB_LOCAL_DATA_DIR=W:/AI/Agent/TradingAgents/.local/web_history
```

Catatan:

- Ganti hanya `project-id-anda` dengan Project ID sebenarnya.
- Path relatif dihitung dari working directory ketika server dijalankan. Jika
  server dijalankan dari folder lain, gunakan path absolut dengan slash `/`,
  misalnya `W:/AI/Agent/TradingAgents/secrets/firebase-service-account.json`.
- `GOOGLE_APPLICATION_CREDENTIALS` dapat dipakai sebagai alternatif
  `FIREBASE_CREDENTIALS_PATH`; cukup gunakan salah satunya. Aplikasi memberi
  prioritas pada `FIREBASE_CREDENTIALS_PATH`.
- Pertahankan `FIREBASE_DATABASE_ID=(default)` dan
  `FIREBASE_COLLECTION=trading_runs` kecuali Anda memang membuat database atau
  namespace collection lain.
- Set `FIREBASE_ENABLED=false` untuk sengaja memaksa penyimpanan JSON lokal.
- `WEB_CORS_ORIGINS` berisi origin HTTP(S) lengkap, termasuk port, yang
  dipisahkan koma. Jangan gunakan wildcard `*`, path, credentials, query, atau
  fragment. CORS tidak menggantikan autentikasi Bearer.
- Restart backend API setiap kali `.env` berubah.

Pastikan dependency API/Firebase proyek sudah terpasang. Aktifkan environment
Conda lalu instal extra `api` yang disediakan project:

```powershell
conda activate tradingagents
python -m pip install -e ".[api]"
```

Import Firebase dibuat lazy, sehingga CLI TradingAgents biasa tetap dapat
berjalan walau `firebase-admin` belum terpasang.

## 4. Kunci Firestore Security Rules

File [`firebase/firestore.rules`](../firebase/firestore.rules) menolak semua
akses langsung dari mobile/web client:

```javascript
rules_version = '2';

service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

Ini memang disengaja. Python backend memakai Admin SDK. Server client library
melewati Firestore Security Rules dan aksesnya dikendalikan oleh IAM, sehingga
rules `false` tidak memblokir backend. Pola server-only ini secara eksplisit
didokumentasikan dalam
[panduan memperbaiki rules yang tidak aman](https://firebase.google.com/docs/firestore/security/insecure-rules#closed_access).

### Opsi A — deploy manual dari console

1. Buka **Firestore Database > Rules** pada Firebase Console.
2. Salin seluruh isi `firebase/firestore.rules` ke editor.
3. Klik **Publish**.
4. Pastikan tidak ada rule lain yang berisi `allow ...: if true`.

### Opsi B — deploy dengan Firebase CLI

Repository ini sudah menyediakan `firebase.json`, rules, dan file indexes. Instal
[Firebase CLI](https://firebase.google.com/docs/cli#setup_update_cli), login, lalu
hubungkan checkout lokal ke project Anda:

```powershell
npm install -g firebase-tools
firebase login
firebase use --add
```

Saat `firebase use --add` bertanya:

- pilih project Firebase yang tadi dibuat;
- masukkan alias, misalnya `default`.

Kemudian deploy rules dan indexes Firestore yang disediakan repository:

```powershell
firebase deploy --only firestore
```

Untuk menghindari salah project, Anda juga dapat menyebut Project ID secara
eksplisit:

```powershell
firebase deploy --only firestore --project project-id-anda
```

Firebase menjelaskan deployment parsial Firestore dan rules pada
[Manage and deploy Firebase Security Rules](https://firebase.google.com/docs/rules/manage-deploy#deploy_your_updates).
Deploy dari CLI dapat menimpa rules yang diedit di console; pilih satu sumber
utama dan selalu sinkronkan perubahan.

## 5. Jalankan backend dan verifikasi

Dari root repository:

```powershell
conda activate tradingagents
python -m pip install -e ".[api]"
tradingagents-api
```

Backend API berjalan di `http://127.0.0.1:8000`. Root URL berisi informasi
service API dan tidak menyajikan frontend. Status koneksi dapat dicek di:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health |
  ConvertTo-Json -Depth 5
```

Jalankan frontend React dari repository terpisah pada terminal kedua. Frontend
harus memiliki konfigurasi berikut:

```dotenv
VITE_TRADINGAGENTS_API_URL=http://127.0.0.1:8000
```

Kemudian jalankan `npm install` dan `npm run dev`, lalu buka
`http://localhost:5173`. Pertahankan kedua proses selama menggunakan aplikasi.
Instruksi pembuatan, pengujian, dan struktur frontend ada di
[`REACT_FRONTEND_PROMPT.md`](REACT_FRONTEND_PROMPT.md).

Storage yang berhasil memakai Firebase akan menunjukkan nilai ekuivalen dengan:

```json
{
  "storage": {
    "mode": "firebase",
    "backend": "firestore",
    "configured": true
  }
}
```

Jika status masih `local` / `local-json`, jalankan pemeriksaan langsung berikut
dari root repository. Pemeriksaan `list_runs` juga memaksa koneksi pertama agar
error network, database, atau IAM tidak tersembunyi oleh lazy client:

```powershell
@'
from pathlib import Path
from dotenv import load_dotenv

# Beri path eksplisit karena script dijalankan melalui stdin (`python -`).
load_dotenv(dotenv_path=Path.cwd() / ".env")

from tradingagents.webapp.storage import build_run_store

store = build_run_store()
store.list_runs(None)
print({"backend": store.backend_name, "configured": store.configured})
'@ | python -
```

Setelah membuat satu analisis dari frontend React, buka **Firestore Database >
Data** di
Firebase Console. Anda seharusnya melihat collection `trading_runs`, sebuah
dokumen run, dan subcollection `events`. History tetap ditampilkan per hari di
frontend berdasarkan `date_key`.

## Keamanan dan biaya

- Browser hanya berbicara dengan backend TradingAgents untuk data aplikasi dan
  Firestore. Browser menerima Firebase **Web App config** (identifier publik)
  untuk login, tetapi tidak pernah menerima service-account key, API key LLM,
  atau akses Firestore langsung.
- Frontend mengirim `Authorization: Bearer <Firebase ID token>` pada setiap
  request options, run, polling, dan history. API memverifikasi token tersebut.
  Tetap gunakan TLS dan rate limiting saat diekspos ke jaringan; login tidak
  membatasi seberapa banyak kuota LLM yang dapat dipakai akun sah.
- Izinkan hanya origin frontend yang diperlukan melalui `WEB_CORS_ORIGINS`.
  Jangan gunakan wildcard, dan jangan menganggap CORS sebagai autentikasi.
- Backend API menjalankan analisis secara serial dan membatasi antrean melalui
  `WEB_RUN_QUEUE_LIMIT` (default `4`). Rekonsiliasi startup default mengasumsikan
  hanya satu instance server. Jika beberapa instance sengaja memakai Firestore
  yang sama, set `WEB_RECONCILE_STALE_RUNS=false` dan gunakan mekanisme ownership
  atau job queue eksternal. Untuk deployment lokal yang didukung, gunakan
  launcher `tradingagents-api` dengan satu worker; jangan menambahkan
  `uvicorn --workers 2` atau lebih.
- Secara default URL Ollama/OpenAI-compatible dari request harus sama dengan
  endpoint yang telah dikonfigurasi server. Jangan aktifkan
  `WEB_ALLOW_CUSTOM_BACKEND_URLS=true` pada deployment bersama kecuali semua
  pengguna dan endpoint dipercaya. URL tersebut membuat server melakukan
  koneksi keluar dan karena itu harus diperlakukan sebagai input sensitif
  terhadap SSRF/jaringan internal.
- Batasi siapa yang dapat membaca file key pada host. Untuk deployment Google
  Cloud, gunakan Application Default Credentials/identity runtime alih-alih
  menyalin key statis. Panduan inisialisasi untuk Google dan non-Google
  environment tersedia di
  [Admin SDK setup](https://firebase.google.com/docs/admin/setup#initialize_the_sdk).
- Jika key pernah masuk Git, log, atau chat, anggap bocor: nonaktifkan/hapus key
  tersebut di **Google Cloud Console > IAM & Admin > Service Accounts > Keys**,
  lalu buat key baru dan perbarui `.env`.
- Firestore mengenakan biaya berdasarkan document reads, writes, deletes,
  storage, dan bandwidth. Firebase saat ini menyediakan kuota gratis untuk satu
  database per project, tetapi batas dan harga dapat berubah. Periksa angka
  terbaru dan buat budget alert melalui
  [halaman billing Firestore resmi](https://firebase.google.com/docs/firestore/pricing#free-quota).
- Setiap event agent adalah satu dokumen/write. History yang panjang akan
  meningkatkan penggunaan storage dan reads, jadi hapus/arsipkan data lama
  sesuai kebijakan Anda.

## Troubleshooting

### `backend` tetap `local-json`

Periksa berurutan:

1. server sudah direstart setelah `.env` diubah;
2. `FIREBASE_ENABLED` bukan `false`;
3. path key benar dan `Test-Path` menghasilkan `True`;
4. `firebase-admin` terpasang pada environment Python yang menjalankan server;
5. `FIREBASE_PROJECT_ID` sama persis dengan `project_id` di JSON;
6. database Firestore `(default)` sudah benar-benar dibuat;
7. koneksi jaringan ke Google APIs tidak diblokir proxy/firewall.

Lihat warning pada terminal backend API. Storage sengaja beralih ke JSON lokal
ketika inisialisasi atau operasi Firestore gagal agar frontend tidak berhenti.

### `ModuleNotFoundError: firebase_admin`

Pastikan instalasi dilakukan di environment aktif:

```powershell
conda activate tradingagents
python -m pip install firebase-admin
python -c "import firebase_admin; print(firebase_admin.__version__)"
```

### `PermissionDenied` / `403`

Pastikan service account berasal dari project yang sama dan key masih aktif.
Admin SDK memakai IAM, bukan browser Security Rules. Penjelasan resmi tentang
pemisahan rules client dan IAM server ada di
[Secure data in Cloud Firestore](https://firebase.google.com/docs/firestore/security/overview).

### `NotFound` / database tidak ada

Buat Firestore database pada project yang tercantum di `.env`. Jika memakai
database bernama selain default, isi `FIREBASE_DATABASE_ID` dengan ID persisnya
dan deploy rules secara khusus untuk database tersebut.

### Data baru tidak terlihat di Firebase Console

Cek `/api/health`. Jika backend telah failover ke `local-json`, data run tersebut
ada di `WEB_LOCAL_DATA_DIR` atau `~/.tradingagents/web_history`, bukan di
Firestore. Perbaiki koneksi lalu restart server; failover mencegah kehilangan
run lokal, tetapi tidak melakukan migrasi otomatis terhadap history lama.
