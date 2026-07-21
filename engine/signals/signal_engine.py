"""
Signal Engine — Main orchestrator for morning trade signal generation.
Runs daily at 10:30 AM PHT (08:00 IST) via Windows Task Scheduler.

Flow:
1. Fetch overnight global data (yfinance)
2. Run pattern matching against 5-year NIFTY history
3. Pick strategy + calculate strikes
4. Generate trade card JSON
5. Send via Telegram
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from engine.signals.data_fetcher import fetch_global_data
from engine.signals.pattern_matcher import generate_pattern_signal
from engine.signals.strategy_picker import generate_trade_card
from engine.signals.stock_scanner import scan_all_stocks, format_stock_signal
from engine.signals.quality_filters import run_all_filters
from db.signal_history import save_signal

# Import telegram bot from scripts
sys.path.insert(0, str(ROOT / "scripts"))
from telegram_bot import send_signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(ROOT / "output" / "signal_engine.log", mode="a"),
    ]
)
logger = logging.getLogger("signal_engine")


def run_morning_signal():
    """
    Complete morning signal generation pipeline.
    Called by Task Scheduler at 10:30 AM PHT daily.
    """
    logger.info("=" * 60)
    logger.info(f"Signal Engine started at {datetime.now().isoformat()}")
    logger.info("=" * 60)
    
    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    
    # Step 1: Fetch global data
    logger.info("Step 1: Fetching overnight global data...")
    try:
        global_data = fetch_global_data(str(output_dir))
    except Exception as e:
        logger.error(f"Data fetch failed: {e}")
        skip_card = {"action": "skip", "reason": f"Data fetch error: {str(e)[:100]}", "conditions": {}, "date": datetime.now().strftime("%Y-%m-%d")}
        send_signal(skip_card)
        return skip_card
    
    if global_data.get("status") == "failed":
        logger.error("All data sources failed")
        skip_card = {"action": "skip", "reason": "All data sources failed. No signal today.", "conditions": {}, "date": datetime.now().strftime("%Y-%m-%d")}
        send_signal(skip_card)
        return skip_card
    
    logger.info(f"Data fetched: status={global_data['status']}, errors={len(global_data.get('errors', []))}")
    
    # Step 2: Pattern matching
    logger.info("Step 2: Running pattern matching...")
    try:
        pattern_result = generate_pattern_signal(global_data)
    except Exception as e:
        logger.error(f"Pattern matching failed: {e}")
        skip_card = {"action": "skip", "reason": f"Pattern matching error: {str(e)[:100]}", "conditions": {}, "date": datetime.now().strftime("%Y-%m-%d")}
        send_signal(skip_card)
        return skip_card
    
    logger.info(f"Pattern result: direction={pattern_result.get('direction')}, "
                f"confidence={pattern_result.get('confidence')}%")
    
    # Step 3: Generate trade card
    logger.info("Step 3: Generating trade card...")
    projected_open = global_data.get("data", {}).get("gift_nifty", {})
    if isinstance(projected_open, dict):
        projected_open = projected_open.get("last_close", 24500)
    
    try:
        trade_card = generate_trade_card(pattern_result, projected_open)
    except Exception as e:
        logger.error(f"Strategy picker failed: {e}")
        skip_card = {"action": "skip", "reason": f"Strategy error: {str(e)[:100]}", "conditions": {}, "date": datetime.now().strftime("%Y-%m-%d")}
        send_signal(skip_card)
        return skip_card
    
    # Add timestamp
    trade_card["timestamp"] = datetime.now().isoformat()
    trade_card["date"] = datetime.now().strftime("%Y-%m-%d")
    
    # Step 4: Run 7 quality filters
    logger.info("Step 4: Running quality filters...")
    filter_results = run_all_filters(global_data, pattern_result, trade_card)
    trade_card["quality_filters"] = filter_results
    
    # Filters determine POSITION SIZE, not whether to trade
    # Only skip if literally no edge exists (0-2 filters)
    if filter_results["passed"] < 3 and trade_card.get("action") == "trade":
        logger.info(f"Filters: {filter_results['passed']}/7 — No edge. Sitting out.")
        trade_card["action"] = "skip"
        trade_card["reason"] = f"Only {filter_results['passed']}/7 filters passed. No edge today — preserving capital."
        trade_card["failed_reasons"] = filter_results.get("failed_reasons", [])
    else:
        # Add position sizing recommendation based on filter score
        trade_card["position_sizing"] = filter_results.get("position_sizing", {})
        logger.info(f"Filters: {filter_results['passed']}/7 — {filter_results['strength']}. "
                    f"Size: {filter_results.get('position_sizing', {}).get('label', '?')}")
    
    # Step 4: Save trade card to output
    signal_path = output_dir / "today_signal.json"
    with open(signal_path, "w") as f:
        json.dump(trade_card, f, indent=2, default=str)
    logger.info(f"Trade card saved to {signal_path}")
    
    # Step 4b: Scan watchlist stocks for additional signals
    logger.info("Step 4b: Scanning watchlist stocks...")
    try:
        stock_signals = scan_all_stocks(global_data)
        trade_card["stock_signals"] = stock_signals
        # Re-save with stock signals included
        with open(signal_path, "w") as f:
            json.dump(trade_card, f, indent=2, default=str)
        if stock_signals:
            logger.info(f"Stock signals: {len(stock_signals)} found")
            for s in stock_signals:
                logger.info(f"  {s['name']}: {s['direction'].upper()} ({s['confidence']}%)")
        else:
            logger.info("No stock signals above threshold today")
    except Exception as e:
        logger.warning(f"Stock scanner failed (non-fatal): {e}")
        trade_card["stock_signals"] = []
    
    # Step 5: Send via Telegram
    logger.info("Step 5: Sending Telegram notification...")
    try:
        send_signal(trade_card)
        logger.info("Telegram sent successfully")
    except Exception as e:
        logger.warning(f"Telegram send failed (non-fatal): {e}")
    
    # Step 6: Save to signal history (append-only, never overwrites)
    logger.info("Step 6: Saving to signal history database...")
    try:
        row_id = save_signal(trade_card)
        if row_id:
            logger.info(f"Signal persisted to DB: row_id={row_id}")
        else:
            logger.warning("Signal save returned None — check DB connection")
    except Exception as e:
        logger.warning(f"Signal history save failed (non-fatal): {e}")
    
    # Summary
    action = trade_card.get("action", "?")
    if action == "trade":
        trade = trade_card.get("trade", {})
        logger.info(f"SIGNAL GENERATED: {trade_card['direction'].upper()} "
                    f"({trade_card['confidence']}%) - {trade.get('type', '?')} "
                    f"Max loss: Rs.{trade.get('max_loss', 0):,.0f}")
    else:
        logger.info(f"SKIPPED: {trade_card.get('reason', 'No clear signal')}")
    
    logger.info("Signal Engine complete.")
    return trade_card


if __name__ == "__main__":
    run_morning_signal()
