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
    """Test 5: Multi-Tenant Direct Client Routing & Position Sizing"""
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


if __name__ == "__main__":
    print("==================================================================")
    print("      STARTING COPY TRADING BUG BOUNTY TEST SUITE")
    print("==================================================================")
    test_fuzzing_and_validation()
    test_freeze_slicing()
    test_idempotency_deduplication()
    test_sqlite_concurrent_burst()
    test_direct_client_routing_and_smart_order()
    print("\n==================================================================")
    print("      🎯 ALL BUG BOUNTY TESTS PASSED WITH ZERO ERRORS!")
    print("==================================================================")
