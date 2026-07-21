"""Tests for engine/strategies.py — strategy templates, leg generation, and metrics."""

import pytest
from engine.strategies import (
    STRATEGY_TEMPLATES,
    generate_strategy_legs,
    compute_strategy_metrics,
)


# ---------------------------------------------------------------------------
# Sample chain data fixture (mirrors NIFTY mock structure)
# ---------------------------------------------------------------------------

@pytest.fixture
def nifty_chain():
    """Minimal NIFTY-like chain data for testing."""
    return {
        "ticker": "NIFTY",
        "underlying_price": 22500.0,
        "expirations": [
            {
                "date": "2025-02-27",
                "chain": [
                    {"strike": 22000, "call": {"bid": 520, "ask": 525, "last": 522, "volume": 15000, "oi": 85000, "iv": 0.18}, "put": {"bid": 22, "ask": 25, "last": 23, "volume": 8000, "oi": 62000, "iv": 0.16}},
                    {"strike": 22200, "call": {"bid": 345, "ask": 350, "last": 347, "volume": 18000, "oi": 95000, "iv": 0.168}, "put": {"bid": 48, "ask": 52, "last": 50, "volume": 11000, "oi": 71000, "iv": 0.17}},
                    {"strike": 22300, "call": {"bid": 265, "ask": 270, "last": 267, "volume": 22000, "oi": 110000, "iv": 0.165}, "put": {"bid": 68, "ask": 72, "last": 70, "volume": 14000, "oi": 82000, "iv": 0.175}},
                    {"strike": 22400, "call": {"bid": 195, "ask": 200, "last": 197, "volume": 25000, "oi": 125000, "iv": 0.162}, "put": {"bid": 98, "ask": 102, "last": 100, "volume": 16000, "oi": 90000, "iv": 0.18}},
                    {"strike": 22500, "call": {"bid": 135, "ask": 140, "last": 137, "volume": 30000, "oi": 145000, "iv": 0.16}, "put": {"bid": 138, "ask": 142, "last": 140, "volume": 28000, "oi": 138000, "iv": 0.16}},
                    {"strike": 22600, "call": {"bid": 88, "ask": 92, "last": 90, "volume": 20000, "oi": 102000, "iv": 0.165}, "put": {"bid": 190, "ask": 195, "last": 192, "volume": 12000, "oi": 78000, "iv": 0.17}},
                    {"strike": 22700, "call": {"bid": 52, "ask": 55, "last": 53, "volume": 15000, "oi": 88000, "iv": 0.17}, "put": {"bid": 255, "ask": 260, "last": 257, "volume": 9000, "oi": 65000, "iv": 0.175}},
                ],
            },
        ],
    }


# ---------------------------------------------------------------------------
# Template structure tests
# ---------------------------------------------------------------------------

class TestStrategyTemplates:
    def test_all_required_strategies_exist(self):
        """All strategy types specified in requirements 6.1 are present."""
        required = {"iron_condor", "bull_call_spread", "bear_put_spread", "straddle", "strangle"}
        assert required.issubset(set(STRATEGY_TEMPLATES.keys()))

    def test_iron_condor_has_4_legs(self):
        assert STRATEGY_TEMPLATES["iron_condor"]["leg_count"] == 4
        assert len(STRATEGY_TEMPLATES["iron_condor"]["legs"]) == 4

    def test_spreads_have_2_legs(self):
        assert STRATEGY_TEMPLATES["bull_call_spread"]["leg_count"] == 2
        assert STRATEGY_TEMPLATES["bear_put_spread"]["leg_count"] == 2

    def test_straddle_has_2_legs(self):
        assert STRATEGY_TEMPLATES["straddle"]["leg_count"] == 2

    def test_strangle_has_2_legs(self):
        assert STRATEGY_TEMPLATES["strangle"]["leg_count"] == 2

    def test_all_templates_have_description(self):
        for key, template in STRATEGY_TEMPLATES.items():
            assert "description" in template, f"{key} missing description"
            assert len(template["description"]) > 10


# ---------------------------------------------------------------------------
# Leg generation tests
# ---------------------------------------------------------------------------

