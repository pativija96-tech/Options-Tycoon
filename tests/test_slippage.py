"""Unit tests for slippage cost calculation."""

import pytest
from engine.slippage import compute_slippage


# Sample chain data matching the mock data structure
SAMPLE_CHAIN = {
    "expirations": [
        {
            "date": "2025-02-27",
            "chain": [
                {
                    "strike": 22500,
                    "call": {"bid": 135, "ask": 140, "last": 137, "volume": 30000, "oi": 145000, "iv": 0.16},
                    "put": {"bid": 138, "ask": 142, "last": 140, "volume": 28000, "oi": 138000, "iv": 0.16},
                },
                {
                    "strike": 22600,
                    "call": {"bid": 88, "ask": 92, "last": 90, "volume": 20000, "oi": 102000, "iv": 0.165},
                    "put": {"bid": 190, "ask": 195, "last": 192, "volume": 12000, "oi": 78000, "iv": 0.17},
                },
            ],
        },
        {
            "date": "2025-03-27",
            "chain": [
                {
                    "strike": 22500,
                    "call": {"bid": 298, "ask": 305, "last": 301, "volume": 11000, "oi": 72000, "iv": 0.18},
                    "put": {"bid": 292, "ask": 300, "last": 296, "volume": 10000, "oi": 68000, "iv": 0.18},
                },
            ],
        },
    ]
}


class TestComputeSlippage:
    """Tests for compute_slippage function."""

    def test_single_call_leg(self):
        """Single call leg: spread = 140 - 135 = 5, slippage = 0.5 * 5 * 1 = 2.5."""
        legs = [{"contract_type": "call", "strike": 22500, "expiration": "2025-02-27", "quantity": 1, "action": "buy"}]
        result = compute_slippage(legs, SAMPLE_CHAIN)
        assert result == 2.5

    def test_single_put_leg(self):
        """Single put leg: spread = 142 - 138 = 4, slippage = 0.5 * 4 * 1 = 2.0."""
        legs = [{"contract_type": "put", "strike": 22500, "expiration": "2025-02-27", "quantity": 1, "action": "buy"}]
        result = compute_slippage(legs, SAMPLE_CHAIN)
        assert result == 2.0

    def test_quantity_multiplier(self):
        """Quantity multiplies slippage: spread = 5, slippage = 0.5 * 5 * 3 = 7.5."""
        legs = [{"contract_type": "call", "strike": 22500, "expiration": "2025-02-27", "quantity": 3, "action": "buy"}]
        result = compute_slippage(legs, SAMPLE_CHAIN)
        assert result == 7.5

    def test_negative_quantity_uses_abs(self):
        """Negative quantity treated as absolute value."""
        legs = [{"contract_type": "call", "strike": 22500, "expiration": "2025-02-27", "quantity": -2, "action": "sell"}]
        result = compute_slippage(legs, SAMPLE_CHAIN)
        assert result == 5.0  # 0.5 * 5 * 2

    def test_multi_leg_strategy(self):
        """Iron condor style: sum slippage across all legs."""
        legs = [
            {"contract_type": "call", "strike": 22500, "expiration": "2025-02-27", "quantity": 1, "action": "sell"},
            {"contract_type": "call", "strike": 22600, "expiration": "2025-02-27", "quantity": 1, "action": "buy"},
            {"contract_type": "put", "strike": 22500, "expiration": "2025-02-27", "quantity": 1, "action": "sell"},
            {"contract_type": "put", "strike": 22600, "expiration": "2025-02-27", "quantity": 1, "action": "buy"},
        ]
        # call 22500: 0.5 * (140-135) * 1 = 2.5
        # call 22600: 0.5 * (92-88) * 1 = 2.0
        # put 22500: 0.5 * (142-138) * 1 = 2.0
        # put 22600: 0.5 * (195-190) * 1 = 2.5
        result = compute_slippage(legs, SAMPLE_CHAIN)
        assert result == 9.0

    def test_missing_contract_returns_zero_slippage(self):
        """Contract not found in chain_data contributes 0 slippage."""
        legs = [{"contract_type": "call", "strike": 99999, "expiration": "2025-02-27", "quantity": 1, "action": "buy"}]
        result = compute_slippage(legs, SAMPLE_CHAIN)
        assert result == 0.0

    def test_missing_expiration_returns_zero_slippage(self):
        """Expiration not found in chain_data contributes 0 slippage."""
        legs = [{"contract_type": "call", "strike": 22500, "expiration": "2099-12-31", "quantity": 1, "action": "buy"}]
        result = compute_slippage(legs, SAMPLE_CHAIN)
        assert result == 0.0

    def test_empty_legs_returns_zero(self):
        """No legs means no slippage."""
        result = compute_slippage([], SAMPLE_CHAIN)
        assert result == 0.0

    def test_empty_chain_data_returns_zero(self):
        """Empty chain data means no slippage for any leg."""
        legs = [{"contract_type": "call", "strike": 22500, "expiration": "2025-02-27", "quantity": 1, "action": "buy"}]
        result = compute_slippage(legs, {"expirations": []})
        assert result == 0.0

    def test_different_expiration(self):
        """Leg from a different expiration date is found correctly."""
        legs = [{"contract_type": "call", "strike": 22500, "expiration": "2025-03-27", "quantity": 1, "action": "buy"}]
        # spread = 305 - 298 = 7, slippage = 0.5 * 7 * 1 = 3.5
        result = compute_slippage(legs, SAMPLE_CHAIN)
        assert result == 3.5

    def test_result_always_non_negative(self):
        """Slippage is always >= 0 regardless of inputs."""
        legs = [{"contract_type": "call", "strike": 22500, "expiration": "2025-02-27", "quantity": 0, "action": "buy"}]
        result = compute_slippage(legs, SAMPLE_CHAIN)
        assert result >= 0.0

    def test_result_rounded_to_2_decimal_places(self):
        """Result is rounded to 2 decimal places."""
        # Using a chain with odd spread to get fractional result
        chain = {
            "expirations": [
                {
                    "date": "2025-01-01",
                    "chain": [
                        {"strike": 100, "call": {"bid": 10, "ask": 13, "last": 11}, "put": {"bid": 5, "ask": 8, "last": 6}},
                    ],
                }
            ]
        }
        legs = [{"contract_type": "call", "strike": 100, "expiration": "2025-01-01", "quantity": 1, "action": "buy"}]
        result = compute_slippage(legs, chain)
        # spread = 3, slippage = 0.5 * 3 * 1 = 1.5
        assert result == 1.5
        # Verify it's actually rounded
        assert result == round(result, 2)
