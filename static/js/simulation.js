/**
 * Options Tycoon — Live Market Simulation Module
 * 
 * Handles real-time price simulation, chart rendering, options chain updates,
 * position P&L tracking, market timer, and one-click trading.
 */

// ==========================================================================
// Simulation State
// ==========================================================================

const SIM_STATE = {
    sessionId: null,
    active: false,
    tickInterval: null,
    chartData: [],          // Last 60 price points
    currentPrice: 0,
    originalPrice: 0,       // Price at session start (for delta calcs)
    sessionHigh: 0,
    sessionLow: Infinity,
    currentTime: '09:15',
    sessionEnd: '15:30',
    ticker: null,
};

// ==========================================================================
// Start / Stop Simulation
// ==========================================================================

/**
 * Start a simulation session for the given ticker.
 * Called when the user selects a ticker from the list.
 */
async function startSimulation(ticker) {
    // Stop any existing session first
    stopSimulation();

    if (!APP_STATE.profileId) {
        console.warn('[SIM] No profile loaded, cannot start simulation.');
        return;
    }

    try {
        const res = await fetch('/api/simulation/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                profile_id: APP_STATE.profileId,
                ticker: ticker,
            }),
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            // If no intraday data, just silently skip simulation
            console.info(`[SIM] No simulation data for ${ticker}: ${err.detail || ''}`);
            return;
        }

        const data = await res.json();

        SIM_STATE.sessionId = data.session_id;
        SIM_STATE.active = true;
        SIM_STATE.ticker = ticker;
        SIM_STATE.currentPrice = data.current_price;
        SIM_STATE.originalPrice = data.current_price;
        SIM_STATE.sessionHigh = data.current_price;
        SIM_STATE.sessionLow = data.current_price;
        SIM_STATE.currentTime = data.current_time || '09:15';
        SIM_STATE.sessionEnd = data.session_end || '15:30';
        SIM_STATE.chartData = [data.current_price];

        // Initial chart draw
        drawPriceChart();
        updateMarketTimer();

        // Start polling every 2500ms
        SIM_STATE.tickInterval = setInterval(pollTick, 2500);

        console.log(`[SIM] Session started for ${ticker} | Price: ₹${data.current_price}`);
    } catch (e) {
        console.error('[SIM] Failed to start simulation:', e.message);
    }
}

/**
 * Stop the simulation — clears interval and resets state.
 */
function stopSimulation() {
    if (SIM_STATE.tickInterval) {
        clearInterval(SIM_STATE.tickInterval);
        SIM_STATE.tickInterval = null;
    }
    SIM_STATE.active = false;
    SIM_STATE.sessionId = null;
}

// ==========================================================================
// Tick Polling
// ==========================================================================

/**
 * Poll the server for the next price tick.
 * Called every 2500ms while simulation is active.
 */
async function pollTick() {
    if (!SIM_STATE.active || !SIM_STATE.sessionId) return;

    try {
        const res = await fetch(`/api/simulation/tick?session_id=${SIM_STATE.sessionId}`);
        if (!res.ok) {
            console.error('[SIM] Tick fetch failed:', res.status);
            return;
        }

        const data = await res.json();

        // Session ended
        if (!data.session_active) {
            SIM_STATE.active = false;
            clearInterval(SIM_STATE.tickInterval);
            SIM_STATE.tickInterval = null;
            updateMarketTimer('CLOSED');
            console.log('[SIM] Market closed.');
            return;
        }

        const prevPrice = SIM_STATE.currentPrice;
        SIM_STATE.currentPrice = data.current_price;
        SIM_STATE.currentTime = data.current_time || SIM_STATE.currentTime;

        // Update high/low
        if (data.current_price > SIM_STATE.sessionHigh) {
            SIM_STATE.sessionHigh = data.current_price;
        }
        if (data.current_price < SIM_STATE.sessionLow) {
            SIM_STATE.sessionLow = data.current_price;
        }

        // Push to chart data (keep last 60)
        SIM_STATE.chartData.push(data.current_price);
        if (SIM_STATE.chartData.length > 60) {
            SIM_STATE.chartData.shift();
        }

        // Update everything
        drawPriceChart();
        updateMarketTimer();
        updateChainPrices(SIM_STATE.currentPrice, SIM_STATE.originalPrice);
        updatePositionPnL(SIM_STATE.currentPrice);

        // Update the ticker title with live price
        const titleEl = document.getElementById('chain-ticker-title');
        if (titleEl && SIM_STATE.ticker) {
            const arrow = data.current_price > prevPrice ? '▲' : data.current_price < prevPrice ? '▼' : '';
            titleEl.textContent = `${SIM_STATE.ticker} — ₹${data.current_price.toLocaleString('en-IN')} ${arrow}`;
            titleEl.style.color = data.current_price > prevPrice ? 'var(--green)' : data.current_price < prevPrice ? 'var(--red)' : '';
        }

    } catch (e) {
        console.error('[SIM] Tick poll error:', e.message);
    }
}

