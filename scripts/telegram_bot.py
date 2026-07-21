"""
Telegram Bot — Sends trade signals, EOD reports, and alerts.
Uses python-telegram-bot library for async Telegram API.
"""

import json
import logging
import asyncio
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config/telegram.json")


def load_telegram_config() -> dict:
    """Load Telegram bot token and chat ID from config."""
    if not CONFIG_PATH.exists():
        logger.error(f"Telegram config not found at {CONFIG_PATH}")
        return {}
    with open(CONFIG_PATH) as f:
        return json.load(f)


def format_trade_card(trade_card: dict) -> str:
    """Format a trade card into a Telegram-friendly message."""
    if trade_card.get("action") == "skip":
        reason = trade_card.get("reason", "No clear signal")
        conditions = trade_card.get("conditions", {})
        us = conditions.get("us_change_pct", 0)
        vix = conditions.get("vix_change_pct", 0)
        return (
            f"📊 *Options Tycoon — No Signal Today*\n\n"
            f"Reason: {reason}\n"
            f"US: {us:+.1f}% | VIX: {vix:+.1f}%\n\n"
            f"_Sitting out today. Capital preserved._"
        )
    
    direction = trade_card.get("direction", "?").upper()
    confidence = trade_card.get("confidence", 0)
    trade = trade_card.get("trade", {})
    reasoning = trade_card.get("reasoning", "")
    conditions = trade_card.get("conditions", {})
    risk_check = trade_card.get("risk_check", {})
    
    # Direction emoji
    dir_emoji = "🐻" if direction == "BEARISH" else "🐂" if direction == "BULLISH" else "⚖️"
    
    # Format legs
    legs_text = ""
    for leg in trade.get("legs", []):
        action_emoji = "🟢" if leg["action"] == "BUY" else "🔴"
        legs_text += f"  {action_emoji} {leg['action']} NIFTY {leg['strike']} {leg['option']} @ ₹{leg['premium_est']}\n"
    
    # Risk/Reward
    max_profit = trade.get("max_profit", 0)
    max_loss = trade.get("max_loss", 0)
    rr = trade.get("risk_reward", 0)
    
    msg = (
        f"{dir_emoji} *NIFTY Signal: {direction} ({confidence}% confidence)*\n\n"
        f"📈 *US:* {conditions.get('us_change_pct', 0):+.1f}% | "
        f"*VIX:* {conditions.get('vix_change_pct', 0):+.1f}% | "
        f"*DXY:* {conditions.get('dxy_change_pct', 0):+.1f}%\n\n"
        f"🎯 *Strategy: {trade.get('type', '?').replace('_', ' ').title()}*\n"
        f"{legs_text}\n"
        f"💰 *Cost:* ₹{trade.get('net_cost_total', 0):,.0f} | "
        f"*Max Profit:* ₹{max_profit:,.0f}\n"
        f"⚠️ *Max Loss:* ₹{max_loss:,.0f} | "
        f"*R:R =* {rr}:1\n"
        f"🛑 *SL:* ₹{trade.get('sl_value', 0):,.0f}\n\n"
        f"📝 *Why:* {reasoning}\n\n"
        f"_Risk: {risk_check.get('max_loss_pct', 0):.1f}% of capital_\n\n"
        f"🚀 Execute at market open → http://127.0.0.1:8082/static/live.html"
    )
    
    return msg


