# Deploy backend TradingAgents dan frontend React di Render Free

TradingAgents sekarang terdiri dari dua aplikasi yang di-deploy secara
terpisah:

```text
Browser
  -> frontend React static (hostname frontend)
  -> FastAPI backend (hostname API)
  -> Firebase Authentication, Firestore, dan provider LLM/data
```

Repository Python ini **tidak menyediakan `render.yaml`** dan tidak lagi
menyajikan Bloomberg-style UI. Karena itu, buat backend Web Service secara
manual. Frontend React + Vite berada di repository terpisah dan dapat di-host
sebagai Render Static Site atau static host lain. Docker tidak diperlukan untuk
keduanya.

Ketersediaan plan gratis, batas resource, dan persyaratan verifikasi akun Render
dapat berubah. Periksa pilihan yang benar-benar tersedia pada akun Anda sebelum
membuat service.

## 1. Siapkan frontend dan Firebase

1. Selesaikan setup Firestore dan Authentication di
   [`FIREBASE_SETUP.md`](FIREBASE_SETUP.md) dan
   [`FIREBASE_AUTH_SETUP.md`](FIREBASE_AUTH_SETUP.md).
2. Buat repository frontend React + Vite terpisah menggunakan spesifikasi
   lengkap [`REACT_FRONTEND_PROMPT.md`](REACT_FRONTEND_PROMPT.md).
3. Tentukan dua hostname deployment, misalnya:

   ```text
   Frontend: https://tradingagents-ui.onrender.com
   Backend:  https://tradingagents-api.onrender.com
   ```

4. Di Firebase Console, tambahkan **hostname frontend**
   `tradingagents-ui.onrender.com` ke **Authentication > Settings > Authorized
   domains**. Jangan menambahkan scheme, port, atau path. Hostname backend tidak
   diperlukan karena halaman login dijalankan dari frontend.

Jangan commit `.env` atau service-account JSON. Service-account key, API key
Gemini, dan semua secret lain hanya boleh berada pada backend; jangan pernah
menyalinnya ke repository frontend atau variabel `VITE_*`.

## 2. Buat backend Web Service secara manual

1. Push repository Python TradingAgents ke GitHub.
2. Di Render Dashboard, pilih **New > Web Service** dan hubungkan repository
   tersebut. Jangan pilih Blueprint karena repository ini tidak memiliki
   `render.yaml`.
3. Pilih runtime Python. File `.python-version` repository meminta Python 3.12.
4. Isi **Build Command**:

   ```bash
   pip install -e ".[api]"
   ```

5. Isi **Start Command**:

   ```bash
   WEB_HOST=0.0.0.0 WEB_PORT=$PORT tradingagents-api
   ```

6. Pilih plan yang sesuai dengan akun dan kebutuhan Anda. Launcher
   `tradingagents-api` menggunakan tepat satu worker karena state run, execution
   lock, dan antrean bersifat process-local.

FastAPI root hanya mengembalikan metadata service. Endpoint health berada di
`/api/health`, dokumentasi interaktif di `/api/docs`, dan aplikasi React berada
pada hostname frontend yang berbeda.

## 3. Konfigurasikan environment backend

Tambahkan environment variables berikut pada backend Web Service:

```dotenv
GOOGLE_API_KEY=isi-key-gemini

FIREBASE_ENABLED=true
FIREBASE_PROJECT_ID=project-id-anda
FIREBASE_DATABASE_ID=(default)
FIREBASE_COLLECTION=trading_runs
FIREBASE_CREDENTIALS_PATH=/etc/secrets/firebase-service-account.json

WEB_AUTH_REQUIRED=true
FIREBASE_WEB_API_KEY=AIza...
FIREBASE_AUTH_DOMAIN=project-id-anda.firebaseapp.com
FIREBASE_WEB_APP_ID=1:123456789:web:abcdef123456
WEB_AUTH_ALLOWED_EMAILS=anda@gmail.com

# Origin frontend persis, bukan URL backend dan bukan wildcard.
WEB_CORS_ORIGINS=https://tradingagents-ui.onrender.com

# Konservatif untuk instance kecil.
WEB_RUN_QUEUE_LIMIT=1
WEB_LIVE_CACHE_TTL_SECONDS=60
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1
NUMEXPR_NUM_THREADS=1
```

Ganti hostname dan nilai Firebase dengan milik Anda. `WEB_CORS_ORIGINS` menerima
daftar origin HTTP(S) yang dipisahkan koma dan mencocokkannya secara persis.
Jangan gunakan `*`, path, credentials, query, atau fragment. Trailing slash akan
dinormalisasi, tetapi format canonical tanpa slash lebih jelas. Jika Anda juga
memiliki preview frontend dengan hostname tetap, tambahkan origin tersebut
secara eksplisit; jangan membuka semua origin.

