/**
 * Options Tycoon - Core Application JavaScript
 * Vanilla JS with fetch-based API calls, profile management, and HUD updates.
 */

// ==========================================================================
// Global State
// ==========================================================================

window.APP_STATE = {
    profileId: null,
    currentTicker: null,
    currentExpiry: null,
    chainOpenedAt: null,
    legs: [],
    tickers: [],
    chain: null,
};

// ==========================================================================
// API Helper
// ==========================================================================

const api = {
    async get(url) {
        try {
            const res = await fetch(`/api/${url}`);
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(err.detail || err.message || `HTTP ${res.status}`);
            }
            return await res.json();
        } catch (e) {
            console.error(`[API GET] /api/${url}:`, e.message);
            throw e;
        }
    },

    async post(url, body = {}) {
        try {
            const res = await fetch(`/api/${url}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(err.detail || err.message || `HTTP ${res.status}`);
            }
            if (res.status === 204) return null;
            return await res.json();
        } catch (e) {
            console.error(`[API POST] /api/${url}:`, e.message);
            throw e;
        }
    },

    async put(url, body = {}) {
        try {
            const res = await fetch(`/api/${url}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(err.detail || err.message || `HTTP ${res.status}`);
            }
            if (res.status === 204) return null;
            return await res.json();
        } catch (e) {
            console.error(`[API PUT] /api/${url}:`, e.message);
            throw e;
        }
    },

    async delete(url) {
        try {
            const res = await fetch(`/api/${url}`, { method: 'DELETE' });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(err.detail || err.message || `HTTP ${res.status}`);
            }
            return null;
        } catch (e) {
            console.error(`[API DELETE] /api/${url}:`, e.message);
            throw e;
        }
    },
};

// ==========================================================================
// Profile Management
// ==========================================================================

async function loadProfile() {
    const savedId = localStorage.getItem('ot_profile_id');

    if (savedId) {
        try {
            const profile = await api.get(`profiles/${savedId}`);
            APP_STATE.profileId = profile.id;
            updateHUD(profile);
            return profile;
        } catch (e) {
            // Profile doesn't exist anymore, clear and create new
            localStorage.removeItem('ot_profile_id');
        }
    }

    // No saved profile — check if any exist
    try {
        const profiles = await api.get('profiles');
        if (profiles.length > 0) {
            const profile = profiles[0];
            APP_STATE.profileId = profile.id;
            localStorage.setItem('ot_profile_id', profile.id);
            updateHUD(profile);
            return profile;
        }
    } catch (e) {
        console.error('Failed to list profiles:', e.message);
    }

    // No profiles exist — create default
    return await createProfile('Trader 1');
}

async function createProfile(name) {
    try {
        const profile = await api.post('profiles', { name });
        APP_STATE.profileId = profile.id;
        localStorage.setItem('ot_profile_id', profile.id);
        updateHUD(profile);
        return profile;
    } catch (e) {
        console.error('Failed to create profile:', e.message);
        return null;
    }
}

async function switchProfile(id) {
    try {
        const profile = await api.get(`profiles/${id}`);
        APP_STATE.profileId = profile.id;
        localStorage.setItem('ot_profile_id', profile.id);
        updateHUD(profile);
        return profile;
    } catch (e) {
        console.error('Failed to switch profile:', e.message);
        return null;
    }
}

// ==========================================================================
// HUD Update
// ==========================================================================

function updateHUD(data) {
    // Balance
    const balanceEl = document.getElementById('hud-balance');
    if (balanceEl) {
        const formatted = formatCurrency(data.balance);
        balanceEl.textContent = formatted;
        balanceEl.classList.toggle('text-red', data.balance <= 2000);
    }

    // Phase
    const phaseEl = document.getElementById('hud-phase');
    if (phaseEl && data.phase) {
        phaseEl.textContent = `Phase ${data.phase}`;
    }

    // Total trades
    const tradesEl = document.getElementById('hud-total-trades');
    if (tradesEl && data.total_trades !== undefined) {
        tradesEl.textContent = data.total_trades;
    }

    // Game over state
    const gameOverEl = document.getElementById('hud-game-over');
    if (gameOverEl) {
        gameOverEl.classList.toggle('hidden', !data.is_locked);
    }
}

