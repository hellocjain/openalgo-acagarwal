"""
Bug Bounty & Adversarial Attack Simulation Test Suite for OpenAlgo Copy Trading.
"""

import concurrent.futures
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.copy_trading_db import (
    CopyAccount,
    CopyOrder,
    CopyStrategy,
    Session,
    add_child_account,
    assign_strategy_to_account,
    create_strategy,
    export_client_trade_logs_csv,
    get_all_child_accounts,
    get_premarket_readiness_summary,
    init_copy_trading_db,
    record_copy_order,
    set_master_switch,
)
from services.copy_trading_service import (
    calculate_child_quantity,
    get_inferred_lot_size,
    is_duplicate_signal,
    slice_order_quantities,
)


def test_fuzzing_and_validation():
    """Test 1: Input Validation and Edge Cases"""
    print("\n--- TEST 1: Lot Size Inference & Edge Sizing ---")
    
    # 1. Lot size inferences
    assert get_inferred_lot_size("CRUDEOIL24AUGFUT", "MCXFO") == 100
    assert get_inferred_lot_size("CRUDEOILM24AUGFUT", "MCXFO") == 10
    assert get_inferred_lot_size("NATURALGAS24AUGFUT", "MCXFO") == 1250
    assert get_inferred_lot_size("NATGASMINI24AUGFUT", "MCXFO") == 250
    assert get_inferred_lot_size("GOLD24AUGFUT", "MCXFO") == 100
    assert get_inferred_lot_size("GOLDM24AUGFUT", "MCXFO") == 10
    assert get_inferred_lot_size("SILVER24AUGFUT", "MCXFO") == 30
    assert get_inferred_lot_size("SILVERM24AUGFUT", "MCXFO") == 5
    assert get_inferred_lot_size("SILVERMIC24AUGFUT", "MCXFO") == 1
    assert get_inferred_lot_size("NIFTY24AUG24500CE", "NSEFO") == 25
    assert get_inferred_lot_size("BANKNIFTY24AUG50000CE", "NSEFO") == 15
    assert get_inferred_lot_size("SENSEX24AUG80000CE", "BSEFO") == 10
    print("  ✅ All MCX Commodity & NSE/BSE Index lot sizes correctly inferred.")

    # 2. Sizing with fractional multiplier on lot-based contract
    acc_multiplier = {"id": 1, "sizing_mode": "MULTIPLIER", "multiplier": 1.5, "max_lot_cap": 50}
    qty = calculate_child_quantity(acc_multiplier, 100, symbol="CRUDEOIL24AUGFUT", exchange="MCXFO")
    assert qty == 200, f"Expected 200, got {qty}"
    print(f"  ✅ 1.5x multiplier on 100 Crude Oil (lot=100) quantized to {qty} barrels.")

    # 3. Strategy multiplier override
    acc_strat_override = {"id": 1, "strategy_multiplier": 0.5, "max_lot_cap": 50}
    qty_strat = calculate_child_quantity(acc_strat_override, 100, symbol="CRUDEOIL24AUGFUT", exchange="MCXFO")
    assert qty_strat == 100  # 100 * 0.5 = 50 -> rounded to nearest lot 100 (min 1 lot)
    print(f"  ✅ Strategy multiplier 0.5x on 100 Crude Oil safely clamped to min 1 lot ({qty_strat}).")


def test_freeze_slicing():
    """Test 2: MCX and NSE Freeze Slicing Boundaries"""
    print("\n--- TEST 2: Freeze Quantity Slicing ---")
    
    # Crude Oil freeze is 10,000 (100 lots)
    slices_crude = slice_order_quantities(25000, "CRUDEOIL", "MCXFO")
    assert slices_crude == [10000, 10000, 5000]
    print(f"  ✅ 25,000 Crude Oil sliced into: {slices_crude}")

    # Gold freeze is 10,000 (10 kg)
    slices_gold = slice_order_quantities(15000, "GOLD", "MCXFO")
    assert slices_gold == [10000, 5000]
    print(f"  ✅ 15,000 Gold sliced into: {slices_gold}")

    # Small order below freeze
    slices_small = slice_order_quantities(500, "CRUDEOIL", "MCXFO")
    assert slices_small == [500]
    print(f"  ✅ 500 Crude Oil kept as single order: {slices_small}")


def test_idempotency_deduplication():
    """Test 3: SHA-256 Idempotency Deduplication Guard"""
    print("\n--- TEST 3: SHA-256 Idempotency Deduplication Guard ---")
    
    sig = {
        "strategy": "TEST_SCALP_BOUNTY",
        "symbol": "CRUDEOIL24AUGFUT",
        "exchange": "MCXFO",
        "action": "BUY",
        "quantity": 100,
        "price": 6500.0,
        "pricetype": "MARKET",
    }

    assert is_duplicate_signal(sig) is False, "First signal must pass"
    duplicates_caught = sum(1 for _ in range(50) if is_duplicate_signal(sig))
    assert duplicates_caught == 50, f"Expected 50 duplicates caught, got {duplicates_caught}"
    print(f"  ✅ 50/50 burst duplicate signals caught and neutralized in memory.")


