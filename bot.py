import asyncio
import json
import logging
import os
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from textwrap import shorten
from typing import Iterable, Optional, Sequence, Set

import discord
import feedparser
from discord import Embed
from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore[assignment]


load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "180"))
MAX_AGE_HOURS = float(os.getenv("MAX_AGE_HOURS", "24"))
KEYWORDS = os.getenv("KEYWORDS", "")
FEEDS = [feed.strip() for feed in os.getenv("FEEDS", "").split(",") if feed.strip()]
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip() or "gpt-4o-mini"
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "20"))

if not TOKEN:
    raise SystemExit("DISCORD_TOKEN belum di-set di file .env")

if not CHANNEL_ID:
    raise SystemExit("DISCORD_CHANNEL_ID belum di-set di file .env")

try:
    CHANNEL_ID_INT = int(CHANNEL_ID)
except ValueError as exc:
    raise SystemExit("DISCORD_CHANNEL_ID harus berupa angka (integer).") from exc

if not FEEDS:
    raise SystemExit("Daftar FEEDS kosong. Isi setidaknya satu URL RSS di file .env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("news-bot")

openai_client: Optional["OpenAI"] = None
if OPENAI_API_KEY:
    if OpenAI is None:
        logger.warning(
            "OPENAI_API_KEY terdeteksi, tetapi library openai tidak tersedia. "
            "Jalankan 'pip install openai' jika ingin memakai summarizer AI."
        )
    else:
        try:
            openai_client = OpenAI(api_key=OPENAI_API_KEY, max_retries=1)
        except Exception as exc:  # pragma: no cover - config error
            logger.exception("Gagal menginisialisasi OpenAI client: %s", exc)

intents = discord.Intents.default()
client = discord.Client(intents=intents)

keyword_pattern: Optional[re.Pattern[str]] = (
    re.compile(KEYWORDS, re.IGNORECASE) if KEYWORDS else None
)

SEEN_MAX = 2000
seen_queue: deque[str] = deque(maxlen=SEEN_MAX)
seen_lookup: Set[str] = set()

TOPIC_KEYWORDS: dict[str, Sequence[str]] = {
    "fed": ("powell", "federal reserve", "fed", "fomc", "rate", "policy", "treasury"),
    "inflation": ("inflation", "cpi", "ppi", "price", "prices", "cost", "pce"),
    "war": (
        "war",
        "conflict",
        "attack",
        "missile",
        "invasion",
        "israel",
        "gaza",
        "ukraine",
        "russia",
        "iran",
        "taiwan",
    ),
    "china": ("china", "xi", "beijing", "tariff", "trade", "export", "import"),
    "economy": (
        "economy",
        "growth",
        "gdp",
        "jobs",
        "employment",
        "nfp",
        "unemployment",
        "recession",
    ),
    "bank": ("bank", "credit", "loan", "regulator", "capital", "stress"),
    "energy": ("oil", "gas", "energy", "opec", "brent", "wti"),
    "crypto": ("bitcoin", "btc", "crypto", "ethereum", "eth", "stablecoin"),
}

FALLBACK_IMPACT: dict[str, dict[str, str]] = {
    "fed": {
        "crypto": "Ekspektasi perubahan kebijakan Fed dapat menggoyang sentimen risk-on pada BTC dan pasar kripto.",
        "gold": "Langkah Fed biasanya memengaruhi yield dan USD, sehingga emas bisa tertekan atau menguat tergantung nada kebijakan.",
        "outlook": "Pasar menanti panduan lanjutan dari pejabat Fed; rilis data berikutnya berpotensi memicu volatilitas baru.",
    },
    "inflation": {
        "crypto": "Data inflasi tinggi bisa memicu kekhawatiran tightening, menekan aset kripto.",
        "gold": "Inflasi tinggi sering menopang emas sebagai lindung nilai jangka panjang.",
        "outlook": "Jika tekanan harga berlanjut, ekspektasi kenaikan suku bunga dapat menahan sentimen risiko dan mendukung aset defensif.",
    },
    "war": {
        "crypto": "Ketegangan geopolitik mendorong risk-off; BTC cenderung volatil dan bisa tertekan jangka pendek.",
        "gold": "Konflik meningkatkan permintaan safe haven sehingga emas biasanya mendapat dukungan.",
        "outlook": "Eskalasi konflik berpotensi menjaga volatilitas lintas aset tinggi; investor fokus pada perkembangan diplomatik dan respon kebijakan.",
    },
    "china": {
        "crypto": "Sentimen risiko global terkait China bisa mempengaruhi arus modal kripto.",
        "gold": "Kekhawatiran terhadap ekonomi China dapat meningkatkan permintaan emas sebagai diversifikasi.",
        "outlook": "Keputusan kebijakan China dan arah perdagangan global menjadi katalis berikutnya; ketidakpastian bisa menekan aset berisiko.",
    },
    "economy": {
        "crypto": "Data ekonomi kuat dapat mendukung aset berisiko; sebaliknya pelemahan memicu aksi hindari risiko pada kripto.",
        "gold": "Perlambatan ekonomi sering memperkuat emas karena investor mencari aset defensif.",
        "outlook": "Rangkaian data berikut akan menentukan arah; tanda-tanda pelemahan lanjutan dapat memicu rotasi ke aset defensif.",
    },
    "bank": {
        "crypto": "Isu perbankan dapat menyalakan narasi 'crypto as alternative', tetapi juga memicu risk-off umum.",
        "gold": "Ketidakpastian sektor bank biasanya positif bagi emas sebagai tempat berlindung.",
        "outlook": "Jika tekanan sektor bank melebar, regulator bisa merespons dengan kebijakan tambahan; volatilitas finansial dapat menyebar ke kripto.",
    },
    "energy": {
        "crypto": "Lonjakan harga energi meningkatkan biaya mining dan melemahkan sentimen risk-on.",
        "gold": "Harga energi tinggi dapat meningkatkan inflasi, mendukung emas.",
        "outlook": "Pasar energi ketat berpotensi mempertahankan inflasi tinggi; ekspektasi kebijakan moneter ketat bisa menjaga volatilitas pasar.",
    },
    "crypto": {
        "crypto": "Berita langsung industri kripto bisa memicu reaksi cepat pada BTC dan altcoin.",
        "gold": "Dampak ke emas cenderung terbatas kecuali mempengaruhi USD atau likuiditas global.",
        "outlook": "Perkembangan regulasi dan adopsi institusional tetap menjadi fokus; volatilitas kripto berpotensi tinggi dalam waktu dekat.",
    },
}

TOPIC_LABELS: dict[str, str] = {
    "fed": "kebijakan Federal Reserve",
    "inflation": "inflasi",
    "war": "ketegangan geopolitik",
    "china": "hubungan dagang China",
    "economy": "data ekonomi makro",
    "bank": "stabilitas perbankan",
    "energy": "pasar energi",
    "crypto": "sektor kripto",
}


@dataclass
class AnalysisResult:
    summary: str
    crypto: str
    gold: str
    outlook: str


def remember_uid(uid: str) -> bool:
    """Return True if uid is new; otherwise False. Maintains a rolling cache."""
    if uid in seen_lookup:
        return False
    if len(seen_queue) == seen_queue.maxlen:
        oldest = seen_queue.popleft()
        seen_lookup.discard(oldest)
    seen_queue.append(uid)
    seen_lookup.add(uid)
    return True


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]*>", "", text or "").strip()


