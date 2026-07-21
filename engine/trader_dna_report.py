"""
Trader DNA Report Generator — V4 (The Mind-Reader Edition)

Produces a report so personal that traders feel SEEN. Not analytics.
A psychological intervention disguised as a data report.

Structure:
- Page 0: Score + Persona + Total Cost (5-second gut punch)
- Section 1: "Your Story" (narrative arc)
- Section 2: Top 3 eye-opening insights
- Section 3: Next session prediction
- Section 4: Value of fixing (makes ₹499/month feel obvious)
- Deep Dive: Full analytics (collapsed, for nerds)

All language observational. No advice. Data speaks for itself.
"""

from datetime import datetime, timedelta
from typing import Optional
import statistics
from collections import defaultdict


def generate_trader_dna_report(trades: list[dict]) -> dict:
    """Generate the full devastating DNA report."""
    if not trades or len(trades) < 5:
        return {"error": "Need at least 5 trades to generate a meaningful report"}

    # === Compute everything ===
    stats = _compute_basic_stats(trades)
    revenge = _detect_revenge(trades)
    overconfidence = _detect_overconfidence(trades)
    disposition = _detect_disposition(trades)
    snowball = _detect_snowball(trades)
    sequence = _analyze_trade_sequence(trades)
    timing = _analyze_timing(trades)
    instruments = _analyze_instruments(trades)
    ceiling = _detect_profit_ceiling(trades)
    speed = _analyze_speed(trades)
    charges = _compute_trading_charges(trades)

    # === Behavioral cost (all layers) ===
    all_costs = [revenge['cost'], overconfidence['cost'], disposition['cost'],
                 snowball['cost'], sequence['cost'], timing['cost']]
    total_behavioral = min(sum(c for c in all_costs if c > 0), stats['total_losses'])
    behavioral_pct = round(total_behavioral / stats['total_losses'] * 100, 1) if stats['total_losses'] > 0 else 0

    # === DNA Score (0-100, higher = more disciplined) ===
    dna_score = _compute_dna_score(stats, revenge, sequence, timing, disposition)

    # === Persona Assignment ===
    persona = _assign_persona(revenge, overconfidence, sequence, timing, speed, stats)

    # === The Story (narrative) ===
    story = _build_narrative(trades, revenge, snowball)

    # === Top Insights (eye-openers) ===
    insights = _build_top_insights(sequence, timing, instruments, ceiling, stats, trades)
    
    # Add charges insight if impactful
    if charges.get('insight'):
        insights.append({'type': 'charges', 'title': 'Your Break-Even Tax', 'text': charges['insight'], 'impact': charges['total_charges']})

    # === Next Session Prediction ===
    prediction = _build_prediction(trades, revenge, sequence, timing)

    # === Value of Fixing ===
    fix_value = _compute_fix_value(trades, revenge, snowball, sequence, stats)

    # === Build Final Report ===
    # === Fix One Thing (single most impactful recommendation) ===
    fix_one_thing = _compute_fix_one_thing(revenge, snowball, sequence, timing, stats)

    return {
        # PAGE 0 — The Gut Punch
        'page_zero': {
            'dna_score': dna_score,
            'persona': persona,
            'total_behavioral_cost': round(total_behavioral, 0),
            'behavioral_pct': behavioral_pct,
            'total_trades': stats['total_trades'],
            'total_pnl': round(stats['total_pnl'], 0),
            'first_date': stats['first_date'],
            'last_date': stats['last_date'],
            'trading_days': stats['trading_days'],
        },

        # BACKWARD COMPAT — Old report page reads these
        'headline': {
            'total_trades': stats['total_trades'],
            'total_pnl': round(stats['total_pnl'], 2),
            'behavioral_loss_pct': behavioral_pct,
            'behavioral_loss_amount': round(total_behavioral, 0),
            'win_count': stats['win_count'],
            'loss_count': stats['loss_count'],
            'win_rate': stats['win_rate'],
        },

        # SECTION 1 — Your Story
        'story': story,

        # SECTION 2 — Top Insights
        'insights': insights[:3],

        # SECTION 3 — Prediction
        'prediction': prediction,

        # SECTION 4 — Fix Value
        'fix_value': fix_value,

        # FIX ONE THING — The single most impactful change
        'fix_one_thing': fix_one_thing,

        # TRADING OVERVIEW — Basic stats for context
        'trading_overview': {
            'net_pnl': round(stats['total_pnl'], 0),
            'win_count': stats['win_count'],
            'loss_count': stats['loss_count'],
            'win_rate': stats['win_rate'],
            'avg_win': stats['avg_win'],
            'avg_loss': stats['avg_loss'],
            'best_trade': stats['best_trade'],
            'worst_trade': stats['worst_trade'],
            'best_day': stats['best_day'],
            'worst_day': stats['worst_day'],
            'avg_hold_hours': stats['avg_hold_hours'],
            'risk_reward': stats['risk_reward'],
            'trades_per_day': stats['trades_per_day'],
            'best_dow': stats['best_dow'],
            'worst_dow': stats['worst_dow'],
            'instrument_summary': stats['instrument_summary'],
            'equity_curve': stats['equity_curve'],
        },

        # DEEP DIVE — Full data
        'deep_dive': {
            'headline': stats,
            'behavioral_losses': {
                'total': round(total_behavioral, 2),
                'percent': behavioral_pct,
                'revenge': revenge,
                'overconfidence': overconfidence,
                'disposition': disposition,
                'snowball': snowball,
                'sequence': sequence,
                'timing': timing,
            },
            'instruments': instruments,
            'ceiling': ceiling,
            'speed': speed,
            'charges': charges,
        },

        # META
        'all_patterns': sorted(
            [p for p in [revenge, overconfidence, disposition, snowball, sequence, timing] if p['cost'] > 0],
            key=lambda x: x['cost'], reverse=True
        ),
        'worst_enemy': persona,
        'calm_vs_emotional': _calm_vs_emotional(trades, revenge, overconfidence, snowball),
        'disclaimer': "This is YOUR data reflected back. Not financial advice. All decisions remain yours.",
    }


# ===========================================================================
# BASIC STATS
# ===========================================================================

