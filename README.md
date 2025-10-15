# Bot Discord Pemantau Berita

Bot ini memantau beberapa RSS feed, memfilter berita dengan kata kunci geopolitik/ekonomi, lalu mengirim embed berisi ringkasan bahasa Indonesia plus analisa dampak ke pasar kripto dan emas.

## Persiapan

1. Buat aplikasi & bot di [Discord Developer Portal](https://discord.com/developers/applications)
   - Simpan token bot dari tab **Bot**.
   - Aktifkan **Message Content Intent**.
   - Buat URL invite (scopes `bot`, permission minimal `Send Messages` dan `Embed Links`) lalu undang bot ke servermu.
   - Klik kanan channel target → **Copy Channel ID** (aktifkan Developer Mode di Discord bila perlu).
2. Ganti nama `.env.example` menjadi `.env` dan isi sesuai data milikmu.
   - `OPENAI_API_KEY` opsional, tetapi sangat disarankan agar ringkasan & analisa memakai model AI.
   - Tanpa API key, bot akan memakai heuristik sederhana (ringkasan generik + analisa dasar).

```env
DISCORD_TOKEN=PASTE_TOKEN_BOT_KAMU_DI_SINI
DISCORD_CHANNEL_ID=123456789012345678
POLL_SECONDS=180
MAX_AGE_HOURS=24
KEYWORDS=powell|federal reserve|fomc|rate cut|rate hike|tariff|trade|china|xi|war|conflict|geopolitics|israel|ukraine|middle east|inflation|cpi|nfp|nonfarm|yield|treasury|shutdown|bank of japan|ecb|boe|pmi|oil|middle-east|taiwan|banjir|gempa|serangan
FEEDS=https://www.federalreserve.gov/feeds/press_all.xml,https://www.whitehouse.gov/briefing-room/feed/,https://feeds.reuters.com/reuters/worldNews,https://feeds.reuters.com/reuters/businessNews,https://www.marketwatch.com/feeds/topstories,https://www.ft.com/rss/home/asia
OPENAI_API_KEY=PASTE_JIKA_PAKAI_AI
OPENAI_MODEL=gpt-4o-mini
OPENAI_TIMEOUT=20
```

Kamu bebas mengubah daftar feed dan kata kunci (regex dipisahkan `|`).

## Menjalankan Bot

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

### Dependensi

Jika kamu belum punya `requirements.txt`, jalankan:

```bash
pip install discord.py feedparser python-dotenv openai
pip freeze > requirements.txt
```

### Cara kerja singkat

- RSS parser menarik entri terbaru dan menyaring berdasarkan `KEYWORDS`.
- Berita lebih lama dari `MAX_AGE_HOURS` (default 24 jam) dilewati agar hanya info terbaru yang diposting.
- Fungsi summarizer menyatukan judul + ringkasan feed:
  - Jika `OPENAI_API_KEY` tersedia, bot meminta model OpenAI menyusun ringkasan serta analisa dampak (crypto & emas) dalam bahasa Indonesia.
  - Jika tidak, bot memakai heuristik sendiri (topik keyword → analisa dasar).
- Embed dikirim ke channel dengan struktur:
  - Deskripsi: ringkasan 1–2 kalimat bahasa Indonesia.
  - Field 1: 📈 Dampak Crypto.
  - Field 2: 🟡 Dampak Emas.
  - Field 3: 🔮 Outlook (ekspektasi pasar/regulasi mendatang).
  - Footer menampilkan sumber feed.

Jika channel tidak ditemukan, pastikan bot sudah masuk ke server dan `DISCORD_CHANNEL_ID` benar. Perhatikan limit rate API saat menambah banyak feed atau menurunkan `POLL_SECONDS`.