def collect_text(entry: feedparser.FeedParserDict, keys: Iterable[str]) -> str:
    return " ".join(entry.get(key, "") or "" for key in keys)


def extract_tags(entry: feedparser.FeedParserDict) -> str:
    tags = entry.get("tags") or []
    return " ".join(tag.get("term", "") for tag in tags if tag)


def match_entry(entry: feedparser.FeedParserDict) -> bool:
    if keyword_pattern is None:
        return True
    haystack = " ".join(
        filter(
            None,
            [
                collect_text(entry, ("title", "summary", "description")),
                extract_tags(entry),
            ],
        )
    )
    return bool(keyword_pattern.search(haystack))


def entry_timestamp(entry: feedparser.FeedParserDict) -> datetime:
    ts_struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if ts_struct:
        return datetime.fromtimestamp(time.mktime(ts_struct), tz=timezone.utc)
    return datetime.now(timezone.utc)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def aggregate_entry_text(entry: feedparser.FeedParserDict) -> str:
    components: list[str] = []
    for key in ("title", "summary", "description"):
        value = strip_html(entry.get(key, ""))
        if value:
            components.append(value)
    contents = entry.get("content") or []
    if isinstance(contents, list):
        for block in contents:
            if isinstance(block, dict):
                value = strip_html(block.get("value", ""))
                if value:
                    components.append(value)
    tags = extract_tags(entry)
    if tags:
        components.append(f"Tags: {tags}")
    return normalize_whitespace(" ".join(components))