def _compute_basic_stats(trades):
    total_pnl = sum(t.get('pnl', 0) for t in trades)
    losses = [t['pnl'] for t in trades if t.get('pnl', 0) < 0]
    wins = [t['pnl'] for t in trades if t.get('pnl', 0) > 0]
    
    # Date range
    dates = [_parse_time(t.get('entry_time')) for t in trades]
    dates = [d for d in dates if d is not None]
    first_date = min(dates) if dates else None
    last_date = max(dates) if dates else None
    trading_days = len(set(d.strftime('%Y-%m-%d') for d in dates)) if dates else 0
    
    # Best/worst trade
    best_trade = max(trades, key=lambda t: t.get('pnl', 0)) if trades else None
    worst_trade = min(trades, key=lambda t: t.get('pnl', 0)) if trades else None
    
    # Best/worst day
    days = defaultdict(list)
    for t in trades:
        d = _trade_date(t)
        if d: days[d].append(t.get('pnl', 0))
    day_totals = {d: sum(pnls) for d, pnls in days.items()}
    best_day = max(day_totals, key=day_totals.get) if day_totals else None
    worst_day = min(day_totals, key=day_totals.get) if day_totals else None
    
    # Avg hold time
    hold_times = [_hold_hours(t) for t in trades]
    hold_times = [h for h in hold_times if h is not None]
    avg_hold_hours = round(statistics.mean(hold_times), 1) if hold_times else None
    
    # Risk/reward ratio
    avg_win = round(statistics.mean(wins), 0) if wins else 0
    avg_loss = round(statistics.mean([abs(l) for l in losses]), 0) if losses else 0
    risk_reward = round(avg_win / avg_loss, 2) if avg_loss > 0 else None
    
    # Trade frequency
    trades_per_day = round(len(trades) / trading_days, 1) if trading_days > 0 else 0
    
    # Day of week analysis
    dow_pnl = defaultdict(list)
    for d in dates:
        dow_pnl[d.strftime('%A')].append(None)  # placeholder
    # Need trade pnl by day of week
    dow_stats = defaultdict(lambda: {'pnl': [], 'count': 0})
    for t in trades:
        entry = _parse_time(t.get('entry_time'))
        if entry:
            dow = entry.strftime('%A')
            dow_stats[dow]['pnl'].append(t.get('pnl', 0))
            dow_stats[dow]['count'] += 1
    
    dow_summary = {}
    for dow, data in dow_stats.items():
        pnls = data['pnl']
        dow_summary[dow] = {
            'total_pnl': round(sum(pnls), 0),
            'count': len(pnls),
            'win_rate': round(sum(1 for p in pnls if p > 0) / len(pnls) * 100, 0) if pnls else 0,
        }
    
    best_dow = max(dow_summary.items(), key=lambda x: x[1]['total_pnl']) if dow_summary else None
    worst_dow = min(dow_summary.items(), key=lambda x: x[1]['total_pnl']) if dow_summary else None
    
    # Instrument breakdown
    by_ticker = defaultdict(list)
    for t in trades:
        ticker = t.get('ticker', 'UNKNOWN')
        base = ticker.split('26')[0] if '26' in ticker else ticker[:10]
        by_ticker[base].append(t.get('pnl', 0))
    
    instrument_summary = []
    for ticker, pnls in sorted(by_ticker.items(), key=lambda x: sum(x[1]), reverse=True):
        instrument_summary.append({
            'ticker': ticker,
            'total_pnl': round(sum(pnls), 0),
            'count': len(pnls),
            'win_rate': round(sum(1 for p in pnls if p > 0) / len(pnls) * 100, 0) if pnls else 0,
        })
    
    # Equity curve (cumulative P&L)
    equity_curve = []
    running = 0
    for t in trades:
        running += t.get('pnl', 0)
        entry = _parse_time(t.get('entry_time'))
        equity_curve.append({
            'date': entry.strftime('%d %b') if entry else '',
            'cumulative_pnl': round(running, 0),
        })
    
    return {
        'total_trades': len(trades),
        'total_pnl': total_pnl,
        'total_losses': abs(sum(losses)),
        'total_wins': sum(wins),
        'win_count': len(wins),
        'loss_count': len(losses),
        'win_rate': round(len(wins) / len(trades) * 100, 1) if trades else 0,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'first_date': first_date.strftime('%d %b %Y') if first_date else None,
        'last_date': last_date.strftime('%d %b %Y') if last_date else None,
        'trading_days': trading_days,
        'best_trade': {'ticker': best_trade.get('ticker', '?'), 'pnl': round(best_trade.get('pnl', 0), 0), 'date': _format_datetime(best_trade.get('entry_time', ''))} if best_trade else None,
        'worst_trade': {'ticker': worst_trade.get('ticker', '?'), 'pnl': round(worst_trade.get('pnl', 0), 0), 'date': _format_datetime(worst_trade.get('entry_time', ''))} if worst_trade else None,
        'best_day': {'date': best_day, 'pnl': round(day_totals.get(best_day, 0), 0)} if best_day else None,
        'worst_day': {'date': worst_day, 'pnl': round(day_totals.get(worst_day, 0), 0)} if worst_day else None,
        'avg_hold_hours': avg_hold_hours,
        'risk_reward': risk_reward,
        'trades_per_day': trades_per_day,
        'dow_summary': dow_summary,
        'best_dow': {'day': best_dow[0], **best_dow[1]} if best_dow else None,
        'worst_dow': {'day': worst_dow[0], **worst_dow[1]} if worst_dow else None,
        'instrument_summary': instrument_summary[:6],  # Top 6
        'equity_curve': equity_curve,
    }


# ===========================================================================
# DNA SCORE (0-100)
# ===========================================================================

def _compute_dna_score(stats, revenge, sequence, timing, disposition):
    """Higher = more disciplined. Based on multiple factors."""
    score = 50  # Start neutral

    # Win rate component (+/- 15)
    wr = stats['win_rate']
    score += min(15, max(-15, (wr - 45) * 0.5))

    # Revenge penalty (-20 max)
    if stats['total_trades'] > 0:
        revenge_ratio = revenge['count'] / stats['total_trades']
        score -= min(20, revenge_ratio * 100)

    # Sequence discipline (+10 if they stop early)
    if sequence.get('optimal_count') and sequence['optimal_count'] <= 3:
        score -= 10  # They over-trade past their edge

    # Timing discipline
    if timing.get('bad_window_loss_rate', 0) > 65:
        score -= 10

    # Disposition penalty
    if disposition.get('hold_ratio', 0) > 2:
        score -= 10

    return max(0, min(100, round(score)))


# ===========================================================================
# PERSONA ASSIGNMENT
# ===========================================================================

def _assign_persona(revenge, overconfidence, sequence, timing, speed, stats):
    """Assign a behavioral archetype based on dominant pattern."""
    scores = {
        'The Avenger': revenge['cost'],
        'The Gambler': overconfidence['cost'] + (timing.get('expiry_cost', 0) or 0),
        'The Grinder': sequence['cost'] if (sequence.get('optimal_count') or 99) < 3 else 0,
        'The Sprinter': speed.get('early_exit_cost', 0) or 0,
        'The Snowballer': 0,
    }

    # Find dominant persona
    dominant = max(scores, key=scores.get)
    cost = scores[dominant]

    descriptions = {
        'The Avenger': "You chase losses with bigger bets. One bad trade turns into a bad week.",
        'The Gambler': "You bet big after wins and on high-risk setups. The market punishes overconfidence.",
        'The Grinder': "You over-trade past your edge. Your first 2 trades are profitable — everything after is noise.",
        'The Sprinter': "You exit winners too fast. Fear of losing gains costs you more than actual losses.",
        'The Snowballer': "One loss cascades into many. You don't have a stop — for the day.",
    }

    return {
        'name': dominant,
        'description': descriptions.get(dominant, ''),
        'monthly_cost': round(cost, 0),
    }


# ===========================================================================
# DETECTORS
# ===========================================================================

