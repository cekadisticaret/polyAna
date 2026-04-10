"""
Polymarket Analyzer - Ana giriş noktası.

Cron:
  10 * * * * … python -m src.main open    — her saat :10 geçe tahmin + (POLYMARKET_BOT_ENABLED ise emir) + Saatlik Tahminler
  15 * * * * … python -m src.main resolve — DB çözümü + gün özeti
"""
import argparse
import logging
import sys

from src.analyzer.pipeline import run_hourly_cycle_open, run_hourly_cycle_resolve_summary
from src.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket saatlik pipeline")
    parser.add_argument(
        "mode",
        nargs="?",
        default="open",
        choices=["open", "resolve"],
        help="open: tahmin+emir+Saatlik Tahminler; resolve: Gamma çözümü DB+gün özeti",
    )
    args = parser.parse_args()

    issues = Config.validate()
    if issues:
        for i in issues:
            logger.warning("Config: %s", i)

    logger.info("Polymarket Analyzer başlatıldı (mode=%s)", args.mode)
    if args.mode == "open":
        run_hourly_cycle_open()
    else:
        run_hourly_cycle_resolve_summary()
    logger.info("Döngü tamamlandı")


if __name__ == "__main__":
    main()
