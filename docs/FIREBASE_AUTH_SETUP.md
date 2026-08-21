# Setup Firebase Authentication untuk TradingAgents

TradingAgents menyediakan **login saja**, tanpa tombol atau endpoint register.
Metode yang tersedia adalah Google dan email/password. Aplikasi React berjalan
sebagai frontend terpisah, sedangkan FastAPI hanya melayani backend API. Sesudah
login, frontend mengirim Firebase ID token sebagai `Authorization: Bearer
<token>` pada setiap request API yang dilindungi; Python Firebase Admin SDK
memverifikasi token tersebut sebelum mengizinkan akses konfigurasi analisis,
run, respons agent, dan history.

Firestore tetap server-only. File `firebase/firestore.rules` menolak seluruh
akses langsung dari browser; autentikasi tidak pernah memberikan Firebase Web
SDK akses langsung ke collection `trading_runs`.

## Prasyarat

Selesaikan [`FIREBASE_SETUP.md`](FIREBASE_SETUP.md) terlebih dahulu sampai Anda
memiliki:

- project Firebase dan database Firestore;
- `secrets/firebase-service-account.json`;
- `FIREBASE_PROJECT_ID` dan `FIREBASE_CREDENTIALS_PATH` di `.env`;
- dependency `firebase-admin` melalui `pip install -e ".[api]"`.

## 1. Daftarkan Firebase Web App