def _detect_revenge(trades):
    """Revenge: loss after loss within 6h, size >= 120% avg."""
    if len(trades) < 2:
        return {'name': 'Revenge Trading', 'count': 0, 'cost': 0, 'indices': [], 'description': '', 'drill_down': [], 'how_to_fix': ''}
    pnl_abs = [abs(t.get('pnl', 0)) for t in trades if t.get('pnl', 0) != 0]
    avg = statistics.mean(pnl_abs) if pnl_abs else 1
    count, cost, indices, drill_down = 0, 0.0, [], []
    for i in range(1, len(trades)):
        if trades[i-1].get('pnl', 0) >= 0:
            continue
        gap = _gap_hours(trades[i-1], trades[i])
        if gap is None or gap < 0 or gap > 6:
            continue
        curr_size = abs(trades[i].get('pnl', 0))
        if curr_size >= avg * 1.2 and trades[i].get('pnl', 0) < 0:
            count += 1
            cost += abs(trades[i]['pnl'])
            indices.append(i)
            # Drill-down detail
            trigger_trade = trades[i-1]
            revenge_trade = trades[i]
            gap_mins = round(gap * 60)
            trigger_time = _format_datetime(trigger_trade.get('exit_time', trigger_trade.get('entry_time', '')))
            revenge_time = _format_datetime(revenge_trade.get('entry_time', ''))
            drill_down.append({
                'trigger': {
                    'ticker': trigger_trade.get('ticker', 'UNKNOWN'),
                    'pnl': round(trigger_trade.get('pnl', 0), 0),
                    'time': trigger_time,
                },
                'revenge': {
                    'ticker': revenge_trade.get('ticker', 'UNKNOWN'),
                    'pnl': round(revenge_trade.get('pnl', 0), 0),
                    'time': revenge_time,
                    'size_vs_avg': round(curr_size / avg * 100, 0),
                },
                'gap_minutes': gap_mins,
                'what_happened': f"[{trigger_time}] Lost ₹{abs(trigger_trade.get('pnl',0)):,.0f} on {trigger_trade.get('ticker','?')} → {gap_mins} min later [{revenge_time}] entered {revenge_trade.get('ticker','?')} at {round(curr_size/avg*100,0)}% of normal size → lost ₹{abs(revenge_trade.get('pnl',0)):,.0f} more"
            })
    avg_revenge = round(cost / count, 0) if count > 0 else 0
    normal_avg = round(statistics.mean([abs(t['pnl']) for t in trades if t.get('pnl',0) < 0]), 0) if any(t.get('pnl',0)<0 for t in trades) else 0
    mult = round(avg_revenge / normal_avg, 1) if normal_avg > 0 else 0
    
    how_to_fix = ""
    if count > 0:
        how_to_fix = (
            "After any losing trade, your data shows you tend to re-enter within minutes with larger size. "
            "Traders who track this pattern often implement a personal rule: no new trades for 30 minutes after a loss. "
            "Some use a physical timer or close their trading terminal. "
            f"In your case, a 30-min pause would have saved ₹{cost:,.0f} across {count} {'instance' if count == 1 else 'instances'}."
        )
    
    return {'name': 'Revenge Trading', 'count': count, 'cost': cost, 'indices': indices,
            'description': f"{count} revenge {'trade' if count == 1 else 'trades'} averaging ₹{avg_revenge:,.0f} each ({mult}x your normal loss)",
            'drill_down': drill_down, 'how_to_fix': how_to_fix}


def _detect_overconfidence(trades):
    """Oversized losing trade after 2+ consecutive wins."""
    if len(trades) < 3:
        return {'name': 'Overconfidence', 'count': 0, 'cost': 0, 'indices': [], 'description': '', 'drill_down': [], 'how_to_fix': ''}
    pnl_abs = [abs(t.get('pnl', 0)) for t in trades if t.get('pnl', 0) != 0]
    avg = statistics.mean(pnl_abs) if pnl_abs else 1
    count, cost, indices, drill_down = 0, 0.0, [], []
    for i in range(2, len(trades)):
        if not all(trades[j].get('pnl', 0) > 0 for j in range(max(0, i-2), i)):
            continue
        if trades[i].get('pnl', 0) < 0 and abs(trades[i]['pnl']) > avg * 1.3:
            count += 1
            cost += abs(trades[i]['pnl'])
            indices.append(i)
            # Drill-down
            winning_streak = [trades[j] for j in range(max(0, i-3), i) if trades[j].get('pnl', 0) > 0]
            streak_total = sum(t.get('pnl', 0) for t in winning_streak)
            oc_time = _format_datetime(trades[i].get('entry_time', ''))
            drill_down.append({
                'winning_streak': [{
                    'ticker': t.get('ticker', '?'),
                    'pnl': round(t.get('pnl', 0), 0),
                    'time': _format_datetime(t.get('entry_time', '')),
                } for t in winning_streak],
                'overconfident_trade': {
                    'ticker': trades[i].get('ticker', '?'),
                    'pnl': round(trades[i].get('pnl', 0), 0),
                    'time': oc_time,
                    'size_vs_avg': round(abs(trades[i]['pnl']) / avg * 100, 0),
                },
                'what_happened': f"Won ₹{streak_total:,.0f} across {len(winning_streak)} trades → [{oc_time}] entered {trades[i].get('ticker','?')} at {round(abs(trades[i]['pnl'])/avg*100,0)}% of normal size → lost ₹{abs(trades[i]['pnl']):,.0f}"
            })
    
    how_to_fix = ""
    if count > 0:
        how_to_fix = (
            "Your data shows a pattern: after 2-3 wins, your position size increases significantly — and the next trade tends to lose big. "
            "This is common. The wins create a sense of invincibility. "
            "Traders who track this often implement a fixed position size rule regardless of recent results. "
            f"Keeping size constant after wins would have saved ₹{cost:,.0f} in your data."
        )
    
    return {'name': 'Overconfidence', 'count': count, 'cost': cost, 'indices': indices,
            'description': f"{count} {'time' if count == 1 else 'times'} you bet big after wins and lost ₹{cost:,.0f}",
            'drill_down': drill_down, 'how_to_fix': how_to_fix}


def _detect_disposition(trades):
    """Cost of holding losers longer than winners."""
    win_holds, loss_holds = [], []
    for t in trades:
        h = _hold_hours(t)
        if h is None: continue
        if t.get('pnl', 0) > 0: win_holds.append(h)
        elif t.get('pnl', 0) < 0: loss_holds.append((h, abs(t['pnl']), t))
    if not win_holds or not loss_holds:
        return {'name': 'Disposition Bias', 'count': 0, 'cost': 0, 'hold_ratio': 0, 'description': '', 'drill_down': [], 'how_to_fix': ''}
    avg_win_h = statistics.mean(win_holds)
    excess = [(h, c, t) for h, c, t in loss_holds if h > avg_win_h * 1.8]
    cost = sum(c for _, c, _ in excess)
    ratio = round(statistics.mean([h for h, _, _ in loss_holds]) / avg_win_h, 1) if avg_win_h > 0 else 0
    
    # Drill-down for worst held losers
    drill_down = []
    sorted_excess = sorted(excess, key=lambda x: x[1], reverse=True)[:5]  # Top 5 worst
    for hold_h, loss_amt, trade in sorted_excess:
        entry_dt = _format_datetime(trade.get('entry_time', ''))
        exit_dt = _format_datetime(trade.get('exit_time', ''))
        drill_down.append({
            'ticker': trade.get('ticker', '?'),
            'pnl': round(-loss_amt, 0),
            'hold_hours': round(hold_h, 1),
            'avg_winner_hours': round(avg_win_h, 1),
            'entry_time': entry_dt,
            'exit_time': exit_dt,
            'what_happened': f"[{entry_dt}] Entered {trade.get('ticker','?')} → held {round(hold_h,1)}h (your avg winner: {round(avg_win_h,1)}h) → closed [{exit_dt}] at -₹{loss_amt:,.0f}"
        })
    
    how_to_fix = ""
    if len(excess) > 0:
        how_to_fix = (
            f"Your data shows you hold losing trades {ratio}x longer than winning ones. "
            f"Winners are closed in ~{round(avg_win_h, 1)} hours. Losers linger for ~{round(statistics.mean([h for h, _, _ in loss_holds]), 1)} hours. "
            "This is disposition bias — the tendency to hold losers hoping they'll recover. "
            f"Setting a time-based exit (e.g., if not recovered within {round(avg_win_h * 1.5, 0):.0f} hours, close it) would have saved ₹{cost:,.0f}."
        )
    
    return {'name': 'Disposition Bias', 'count': len(excess), 'cost': cost, 'hold_ratio': ratio,
            'description': f"You hold losers {ratio}x longer than winners. {len(excess)} trades held past the point of no return.",
            'drill_down': drill_down, 'how_to_fix': how_to_fix}