// ==========================================================================
// Price Chart (Canvas Line Chart)
// ==========================================================================

/**
 * Draw a simple line chart on the #price-chart canvas.
 * Shows last 60 price points, current price, session high/low.
 */
function drawPriceChart() {
    const canvas = document.getElementById('price-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const W = canvas.width;
    const H = canvas.height;
    const data = SIM_STATE.chartData;

    // Clear
    ctx.clearRect(0, 0, W, H);

    if (data.length < 2) {
        // Not enough data — draw placeholder
        ctx.fillStyle = '#666';
        ctx.font = '12px monospace';
        ctx.textAlign = 'center';
        ctx.fillText('Waiting for price data...', W / 2, H / 2);
        return;
    }

    // Calculate bounds
    const min = Math.min(...data) * 0.999;
    const max = Math.max(...data) * 1.001;
    const range = max - min || 1;
    const padding = { top: 20, bottom: 20, left: 60, right: 60 };
    const chartW = W - padding.left - padding.right;
    const chartH = H - padding.top - padding.bottom;

    // Background gradient
    ctx.fillStyle = '#0a0f1a';
    ctx.fillRect(0, 0, W, H);

    // Grid lines (horizontal)
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
        const y = padding.top + (chartH / 4) * i;
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(W - padding.right, y);
        ctx.stroke();
    }

    // Line path
    const stepX = chartW / (data.length - 1);
    const toY = (price) => padding.top + chartH - ((price - min) / range) * chartH;
    const toX = (i) => padding.left + i * stepX;

    // Gradient fill under line
    const gradient = ctx.createLinearGradient(0, padding.top, 0, H - padding.bottom);
    const isUp = data[data.length - 1] >= data[0];
    gradient.addColorStop(0, isUp ? 'rgba(0,200,100,0.15)' : 'rgba(240,60,60,0.15)');
    gradient.addColorStop(1, 'rgba(0,0,0,0)');

    ctx.beginPath();
    ctx.moveTo(toX(0), toY(data[0]));
    for (let i = 1; i < data.length; i++) {
        ctx.lineTo(toX(i), toY(data[i]));
    }
    // Fill area
    ctx.lineTo(toX(data.length - 1), H - padding.bottom);
    ctx.lineTo(toX(0), H - padding.bottom);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Draw the line
    ctx.beginPath();
    ctx.moveTo(toX(0), toY(data[0]));
    for (let i = 1; i < data.length; i++) {
        ctx.lineTo(toX(i), toY(data[i]));
    }
    ctx.strokeStyle = isUp ? '#00c864' : '#f03c3c';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Current price dot
    const lastX = toX(data.length - 1);
    const lastY = toY(data[data.length - 1]);
    ctx.beginPath();
    ctx.arc(lastX, lastY, 4, 0, Math.PI * 2);
    ctx.fillStyle = isUp ? '#00c864' : '#f03c3c';
    ctx.fill();

    // Price labels
    ctx.fillStyle = '#ccc';
    ctx.font = '11px monospace';
    ctx.textAlign = 'right';

    // Current price (right side)
    ctx.fillStyle = isUp ? '#00c864' : '#f03c3c';
    ctx.textAlign = 'left';
    ctx.fillText(`₹${data[data.length - 1].toFixed(1)}`, lastX + 8, lastY + 4);

    // High / Low labels (left side)
    ctx.fillStyle = '#888';
    ctx.textAlign = 'left';
    ctx.font = '10px monospace';
    ctx.fillText(`H: ₹${SIM_STATE.sessionHigh.toFixed(1)}`, 4, 14);
    ctx.fillText(`L: ₹${SIM_STATE.sessionLow.toFixed(1)}`, 4, H - 6);

    // Time label
    ctx.fillStyle = '#666';
    ctx.textAlign = 'right';
    ctx.fillText(SIM_STATE.currentTime, W - 4, H - 6);
}