class TestGenerateStrategyLegs:
    def test_iron_condor_generates_4_legs(self, nifty_chain):
        legs = generate_strategy_legs("iron_condor", 22500.0, nifty_chain)
        assert len(legs) == 4

    def test_iron_condor_leg_structure(self, nifty_chain):
        legs = generate_strategy_legs("iron_condor", 22500.0, nifty_chain)
        # Should have: buy put (far OTM), sell put (OTM), sell call (OTM), buy call (far OTM)
        buy_puts = [l for l in legs if l["contract_type"] == "put" and l["action"] == "buy"]
        sell_puts = [l for l in legs if l["contract_type"] == "put" and l["action"] == "sell"]
        sell_calls = [l for l in legs if l["contract_type"] == "call" and l["action"] == "sell"]
        buy_calls = [l for l in legs if l["contract_type"] == "call" and l["action"] == "buy"]
        assert len(buy_puts) == 1
        assert len(sell_puts) == 1
        assert len(sell_calls) == 1
        assert len(buy_calls) == 1
        # Buy put should be further OTM (lower strike) than sell put
        assert buy_puts[0]["strike"] < sell_puts[0]["strike"]
        # Buy call should be further OTM (higher strike) than sell call
        assert buy_calls[0]["strike"] > sell_calls[0]["strike"]

    def test_bull_call_spread_generates_2_legs(self, nifty_chain):
        legs = generate_strategy_legs("bull_call_spread", 22500.0, nifty_chain)
        assert len(legs) == 2
        buy_leg = [l for l in legs if l["action"] == "buy"][0]
        sell_leg = [l for l in legs if l["action"] == "sell"][0]
        assert buy_leg["contract_type"] == "call"
        assert sell_leg["contract_type"] == "call"
        assert buy_leg["strike"] <= sell_leg["strike"]

    def test_bear_put_spread_generates_2_legs(self, nifty_chain):
        legs = generate_strategy_legs("bear_put_spread", 22500.0, nifty_chain)
        assert len(legs) == 2
        buy_leg = [l for l in legs if l["action"] == "buy"][0]
        sell_leg = [l for l in legs if l["action"] == "sell"][0]
        assert buy_leg["contract_type"] == "put"
        assert sell_leg["contract_type"] == "put"
        # Buy put is ATM (higher), sell put is OTM (lower)
        assert buy_leg["strike"] >= sell_leg["strike"]

    def test_straddle_same_strike(self, nifty_chain):
        legs = generate_strategy_legs("straddle", 22500.0, nifty_chain)
        assert len(legs) == 2
        assert legs[0]["strike"] == legs[1]["strike"]
        types = {l["contract_type"] for l in legs}
        assert types == {"call", "put"}
        assert all(l["action"] == "buy" for l in legs)

    def test_strangle_different_strikes(self, nifty_chain):
        legs = generate_strategy_legs("strangle", 22500.0, nifty_chain)
        assert len(legs) == 2
        types = {l["contract_type"] for l in legs}
        assert types == {"call", "put"}
        assert all(l["action"] == "buy" for l in legs)
        # Strikes should differ (OTM on both sides)
        put_leg = [l for l in legs if l["contract_type"] == "put"][0]
        call_leg = [l for l in legs if l["contract_type"] == "call"][0]
        assert put_leg["strike"] < call_leg["strike"]

    def test_legs_have_all_required_fields(self, nifty_chain):
        legs = generate_strategy_legs("straddle", 22500.0, nifty_chain)
        required_fields = {"contract_type", "action", "strike", "expiration", "quantity", "bid", "ask", "mid_price"}
        for leg in legs:
            assert required_fields.issubset(set(leg.keys()))

    def test_unknown_strategy_raises(self, nifty_chain):
        with pytest.raises(ValueError, match="Unknown strategy type"):
            generate_strategy_legs("butterfly", 22500.0, nifty_chain)

    def test_empty_chain_raises(self):
        with pytest.raises(ValueError, match="No expiration data"):
            generate_strategy_legs("straddle", 22500.0, {"expirations": []})

    def test_custom_quantity(self, nifty_chain):
        legs = generate_strategy_legs("straddle", 22500.0, nifty_chain, quantity=3)
        assert all(l["quantity"] == 3 for l in legs)