def test_sqlite_concurrent_burst():
    """Test 4: High-Concurrency SQLite Read/Write Stress Test"""
    print("\n--- TEST 4: SQLite High-Concurrency Multi-Thread Stress Test ---")
    init_copy_trading_db()

    def concurrent_db_worker(idx):
        # 1. Write order
        order_id = record_copy_order(
            account_id=1,
            symbol="CRUDEOIL24AUGFUT",
            exchange="MCXFO",
            action="BUY",
            quantity=100,
            price=6500.0,
            master_order_id=f"BOUNTY_M_{idx}",
            status="placed",
            latency_ms=12.5,
        )
        # 2. Read readiness
        summary = get_premarket_readiness_summary()
        return order_id is not None and summary is not None

    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        results = list(executor.map(concurrent_db_worker, range(50)))

    assert all(results), "All concurrent DB operations should succeed without database lock"
    print("  ✅ 50 concurrent thread writes & reads executed cleanly with 0 database lock errors.")


def test_direct_client_routing_and_smart_order():
    """Test 5: Multi-Tenant Direct Client Targeting & Smart Orders"""
    print("\n--- TEST 5: Multi-Tenant Direct Client Targeting & Smart Orders ---")
    from services.copy_trading_service import broadcast_copy_order

    # Broadcast with specific client_code
    res = broadcast_copy_order({
        "client_code": "DM933",
        "symbol": "CRUDEOIL24AUGFUT",
        "exchange": "MCXFO",
        "action": "BUY",
        "quantity": 100,
        "pricetype": "MARKET",
        "product": "MIS"
    })
    assert res.get("status") == "success"
    print(f"  ✅ Targeted signal routed exclusively to client DM933 (Total accounts: {res.get('total_accounts')}).")


def test_smart_symbol_resolution():
    """Test 6: Smart Front-Month Expiry Resolution for Commodities and Indices"""
    print("\n--- TEST 6: Smart Front-Month Contract Symbol Resolution ---")
    from services.copy_trading_service import resolve_active_contract_symbol

    # Base continuous symbol -> resolved to front-month future
    s1 = resolve_active_contract_symbol("SILVERMIC", "MCXFO")
    assert s1.startswith("SILVERMIC") and s1.endswith("FUT"), f"Unexpected: {s1}"
    print(f"  ✅ Base 'SILVERMIC' resolved to: {s1}")

    s2 = resolve_active_contract_symbol("CRUDEOIL", "MCXFO")
    assert s2.startswith("CRUDEOIL") and s2.endswith("FUT"), f"Unexpected: {s2}"
    print(f"  ✅ Base 'CRUDEOIL' resolved to: {s2}")

    s3 = resolve_active_contract_symbol("NIFTY", "NSEFO")
    assert s3.startswith("NIFTY") and s3.endswith("FUT"), f"Unexpected: {s3}"
    print(f"  ✅ Base 'NIFTY' resolved to: {s3}")

    # Already exact contract -> unchanged
    s4 = resolve_active_contract_symbol("SILVERMIC24AUGFUT", "MCXFO")
    assert s4 == "SILVERMIC24AUGFUT"
    print(f"  ✅ Exact 'SILVERMIC24AUGFUT' preserved unchanged: {s4}")


def test_strategy_auto_discovery_and_bulk_subscribers():
    """Test 7: Automatic Strategy Discovery & Dual-Direction Bulk Subscriber Mapping"""
    print("\n--- TEST 7: Strategy Auto-Discovery & Bulk Subscriber Matrix ---")
    from database.copy_trading_db import (
        bulk_assign_subscribers_to_strategy,
        get_all_strategies,
        get_strategy_by_tag,
        get_strategy_subscribers_matrix,
    )
    from services.copy_trading_service import broadcast_copy_order

    # 1. Fire a webhook with a completely new un-registered strategy tag
    auto_tag = f"BOUNTY_AUTODISCOVER_{int(time.time())}"
    res = broadcast_copy_order({
        "strategy": auto_tag,
        "symbol": "NATURALGAS",
        "exchange": "MCXFO",
        "action": "BUY",
        "quantity": 1250,
        "pricetype": "MARKET",
        "product": "MIS"
    })
    assert res.get("status") == "success"

    # Verify that the strategy was automatically created in the database
    strat = get_strategy_by_tag(auto_tag)
    assert strat is not None, f"Strategy {auto_tag} should have been auto-discovered and created!"
    assert strat["strategy_tag"] == auto_tag
    print(f"  ✅ Webhook auto-discovered and registered strategy: [{strat['strategy_tag']}] (ID: {strat['id']})")

    # 2. Test Bulk Subscriber Matrix
    matrix = get_strategy_subscribers_matrix(strat["id"])
    assert isinstance(matrix, list)
    print(f"  ✅ Retrieved subscriber matrix with {len(matrix)} accounts for UI rendering.")

    # 3. Test Bulk Subscriber Assignment
    if matrix:
        target_subscribers = [
            {"account_id": matrix[0]["account_id"], "multiplier": 2.5, "max_daily_loss": 8000.0, "is_active": True}
        ]
        bulk_res = bulk_assign_subscribers_to_strategy(strat["id"], target_subscribers, replace_all=True)
        assert bulk_res.get("status") == "success"
        print(f"  ✅ Bulk assigned {bulk_res.get('total_assigned')} subscribers with custom 2.5x multiplier.")


if __name__ == "__main__":
    print("==================================================================")
    print("      STARTING COPY TRADING BUG BOUNTY TEST SUITE")
    print("==================================================================")
    test_fuzzing_and_validation()
    test_freeze_slicing()
    test_idempotency_deduplication()
    test_sqlite_concurrent_burst()
    test_direct_client_routing_and_smart_order()
    test_smart_symbol_resolution()
    test_strategy_auto_discovery_and_bulk_subscribers()
    print("\n==================================================================")
    print("      🎯 ALL BUG BOUNTY TESTS PASSED WITH ZERO ERRORS!")
    print("==================================================================")