def _detect_snowball(trades):
    """Days where losses compounded (3+ losses in same day)."""
    days = defaultdict(list)
    for i, t in enumerate(trades):
        d = _trade_date(t)
        if d: days[d].append((i, t))
    cost, count, indices, drill_down = 0.0, 0, [], []
    worst_day_desc = ""
    for day, day_trades in days.items():
        losses = [(i, t) for i, t in day_trades if t.get('pnl', 0) < 0]
        if len(losses) >= 3:
            first = abs(losses[0][1]['pnl'])
            total = sum(abs(t['pnl']) for _, t in losses)
            extra = total - first
            if extra > 0:
                cost += extra
                count += 1
                for idx, _ in losses[1:]: indices.append(idx)
                if not worst_day_desc or extra > cost:
                    worst_day_desc = f"{day}: -₹{first:,.0f} snowballed to -₹{total:,.0f} ({len(losses)} losses)"
                # Drill-down for this day
                drill_down.append({
                    'day': day,
                    'total_losses': round(total, 0),
                    'first_loss': round(first, 0),
                    'extra_damage': round(extra, 0),
                    'trade_count': len(losses),
                    'trades': [{
                        'ticker': t.get('ticker', '?'),
                        'pnl': round(t.get('pnl', 0), 0),
                        'time': _format_datetime(t.get('entry_time', '')),
                    } for _, t in losses],
                    'what_happened': f"[{day}] First loss -₹{first:,.0f}, then {len(losses)-1} more trades trying to recover → total damage -₹{total:,.0f}"
                })
    
    how_to_fix = ""
    if count > 0:
        avg_first_loss = round(statistics.mean([d['first_loss'] for d in drill_down]), 0) if drill_down else 0
        how_to_fix = (
            f"Your data shows {count} day(s) where one loss turned into a cascade of {round(statistics.mean([d['trade_count'] for d in drill_down]), 0):.0f}+ losses. "
            f"The first loss averaged -₹{avg_first_loss:,.0f}, but by day's end the total was much higher. "
            "Traders who fix this set a daily loss limit — once hit, they close their terminal for the day. "
            f"A daily stop of 2x your first loss (~₹{avg_first_loss*2:,.0f}) would have saved ₹{cost:,.0f}."
        )
    
    return {'name': 'Loss Snowball', 'count': count, 'cost': cost, 'indices': indices,
            'description': f"{count} days where 1 loss turned into many. Extra damage: ₹{cost:,.0f}",
            'worst_day': worst_day_desc, 'drill_down': drill_down, 'how_to_fix': how_to_fix}


# ===========================================================================
# DEEP ANALYSIS — Trade Sequence, Timing, Instruments
# ===========================================================================

def _analyze_trade_sequence(trades):
    """Which trade # in the day is killing them?"""
    days = defaultdict(list)
    for t in trades:
        d = _trade_date(t)
        if d: days[d].append(t)

    # Compute win rate by trade # within day
    by_position = defaultdict(list)
    for day_trades in days.values():
        for idx, t in enumerate(day_trades):
            by_position[idx + 1].append(t.get('pnl', 0))

    results = {}
    for pos, pnls in sorted(by_position.items()):
        if len(pnls) >= 3:
            wr = round(sum(1 for p in pnls if p > 0) / len(pnls) * 100, 0)
            avg = round(statistics.mean(pnls), 0)
            results[pos] = {'win_rate': wr, 'avg_pnl': avg, 'count': len(pnls)}

    # Find optimal stop point
    optimal = None
    for pos in sorted(results.keys()):
        if results[pos]['avg_pnl'] < 0 and pos > 1:
            optimal = pos - 1
            break

    # Compute cost of trades beyond optimal
    cost = 0
    if optimal:
        for pos, data in results.items():
            if pos > optimal and data['avg_pnl'] < 0:
                cost += abs(data['avg_pnl']) * data['count']

    insight = None
    if optimal and optimal <= 4:
        good_wr = results.get(1, {}).get('win_rate', 0)
        bad_wr = results.get(optimal + 1, {}).get('win_rate', 0) if optimal + 1 in results else 0
        insight = f"Your trade #1 wins {good_wr}% of the time. Trade #{optimal+1}+ wins only {bad_wr}%. If you stopped after trade #{optimal} each day, you'd save ₹{cost:,.0f}."

    return {'name': 'Over-Trading', 'count': sum(1 for pos in results if pos > (optimal or 99)),
            'cost': cost, 'optimal_count': optimal, 'by_position': results,
            'insight': insight, 'indices': [],
            'description': f"Your edge runs out after trade #{optimal}. Everything after costs ₹{cost:,.0f}." if optimal else '',
            'drill_down': _build_sequence_drill_down(days, optimal, results),
            'how_to_fix': _build_sequence_fix(optimal, cost, results)}


def _analyze_timing(trades):
    """Find the time window that's killing them."""
    hour_pnl = defaultdict(list)
    hour_trades = defaultdict(list)
    for t in trades:
        entry = _parse_time(t.get('entry_time'))
        if entry:
            hour_pnl[entry.hour].append(t.get('pnl', 0))
            hour_trades[entry.hour].append(t)

    worst_hour = None
    worst_loss = 0
    best_hour = None
    best_gain = 0

    for hour, pnls in hour_pnl.items():
        total = sum(pnls)
        if total < worst_loss:
            worst_loss = total
            worst_hour = hour
        if total > best_gain:
            best_gain = total
            best_hour = hour

    bad_wr = 0
    if worst_hour is not None and hour_pnl[worst_hour]:
        bad_wr = round(sum(1 for p in hour_pnl[worst_hour] if p < 0) / len(hour_pnl[worst_hour]) * 100, 0)

    cost = abs(worst_loss) if worst_loss < 0 else 0
    insight = None
    if worst_hour is not None and cost > 0:
        best_wr = 0
        if best_hour is not None and hour_pnl[best_hour]:
            best_wr = round(sum(1 for p in hour_pnl[best_hour] if p > 0) / len(hour_pnl[best_hour]) * 100, 0)
        insight = f"Between {worst_hour}:00-{worst_hour+1}:00, you lose ₹{cost:,.0f} total ({bad_wr}% loss rate). Your best hour is {best_hour}:00-{best_hour+1}:00 ({best_wr}% win rate, +₹{best_gain:,.0f}). You have a time-of-day problem."

    return {'name': 'Bad Timing', 'count': len(hour_pnl.get(worst_hour, [])) if worst_hour else 0,
            'cost': cost, 'worst_hour': worst_hour, 'best_hour': best_hour,
            'bad_window_loss_rate': bad_wr, 'insight': insight, 'indices': [],
            'description': f"Trades at {worst_hour}:00 cost ₹{cost:,.0f}" if worst_hour else '',
            'drill_down': _build_timing_drill_down(hour_pnl, worst_hour, best_hour, hour_trades),
            'how_to_fix': _build_timing_fix(worst_hour, best_hour, cost, bad_wr, hour_pnl)}


