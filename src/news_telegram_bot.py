'''NEPSE News Telegram Bot

Fetches financial news headlines for NEPSE‑listed companies from multiple
Nepali financial news sources and sends them to a Telegram chat.

Supported sources (auto-detected by domain):
  • ShareSansar   – https://www.sharesansar.com/category/latest
  • MeroLagani    – https://merolagani.com/NewsList.aspx
  • NepseTrading  – https://nepsetrading.com/news

Configuration is read from a `.env` file:
    TELEGRAM_BOT_TOKEN   – Bot token from BotFather
    TELEGRAM_CHAT_ID     – Destination chat ID (integer or "@channelusername")
    COMPANY_LIST_PATH    – Path to a CSV/TXT file containing company names or tickers
    NEWS_URLS            – Comma-separated list of news source URLs
    NEWS_URL             – Fallback single URL (used if NEWS_URLS is empty)
'''

import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Set
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Nepal Standard Time
NPT = timezone(timedelta(hours=5, minutes=45))

# ─── Configuration ──────────────────────────────────────────────────────────────

def load_config() -> dict:
    """Load environment variables from .env and validate required keys."""
    env_path = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=env_path)
    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "COMPANY_LIST_PATH"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        sys.exit(f"Missing required env variables: {', '.join(missing)}")
    return {
        "token": os.getenv("TELEGRAM_BOT_TOKEN"),
        "chat_id": os.getenv("TELEGRAM_CHAT_ID"),
        "company_path": os.getenv("COMPANY_LIST_PATH"),
        "news_urls": (
            [url.strip() for url in os.getenv("NEWS_URLS", "").split(",") if url.strip()]
            or [os.getenv("NEWS_URL", "https://www.sharesansar.com/category/latest")]
        ),
    }