def primary_summary_text(entry: feedparser.FeedParserDict) -> str:
    summary_source = (
        entry.get("summary")
        or entry.get("description")
        or entry.get("content", [{}])[0].get("value", "")
    )
    return normalize_whitespace(strip_html(summary_source))


def classify_topics(text: str) -> Set[str]:
    lowered = text.lower()
    hits: Set[str] = set()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            hits.add(topic)
    return hits


def fallback_summary(
    title: str, base_text: str, topics: Set[str]
) -> str:
    snippet = shorten(normalize_whitespace(base_text), width=280, placeholder="...")
    topical_hint = ""
    if topics:
        topic_sentence = ", ".join(
            TOPIC_LABELS.get(topic, topic) for topic in sorted(topics)
        )
        topical_hint = f" Fokus utama: {topic_sentence}."
    if snippet:
        return f"{title}. Ringkasan singkat: {snippet}{topical_hint}"
    if title:
        return f"{title}. Detail lengkap tersedia pada tautan berita.{topical_hint}"
    return "Ringkasan belum tersedia, silakan cek tautan berita untuk detail."


def fallback_impact(topics: Set[str]) -> tuple[str, str, str]:
    crypto_notes: list[str] = []
    gold_notes: list[str] = []
    outlook_notes: list[str] = []
    for topic in topics:
        impact = FALLBACK_IMPACT.get(topic)
        if not impact:
            continue
        crypto_notes.append(impact["crypto"])
        gold_notes.append(impact["gold"])
        outlook_note = impact.get("outlook")
        if outlook_note:
            outlook_notes.append(outlook_note)

    if not crypto_notes:
        crypto_notes.append(
            "Belum terlihat katalis khusus; pasar kripto kemungkinan menunggu klarifikasi lanjutan."
        )
    if not gold_notes:
        gold_notes.append(
            "Tidak ada pemicu langsung; perhatikan pergerakan USD dan yield untuk arah emas."
        )
    if not outlook_notes:
        outlook_notes.append(
            "Pelaku pasar akan mengikuti rilis data dan headline berikutnya; volatilitas bisa meningkat jika muncul katalis baru."
        )

    return (" ".join(crypto_notes), " ".join(gold_notes), " ".join(outlook_notes))


def parse_ai_response(payload: str) -> Optional[AnalysisResult]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None

    summary = normalize_whitespace(data.get("summary", ""))
    crypto = normalize_whitespace(data.get("crypto", ""))
    gold = normalize_whitespace(data.get("gold", ""))
    outlook = normalize_whitespace(data.get("outlook", ""))
    if not summary or not crypto or not gold or not outlook:
        return None
    return AnalysisResult(summary=summary, crypto=crypto, gold=gold, outlook=outlook)


def call_openai_analysis(
    entry: feedparser.FeedParserDict, topics: Set[str], context: str
) -> Optional[AnalysisResult]:
    if openai_client is None:
        return None

    title = entry.get("title") or "(Tanpa Judul)"
    tags = ", ".join(TOPIC_LABELS.get(topic, topic) for topic in sorted(topics)) or "tidak terdeteksi"
    prompt = (
        "Anda adalah analis pasar profesional yang menulis bahasa Indonesia ringkas dan jelas.\n"
        "Ringkas berita (maks 2 kalimat), lalu jelaskan dampak ke crypto (BTC & sentimen risiko), "
        "emas (safe haven & USD), dan outlook pasar ke depan. Gunakan tone profesional.\n"
        "Kembalikan hasil dalam format JSON dengan kunci: summary, crypto, gold, outlook."
    )
    user_content = (
        f"Judul: {title}\n"
        f"Topik kunci: {tags}\n"
        f"Konten:\n{context}\n"
        "Instruksi khusus:\n"
        "- summary: ringkasan 1-2 kalimat bahasa Indonesia.\n"
        "- crypto: jelaskan dampak singkat ke BTC/pasar kripto.\n"
        "- gold: jelaskan dampak singkat ke emas/safe haven.\n"
        "- outlook: gambarkan ekspektasi pasar/regulasi/volatilitas ke depan.\n"
    )

    try:
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            timeout=OPENAI_TIMEOUT,
        )
    except Exception as exc:  # pragma: no cover - API failure
        logger.warning("Gagal memanggil OpenAI: %s", exc)
        return None

    message = response.choices[0].message.content if response.choices else None
    if not message:
        return None
    return parse_ai_response(message)