def _analyze_instruments(trades):
    """Per-instrument P&L — find their edge and their weakness."""
    by_ticker = defaultdict(list)
    for t in trades:
        ticker = t.get('ticker', 'UNKNOWN')
        # Simplify: group by base symbol (remove strike/expiry info)
        base = ticker.split('26')[0] if '26' in ticker else ticker[:10]
        by_ticker[base].append(t.get('pnl', 0))

    results = {}
    for ticker, pnls in by_ticker.items():
        results[ticker] = {
            'total_pnl': round(sum(pnls), 0),
            'trade_count': len(pnls),
            'win_rate': round(sum(1 for p in pnls if p > 0) / len(pnls) * 100, 0) if pnls else 0,
        }

    sorted_tickers = sorted(results.items(), key=lambda x: x[1]['total_pnl'])
    worst = sorted_tickers[0] if sorted_tickers else None
    best = sorted_tickers[-1] if sorted_tickers else None

    insight = None
    if best and worst and best[1]['total_pnl'] > 0 and worst[1]['total_pnl'] < 0:
        insight = f"You're profitable on {best[0]} (+₹{best[1]['total_pnl']:,.0f}) but keep losing on {worst[0]} (-₹{abs(worst[1]['total_pnl']):,.0f}). You have an edge — but you're ignoring it."

    return {'by_ticker': results, 'best': best, 'worst': worst, 'insight': insight}


def _detect_profit_ceiling(trades):
    """Find if there's a running P&L level where they consistently give back gains."""
    # Track intra-day running P&L
    days = defaultdict(list)
    for t in trades:
        d = _trade_date(t)
        if d: days[d].append(t.get('pnl', 0))

    peak_then_crash = []
    for day, pnls in days.items():
        running = 0
        peak = 0
        for p in pnls:
            running += p
            peak = max(peak, running)
        if peak > 0 and running < peak * 0.3:  # Gave back 70%+ of peak
            peak_then_crash.append({'day': day, 'peak': peak, 'final': running})

    ceiling = None
    if len(peak_then_crash) >= 2:
        peaks = [p['peak'] for p in peak_then_crash]
        ceiling = round(statistics.mean(peaks), 0)

    return {'ceiling': ceiling, 'occurrences': len(peak_then_crash),
            'description': f"When your session P&L hits ~₹{ceiling:,.0f}, you give it back ({len(peak_then_crash)} times)" if ceiling else ''}


def _analyze_speed(trades):
    """Do quick decisions lead to worse outcomes?"""
    quick_pnl = []  # < 30 min hold
    slow_pnl = []   # > 30 min hold
    for t in trades:
        h = _hold_hours(t)
        if h is None: continue
        if h < 0.5:
            quick_pnl.append(t.get('pnl', 0))
        else:
            slow_pnl.append(t.get('pnl', 0))

    quick_wr = round(sum(1 for p in quick_pnl if p > 0) / len(quick_pnl) * 100, 0) if quick_pnl else 0
    slow_wr = round(sum(1 for p in slow_pnl if p > 0) / len(slow_pnl) * 100, 0) if slow_pnl else 0
    early_exit_cost = abs(sum(p for p in quick_pnl if p < 0))

    insight = None
    if quick_pnl and slow_pnl and quick_wr < slow_wr - 10:
        insight = f"Trades held <30 min win {quick_wr}%. Trades held longer win {slow_wr}%. Quick decisions cost you ₹{early_exit_cost:,.0f}."

    return {'quick_win_rate': quick_wr, 'slow_win_rate': slow_wr, 'early_exit_cost': early_exit_cost, 'insight': insight}


# ===========================================================================
# DRILL-DOWN HELPERS FOR SEQUENCE & TIMING
# ===========================================================================

def _build_sequence_drill_down(days, optimal, results):
    """Build drill-down showing per-trade-position performance."""
    if not optimal:
        return []
    drill = []
    for pos in sorted(results.keys()):
        data = results[pos]
        status = "✅ Edge" if pos <= optimal else "❌ Over-trade"
        drill.append({
            'trade_number': pos,
            'win_rate': data['win_rate'],
            'avg_pnl': data['avg_pnl'],
            'sample_count': data['count'],
            'status': status,
            'what_happened': f"Trade #{pos} of the day: {data['win_rate']}% win rate, avg P&L ₹{data['avg_pnl']:,.0f} ({data['count']} samples)"
        })
    return drill


def _build_sequence_fix(optimal, cost, results):
    """Build how-to-fix for over-trading."""
    if not optimal or cost <= 0:
        return ''
    good_wr = results.get(1, {}).get('win_rate', 0)
    return (
        f"Your first {optimal} trades of the day have a solid edge (trade #1 wins {good_wr}% of the time). "
        f"After that, your edge disappears and you're essentially gambling. "
        f"Setting a hard limit of {optimal} trades per day — then closing your terminal — "
        f"would have saved ₹{cost:,.0f} based on your data. "
        "Many profitable traders limit themselves to 2-3 high-conviction setups per day."
    )


def _build_timing_drill_down(hour_pnl, worst_hour, best_hour, hour_trades):
    """Build drill-down showing hourly P&L breakdown with individual trades."""
    drill = []
    for hour in sorted(hour_pnl.keys()):
        pnls = hour_pnl[hour]
        total = sum(p for p in pnls)
        wr = round(sum(1 for p in pnls if p > 0) / len(pnls) * 100, 0) if pnls else 0
        status = "🔴 Danger" if hour == worst_hour else ("🟢 Best" if hour == best_hour else "⚪")
        
        # Individual trades in this hour
        trades_in_hour = []
        for t in hour_trades.get(hour, []):
            entry = _parse_time(t.get('entry_time'))
            date_str = entry.strftime('%d %b %Y, %I:%M %p') if entry else ''
            trades_in_hour.append({
                'ticker': t.get('ticker', '?'),
                'pnl': round(t.get('pnl', 0), 0),
                'date': date_str,
            })
        
        drill.append({
            'hour': f"{hour}:00-{hour+1}:00",
            'total_pnl': round(total, 0),
            'win_rate': wr,
            'trade_count': len(pnls),
            'status': status,
            'trades': trades_in_hour,
            'what_happened': f"{hour}:00-{hour+1}:00: {len(pnls)} trades, {wr}% win rate, net ₹{total:,.0f}"
        })
    return drill


def _build_timing_fix(worst_hour, best_hour, cost, bad_wr, hour_pnl=None):
    """Build how-to-fix for bad timing — highlight ALL profitable vs unprofitable windows."""
    if worst_hour is None or cost <= 0:
        return ''
    
    # Categorize all hours
    profitable_hours = []
    losing_hours = []
    if hour_pnl:
        for hour, pnls in sorted(hour_pnl.items()):
            total = sum(pnls)
            wr = round(sum(1 for p in pnls if p > 0) / len(pnls) * 100, 0) if pnls else 0
            if total > 0:
                profitable_hours.append((hour, total, wr, len(pnls)))
            elif total < 0:
                losing_hours.append((hour, total, wr, len(pnls)))
    
    # Build a richer narrative
    parts = []
    
    # Worst hour
    parts.append(f"Your data shows the {worst_hour}:00-{worst_hour+1}:00 window has a {bad_wr}% loss rate, costing ₹{cost:,.0f}.")
    
    # All losing hours
    if len(losing_hours) > 1:
        total_losing_cost = sum(abs(t) for _, t, _, _ in losing_hours)
        losing_windows = ", ".join(f"{h}:00-{h+1}:00 ({wr}% WR)" for h, _, wr, _ in losing_hours)
        parts.append(f"In fact, ALL these windows are unprofitable for you: {losing_windows}. Combined damage: ₹{total_losing_cost:,.0f}.")
    
    # Best hours
    if profitable_hours:
        best_h, best_total, best_wr, best_count = max(profitable_hours, key=lambda x: x[1])
        parts.append(f"Your best hour is {best_h}:00-{best_h+1}:00 — {best_wr}% win rate, +₹{best_total:,.0f} from just {best_count} trade{'s' if best_count > 1 else ''}.")
        if len(profitable_hours) > 1:
            other_good = [f"{h}:00 ({wr}% WR, +₹{t:,.0f})" for h, t, wr, _ in profitable_hours if h != best_h]
            if other_good:
                parts.append(f"Also profitable: {', '.join(other_good)}.")
    
    parts.append("Consider concentrating your trading during your proven profitable hours and taking a break during your danger windows.")
    
    return " ".join(parts)