def load_company_names(path: str) -> Set[str]:
    """Read a CSV or plain‑text file and return a set of normalized company names.

    The file can be a CSV with a column named `name` or `ticker`; any other
    columns are ignored. Blank lines are skipped.
    """
    p = Path(path)
    if not p.exists():
        sys.exit(f"Company list file not found: {path}")
    names: Set[str] = set()
    if p.suffix.lower() == ".csv":
        import csv
        with p.open(newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                for col in ("name", "ticker", "company", "symbol"):
                    if col in row and row[col].strip():
                        names.add(row[col].strip().lower())
    else:
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                names.add(line.lower())
    return names


# ─── Source‑specific parsers ────────────────────────────────────────────────────

HEADERS = {"User-Agent": "Mozilla/5.0 (NEPSE-NewsBot/1.0)"}


def _parse_sharesansar(soup: BeautifulSoup, base: str) -> List[dict]:
    """Parse ShareSansar news page.

    Structure: <a href="..."><h4 class="featured-news-title">Title</h4></a>
    """
    items: List[dict] = []
    for heading in soup.select("h4.featured-news-title"):
        title = heading.get_text(strip=True)
        # The h4 is wrapped inside an <a> parent
        parent = heading.parent
        link = ""
        if parent and parent.name == "a":
            link = parent.get("href", "")
        if not link:
            # Fallback: look for nearest <a> in the enclosing div
            wrapper = heading.find_parent("div")
            if wrapper:
                a = wrapper.find("a")
                if a:
                    link = a.get("href", "")
        if not link.startswith("http"):
            link = f"https://www.sharesansar.com{link}"
        if title:
            items.append({"title": title, "link": link, "source": "ShareSansar"})
    return items


def _parse_merolagani(soup: BeautifulSoup, base: str) -> List[dict]:
    """Parse MeroLagani news list (h4.media-title a)."""
    items: List[dict] = []
    for heading in soup.select("h4.media-title a"):
        title = heading.get_text(strip=True)
        link = heading.get("href", "")
        if not link.startswith("http"):
            link = f"https://merolagani.com{link}"
        if title:
            items.append({"title": title, "link": link, "source": "MeroLagani"})
    return items


def _parse_nepsetrading(soup: BeautifulSoup, base: str) -> List[dict]:
    """Parse NepseTrading news (article links with meaningful text)."""
    items: List[dict] = []
    seen_links: set = set()
    for article in soup.select("article"):
        for a in article.select("a"):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if not href or not text or len(text) < 10:
                continue
            if not href.startswith("http"):
                href = f"https://nepsetrading.com{href}"
            if href not in seen_links:
                seen_links.add(href)
                items.append({"title": text, "link": href, "source": "NepseTrading"})
    return items


def _parse_generic(soup: BeautifulSoup, base: str) -> List[dict]:
    """Fallback parser — look for anchor tags inside headings."""
    items: List[dict] = []
    for tag in soup.select("h1 a, h2 a, h3 a, h4 a, h5 a"):
        text = tag.get_text(strip=True)
        href = tag.get("href", "")
        if text and href and len(text.split()) >= 3:
            if not href.startswith("http"):
                href = f"{base}{href}"
            items.append({"title": text, "link": href, "source": urlparse(base).netloc})
    return items


# Map domain substrings → parser functions
_PARSERS = {
    "sharesansar": _parse_sharesansar,
    "merolagani": _parse_merolagani,
    "nepsetrading": _parse_nepsetrading,
}


def _get_parser(url: str):
    """Return the best parser for a given URL based on domain."""
    domain = urlparse(url).netloc.lower()
    for key, parser in _PARSERS.items():
        if key in domain:
            return parser
    return _parse_generic


# ─── Fetching ───────────────────────────────────────────────────────────────────

def fetch_headlines(url: str) -> List[dict]:
    """Scrape a single news page and return a list of headline dicts."""
    resp = requests.get(url, timeout=15, headers=HEADERS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    parser = _get_parser(url)
    return parser(soup, base)


def fetch_all_headlines(urls: List[str]) -> List[dict]:
    """Fetch headlines from multiple news URLs and deduplicate by title+link."""
    seen: set = set()
    all_items: List[dict] = []
    for u in urls:
        try:
            items = fetch_headlines(u)
            print(f"[INFO] {u} → {len(items)} headlines")
        except Exception as e:
            print(f"[WARN] Failed to fetch {u}: {e}")
            continue
        for it in items:
            key = (it["title"], it["link"])
            if key not in seen:
                seen.add(key)
                all_items.append(it)
    return all_items


# ─── Filtering ──────────────────────────────────────────────────────────────────

def filter_by_companies(headlines: List[dict], companies: Set[str]) -> List[dict]:
    """Return only headlines that mention any company name/ticker.

    Matching is case‑insensitive and looks for whole‑word occurrences.
    """
    pattern = re.compile(
        r"\b(" + "|".join(map(re.escape, companies)) + r")\b",
        re.IGNORECASE,
    )
    return [item for item in headlines if pattern.search(item["title"])]


# ─── Formatting ─────────────────────────────────────────────────────────────────

def format_message(items: List[dict]) -> str:
    """Create a Markdown‑formatted message grouped by source."""
    now = datetime.now(NPT).strftime("%Y-%m-%d")
    if not items:
        return f"📰 *NEPSE Daily News — {now}*\n\n_No relevant headlines found today._"

    lines = [f"📰 *NEPSE Daily News — {now}*\n"]

    # Group by source
    by_source: dict = {}
    for it in items:
        src = it.get("source", "Unknown")
        by_source.setdefault(src, []).append(it)

    for source, headlines in by_source.items():
        lines.append(f"\n*{source}*")
        for it in headlines:
            title = it["title"].replace("_", "\\_").replace("*", "\\*")
            lines.append(f"• [{title}]({it['link']})")

    lines.append(f"\n_Total: {len(items)} headlines_")
    return "\n".join(lines)


# ─── Telegram ───────────────────────────────────────────────────────────────────

def send_to_telegram(token: str, chat_id: str, text: str) -> None:
    """Send a Markdown message via the Telegram Bot API.

    Automatically splits long messages into chunks of ≤4096 characters.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    max_len = 4096

    chunks = []
    if len(text) <= max_len:
        chunks.append(text)
    else:
        # Split on newlines to avoid breaking markdown
        current = ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > max_len:
                chunks.append(current)
                current = line
            else:
                current = f"{current}\n{line}" if current else line
        if current:
            chunks.append(current)

    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()


# ─── Main ───────────────────────────────────────────────────────────────────────

def main():
    cfg = load_config()
    companies = load_company_names(cfg["company_path"]).union({"nepse"})
    print(f"[INFO] Tracking {len(companies)} companies/keywords")

    # Fetch from all configured news URLs
    headlines = fetch_all_headlines(cfg["news_urls"])[:200]
    print(f"[INFO] Total unique headlines: {len(headlines)}")

    relevant = filter_by_companies(headlines, companies)
    print(f"[INFO] Relevant headlines: {len(relevant)}")

    message = format_message(relevant)
    send_to_telegram(cfg["token"], cfg["chat_id"], message)
    print("[INFO] Message sent to Telegram ✅")


if __name__ == "__main__":
    main()
