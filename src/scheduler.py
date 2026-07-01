"""NEPSE News Scheduler

Long-running process that triggers the NEPSE news Telegram bot every day at a
configurable time (default 07:00 Nepal Standard Time, UTC+5:45).

Usage:
    python -m src.scheduler          # runs forever, sends news daily at 07:00
    python -m src.scheduler --now    # send immediately then exit (for testing)
"""

import os
import signal
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import schedule
from dotenv import load_dotenv

# Ensure the package root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.news_telegram_bot import main as send_news  # noqa: E402

# Nepal Standard Time offset
NPT = timezone(timedelta(hours=5, minutes=45))


def _now_npt() -> str:
    """Return current Nepal time as HH:MM:SS string (for logging)."""
    return datetime.now(NPT).strftime("%Y-%m-%d %H:%M:%S NPT")


def job():
    """Wrapper that runs the news bot and logs the outcome."""
    print(f"[{_now_npt()}] Running NEPSE news job …")
    try:
        send_news()
        print(f"[{_now_npt()}] ✅ News sent successfully.")
    except Exception as exc:
        print(f"[{_now_npt()}] ❌ Job failed: {exc}")


def _graceful_exit(signum, _frame):
    """Handle SIGINT / SIGTERM so the process can be stopped cleanly."""
    print(f"\n[{_now_npt()}] Received signal {signum}. Shutting down.")
    sys.exit(0)


def main():
    # Load .env so SCHEDULE_TIME is available
    env_path = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=env_path)

    # --now flag: run once immediately (handy for testing)
    if "--now" in sys.argv:
        job()
        return

    run_time = os.getenv("SCHEDULE_TIME", "07:00")

    # Register the daily job
    schedule.every().day.at(run_time).do(job)

    # Graceful shutdown on Ctrl-C or kill
    signal.signal(signal.SIGINT, _graceful_exit)
    signal.signal(signal.SIGTERM, _graceful_exit)

    print(f"[{_now_npt()}] Scheduler started. News will be sent daily at {run_time} NPT.")
    print(f"[{_now_npt()}] Next run: {schedule.next_run()}")
    print("Press Ctrl+C to stop.\n")

    while True:
        schedule.run_pending()
        time.sleep(30)  # check every 30 seconds


if __name__ == "__main__":
    main()