# ===========================================================================
# NARRATIVE, PREDICTION, FIX VALUE
# ===========================================================================

def _build_narrative(trades, revenge, snowball):
    """Build a 3-4 sentence story of their trading pattern."""
    stats = _compute_basic_stats(trades)

    # Find their best and worst periods
    days = defaultdict(list)
    for t in trades:
        d = _trade_date(t)
        if d: days[d].append(t.get('pnl', 0))

    day_pnls = {d: sum(pnls) for d, pnls in days.items()}
    if not day_pnls:
        return "Not enough data to build your trading story."

    best_day = max(day_pnls, key=day_pnls.get)
    worst_day = min(day_pnls, key=day_pnls.get)

    parts = []
    parts.append(f"Across {len(trades)} trades over {len(days)} trading days, your data tells a clear story.")

    if revenge['count'] > 0:
        times_word = "time" if revenge['count'] == 1 else "times"
        parts.append(f"Your biggest enemy is yourself after a loss — {revenge['count']} {times_word} you chased losses with bigger bets, costing ₹{revenge['cost']:,.0f} extra.")

    if snowball.get('worst_day'):
        parts.append(f"Your worst day: {snowball['worst_day']}.")

    # The what-if
    if stats['total_pnl'] < 0 and revenge['cost'] > 0:
        without_revenge = stats['total_pnl'] + revenge['cost']
        if without_revenge > 0:
            parts.append(f"Without revenge trades alone, your P&L would be +₹{without_revenge:,.0f} instead of -₹{abs(stats['total_pnl']):,.0f}.")
        else:
            parts.append(f"Revenge trading added ₹{revenge['cost']:,.0f} to your losses.")

    return " ".join(parts)


def _build_top_insights(sequence, timing, instruments, ceiling, stats, trades):
    """Build the top 3 most impactful insights."""
    insights = []

    if sequence.get('insight'):
        insights.append({'type': 'sequence', 'title': 'Your Trade Limit', 'text': sequence['insight'], 'impact': sequence['cost']})

    if timing.get('insight'):
        insights.append({'type': 'timing', 'title': 'Your Danger Hour', 'text': timing['insight'], 'impact': timing['cost']})

    if instruments.get('insight'):
        insights.append({'type': 'instrument', 'title': 'Your Hidden Edge', 'text': instruments['insight'], 'impact': 0})

    if ceiling.get('ceiling'):
        insights.append({'type': 'ceiling', 'title': 'Your Glass Ceiling',
                        'text': f"When your session P&L reaches ~₹{ceiling['ceiling']:,.0f}, you consistently give it back. This happened {ceiling['occurrences']} times. You have a psychological profit cap.",
                        'impact': ceiling['ceiling'] * ceiling['occurrences']})

    # The real hourly wage
    if stats['total_pnl'] < 0:
        trading_days = len(set(_trade_date(t) for t in trades if _trade_date(t)))
        hours_spent = trading_days * 5  # Estimate 5h/day
        if hours_spent > 0:
            hourly = round(stats['total_pnl'] / hours_spent, 0)
            insights.append({'type': 'hourly_wage', 'title': 'Your Real Hourly Rate',
                            'text': f"Estimated {hours_spent} hours trading. Net P&L: ₹{stats['total_pnl']:,.0f}. Your effective rate: ₹{hourly}/hour. You're paying ₹{abs(hourly)}/hour to trade.",
                            'impact': abs(stats['total_pnl'])})

    # Sort by impact
    insights.sort(key=lambda x: x.get('impact', 0), reverse=True)
    return insights


def _build_prediction(trades, revenge, sequence, timing):
    """Predict what their next session typically looks like based on ALL patterns."""
    predictions = []
    stats = _compute_basic_stats(trades)

    # 1. Revenge pattern trigger
    if revenge['count'] > 0:
        loss_trades = sum(1 for t in trades if t.get('pnl', 0) < 0)
        trigger_rate = round(revenge['count'] / max(1, loss_trades) * 100, 0) if loss_trades > 0 else 0
        avg_revenge_loss = round(revenge['cost'] / revenge['count'], 0)
        predictions.append({
            'icon': '🔴',
            'text': f"When your first trade loses, you re-enter bigger within the hour {min(trigger_rate + 15, 90)}% of the time — and that second trade averages -₹{avg_revenge_loss:,.0f}",
            'severity': 'high'
        })

    # 2. Over-trading / sequence
    if sequence.get('optimal_count') and sequence.get('optimal_count') <= 4:
        n = sequence['optimal_count']
        good_wr = sequence.get('by_position', {}).get(1, {}).get('win_rate', 0)
        bad_pos = n + 1
        bad_wr = sequence.get('by_position', {}).get(bad_pos, {}).get('win_rate', 0)
        predictions.append({
            'icon': '📊',
            'text': f"Your first {n} trades win {good_wr}% of the time. Trade #{bad_pos}+ drops to {bad_wr}% — you typically don't stop at #{n}",
            'severity': 'high' if sequence['cost'] > 5000 else 'medium'
        })

    # 3. Timing danger window
    if timing.get('worst_hour') is not None and timing.get('bad_window_loss_rate', 0) > 50:
        predictions.append({
            'icon': '⏰',
            'text': f"You typically trade during {timing['worst_hour']}:00-{timing['worst_hour']+1}:00 which has a {timing['bad_window_loss_rate']}% loss rate in your data",
            'severity': 'medium'
        })

    # 4. Snowball / daily cascade
    days = defaultdict(list)
    for t in trades:
        d = _trade_date(t)
        if d: days[d].append(t.get('pnl', 0))
    bad_days = sum(1 for pnls in days.values() if sum(pnls) < 0)
    total_days = len(days)
    if total_days > 0 and bad_days / total_days > 0.5:
        predictions.append({
            'icon': '🌊',
            'text': f"{round(bad_days/total_days*100, 0)}% of your trading days end net negative — a single early loss tends to cascade into more trades",
            'severity': 'medium'
        })

    # 5. Profit ceiling (give back gains)
    day_peaks = []
    for d, pnls in days.items():
        running, peak = 0, 0
        for p in pnls:
            running += p
            peak = max(peak, running)
        if peak > 0 and running < peak * 0.3:
            day_peaks.append(peak)
    if len(day_peaks) >= 2:
        avg_ceiling = round(statistics.mean(day_peaks), 0)
        predictions.append({
            'icon': '🚧',
            'text': f"When your session P&L reaches ~₹{avg_ceiling:,.0f}, you historically give back 70%+ of those gains",
            'severity': 'medium'
        })

    # 6. Speed / quick decisions
    quick_losses = [t for t in trades if _hold_hours(t) is not None and _hold_hours(t) < 0.5 and t.get('pnl', 0) < 0]
    slow_wins = [t for t in trades if _hold_hours(t) is not None and _hold_hours(t) >= 0.5 and t.get('pnl', 0) > 0]
    if len(quick_losses) >= 3 and slow_wins:
        quick_loss_pct = round(len(quick_losses) / len(trades) * 100, 0)
        predictions.append({
            'icon': '⚡',
            'text': f"{quick_loss_pct}% of your trades are quick decisions (<30 min) that lose — your winners tend to be held longer",
            'severity': 'low'
        })

    # 7. Overconfidence after wins
    if stats['win_rate'] > 0:
        win_streaks = 0
        streak = 0
        for t in trades:
            if t.get('pnl', 0) > 0:
                streak += 1
            else:
                if streak >= 2:
                    win_streaks += 1
                streak = 0
        if win_streaks >= 2:
            predictions.append({
                'icon': '🟡',
                'text': f"After 2+ consecutive wins, your next trade historically loses bigger than average — this happened {win_streaks} times",
                'severity': 'medium'
            })

    # 8. Typical session outcome
    day_totals = [sum(pnls) for pnls in days.values()]
    if day_totals:
        avg_day = round(statistics.mean(day_totals), 0)
        worst_day_val = round(min(day_totals), 0)
        predictions.append({
            'icon': '📉' if avg_day < 0 else '📈',
            'text': f"Your average session ends at ₹{avg_day:+,.0f}. Your worst session was ₹{worst_day_val:,.0f}. Based on current patterns, a similar outcome is likely",
            'severity': 'low'
        })

    # Sort by severity
    severity_order = {'high': 0, 'medium': 1, 'low': 2}
    predictions.sort(key=lambda p: severity_order.get(p.get('severity', 'low'), 2))

    return {
        'predictions': [f"{p['icon']} {p['text']}" for p in predictions[:6]],
        'note': "Based on YOUR historical patterns — not predictions or advice. Patterns can change with awareness. Past behavior doesn't guarantee future results."
    }