CORS bukan autentikasi. Frontend harus memperoleh Firebase ID token,
memverifikasi session melalui backend, lalu mengirim `Authorization: Bearer
<token>` pada setiap request options, run, polling, dan history yang dilindungi.

## 4. Upload service account sebagai Secret File

Setelah backend service dibuat:

1. Buka backend service **tradingagents-api > Environment**.
2. Di **Secret Files**, klik **Add Secret File**.
3. Gunakan filename persis `firebase-service-account.json`.
4. Paste seluruh isi JSON service account, kemudian simpan.

Render memasangnya sebagai
`/etc/secrets/firebase-service-account.json`, sesuai
`FIREBASE_CREDENTIALS_PATH` di atas. Jangan memasukkan JSON ke environment
variable biasa, source code, frontend, atau repository.

## 5. Deploy frontend secara terpisah

Deploy repository React yang dibuat dari
[`REACT_FRONTEND_PROMPT.md`](REACT_FRONTEND_PROMPT.md) sebagai Render Static Site
atau pada penyedia static hosting lain. Konfigurasikan build-time environment:

```dotenv
VITE_TRADINGAGENTS_API_URL=https://tradingagents-api.onrender.com
```

Untuk struktur Vite standar, gunakan:

```text
Build command:     npm ci && npm run build
Publish directory: dist
```

Hanya Firebase Web App config publik yang diterima frontend dari
`/api/auth/config`. Jangan membuat variabel frontend untuk service-account JSON,
`GOOGLE_API_KEY`, atau secret backend lain.

Setelah hostname frontend final diketahui, pastikan dua konfigurasi berikut
persis cocok lalu redeploy bila Anda mengubahnya:

- hostname frontend, tanpa scheme/port/path, ada di Firebase Authorized Domains;
- origin frontend lengkap ada di `WEB_CORS_ORIGINS` backend.

## 6. Verifikasi deployment

1. Buka `https://tradingagents-api.onrender.com/api/health`. Pastikan `status`
   bernilai `ok` dan storage menunjukkan Firestore/Firebase terkonfigurasi.
2. Buka root backend dan pastikan respons menjelaskan bahwa frontend merupakan
   aplikasi terpisah; halaman login frontend tidak tersedia pada URL API.
3. Buka `https://tradingagents-ui.onrender.com`, login, dan jalankan satu
   analisis Shallow dengan satu analyst.
4. Pada Browser DevTools, pastikan protected API requests menuju hostname
   backend dan membawa header Bearer. Jangan menampilkan atau menyalin token ke
   log.
5. Pastikan hasil muncul kembali di Daily History dan collection `trading_runs`
   beserta subcollection `events` terlihat di Firebase Console.

Jika health masih menunjukkan local JSON, periksa nama Secret File,
`FIREBASE_CREDENTIALS_PATH`, `FIREBASE_PROJECT_ID`, database ID, IAM service
account, dan log startup backend. Jika login berhasil tetapi API gagal karena
CORS, bandingkan origin address bar frontend dengan `WEB_CORS_ORIGINS` secara
karakter demi karakter.

## Batasan instance gratis atau ber-resource kecil

Instance gratis dapat memiliki RAM/CPU rendah, cold start setelah idle, dan
filesystem ephemeral. Detail angkanya dapat berubah, tetapi konsekuensinya tetap:

- response dan Daily History harus dipersistenkan melalui Firestore;
- cache market data, full-state log, dan adaptive `trading_memory.md` dapat
  hilang saat spin-down, restart, atau redeploy;
- background analysis dapat terputus ketika Render menghentikan atau me-restart
  backend;
- pertahankan frontend terbuka saat analisis berlangsung. Polling frontend
  menghasilkan inbound request ke backend, tetapi bukan jaminan bahwa platform
  tidak akan melakukan restart;
- gunakan satu worker dan `WEB_RUN_QUEUE_LIMIT=1` pada resource sangat kecil;
- static frontend terpisah tidak menyimpan history dan tidak menggantikan
  Firestore.

Ollama pada laptop tidak dapat dicapai melalui
`http://localhost:11434` dari backend Render: `localhost` di sana berarti mesin
Render. Untuk deployment cloud ini gunakan Gemini atau sediakan endpoint Ollama
remote yang diamankan dan memang dapat diakses backend. Setup Llama lokal pada
[`LOCAL_OLLAMA_SETUP.md`](LOCAL_OLLAMA_SETUP.md) ditujukan untuk backend yang
berjalan di laptop yang sama dengan Ollama.

Konfigurasi resource kecil cocok untuk penggunaan personal/demo, bukan workload
production. Referensi resmi:

- [Render instance types](https://render.com/docs/compute-plans)
- [Render Free limitations](https://render.com/docs/free)
- [Render Python versions](https://render.com/docs/python-version)
- [Render environment variables and secret files](https://render.com/docs/configure-environment-variables)
- [Render static sites](https://render.com/docs/static-sites)