function updateHUDPositions(positions) {
    const countEl = document.getElementById('hud-open-positions');
    const listEl = document.getElementById('hud-positions-list');
    const pnlEl = document.getElementById('hud-unrealized-pnl');

    if (!positions) return;

    const openPositions = positions.filter(p => p.status === 'open');

    if (countEl) {
        countEl.textContent = openPositions.length;
    }

    // Calculate total unrealized P&L
    let totalPnl = 0;
    openPositions.forEach(p => { totalPnl += p.unrealized_pnl || 0; });

    if (pnlEl) {
        pnlEl.textContent = formatCurrency(totalPnl);
        pnlEl.className = 'hud-stat-value mono ' + (totalPnl >= 0 ? 'text-green' : 'text-red');
    }

    // Mini position list
    if (listEl) {
        if (openPositions.length === 0) {
            listEl.innerHTML = '<div class="empty-state">No open positions</div>';
            return;
        }
        listEl.innerHTML = openPositions.slice(0, 5).map(p => `
            <div class="position-mini">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div class="position-mini-ticker">${p.ticker} ${p.strategy_type || ''}</div>
                        <div class="position-mini-detail">Exp: ${p.expiration_date || p.expiry || '—'}</div>
                    </div>
                    <div style="text-align:right;">
                        <div class="position-mini-pnl ${(p.unrealized_pnl || 0) >= 0 ? 'text-green' : 'text-red'}">
                            ${formatCurrency(p.unrealized_pnl || 0)}
                        </div>
                        <button class="btn btn-sm btn-cancel" onclick="closePosition(${p.id})" style="margin-top:4px; padding:3px 8px; font-size:10px;">Close</button>
                    </div>
                </div>
            </div>
        `).join('');
    }
}

function updateBehavioralGauges(metrics) {
    if (!metrics) return;

    // Discipline: already 0-100%, higher is better
    setGauge('gauge-discipline', metrics.discipline, metrics.discipline !== null ? metrics.discipline.toFixed(0) + '%' : '—', true);

    // Patience: seconds — normalize to 0-100 scale (0s=0, 120s+=100)
    const patiencePct = metrics.patience !== null ? Math.min(100, (metrics.patience / 120) * 100) : null;
    setGauge('gauge-patience', patiencePct, metrics.patience !== null ? metrics.patience.toFixed(0) + 's' : '—', true);

    // Sizing: std deviation — lower is better. Normalize inverted (0=perfect, 10+=bad)
    const sizingPct = metrics.sizing !== null ? Math.max(0, 100 - metrics.sizing * 10) : null;
    setGauge('gauge-sizing', sizingPct, metrics.sizing !== null ? metrics.sizing.toFixed(1) + '%' : '—', true);

    // Emotional: 0-100, but inverted for display (lower reactivity = better = green)
    const emotionalPct = metrics.emotional !== null ? (100 - metrics.emotional) : null;
    setGauge('gauge-emotional', emotionalPct, metrics.emotional !== null ? metrics.emotional.toFixed(0) + '/100' : '—', true);

    // Streak
    const streakEl = document.getElementById('hud-streak');
    if (streakEl && metrics.streak !== undefined && metrics.streak !== null) {
        const count = metrics.streak;
        streakEl.className = `streak-badge ${count > 0 ? 'winning' : ''}`;
        streakEl.textContent = `🔥 ${count}`;
    }
}

function setGauge(id, pct, displayText, higherIsBetter) {
    const fillEl = document.getElementById(id);
    const valEl = document.getElementById(id + '-val');

    if (valEl) valEl.textContent = displayText || '—';

    if (!fillEl || pct === null || pct === undefined) return;

    const clamped = Math.min(100, Math.max(0, pct));
    fillEl.style.width = clamped + '%';

    // Color: green = good, red = bad
    fillEl.className = 'gauge-fill';
    if (clamped >= 70) fillEl.classList.add('green');
    else if (clamped >= 50) fillEl.classList.add('yellow');
    else if (clamped >= 30) fillEl.classList.add('orange');
    else fillEl.classList.add('red');
}

// ==========================================================================
// IV Rank
// ==========================================================================

async function loadIVRank(ticker) {
    const el = document.getElementById('hud-iv-rank');
    if (!el) return;

    try {
        const data = await api.get(`iv-rank/${ticker}`);
        if (data.iv_rank !== null) {
            el.textContent = (data.iv_rank * 100).toFixed(0) + '%';
            el.className = 'hud-stat-value mono ' + (data.iv_rank > 0.5 ? 'text-green' : 'text-secondary');
        } else {
            el.textContent = '—';
        }
    } catch (e) {
        el.textContent = '—';
    }
}

