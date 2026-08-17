# Deploy TradingAgents ke Render Free

Repository ini menyediakan Blueprint [`render.yaml`](../render.yaml) untuk
native Python. Docker tidak digunakan pada deployment ini. Konfigurasinya
memakai satu Uvicorn worker, membatasi thread library numerik ke satu, melepas
cache response setelah run selesai, serta tetap mempertahankan queue dan seluruh
output TradingAgents.

## 1. Persiapkan Firebase

Selesaikan setup Firestore dan Authentication di
[`FIREBASE_SETUP.md`](FIREBASE_SETUP.md) dan
[`FIREBASE_AUTH_SETUP.md`](FIREBASE_AUTH_SETUP.md). Jangan commit `.env` atau
service-account JSON ke Git.

Di Firebase Console, tambahkan domain Render Anda (contoh
`tradingagents-web.onrender.com`) ke **Authentication > Settings > Authorized
domains** agar Google Sign-In dapat kembali ke aplikasi.

## 2. Buat service dari Blueprint

1. Push repository ke GitHub.
2. Buka Render Dashboard, pilih **New > Blueprint**, lalu hubungkan repository.
3. Render membaca `render.yaml`. Pastikan plan yang dipilih adalah **Free**.
4. Isi variable yang diminta saat Blueprint pertama kali dibuat:

   - `GOOGLE_API_KEY`
   - `FIREBASE_PROJECT_ID`
   - `FIREBASE_WEB_API_KEY`
   - `FIREBASE_AUTH_DOMAIN`
   - `FIREBASE_WEB_APP_ID`
   - `WEB_AUTH_ALLOWED_EMAILS` (pisahkan beberapa email dengan koma)

Nilai tersebut sama dengan konfigurasi web app Firebase yang digunakan saat
setup lokal. `FIREBASE_WEB_API_KEY` adalah konfigurasi client Firebase dan akan
dikirim ke browser; service-account JSON tetap merupakan credential server yang
rahasia.

## 3. Upload service-account sebagai Secret File

Setelah service dibuat:

1. Buka service **tradingagents-web > Environment**.
2. Di **Secret Files**, klik **Add Secret File**.
3. Gunakan filename persis `firebase-service-account.json`.
4. Paste seluruh isi JSON service account, kemudian simpan.

Render memasangnya sebagai
`/etc/secrets/firebase-service-account.json`. Blueprint sudah mengatur
`FIREBASE_CREDENTIALS_PATH` ke path tersebut. Jangan memasukkan JSON ini ke
environment variable biasa, source code, atau repository.

## 4. Deploy dan verifikasi

Render menjalankan:

```bash
python -m pip install --no-cache-dir ".[web]"
python -m uvicorn tradingagents.webapp.main:app --host 0.0.0.0 --port $PORT --workers 1 --no-access-log
```

Sesudah deploy berstatus **Live**:

1. Buka `https://<nama-service>.onrender.com/api/health`.
2. Pastikan `status` bernilai `ok` dan storage menunjukkan Firestore/Firebase
   terkonfigurasi.
3. Buka root URL, login, jalankan satu analisis singkat, lalu pastikan hasilnya
   muncul lagi di History.
4. Periksa collection `trading_runs` di Firebase Console.

Jika health masih menunjukkan local JSON, periksa nama Secret File,
`FIREBASE_PROJECT_ID`, database ID, IAM service account, dan log startup Render.

## Batasan Render Free yang tidak dapat dihilangkan lewat optimasi kode

Render Free saat ini menyediakan 512 MB RAM dan 0,1 CPU. Service berhenti setelah
15 menit tanpa inbound traffic dan filesystem lokal hilang pada spin-down,
restart, atau redeploy. Karena itu:

- response dan History tetap persisten melalui Firestore;
- cache market data, full-state log, dan adaptive `trading_memory.md` hanya
  bertahan selama instance yang sama hidup;
- background analysis dapat terputus bila Render me-restart service;
- pertahankan tab browser terbuka saat analisis berjalan. Polling dari tab
  menghasilkan inbound request dan biasanya mencegah idle spin-down;
- gunakan tepat satu worker. State graph dan execution lock bersifat
  process-local.

Konfigurasi ini cocok untuk penggunaan personal/demo. Render sendiri menyatakan
Free instance bukan target production. Referensi resmi:

- [Render instance types](https://render.com/docs/compute-plans)
- [Render Free limitations](https://render.com/docs/free)
- [Render Python versions](https://render.com/docs/python-version)
- [Render environment variables and secret files](https://render.com/docs/configure-environment-variables)
- [Render Blueprint specification](https://render.com/docs/blueprint-spec)