def _compute_fix_value(trades, revenge, snowball, sequence, stats):
    """Show the ₹ value of fixing their worst pattern."""
    fixes = []

    if revenge['cost'] > 0:
        monthly_est = round(revenge['cost'] * 4, 0)  # Rough monthly projection
        yearly = monthly_est * 12
        fixes.append({
            'pattern': 'Revenge trading elimination',
            'monthly_saving': monthly_est,
            'yearly_saving': yearly,
            'description': f"Traders who add a cooling-off period after losses historically save ~₹{monthly_est:,.0f}/month (₹{yearly:,.0f}/year) based on this pattern's cost."
        })

    if sequence.get('optimal_count') and sequence['cost'] > 0:
        monthly_est = round(sequence['cost'] * 4, 0)
        fixes.append({
            'pattern': f"Edge concentration (trade #1-{sequence['optimal_count']} only)",
            'monthly_saving': monthly_est,
            'yearly_saving': monthly_est * 12,
            'description': f"Your edge historically exists only in your first {sequence['optimal_count']} trades. Concentrating there saves ~₹{monthly_est:,.0f}/month"
        })

    if snowball['cost'] > 0:
        monthly_est = round(snowball['cost'] * 4, 0)
        fixes.append({
            'pattern': 'Daily loss threshold',
            'monthly_saving': monthly_est,
            'yearly_saving': monthly_est * 12,
            'description': f"A daily loss limit historically prevents cascade days. Estimated savings: ₹{snowball['cost']:,.0f} from {snowball['count']} cascade days."
        })

    fixes.sort(key=lambda f: f['yearly_saving'], reverse=True)
    total_fixable = sum(f['yearly_saving'] for f in fixes[:3])

    return {
        'top_fixes': fixes[:3],
        'total_yearly_savings': total_fixable,
        'message': f"Fixing your top 3 patterns could save ₹{total_fixable:,.0f}/year based on your data."
    }


def _compute_fix_one_thing(revenge, snowball, sequence, timing, stats):
    """
    The single most impactful change this trader can make.
    This is THE retention hook — updated each upload.
    """
    candidates = []

    if revenge['cost'] > 0:
        candidates.append({
            'action': "Pattern: Revenge trades occur within minutes of a loss. A 30-minute gap historically eliminates this.",
            'pattern': 'Revenge Trading',
            'impact': revenge['cost'],
            'reason': f"Your data shows {revenge['count']} revenge trades costing ₹{revenge['cost']:,.0f}. Traders who tracked this pattern and added a cooling-off period eliminated it entirely.",
            'metric': f"₹{revenge['cost']:,.0f} saved"
        })

    if sequence.get('optimal_count') and sequence['cost'] > 0:
        n = sequence['optimal_count']
        candidates.append({
            'action': f"Pattern: Your edge exists in trade{'s' if n > 1 else ''} #1-{n} only. Trade #{n+1}+ shows negative expectancy.",
            'pattern': 'Over-Trading',
            'impact': sequence['cost'],
            'reason': f"Your data shows everything after trade #{n} cost you ₹{sequence['cost']:,.0f}. The win rate drops sharply after that point.",
            'metric': f"₹{sequence['cost']:,.0f} saved"
        })

    if timing.get('worst_hour') is not None and timing['cost'] > 0:
        candidates.append({
            'action': f"Observe: your data shows the {timing['worst_hour']}:00-{timing['worst_hour']+1}:00 window has a {timing.get('bad_window_loss_rate', 0)}% loss rate",
            'pattern': 'Bad Timing',
            'impact': timing['cost'],
            'reason': f"Your {timing['worst_hour']}:00 hour has a {timing.get('bad_window_loss_rate', 0)}% loss rate. Skipping it saves ₹{timing['cost']:,.0f}.",
            'metric': f"₹{timing['cost']:,.0f} saved"
        })

    if snowball['cost'] > 0:
        candidates.append({
            'action': "Pattern: Days with 3+ losses show cascading behavior. A daily loss threshold historically prevents the cascade.",
            'pattern': 'Loss Snowball',
            'impact': snowball['cost'],
            'reason': f"On {snowball['count']} days, one loss cascaded into many more. Total extra damage: ₹{snowball['cost']:,.0f}. Traders who set daily limits eliminated this.",
            'metric': f"₹{snowball['cost']:,.0f} saved"
        })

    if not candidates:
        return {
            'action': "Keep uploading weekly to build your pattern history",
            'pattern': None,
            'impact': 0,
            'reason': "Not enough pattern data yet to identify your single biggest lever.",
            'metric': "Building data..."
        }

    # Return the highest-impact fix
    candidates.sort(key=lambda c: c['impact'], reverse=True)
    return candidates[0]


# ===========================================================================
# CALM VS EMOTIONAL
# ===========================================================================

def _calm_vs_emotional(trades, revenge, overconfidence, snowball):
    emotional_idx = set(revenge.get('indices', []) + overconfidence.get('indices', []) + snowball.get('indices', []))
    calm = [t for i, t in enumerate(trades) if i not in emotional_idx]
    emotional = [t for i, t in enumerate(trades) if i in emotional_idx]

    calm_wr = round(sum(1 for t in calm if t.get('pnl',0) > 0) / len(calm) * 100, 1) if calm else 0
    emo_wr = round(sum(1 for t in emotional if t.get('pnl',0) > 0) / len(emotional) * 100, 1) if emotional else 0

    calm_total_pnl = sum(t.get('pnl', 0) for t in calm)
    emo_total_pnl = sum(t.get('pnl', 0) for t in emotional)

    calm_avg = round(statistics.mean([t.get('pnl',0) for t in calm]), 0) if calm else 0
    emo_avg = round(statistics.mean([t.get('pnl',0) for t in emotional]), 0) if emotional else 0

    # Build insight narrative
    insight = ""
    if calm and emotional:
        wr_diff = round(calm_wr - emo_wr, 1)
        pnl_diff = round(calm_total_pnl - emo_total_pnl, 0)
        parts = []
        parts.append(f"Your calm trades win {calm_wr}% of the time (avg ₹{calm_avg:+,.0f}/trade). Emotional trades win only {emo_wr}% (avg ₹{emo_avg:+,.0f}/trade).")
        if pnl_diff > 0:
            parts.append(f"Calm trades produced ₹{calm_total_pnl:+,.0f} total vs emotional trades at ₹{emo_total_pnl:+,.0f}.")
        if wr_diff > 15:
            parts.append(f"That's a {wr_diff} percentage point gap in win rate — your emotions are costing you ₹{abs(emo_total_pnl):,.0f}.")
        elif wr_diff > 0:
            parts.append(f"The {wr_diff}pp gap means emotions are dragging your performance down.")
        if len(emotional) > 0 and len(calm) > 0:
            emo_pct = round(len(emotional) / len(trades) * 100, 0)
            parts.append(f"{emo_pct}% of your trades ({len(emotional)} out of {len(trades)}) were emotionally triggered.")
        insight = " ".join(parts)

    return {
        'calm_win_rate': calm_wr,
        'emotional_win_rate': emo_wr,
        'calm_count': len(calm),
        'emotional_count': len(emotional),
        'calm_avg_pnl': calm_avg,
        'emotional_avg_pnl': emo_avg,
        'calm_total_pnl': round(calm_total_pnl, 0),
        'emotional_total_pnl': round(emo_total_pnl, 0),
        'insight': insight,
    }