1. Buka [Firebase Console](https://console.firebase.google.com/) dan pilih
   project yang sama dengan service account.
2. Buka ikon roda gigi **Project settings > General**.
3. Pada **Your apps**, klik ikon Web `</>` atau **Add app > Web**.
4. Isi nickname, misalnya `TradingAgents React`. Firebase Hosting tidak wajib
   dicentang. Frontend React dijalankan atau di-host sebagai aplikasi terpisah;
   backend FastAPI tidak menyajikan Bloomberg UI.
5. Klik **Register app**.
6. Firebase menampilkan objek `firebaseConfig`. Salin nilainya apa adanya;
   jangan menyalin baris JavaScript ke `.env`.

Firebase menjelaskan proses registrasi dan config object pada
[Add Firebase to your JavaScript project](https://firebase.google.com/docs/web/setup).
Firebase Web App config berisi identifier project, bukan service-account private
key; lihat [penjelasan config object resmi](https://firebase.google.com/docs/web/learn-more#config-object).

## 2. Aktifkan metode login

1. Di Firebase Console, buka **Build/Security > Authentication** lalu klik
   **Get started** jika diminta.
2. Buka tab **Sign-in method**.
3. Pilih **Email/Password**, aktifkan opsi **Email/Password**, lalu **Save**.
   Jangan aktifkan Email link bila tidak diperlukan.
4. Pilih **Google**, aktifkan provider, pilih **Project support email**, lalu
   **Save**.

Referensi resmi:

- [Email/password sign-in](https://firebase.google.com/docs/auth/web/password-auth)
- [Google sign-in](https://firebase.google.com/docs/auth/web/google-signin)

## 3. Tambahkan domain aplikasi

1. Buka **Authentication > Settings > Authorized domains**.
2. Untuk development lokal, tambahkan `localhost` bila belum ada. Project yang
   dibuat setelah 28 April 2025 tidak selalu menambahkannya otomatis.
3. Jika frontend dibuka dari host LAN atau domain produksi, tambahkan hostname
   **frontend** tanpa scheme, port, atau path, misalnya `trading.example.com`.
   Hostname backend API bukan Authorized Domain kecuali halaman login memang
   dijalankan dari hostname yang sama.
4. Jangan menambahkan domain yang tidak Anda kontrol. Hapus `localhost` dari
   project produksi bila tidak diperlukan.

Port tidak ditulis pada daftar domain. Untuk setup lokal yang didukung, buka
frontend di `http://localhost:5173` dan tambahkan `localhost`; backend tetap
berjalan di `http://127.0.0.1:8000`. Jika Firebase menampilkan error domain,
tambahkan hostname frontend yang benar-benar tercantum pada error. Lihat
[Firebase Authentication FAQ tentang authorized domains](https://firebase.google.com/support/faq#auth-allowed-domains).

## 4. Isi Web App config di `.env`

Edit `.env` (bukan `.env.example`) dan petakan nilai dari `firebaseConfig`:

```dotenv
WEB_AUTH_REQUIRED=true

# Origin frontend React yang boleh memanggil backend API. Origin harus persis.
WEB_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# firebaseConfig.apiKey
FIREBASE_WEB_API_KEY=AIza...
# firebaseConfig.authDomain
FIREBASE_AUTH_DOMAIN=project-id-anda.firebaseapp.com
# firebaseConfig.projectId (harus sama dengan service account)
FIREBASE_PROJECT_ID=project-id-anda
# firebaseConfig.appId
FIREBASE_WEB_APP_ID=1:123456789:web:abcdef123456

# Opsional, salin hanya bila ada pada firebaseConfig
FIREBASE_MESSAGING_SENDER_ID=123456789
FIREBASE_STORAGE_BUCKET=project-id-anda.firebasestorage.app
FIREBASE_MEASUREMENT_ID=G-XXXXXXXXXX

# Sangat disarankan: akun yang diizinkan backend, dipisahkan koma.
WEB_AUTH_ALLOWED_EMAILS=anda@gmail.com,analyst@perusahaan.com
```

Empat nilai wajib adalah `FIREBASE_WEB_API_KEY`, `FIREBASE_AUTH_DOMAIN`,
`FIREBASE_PROJECT_ID`, dan `FIREBASE_WEB_APP_ID`. Web API key memang dikirim ke
browser oleh Firebase dan bukan pengganti rules atau autentikasi. Jangan pernah
memasukkan isi service-account JSON ke variabel `FIREBASE_WEB_*`.

`WEB_CORS_ORIGINS` adalah daftar origin HTTP(S) yang dipisahkan koma, termasuk
scheme dan port tetapi tanpa path. Jangan gunakan wildcard `*`, credentials,
query, atau fragment. Trailing slash akan dinormalisasi; format canonical tanpa
slash tetap disarankan. CORS diperiksa secara exact-match setelah normalisasi dan
tidak menggantikan verifikasi Bearer token. Jika frontend production berada di
`https://trading.example.com`, gunakan origin tersebut alih-alih origin Vite
lokal, atau cantumkan keduanya bila keduanya memang perlu diizinkan.

`WEB_AUTH_ALLOWED_EMAILS` bersifat case-insensitive. Jika kosong, setiap user
valid di Firebase project dapat memakai backend. Ini terutama penting untuk
Google: login federasi pertama dapat membuat record user Firebase secara
otomatis walaupun frontend tidak memiliki tombol register.

## 5. Buat user email/password tanpa halaman register

1. Buka **Authentication > Users**.
2. Klik **Add user**.
3. Isi email dan password awal, lalu simpan.
4. Tambahkan email yang sama ke `WEB_AUTH_ALLOWED_EMAILS`.
5. Bagikan credential melalui kanal aman; jangan menyimpannya di repository.

Firebase Console memang mendukung pembuatan password user melalui **Add user**;
lihat [Manage Users](https://firebase.google.com/docs/auth/web/manage-users#create_a_user).
Frontend React hanya memanggil `signInWithEmailAndPassword` dan tidak memanggil
API pembuatan user.

Untuk user Google, cukup masukkan alamat Google yang disetujui ke
`WEB_AUTH_ALLOWED_EMAILS`. User memilih tombol **Continue with Google** pada
halaman login frontend.

## 6. Jalankan backend dan frontend

Restart backend agar `.env` dibaca ulang. Jalankan dari terminal repository
TradingAgents:

```powershell
conda activate tradingagents
python -m pip install -e ".[api]"
tradingagents-api
```

Backend API tersedia di `http://127.0.0.1:8000`; root URL menampilkan metadata
API, bukan Bloomberg UI. Buat frontend React + Vite di repository terpisah
dengan panduan lengkap [`REACT_FRONTEND_PROMPT.md`](REACT_FRONTEND_PROMPT.md).
Pada frontend tersebut, arahkan API dan jalankan Vite:

```dotenv
VITE_TRADINGAGENTS_API_URL=http://127.0.0.1:8000
```

```powershell
npm install
npm run dev
```

Buka `http://localhost:5173`. Kedua proses harus tetap berjalan. Hasil yang
benar:

1. halaman login frontend tampil; workspace tidak terlihat;
2. email/password yang dibuat di Console dapat login;
3. tombol Google membuka pemilih akun;
4. akun di luar allowlist mendapat pesan ditolak;
5. sesudah login, workspace dan history tampil;
6. tombol **LOGOUT** kembali ke halaman login frontend.

Pemeriksaan API tanpa token harus menghasilkan `401`:

```powershell
try {
  Invoke-RestMethod http://127.0.0.1:8000/api/options
} catch {
  $_.Exception.Response.StatusCode.value__
}
```

Endpoint bootstrap berikut memang publik agar halaman login frontend dapat
dimulai:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/auth/config |
  ConvertTo-Json -Depth 5
```

Pastikan `configured` bernilai `true`. Output ini berisi Web App config publik,
bukan service-account key. Root API, `/api/health`, `/api/auth/config`,
dokumentasi OpenAPI, dan preflight CORS bersifat publik. `/api/auth/session`,
options, run, polling, serta history wajib menerima Firebase ID token melalui
header Bearer. FastAPI tidak lagi menyajikan file HTML/CSS/JS frontend.

## 7. Keamanan deployment

- Gunakan HTTPS pada deployment jaringan/production agar ID token dan session
  tidak melintasi jaringan dalam plaintext.
- Batasi `WEB_CORS_ORIGINS` ke origin frontend yang benar-benar dipercaya.
  Jangan gunakan `*`; CORS bukan autentikasi dan setiap endpoint yang dilindungi
  tetap wajib memverifikasi Bearer token.
- Pertahankan `firebase/firestore.rules` dalam mode deny-all. Backend Admin SDK
  melewati rules melalui IAM; browser tidak membutuhkan Firestore SDK.
- Isi `WEB_AUTH_ALLOWED_EMAILS` untuk server privat. Menonaktifkan user di
  Firebase Console dan menghapusnya dari allowlist sama-sama disarankan ketika
  akses dicabut.
- Batasi Web API key sesuai panduan
  [Firebase API keys](https://firebase.google.com/docs/projects/api-keys), tetapi
  jangan menganggap API key sebagai credential user.
- `WEB_AUTH_REQUIRED=false` hanya disediakan untuk development lokal darurat.
  Jangan gunakan nilai tersebut pada host bersama atau production.
- Terapkan rate limiting pada reverse proxy. User yang sah tetap dapat
  menghabiskan kuota data vendor atau LLM.
- Frontend React memakai Firebase JavaScript SDK untuk Authentication saja.
  Firewall atau Content Security Policy harus mengizinkan endpoint Firebase
  Authentication yang diperlukan. Service-account JSON hanya berada pada host
  backend dan tidak boleh disalin ke repository, build, atau environment
  frontend.

Firebase merekomendasikan mengirim ID token client melalui HTTPS dan
memverifikasinya dengan Admin SDK pada custom backend; lihat
[Verify Firebase ID tokens](https://firebase.google.com/docs/auth/admin/verify-id-tokens).

## Troubleshooting

### `SETUP REQUIRED`

Cek `/api/auth/config` dan isi seluruh nama environment yang tercantum pada
field `missing`. Restart server sesudah mengubah `.env`.

### `auth/unauthorized-domain`

Tambahkan hostname aplikasi ke **Authentication > Settings > Authorized
domains**. Gunakan hostname frontend, bukan URL backend. Untuk Vite lokal,
tambahkan `localhost` secara manual dan buka `http://localhost:5173`.

### Login Google popup tidak muncul

Izinkan popup untuk origin frontend, pastikan provider Google sudah enabled,
dan periksa bahwa browser/firewall dapat menjangkau Firebase Authentication.

### Browser menampilkan error CORS

Pastikan origin yang terlihat di address bar frontend tercantum persis pada
`WEB_CORS_ORIGINS`. `http://localhost:5173` dan
`http://127.0.0.1:5173` adalah dua origin berbeda. Jangan memperbaikinya dengan
wildcard; ubah daftar origin lalu restart `tradingagents-api`.

### Email/password selalu ditolak

Pastikan provider Email/Password enabled, user sudah dibuat pada tab **Users**,
password benar, user tidak disabled, dan email ada di allowlist bila allowlist
diaktifkan.

### Login Firebase berhasil tetapi server menolak sesi

Pastikan Web App, `FIREBASE_PROJECT_ID`, dan service-account JSON berasal dari
project yang sama. Cek juga `FIREBASE_CREDENTIALS_PATH`, dependency
`firebase-admin`, jam sistem server, serta akses jaringan server ke public keys
Google yang dipakai untuk verifikasi token.