# ---------------------------------------------------------------------------
# Strategy metrics tests
# ---------------------------------------------------------------------------

class TestComputeStrategyMetrics:
    def test_bull_call_spread_metrics(self, nifty_chain):
        """Max profit = width - net debit, max loss = net debit."""
        legs = generate_strategy_legs("bull_call_spread", 22500.0, nifty_chain)
        metrics = compute_strategy_metrics(legs)

        assert metrics["net_debit_or_credit"] < 0  # Net debit (buying lower, selling higher)
        net_debit = abs(metrics["net_debit_or_credit"])
        width = abs(legs[1]["strike"] - legs[0]["strike"])
        assert metrics["max_profit"] == round(width - net_debit, 2)
        assert metrics["max_loss"] == round(net_debit, 2)
        assert len(metrics["breakeven_points"]) == 1

    def test_bear_put_spread_metrics(self, nifty_chain):
        """Max profit = width - net debit, max loss = net debit."""
        legs = generate_strategy_legs("bear_put_spread", 22500.0, nifty_chain)
        metrics = compute_strategy_metrics(legs)

        assert metrics["net_debit_or_credit"] < 0  # Net debit
        net_debit = abs(metrics["net_debit_or_credit"])
        buy_put = [l for l in legs if l["action"] == "buy"][0]
        sell_put = [l for l in legs if l["action"] == "sell"][0]
        width = abs(buy_put["strike"] - sell_put["strike"])
        assert metrics["max_profit"] == round(width - net_debit, 2)
        assert metrics["max_loss"] == round(net_debit, 2)
        assert len(metrics["breakeven_points"]) == 1

    def test_iron_condor_metrics(self, nifty_chain):
        """Max profit = net credit, max loss = width - net credit."""
        legs = generate_strategy_legs("iron_condor", 22500.0, nifty_chain)
        metrics = compute_strategy_metrics(legs)

        # Iron condor should generate net credit (positive)
        if metrics["net_debit_or_credit"] > 0:
            net_credit = metrics["net_debit_or_credit"]
            assert metrics["max_profit"] == round(net_credit, 2)
            # Two breakeven points
            assert len(metrics["breakeven_points"]) == 2

    def test_straddle_metrics(self, nifty_chain):
        """Max loss = net debit, max profit = unlimited, two breakevens."""
        legs = generate_strategy_legs("straddle", 22500.0, nifty_chain)
        metrics = compute_strategy_metrics(legs)

        assert metrics["net_debit_or_credit"] < 0  # Net debit
        net_debit = abs(metrics["net_debit_or_credit"])
        assert metrics["max_loss"] == round(net_debit, 2)
        assert metrics["max_profit"] == float("inf")
        assert len(metrics["breakeven_points"]) == 2

    def test_strangle_metrics(self, nifty_chain):
        """Max loss = net debit, max profit = unlimited, two breakevens."""
        legs = generate_strategy_legs("strangle", 22500.0, nifty_chain)
        metrics = compute_strategy_metrics(legs)

        assert metrics["net_debit_or_credit"] < 0
        net_debit = abs(metrics["net_debit_or_credit"])
        assert metrics["max_loss"] == round(net_debit, 2)
        assert metrics["max_profit"] == float("inf")
        assert len(metrics["breakeven_points"]) == 2

    def test_empty_legs_returns_zeros(self):
        metrics = compute_strategy_metrics([])
        assert metrics["net_debit_or_credit"] == 0.0
        assert metrics["max_profit"] == 0.0
        assert metrics["max_loss"] == 0.0
        assert metrics["breakeven_points"] == []

    def test_metrics_contain_all_required_keys(self, nifty_chain):
        legs = generate_strategy_legs("straddle", 22500.0, nifty_chain)
        metrics = compute_strategy_metrics(legs)
        required_keys = {"net_debit_or_credit", "max_profit", "max_loss", "breakeven_points", "strategy_type_detected"}
        assert required_keys.issubset(set(metrics.keys()))