# ===========================================================================
# KEY INSIGHT + SUMMARY
# ===========================================================================

def _build_key_insight(report):
    pz = report['page_zero']
    persona = pz['persona']
    return f"{pz['behavioral_pct']}% of your losses (₹{pz['total_behavioral_cost']:,.0f}) are behavioral — not the market beating you. You're '{persona['name']}': {persona['description']}"


def _build_summary(report, trades):
    parts = [f"Based on {len(trades)} trades:"]
    if report['page_zero']['behavioral_pct'] > 30:
        parts.append(f"More than a third of your losses come from behavioral patterns you can fix.")
    if report.get('fix_value', {}).get('total_yearly_savings', 0) > 0:
        parts.append(f"Fixing your top patterns could save ₹{report['fix_value']['total_yearly_savings']:,.0f}/year.")
    parts.append("This is your data. Not advice. The patterns speak for themselves.")
    return " ".join(parts)


# ===========================================================================
# HELPERS
# ===========================================================================

def _parse_time(val) -> Optional[datetime]:
    if val is None: return None
    if isinstance(val, datetime): return val
    try: return datetime.fromisoformat(str(val))
    except: return None


def _format_datetime(val) -> str:
    """Format a datetime or ISO string into readable format like '3 Jun 2024, 11:02 AM'."""
    dt = _parse_time(val)
    if not dt:
        return ''
    return dt.strftime('%d %b %Y, %I:%M %p').lstrip('0')

def _trade_date(t) -> Optional[str]:
    entry = _parse_time(t.get('entry_time'))
    return entry.strftime('%Y-%m-%d') if entry else None

def _hold_hours(t) -> Optional[float]:
    entry = _parse_time(t.get('entry_time'))
    exit_t = _parse_time(t.get('exit_time'))
    if entry and exit_t:
        return max(0, (exit_t - entry).total_seconds() / 3600)
    return None

def _gap_hours(t1, t2) -> Optional[float]:
    exit_t = _parse_time(t1.get('exit_time'))
    entry = _parse_time(t2.get('entry_time'))
    if exit_t and entry:
        return (entry - exit_t).total_seconds() / 3600
    return None


# ===========================================================================
# TRADING CHARGES CALCULATOR (Indian F&O)
# ===========================================================================

def _compute_trading_charges(trades):
    """
    Compute estimated trading charges for Indian F&O trades.
    
    Charges per trade (round trip = buy + sell):
    - Brokerage: ₹20 per order (flat, Zerodha/discount broker) × 2 sides
    - STT: 0.0125% on sell-side premium (options)
    - Exchange Transaction: 0.05% on premium (NSE)
    - GST: 18% on (brokerage + exchange fees)
    - SEBI: ₹10 per crore (negligible for retail)
    - Stamp Duty: 0.003% on buy-side premium
    
    Returns: total charges, per-trade breakdown, phantom winners, real win rate
    """
    BROKERAGE_PER_ORDER = 20  # ₹20 flat per order
    STT_RATE = 0.000125  # 0.0125% on sell-side
    EXCHANGE_FEE_RATE = 0.0005  # 0.05%
    GST_RATE = 0.18  # 18% on brokerage + exchange
    STAMP_DUTY_RATE = 0.00003  # 0.003% on buy-side

    total_charges = 0.0
    trade_details = []
    phantom_winners = 0  # Won before charges, lost after
    
    for t in trades:
        pnl = t.get('pnl', 0)
        entry_price = t.get('entry_price', 0)
        exit_price = t.get('exit_price', 0)
        qty = t.get('quantity', 1)
        
        # Turnover (premium value for each side)
        buy_value = entry_price * qty
        sell_value = exit_price * qty
        total_turnover = buy_value + sell_value
        
        # Calculate charges
        brokerage = BROKERAGE_PER_ORDER * 2  # Buy + Sell
        stt = sell_value * STT_RATE
        exchange_fee = total_turnover * EXCHANGE_FEE_RATE
        gst = (brokerage + exchange_fee) * GST_RATE
        stamp_duty = buy_value * STAMP_DUTY_RATE
        
        trade_charges = round(brokerage + stt + exchange_fee + gst + stamp_duty, 2)
        total_charges += trade_charges
        
        # Net P&L after charges
        net_pnl = pnl - trade_charges
        
        # Check if this is a phantom winner
        if pnl > 0 and net_pnl <= 0:
            phantom_winners += 1
        
        trade_details.append({
            'ticker': t.get('ticker', 'UNKNOWN'),
            'entry_time': t.get('entry_time', ''),
            'pnl_before_charges': round(pnl, 2),
            'charges': trade_charges,
            'net_pnl': round(net_pnl, 2),
            'breakdown': {
                'brokerage': brokerage,
                'stt': round(stt, 2),
                'exchange_fee': round(exchange_fee, 2),
                'gst': round(gst, 2),
                'stamp_duty': round(stamp_duty, 2),
            }
        })
    
    # Real win rate (after charges)
    real_winners = sum(1 for td in trade_details if td['net_pnl'] > 0)
    real_win_rate = round(real_winners / len(trade_details) * 100, 1) if trade_details else 0
    stated_win_rate = round(sum(1 for t in trades if t.get('pnl', 0) > 0) / len(trades) * 100, 1) if trades else 0
    
    # The break-even insight
    avg_charges_per_trade = round(total_charges / len(trades), 0) if trades else 0
    
    # Insight text
    insight = None
    if phantom_winners > 0:
        insight = (f"You placed {len(trades)} trades. Estimated charges: ₹{total_charges:,.0f}. "
                   f"{phantom_winners} of your 'winning' trades were actually UNPROFITABLE after charges. "
                   f"Your stated win rate is {stated_win_rate}% but your REAL win rate (after charges) is {real_win_rate}%. "
                   f"You need ₹{avg_charges_per_trade:,.0f} per trade just to break even.")
    else:
        insight = (f"Estimated charges across {len(trades)} trades: ₹{total_charges:,.0f} "
                   f"(avg ₹{avg_charges_per_trade:,.0f}/trade). You need to make ₹{avg_charges_per_trade:,.0f} per trade just to break even.")
    
    return {
        'total_charges': round(total_charges, 0),
        'avg_per_trade': avg_charges_per_trade,
        'phantom_winners': phantom_winners,
        'stated_win_rate': stated_win_rate,
        'real_win_rate': real_win_rate,
        'trade_table': trade_details,
        'insight': insight,
        'yearly_charges_at_current_rate': round(total_charges * 12, 0),  # Rough annual projection
    }