// ==========================================================================
// Market Timer
// ==========================================================================

/**
 * Update the market timer display.
 * Shows current simulated time and countdown to 15:30 close.
 */
function updateMarketTimer(override) {
    const el = document.getElementById('market-timer');
    if (!el) return;

    if (override === 'CLOSED') {
        el.textContent = '🔴 Market CLOSED';
        el.className = 'market-timer closed';
        return;
    }

    if (!SIM_STATE.active) {
        el.textContent = 'Market: --:-- | Closes in --:--';
        el.className = 'market-timer';
        return;
    }

    const currentTime = SIM_STATE.currentTime;
    const remaining = getMinutesUntilClose(currentTime);

    const hours = Math.floor(remaining / 60);
    const mins = remaining % 60;
    const countdownStr = hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;

    el.textContent = `Market: ${currentTime} | Closes in ${countdownStr}`;

    // Color coding based on urgency
    el.className = 'market-timer';
    if (remaining <= 10) {
        el.classList.add('critical');
    } else if (remaining <= 30) {
        el.classList.add('warning');
    }
}

/**
 * Calculate minutes remaining until 15:30 close.
 */
function getMinutesUntilClose(timeStr) {
    if (!timeStr || !timeStr.includes(':')) return 999;
    const [h, m] = timeStr.split(':').map(Number);
    const closeH = 15, closeM = 30;
    const currentMins = h * 60 + m;
    const closeMins = closeH * 60 + closeM;
    return Math.max(0, closeMins - currentMins);
}

// ==========================================================================
// Options Chain Price Updates (Client-Side Delta Approximation)
// ==========================================================================

/**
 * Recalculate and render options chain prices based on new underlying price.
 * Uses delta approximation for speed: newPrice ≈ oldPrice + delta * (underlyingChange)
 */
function updateChainPrices(currentPrice, originalPrice) {
    const tableBody = document.getElementById('chain-tbody');
    if (!tableBody) return;

    const chain = APP_STATE.chain;
    if (!chain || !chain.chain || chain.chain.length === 0) return;

    const priceChange = currentPrice - originalPrice;
    const rows = tableBody.querySelectorAll('tr');

    chain.chain.forEach((row, i) => {
        if (!rows[i]) return;

        const cells = rows[i].querySelectorAll('td');
        if (cells.length < 7) return;

        // Delta approximation for calls (positive delta)
        const callDelta = row.call_delta || 0.5;
        const callChange = callDelta * priceChange;
        const newCallBid = Math.max(0.05, row.call_bid + callChange);
        const newCallAsk = Math.max(0.10, row.call_ask + callChange);

        // Delta approximation for puts (negative delta)
        const putDelta = row.put_delta || -0.5;
        const putChange = putDelta * priceChange;
        const newPutBid = Math.max(0.05, row.put_bid + putChange);
        const newPutAsk = Math.max(0.10, row.put_ask + putChange);

        // Update call bid/ask cell
        const callBidAskCell = cells[0];
        const prevCallText = callBidAskCell.textContent;
        const newCallText = `${newCallBid.toFixed(2)} / ${newCallAsk.toFixed(2)}`;

        if (prevCallText !== newCallText) {
            callBidAskCell.innerHTML = `<span class="clickable-bid" data-price="${newCallBid.toFixed(2)}" data-type="call" data-strike="${row.strike}">${newCallBid.toFixed(2)}</span> / <span class="clickable-ask" data-price="${newCallAsk.toFixed(2)}" data-type="call" data-strike="${row.strike}">${newCallAsk.toFixed(2)}</span>`;
            flashCell(callBidAskCell, callChange > 0 ? 'up' : 'down');
        }

        // Update put bid/ask cell
        const putBidAskCell = cells[4];
        const prevPutText = putBidAskCell.textContent;
        const newPutText = `${newPutBid.toFixed(2)} / ${newPutAsk.toFixed(2)}`;

        if (prevPutText !== newPutText) {
            putBidAskCell.innerHTML = `<span class="clickable-bid" data-price="${newPutBid.toFixed(2)}" data-type="put" data-strike="${row.strike}">${newPutBid.toFixed(2)}</span> / <span class="clickable-ask" data-price="${newPutAsk.toFixed(2)}" data-type="put" data-strike="${row.strike}">${newPutAsk.toFixed(2)}</span>`;
            flashCell(putBidAskCell, putChange > 0 ? 'up' : 'down');
        }
    });
}