def format_eod_report(eod_data: dict) -> str:
    """Format EOD report for Telegram."""
    pnl = eod_data.get("today_pnl", 0)
    pnl_emoji = "📈" if pnl >= 0 else "📉"
    
    gate_status = eod_data.get("gate_status", {})
    gates_met = sum(1 for v in gate_status.get("metrics", {}).values() if v)
    total_gates = len(gate_status.get("metrics", {}))
    locked = gate_status.get("locked", True)
    lock_emoji = "🔒" if locked else "🟢"
    
    positions = eod_data.get("open_positions", [])
    pos_text = ""
    if positions:
        for p in positions[:5]:
            pos_text += f"  • {p.get('strategy', '?')}: ₹{p.get('pnl', 0):+,.0f}\n"
    else:
        pos_text = "  No open positions\n"
    
    msg = (
        f"{pnl_emoji} *EOD Report — Options Tycoon*\n\n"
        f"💰 *Today's P&L:* ₹{pnl:+,.0f}\n\n"
        f"📋 *Open Positions:*\n{pos_text}\n"
        f"{lock_emoji} *Gates:* {gates_met}/{total_gates} met "
        f"{'(Paper Mode)' if locked else '(LIVE)'}\n\n"
    )
    
    # Show individual gate metrics
    metrics = gate_status.get("metrics_detail", {})
    if metrics:
        msg += "*Gate Details:*\n"
        for name, passed in metrics.items():
            emoji = "✅" if passed else "❌"
            msg += f"  {emoji} {name}\n"
    
    return msg


def format_alert(alert_type: str, message: str) -> str:
    """Format system alerts for Telegram."""
    emojis = {
        "daily_loss_cap": "⚠️",
        "relock": "🔒",
        "eligible": "🟢",
        "error": "🚨",
    }
    emoji = emojis.get(alert_type, "ℹ️")
    return f"{emoji} *Alert — Options Tycoon*\n\n{message}"


async def send_message(text: str, parse_mode: str = "Markdown") -> bool:
    """Send a message via Telegram Bot API."""
    config = load_telegram_config()
    bot_token = config.get("bot_token", "")
    chat_id = config.get("chat_id", "")
    
    if not bot_token or not chat_id or "YOUR_" in bot_token:
        logger.warning("Telegram not configured — printing to console instead")
        print("\n" + "=" * 60)
        print("TELEGRAM MESSAGE (not sent - bot not configured):")
        print("=" * 60)
        print(text.replace("*", "").replace("_", ""))
        print("=" * 60 + "\n")
        return False
    
    try:
        import telegram
        bot = telegram.Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        logger.info("Telegram message sent successfully")
        return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        # Fallback: print to console
        print(f"\n[TELEGRAM FAILED: {e}]\n{text}\n")
        return False


def send_signal(trade_card: dict) -> bool:
    """Send trade signal via Telegram (sync wrapper, safe from async context)."""
    text = format_trade_card(trade_card)
    try:
        return asyncio.run(send_message(text))
    except RuntimeError:
        # Already in an async event loop (e.g., called from FastAPI via ThreadPoolExecutor)
        # Create a new event loop in this thread
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(send_message(text))
        finally:
            loop.close()


def send_eod(eod_data: dict) -> bool:
    """Send EOD report via Telegram (sync wrapper)."""
    text = format_eod_report(eod_data)
    return asyncio.run(send_message(text))


def send_alert(alert_type: str, message: str) -> bool:
    """Send alert via Telegram (sync wrapper)."""
    text = format_alert(alert_type, message)
    return asyncio.run(send_message(text))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test with today's signal if available
    signal_path = Path("output/today_signal.json")
    if signal_path.exists():
        with open(signal_path) as f:
            trade_card = json.load(f)
        send_signal(trade_card)
    else:
        # Test with a sample
        sample = {
            "action": "trade",
            "direction": "bearish",
            "confidence": 72,
            "strategy_type": "bear_put_spread",
            "trade": {
                "type": "bear_put_spread",
                "legs": [
                    {"action": "BUY", "option": "PE", "strike": 24400, "premium_est": 85},
                    {"action": "SELL", "option": "PE", "strike": 24200, "premium_est": 35},
                ],
                "net_cost_total": 2500,
                "max_profit": 7500,
                "max_loss": 2500,
                "sl_value": 1250,
                "risk_reward": 3.0,
            },
            "reasoning": "US fell 1.1%. VIX spiked. 18/25 similar days saw NIFTY fall.",
            "conditions": {"us_change_pct": -1.1, "vix_change_pct": 12.0, "dxy_change_pct": 0.3},
            "risk_check": {"max_loss_pct": 2.0},
        }
        send_signal(sample)