// ==========================================================================
// Disclaimer Modal
// ==========================================================================

function showDisclaimer() {
    const overlay = document.getElementById('disclaimer-modal');
    if (overlay) {
        overlay.classList.remove('hidden');
    }
}

function dismissDisclaimer() {
    localStorage.setItem('ot_disclaimer_ack', 'true');
    const overlay = document.getElementById('disclaimer-modal');
    if (overlay) {
        overlay.classList.add('hidden');
    }
}

function checkDisclaimer() {
    const ack = localStorage.getItem('ot_disclaimer_ack');
    if (!ack) {
        showDisclaimer();
    }
}

// ==========================================================================
// Utility Functions
// ==========================================================================

function formatCurrency(amount) {
    if (amount === null || amount === undefined) return '₹0.00';
    const sign = amount < 0 ? '-' : '';
    return sign + '₹' + Math.abs(amount).toLocaleString('en-IN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}

function formatNumber(num, decimals = 4) {
    if (num === null || num === undefined) return '—';
    return Number(num).toFixed(decimals);
}

function flashElement(el, type) {
    if (!el) return;
    el.classList.remove('green-flash', 'red-flash');
    // Force reflow
    void el.offsetWidth;
    el.classList.add(type === 'win' ? 'green-flash' : 'red-flash');
}

// ==========================================================================
// Ticker & Chain Loading
// ==========================================================================

async function loadTickers() {
    try {
        const data = await api.get('tickers');
        APP_STATE.tickers = data.tickers || [];
        renderTickerList(APP_STATE.tickers);
    } catch (e) {
        console.error('Failed to load tickers:', e.message);
    }
}

function renderTickerList(tickers) {
    const listEl = document.getElementById('ticker-list');
    if (!listEl) return;

    listEl.innerHTML = tickers.map(ticker => `
        <li class="ticker-item ${ticker === APP_STATE.currentTicker ? 'active' : ''}"
            onclick="selectTicker('${ticker}')">
            <span class="ticker-item-symbol">${ticker}</span>
        </li>
    `).join('');
}

function filterTickers(query) {
    const filtered = APP_STATE.tickers.filter(t =>
        t.toLowerCase().includes(query.toLowerCase())
    );
    renderTickerList(filtered);
}

async function selectTicker(ticker) {
    APP_STATE.currentTicker = ticker;
    APP_STATE.currentExpiry = null;
    APP_STATE.chainOpenedAt = new Date().toISOString(); // Track for patience scoring
    renderTickerList(APP_STATE.tickers);

    // Load chain
    try {
        const data = await api.get(`chain/${ticker}`);
        APP_STATE.chain = data;
        renderExpiryTabs(data.expirations);
        renderChain(data.chain);
        loadIVRank(ticker);

        // Update page title area
        const titleEl = document.getElementById('chain-ticker-title');
        if (titleEl) {
            titleEl.textContent = `${ticker} — ₹${data.underlying_price.toLocaleString('en-IN')}`;
        }
    } catch (e) {
        console.error(`Failed to load chain for ${ticker}:`, e.message);
    }
}

async function selectExpiry(expiry) {
    if (!APP_STATE.currentTicker) return;
    APP_STATE.currentExpiry = expiry;

    try {
        const data = await api.get(`chain/${APP_STATE.currentTicker}?expiry=${expiry}`);
        APP_STATE.chain = data;
        renderExpiryTabs(data.expirations);
        renderChain(data.chain);
    } catch (e) {
        console.error('Failed to load expiry chain:', e.message);
    }
}

function renderExpiryTabs(expirations) {
    const tabsEl = document.getElementById('expiry-tabs');
    if (!tabsEl) return;

    tabsEl.innerHTML = expirations.map(exp => `
        <button class="expiry-tab ${exp === APP_STATE.currentExpiry ? 'active' : ''}"
                onclick="selectExpiry('${exp}')">
            ${exp}
        </button>
    `).join('');
}

function renderChain(chain) {
    const tableBody = document.getElementById('chain-tbody');
    if (!tableBody) return;

    if (!chain || chain.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="9" class="empty-state">Select a ticker to view the options chain</td></tr>';
        return;
    }

    tableBody.innerHTML = chain.map(row => `
        <tr>
            <td class="call-side">${row.call_bid.toFixed(2)} / ${row.call_ask.toFixed(2)}</td>
            <td class="call-side">${formatNumber(row.call_delta, 3)}</td>
            <td class="call-side">${formatNumber(row.call_theta, 3)}</td>
            <td class="strike-col">${row.strike.toFixed(1)}</td>
            <td class="put-side">${row.put_bid.toFixed(2)} / ${row.put_ask.toFixed(2)}</td>
            <td class="put-side">${formatNumber(row.put_delta, 3)}</td>
            <td class="put-side">${formatNumber(row.put_theta, 3)}</td>
        </tr>
    `).join('');
}

// ==========================================================================
// Strategy Builder
// ==========================================================================

function addLeg() {
    if (APP_STATE.legs.length >= 4) return;

    // Pre-fill with ATM strike and current expiry if available
    let defaultStrike = '';
    let defaultExpiry = APP_STATE.currentExpiry || '';

    if (APP_STATE.chain && APP_STATE.chain.chain && APP_STATE.chain.chain.length > 0) {
        const strikes = APP_STATE.chain.chain.map(r => r.strike);
        const underlying = APP_STATE.chain.underlying_price || 0;
        // Find closest to ATM
        defaultStrike = strikes.reduce((best, s) =>
            Math.abs(s - underlying) < Math.abs(best - underlying) ? s : best, strikes[0]);
    }

    if (!defaultExpiry && APP_STATE.chain && APP_STATE.chain.expirations && APP_STATE.chain.expirations.length > 0) {
        defaultExpiry = APP_STATE.chain.expirations[0];
    }

    APP_STATE.legs.push({
        type: 'call',
        action: 'buy',
        strike: defaultStrike,
        expiry: defaultExpiry,
        qty: 1,
    });

    renderLegs();
}

function removeLeg(index) {
    APP_STATE.legs.splice(index, 1);
    renderLegs();
}

function updateLeg(index, field, value) {
    APP_STATE.legs[index][field] = value;
    updateStrategySummary();
}

function renderLegs() {
    const container = document.getElementById('legs-container');
    if (!container) return;

    if (APP_STATE.legs.length === 0) {
        container.innerHTML = '<div class="empty-state">Click "Add Leg" or choose a strategy template</div>';
        updateStrategySummary();
        return;
    }

    // Get available strikes and expirations from loaded chain
    const strikes = (APP_STATE.chain && APP_STATE.chain.chain)
        ? APP_STATE.chain.chain.map(r => r.strike).sort((a, b) => a - b)
        : [];
    const expirations = (APP_STATE.chain && APP_STATE.chain.expirations)
        ? APP_STATE.chain.expirations
        : [];

    const strikeOptions = strikes.map(s => `<option value="${s}">${s}</option>`).join('');
    const expiryOptions = expirations.map(e => `<option value="${e}">${e}</option>`).join('');

    container.innerHTML = APP_STATE.legs.map((leg, i) => `
        <div class="leg-row">
            <select onchange="updateLeg(${i}, 'action', this.value)">
                <option value="buy" ${leg.action === 'buy' ? 'selected' : ''}>Buy</option>
                <option value="sell" ${leg.action === 'sell' ? 'selected' : ''}>Sell</option>
            </select>
            <select onchange="updateLeg(${i}, 'type', this.value)">
                <option value="call" ${leg.type === 'call' ? 'selected' : ''}>Call</option>
                <option value="put" ${leg.type === 'put' ? 'selected' : ''}>Put</option>
            </select>
            <select onchange="updateLeg(${i}, 'strike', parseFloat(this.value))">
                <option value="">Strike</option>
                ${strikes.map(s => `<option value="${s}" ${leg.strike == s ? 'selected' : ''}>${s}</option>`).join('')}
            </select>
            <input type="number" placeholder="Qty" value="${leg.qty}" min="1" max="10"
                   oninput="updateLeg(${i}, 'qty', parseInt(this.value) || 1)" style="width:60px">
            <select onchange="updateLeg(${i}, 'expiry', this.value)">
                <option value="">Expiry</option>
                ${expirations.map(e => `<option value="${e}" ${leg.expiry === e ? 'selected' : ''}>${e}</option>`).join('')}
            </select>
            <button class="leg-remove" onclick="removeLeg(${i})">×</button>
        </div>
    `).join('');

    updateStrategySummary();
}

function updateStrategySummary() {
    // Placeholder computation — real logic would calculate from chain data
    const summary = computeStrategySummary();
    const netEl = document.getElementById('summary-net');
    const profitEl = document.getElementById('summary-max-profit');
    const lossEl = document.getElementById('summary-max-loss');

    if (netEl) netEl.textContent = formatCurrency(summary.net);
    if (profitEl) profitEl.textContent = formatCurrency(summary.maxProfit);
    if (lossEl) lossEl.textContent = formatCurrency(summary.maxLoss);
}

function computeStrategySummary() {
    if (!APP_STATE.chain || APP_STATE.legs.length === 0) {
        return { net: 0, maxProfit: 0, maxLoss: 0 };
    }

    let net = 0;
    APP_STATE.legs.forEach(leg => {
        const chainRow = APP_STATE.chain.chain.find(r =>
            Math.abs(r.strike - leg.strike) < 0.01
        );
        if (!chainRow) return;

        const side = leg.type === 'call' ? 'call' : 'put';
        const mid = (chainRow[`${side}_bid`] + chainRow[`${side}_ask`]) / 2;
        const cost = mid * (leg.qty || 1);

        if (leg.action === 'buy') net -= cost;
        else net += cost;
    });

    return {
        net: net,
        maxProfit: net > 0 ? net : Math.abs(net) * 2,
        maxLoss: net < 0 ? Math.abs(net) : net * 2,
    };
}

// ==========================================================================
// Deploy Trade (with Pre-Trade Confirmation Flow)
// ==========================================================================

async function deployTrade() {
    if (!APP_STATE.profileId || !APP_STATE.currentTicker || APP_STATE.legs.length === 0) {
        alert('Select a ticker and add at least one leg before deploying.');
        return;
    }

    // Step 1: Build the trade payload
    const payload = {
        profile_id: APP_STATE.profileId,
        ticker: APP_STATE.currentTicker,
        strategy_type: APP_STATE.legs.length > 2 ? 'multi_leg' : 'single',
        legs: APP_STATE.legs.map(leg => ({
            contract_type: leg.type,
            strike: parseFloat(leg.strike) || 0,
            expiration: leg.expiry || APP_STATE.currentExpiry || '2025-01-30',
            quantity: parseInt(leg.qty) || 1,
            action: leg.action,
        })),
        chain_opened_at: APP_STATE.chainOpenedAt || new Date().toISOString(),
        confirmation_proceeded: false, // Will update after confirmation
    };

    // Step 2: Show pre-trade confirmation modal with behavioral state
    const confirmed = await showPreTradeConfirmation();
    if (!confirmed) {
        // User cancelled — log telemetry
        logTelemetry('cancelled');
        return;
    }

    // Step 3: Execute the trade
    payload.confirmation_proceeded = true;
    const btn = document.getElementById('btn-deploy');
    if (btn) btn.disabled = true;

    try {
        const result = await api.post('trades', payload);

        // Play fill sound on successful trade
        if (typeof playSound === 'function') playSound('fill');

        // Flash success
        const hudEl = document.querySelector('.pane-right');
        if (hudEl) flashElement(hudEl, 'win');

        // Log telemetry
        logTelemetry('proceeded');

        // Clear legs
        APP_STATE.legs = [];
        renderLegs();

        // Reload profile data
        await loadProfile();
        await loadOpenPositions();
        await loadBehavioral();
        await loadXP();
    } catch (e) {
        const msg = typeof e.message === 'string' ? e.message : JSON.stringify(e.message);
        alert('Trade failed: ' + msg);
    } finally {
        if (btn) btn.disabled = false;
    }
}

// ==========================================================================
// Pre-Trade Confirmation Modal
// ==========================================================================

async function showPreTradeConfirmation() {
    return new Promise(async (resolve) => {
        // Fetch current behavioral state
        let behavioralState = null;
        try {
            behavioralState = await api.get(`behavioral/${APP_STATE.profileId}`);
        } catch (e) {
            // Continue without behavioral data if unavailable
        }

        // Fetch risk gate warnings
        let riskWarnings = [];
        try {
            const expiry = APP_STATE.currentExpiry || (APP_STATE.legs[0] && APP_STATE.legs[0].expiry) || '';
            const ticker = APP_STATE.currentTicker || '';
            // Estimate position_pct from legs (use 5 as default if unknown)
            const positionPct = 5;
            const riskData = await api.get(
                `risk-check/${APP_STATE.profileId}?position_pct=${positionPct}&ticker=${encodeURIComponent(ticker)}&expiry=${encodeURIComponent(expiry)}`
            );
            if (riskData && riskData.warnings) {
                riskWarnings = riskData.warnings;
            }
        } catch (e) {
            // Continue without risk warnings if unavailable
        }

        // Play alert sound if warnings are present
        if (riskWarnings.length > 0 && typeof playSound === 'function') {
            playSound('alert');
        }

        // Build warnings HTML
        let warningsHTML = '';
        if (riskWarnings.length > 0) {
            warningsHTML = '<div style="background:rgba(255,100,0,0.1); border:1px solid var(--orange); border-radius:var(--radius); padding:10px; margin:12px 0; font-size:12px; text-align:left;">';
            for (const w of riskWarnings) {
                if (w.type === 'risk_gate') {
                    warningsHTML += `<div style="margin-bottom:4px;">⚠️ This position risks ${w.position_pct}% of your portfolio</div>`;
                } else if (w.type === 'iv_crush') {
                    warningsHTML += `<div style="margin-bottom:4px;">⚠️ Earnings event within 48 hours for ${APP_STATE.currentTicker || 'ticker'}</div>`;
                } else if (w.type === 'penalty') {
                    const expiresAt = w.expires_at ? new Date(w.expires_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : 'unknown';
                    warningsHTML += `<div style="margin-bottom:4px;">⚠️ Allocation limit reduced to 3% (penalty active until ${expiresAt})</div>`;
                }
            }
            warningsHTML += '</div>';
        }

        // Build modal content
        let stateHTML = '';
        if (behavioralState && behavioralState.total_trades >= 6) {
            stateHTML = `
                <div style="text-align:left; background:var(--bg-input); padding:12px; border-radius:var(--radius); margin:12px 0; font-size:12px; line-height:1.8;">
                    <div style="font-size:10px; text-transform:uppercase; color:var(--text-muted); margin-bottom:6px; letter-spacing:0.5px;">Mirror's Pre-Trade Behavioral State</div>
                    ${behavioralState.discipline_rating != null ? `<div>Discipline: <strong>${behavioralState.discipline_rating.toFixed(0)}%</strong></div>` : ''}
                    ${behavioralState.patience_score != null ? `<div>Patience: <strong>${behavioralState.patience_score.toFixed(0)}s</strong></div>` : ''}
                    ${behavioralState.emotional_reactivity != null ? `<div>Emotional Reactivity: <strong>${behavioralState.emotional_reactivity.toFixed(0)}/100</strong></div>` : ''}
                    <div>Streak: <strong>🔥 ${behavioralState.current_streak || 0}</strong></div>
                </div>
            `;
        }

        // Create modal
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.id = 'pretrade-modal';
        modal.innerHTML = `
            <div class="modal" style="max-width:440px;">
                <h2 style="color:var(--yellow); font-size:1.1rem;">Would you do this with real money?</h2>
                ${warningsHTML}
                ${stateHTML}
                <p style="font-size:12px; color:var(--text-secondary); line-height:1.6; margin:12px 0;">
                    This is YOUR data. Not advice. All decisions are yours alone.
                </p>
                <div style="display:flex; gap:10px; justify-content:center; margin-top:16px;">
                    <button class="btn btn-deploy" id="pretrade-yes" style="padding:10px 24px; font-size:13px;">Yes — Deploy Credits</button>
                    <button class="btn btn-cancel" id="pretrade-cancel" style="padding:10px 24px; font-size:13px;">Cancel</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Wait for user decision
        document.getElementById('pretrade-yes').addEventListener('click', () => {
            modal.remove();
            resolve(true);
        });
        document.getElementById('pretrade-cancel').addEventListener('click', () => {
            modal.remove();
            resolve(false);
        });
    });
}

// ==========================================================================
// Telemetry Logging
// ==========================================================================

async function logTelemetry(decision) {
    if (!APP_STATE.profileId) return;
    try {
        await api.post(`telemetry/${APP_STATE.profileId}`, {
            trade_id: null,
            risk_gate_warnings: [],
            trader_decision: decision,
        });
    } catch (e) {
        console.debug('Telemetry log failed:', e.message);
    }
}

// ==========================================================================
// Load Open Positions
// ==========================================================================

async function loadOpenPositions() {
    if (!APP_STATE.profileId) return;

    try {
        const data = await api.get(`positions/${APP_STATE.profileId}`);
        const positions = data.positions || data;
        updateHUDPositions(positions);
    } catch (e) {
        console.error('Failed to load positions:', e.message);
    }
}

// ==========================================================================
// Close Position
// ==========================================================================

async function closePosition(positionId) {
    return new Promise((resolve) => {
        // Create close modal with dropdown
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.id = 'close-modal';
        modal.innerHTML = `
            <div class="modal" style="max-width:380px;">
                <h2 style="color:var(--text-primary); font-size:1.1rem; margin-bottom:16px;">Close Position</h2>
                <p style="font-size:12px; color:var(--text-secondary); margin-bottom:12px;">How would you tag this exit?</p>
                <select id="close-outcome-select" style="width:100%; padding:10px; margin-bottom:16px;">
                    <option value="success">✅ Success — I hit my target</option>
                    <option value="failure">❌ Failure — It went against me</option>
                    <option value="slippage">⚠️ Slippage — Execution cost hurt</option>
                </select>
                <div style="display:flex; gap:10px; justify-content:center;">
                    <button class="btn btn-cancel" id="close-confirm-btn" style="padding:10px 20px;">Close Position</button>
                    <button class="btn btn-secondary" id="close-cancel-btn" style="padding:10px 20px;">Keep Open</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        document.getElementById('close-confirm-btn').addEventListener('click', async () => {
            const tag = document.getElementById('close-outcome-select').value;
            modal.remove();

            try {
                await api.post(`positions/${positionId}/close`, { outcome_tag: tag });

                // Play win/loss sound based on outcome
                if (typeof playSound === 'function') {
                    if (tag === 'success') {
                        playSound('win');
                    } else {
                        playSound('loss');
                    }
                }

                // Flash based on outcome
                const hudEl = document.querySelector('.pane-right');
                flashElement(hudEl, tag === 'success' ? 'win' : 'loss');

                // Reload
                await loadProfile();
                await loadOpenPositions();
                await loadBehavioral();
                await loadXP();
            } catch (e) {
                alert('Close failed: ' + (e.message || 'Unknown error'));
            }
        });

        document.getElementById('close-cancel-btn').addEventListener('click', () => {
            modal.remove();
        });
    });
}

// ==========================================================================
// Behavioral Metrics Loading
// ==========================================================================

async function loadBehavioral() {
    if (!APP_STATE.profileId) return;

    try {
        const data = await api.get(`behavioral/${APP_STATE.profileId}`);
        updateBehavioralGauges({
            discipline: data.discipline_rating,
            patience: data.patience_score,
            sizing: data.sizing_consistency,
            emotional: data.emotional_reactivity,
            streak: data.current_streak,
        });
    } catch (e) {
        console.debug('Behavioral data not available:', e.message);
    }
}

// ==========================================================================
// XP / Achievements Loading
// ==========================================================================

async function loadXP() {
    if (!APP_STATE.profileId) return;

    try {
        const data = await api.get(`behavioral/${APP_STATE.profileId}/achievements`);
        const xpEl = document.getElementById('hud-xp');
        if (xpEl && data) {
            xpEl.textContent = `${data.xp || 0} XP (Lv ${data.level || 1})`;
        }
    } catch (e) {
        console.debug('XP data not available:', e.message);
    }
}

// ==========================================================================
// Strategy Templates
// ==========================================================================

function applyStrategy(strategyName) {
    // Clear current legs
    APP_STATE.legs = [];

    // Get actual strikes from loaded chain
    const chain = APP_STATE.chain;
    if (!chain || !chain.chain || chain.chain.length === 0) {
        alert('Please select a ticker first to load the options chain.');
        return;
    }

    const strikes = chain.chain.map(r => r.strike).sort((a, b) => a - b);
    const underlying = chain.underlying_price || strikes[Math.floor(strikes.length / 2)];
    
    // Find ATM strike (closest to underlying price)
    const atmIdx = strikes.reduce((bestIdx, s, idx) => 
        Math.abs(s - underlying) < Math.abs(strikes[bestIdx] - underlying) ? idx : bestIdx, 0);
    
    const expiry = APP_STATE.currentExpiry || (chain.expirations && chain.expirations[0]) || '';

    switch (strategyName) {
        case 'iron-condor': {
            // Buy OTM put, Sell closer put, Sell closer call, Buy OTM call
            const putBuyIdx = Math.max(0, atmIdx - 4);
            const putSellIdx = Math.max(0, atmIdx - 2);
            const callSellIdx = Math.min(strikes.length - 1, atmIdx + 2);
            const callBuyIdx = Math.min(strikes.length - 1, atmIdx + 4);
            APP_STATE.legs = [
                { type: 'put', action: 'buy', strike: strikes[putBuyIdx], expiry: expiry, qty: 1 },
                { type: 'put', action: 'sell', strike: strikes[putSellIdx], expiry: expiry, qty: 1 },
                { type: 'call', action: 'sell', strike: strikes[callSellIdx], expiry: expiry, qty: 1 },
                { type: 'call', action: 'buy', strike: strikes[callBuyIdx], expiry: expiry, qty: 1 },
            ];
            break;
        }
        case 'vertical-spread': {
            // Buy ATM call, sell OTM call
            const buyIdx = atmIdx;
            const sellIdx = Math.min(strikes.length - 1, atmIdx + 2);
            APP_STATE.legs = [
                { type: 'call', action: 'buy', strike: strikes[buyIdx], expiry: expiry, qty: 1 },
                { type: 'call', action: 'sell', strike: strikes[sellIdx], expiry: expiry, qty: 1 },
            ];
            break;
        }
        case 'straddle': {
            // Buy ATM call + ATM put
            APP_STATE.legs = [
                { type: 'call', action: 'buy', strike: strikes[atmIdx], expiry: expiry, qty: 1 },
                { type: 'put', action: 'buy', strike: strikes[atmIdx], expiry: expiry, qty: 1 },
            ];
            break;
        }
        case 'strangle': {
            // Buy OTM call + OTM put
            const otmCallIdx = Math.min(strikes.length - 1, atmIdx + 2);
            const otmPutIdx = Math.max(0, atmIdx - 2);
            APP_STATE.legs = [
                { type: 'call', action: 'buy', strike: strikes[otmCallIdx], expiry: expiry, qty: 1 },
                { type: 'put', action: 'buy', strike: strikes[otmPutIdx], expiry: expiry, qty: 1 },
            ];
            break;
        }
    }

    renderLegs();
}

// ==========================================================================
// Daily Focus Banner (Phase 10 — Mirror's Daily Focus)
// ==========================================================================

async function loadDailyFocus() {
    if (localStorage.getItem('ot_focus_dismissed_today') === new Date().toDateString()) return;

    try {
        const data = await api.get(`behavioral/${APP_STATE.profileId}`);
        const focusText = generateFocusMessage(data);
        if (focusText) {
            document.getElementById('daily-focus-text').textContent = focusText;
            document.getElementById('daily-focus-banner').style.display = 'flex';
        }
    } catch(e) {}
}

function generateFocusMessage(data) {
    if (!data || data.total_trades < 6) return null;

    // Priority: most costly pattern from fix_one_thing
    if (data.fix_one_thing && data.fix_one_thing.pattern) {
        const pattern = data.fix_one_thing.pattern;
        if (pattern === 'Revenge Trading') return "Today's focus: Notice if you increase position size after a loss. Pause before reacting.";
        if (pattern === 'Overconfidence') return "Today's focus: After wins, keep your next trade at normal size. Confidence ≠ bigger bets.";
        if (pattern === 'Impulse Exit') return "Today's focus: If a trade is green, let it run to your target. Don't grab small profits early.";
    }

    // Fallback: metric-based
    if (data.emotional_reactivity > 40) return "Today's focus: Notice if you increase position size after a loss.";
    if (data.discipline_rating !== null && data.discipline_rating < 60) return "Today's focus: Keep each trade within 5% of your portfolio.";
    if (data.patience_score !== null && data.patience_score < 30) return "Today's focus: Pause 60 seconds before clicking Deploy.";
    return "Today's focus: Stick to your plan. Mirror is watching.";
}

function dismissDailyFocus() {
    document.getElementById('daily-focus-banner').style.display = 'none';
    localStorage.setItem('ot_focus_dismissed_today', new Date().toDateString());
}

// ==========================================================================
// Initialization
// ==========================================================================

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Check disclaimer
    checkDisclaimer();

    // 2. Load profile
    await loadProfile();

    // 3. Load tickers
    await loadTickers();

    // 4. Load behavioral metrics
    await loadBehavioral();

    // 5. Load open positions
    await loadOpenPositions();

    // 6. Load XP / Achievements
    await loadXP();

    // 7. Load Daily Focus Banner (Mirror)
    await loadDailyFocus();

    // 8. Bind search input
    const searchInput = document.getElementById('ticker-search');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            filterTickers(e.target.value);
        });
    }

    // 9. Initialize empty legs view
    renderLegs();
});