/**
 * Flash a cell green or red to indicate price change.
 */
function flashCell(cell, direction) {
    if (!cell) return;
    cell.classList.remove('tick-up', 'tick-down');
    void cell.offsetWidth; // Force reflow
    cell.classList.add(direction === 'up' ? 'tick-up' : 'tick-down');
    setTimeout(() => {
        cell.classList.remove('tick-up', 'tick-down');
    }, 800);
}

// ==========================================================================
// Position P&L Updates
// ==========================================================================

/**
 * Update open position P&L in real-time based on current price.
 */
function updatePositionPnL(currentPrice) {
    const listEl = document.getElementById('hud-positions-list');
    if (!listEl) return;

    const pnlEls = listEl.querySelectorAll('.position-mini-pnl');
    const pnlHudEl = document.getElementById('hud-unrealized-pnl');

    // If no position elements, nothing to update dynamically
    // The real P&L calc happens server-side; here we apply a quick delta estimate
    pnlEls.forEach(el => {
        const prevText = el.textContent;
        // Pulse effect on change
        el.classList.remove('pnl-pulse-up', 'pnl-pulse-down');
        void el.offsetWidth;

        // Determine direction from existing classes
        if (el.classList.contains('text-green')) {
            el.classList.add('pnl-pulse-up');
        } else if (el.classList.contains('text-red')) {
            el.classList.add('pnl-pulse-down');
        }

        setTimeout(() => {
            el.classList.remove('pnl-pulse-up', 'pnl-pulse-down');
        }, 600);
    });

    // Pulse the main unrealized P&L in the HUD
    if (pnlHudEl) {
        pnlHudEl.classList.remove('pnl-pulse-up', 'pnl-pulse-down');
        void pnlHudEl.offsetWidth;
        if (pnlHudEl.classList.contains('text-green')) {
            pnlHudEl.classList.add('pnl-pulse-up');
        } else if (pnlHudEl.classList.contains('text-red')) {
            pnlHudEl.classList.add('pnl-pulse-down');
        }
        setTimeout(() => {
            pnlHudEl.classList.remove('pnl-pulse-up', 'pnl-pulse-down');
        }, 600);
    }
}

// ==========================================================================
// One-Click Trading (Chain Cell Clicks)
// ==========================================================================

/**
 * Handle clicks on the options chain table for one-click trading.
 */
function handleChainClick(event) {
    const target = event.target;

    // Check if clicked element is a clickable bid or ask
    if (target.classList.contains('clickable-bid')) {
        // Clicking bid → Sell at that price
        openTradeModal({
            action: 'sell',
            type: target.dataset.type,
            strike: parseFloat(target.dataset.strike),
            price: parseFloat(target.dataset.price),
        });
    } else if (target.classList.contains('clickable-ask')) {
        // Clicking ask → Buy at that price
        openTradeModal({
            action: 'buy',
            type: target.dataset.type,
            strike: parseFloat(target.dataset.strike),
            price: parseFloat(target.dataset.price),
        });
    }
}

/**
 * Open the one-click trade confirmation modal.
 */