async def analyze_entry(entry: feedparser.FeedParserDict) -> AnalysisResult:
    context_text = aggregate_entry_text(entry)
    topics = classify_topics(context_text)
    ai_result: Optional[AnalysisResult] = None
    if openai_client is not None:
        ai_result = await asyncio.to_thread(
            call_openai_analysis, entry, topics, context_text
        )
    if ai_result:
        return ai_result
    crypto, gold, outlook = fallback_impact(topics)
    title = entry.get("title") or ""
    base_text = primary_summary_text(entry) or context_text
    summary = fallback_summary(title, base_text, topics)
    return AnalysisResult(summary=summary, crypto=crypto, gold=gold, outlook=outlook)


async def send_news(
    channel: discord.abc.Messageable,
    entry: feedparser.FeedParserDict,
    feed_title: str,
    published_at: datetime,
) -> None:
    url = entry.get("link") or "https://discord.com"
    title = entry.get("title") or "(Untitled)"
    analysis = await analyze_entry(entry)

    embed = Embed(title=title, url=url, description=analysis.summary)
    embed.set_author(name=f"{feed_title} • News Watch")
    embed.timestamp = published_at
    embed.set_footer(text=feed_title)

    embed.add_field(name="📈 Dampak Crypto", value=analysis.crypto, inline=False)
    embed.add_field(name="🟡 Dampak Emas", value=analysis.gold, inline=False)
    embed.add_field(name="🔮 Outlook", value=analysis.outlook, inline=False)

    thumbnail = entry.get("media_thumbnail") or entry.get("media_content")
    if thumbnail:
        image_url = thumbnail[0].get("url")
        if image_url:
            embed.set_thumbnail(url=image_url)

    await channel.send(embed=embed)
    logger.info("Mengirim berita: %s (%s)", title, feed_title)


async def poll_loop() -> None:
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID_INT)
    if channel is None:
        raise SystemExit(
            "Channel tidak ditemukan. Pastikan bot sudah join server dan DISCORD_CHANNEL_ID benar."
        )

    logger.info(
        "Mulai memantau %d feed setiap %d detik dengan pola: %s",
        len(FEEDS),
        POLL_SECONDS,
        KEYWORDS or "(tanpa filter)",
    )

    while not client.is_closed():
        for feed_url in FEEDS:
            try:
                parsed = await asyncio.to_thread(feedparser.parse, feed_url)
            except Exception as exc:  # pragma: no cover - log only
                logger.exception("Gagal memuat feed %s: %s", feed_url, exc)
                continue

            feed_title = parsed.feed.get("title") or feed_url
            entries: list[feedparser.FeedParserDict] = parsed.entries or []

            for entry in entries[:20]:
                uid = entry.get("id") or entry.get("guid") or entry.get("link")
                if not uid or not remember_uid(uid):
                    continue
                if match_entry(entry):
                    published_at = entry_timestamp(entry)
                    if MAX_AGE_HOURS > 0:
                        age_seconds = (datetime.now(timezone.utc) - published_at).total_seconds()
                        if age_seconds > MAX_AGE_HOURS * 3600:
                            logger.debug(
                                "Lewati berita lama (%.1f jam): %s", age_seconds / 3600, entry.get("title")
                            )
                            continue
                    await send_news(channel, entry, feed_title, published_at)

        await asyncio.sleep(POLL_SECONDS)


@client.event
async def on_ready() -> None:
    logger.info("Logged in sebagai %s (%s)", client.user, getattr(client.user, "id", ""))
    if not getattr(client, "poller_started", False):
        client.poller_started = True  # type: ignore[attr-defined]
        client.loop.create_task(poll_loop())


def main() -> None:
    client.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