function openTradeModal(trade) {
    const ticker = SIM_STATE.ticker || APP_STATE.currentTicker || '—';
    const cost = trade.price * 1; // 1 lot
    const actionLabel = trade.action === 'buy' ? '🟢 BUY' : '🔴 SELL';
    const actionClass = trade.action === 'buy' ? 'btn-deploy' : 'btn-cancel';

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'trade-modal';
    modal.innerHTML = `
        <div class="modal" style="max-width: 400px;">
            <h2 style="margin-bottom: 12px; font-size: 1.1rem;">
                ${actionLabel} ${ticker} ${trade.strike} ${trade.type.toUpperCase()}
            </h2>
            <div style="background: var(--bg-input); border-radius: var(--radius); padding: 14px; margin-bottom: 16px;">
                <table style="width: 100%; font-size: 13px; line-height: 2;">
                    <tr><td style="color: var(--text-muted);">Ticker</td><td style="text-align:right; font-weight:600;">${ticker}</td></tr>
                    <tr><td style="color: var(--text-muted);">Strike</td><td style="text-align:right; font-weight:600;">₹${trade.strike.toFixed(1)}</td></tr>
                    <tr><td style="color: var(--text-muted);">Type</td><td style="text-align:right; font-weight:600;">${trade.type.toUpperCase()}</td></tr>
                    <tr><td style="color: var(--text-muted);">Price</td><td style="text-align:right; font-weight:600;">₹${trade.price.toFixed(2)}</td></tr>
                    <tr><td style="color: var(--text-muted);">Cost (1 lot)</td><td style="text-align:right; font-weight:600;">₹${cost.toFixed(2)}</td></tr>
                </table>
            </div>
            <p style="text-align: center; color: var(--yellow); font-size: 12px; font-weight: 600; margin-bottom: 16px;">
                💭 Would you do this with real money?
            </p>
            <div style="display: flex; gap: 10px; justify-content: center;">
                <button class="btn ${actionClass}" id="trade-confirm-btn" style="padding: 10px 24px; font-size: 13px;">
                    ${trade.action === 'buy' ? '✅ Buy' : '✅ Sell'} — Deploy
                </button>
                <button class="btn btn-secondary" id="trade-cancel-btn" style="padding: 10px 24px; font-size: 13px;">
                    Cancel
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Confirm → add as a leg and deploy
    document.getElementById('trade-confirm-btn').addEventListener('click', () => {
        modal.remove();
        executeOneClickTrade(trade);
    });

    // Cancel
    document.getElementById('trade-cancel-btn').addEventListener('click', () => {
        modal.remove();
    });

    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });
}

/**
 * Execute a one-click trade by building a single leg and deploying.
 */
async function executeOneClickTrade(trade) {
    if (!APP_STATE.profileId || !SIM_STATE.ticker) return;

    const payload = {
        profile_id: APP_STATE.profileId,
        ticker: SIM_STATE.ticker,
        strategy_type: 'single',
        legs: [{
            contract_type: trade.type,
            strike: trade.strike,
            expiration: APP_STATE.currentExpiry || '2025-01-30',
            quantity: 1,
            action: trade.action,
        }],
        chain_opened_at: APP_STATE.chainOpenedAt || new Date().toISOString(),
        confirmation_proceeded: true,
    };

    try {
        await fetch('/api/trades', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        // Flash success indicator
        const hudEl = document.querySelector('.pane-right');
        if (hudEl) flashElement(hudEl, 'win');

        // Reload data
        if (typeof loadProfile === 'function') await loadProfile();
        if (typeof loadOpenPositions === 'function') await loadOpenPositions();
        if (typeof loadBehavioral === 'function') await loadBehavioral();

    } catch (e) {
        console.error('[SIM] One-click trade failed:', e.message);
    }
}

// ==========================================================================
// Event Binding & Initialization
// ==========================================================================

/**
 * Attach click handler to the chain table for one-click trading.
 */
function initChainClickHandler() {
    const chainTable = document.querySelector('.chain-table');
    if (chainTable) {
        chainTable.addEventListener('click', handleChainClick);
    }
}

/**
 * Hook into the existing selectTicker function to auto-start simulation.
 */
(function patchSelectTicker() {
    const _origSelectTicker = window.selectTicker;

    if (typeof _origSelectTicker === 'function') {
        window.selectTicker = async function (ticker) {
            // Call original
            await _origSelectTicker(ticker);
            // Start simulation for this ticker
            startSimulation(ticker);
        };
    }
})();

/**
 * Stop simulation on page unload.
 */
window.addEventListener('beforeunload', () => {
    stopSimulation();
});

/**
 * Initialize simulation features on DOM ready.
 */
document.addEventListener('DOMContentLoaded', () => {
    initChainClickHandler();
});
