#!/usr/bin/env python3
"""
Test script for Room Buyout Calculator backend
"""

from room_buyout_calculator import RoomBuyoutCalculator
from utils.api_client import (
    parse_listing_overrides,
    parse_listing_prices,
    count_reservations_by_date,
    compute_nightly_occupancy,
)

def test_basic_functionality():
    """Test basic calculator functionality"""
    print("=" * 60)
    print("Testing Room Buyout Calculator Backend")
    print("=" * 60)
    print()
    
    calculator = RoomBuyoutCalculator()
    
    # Test 1: Check if config loads
    print("Test 1: Loading configuration...")
    if calculator.properties_config:
        print(f"✅ Config loaded. Found {len(calculator.properties_config)} properties")
        print(f"   Properties: {', '.join(calculator.properties_config.keys())}")
    else:
        print("❌ Config not loaded")
        return False
    print()
    
    # Test 2: Get room rates for onera
    print("Test 2: Getting room rates for 'onera'...")
    property_name = "onera"
    start_date = "2026-09-07"
    end_date = "2026-09-09"  # Checkout date (exclusive) - means nights of Sept 7 & 8
    
    try:
        room_rates = calculator.get_room_rates(
            property_name, start_date, end_date, use_live_rates=False, use_live_occupancy=False
        )
        print(f"✅ Found {len(room_rates)} listings with rate data")
        
        if room_rates:
            dates = calculator.generate_date_range(start_date, end_date)
            print(f"\n   Sample listing: {room_rates[0].listing_name}")
            print(f"   Units: {room_rates[0].units}")
            print(f"   Nights: {', '.join(dates)} ({len(dates)} nights)")
            print(f"   Rates: {room_rates[0].rates_by_date}")
    except Exception as e:
        print(f"❌ Error getting room rates: {e}")
        import traceback
        traceback.print_exc()
        return False
    print()
    
    # Test 3: Select cheapest rooms
    print("Test 3: Selecting cheapest 30 rooms...")
    dates = calculator.generate_date_range(start_date, end_date)
    num_rooms = 30
    
    try:
        selected, total_selected = calculator.select_cheapest_rooms(
            room_rates, num_rooms, dates, only_available=True
        )
        print(f"✅ Selected {len(selected)} listings ({total_selected} total rooms)")
        
        if selected:
            print(f"\n   First selected: {selected[0].listing_name} ({selected[0].units} units)")
            print(f"   Total cost: ${selected[0].get_total_for_stay(dates):,.2f}")
    except Exception as e:
        print(f"❌ Error selecting rooms: {e}")
        import traceback
        traceback.print_exc()
        return False
    print()
    
    # Test 4: Calculate buyout
    print("Test 4: Calculating buyout...")
    try:
        buyout = calculator.calculate_buyout(selected, dates)
        print(f"✅ Buyout calculated")
        print(f"\n   Total Buyout: ${buyout['total_buyout']:,.2f}")
        print(f"   Total Rooms: {buyout['total_rooms']}")
        print(f"   Avg Rate per Room: ${buyout['avg_rate_per_room']:.2f}")
        print(f"   Avg Rate per Night: ${buyout['avg_rate_per_night']:.2f}")
    except Exception as e:
        print(f"❌ Error calculating buyout: {e}")
        import traceback
        traceback.print_exc()
        return False
    print()
    
    print("=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
    return True


def test_parse_listing_overrides():
    """Live-rate payload shapes used by GET /listings/{id}/overrides."""
    payload = {
        "overrides": [
            {"date": "2026-09-07", "price": 210, "min_stay": 2},
            {"date": "2026-09-08T00:00:00", "price": "225.5", "min_stay": 1},
            {"date": "2026-09-10", "price": 999, "min_stay": 3},
        ]
    }
    parsed = parse_listing_overrides(payload, start_date="2026-09-07", end_date="2026-09-08")
    assert parsed["2026-09-07"]["price"] == 210.0
    assert parsed["2026-09-07"]["min_stay"] == 2
    assert parsed["2026-09-08"]["price"] == 225.5
    assert "2026-09-10" not in parsed

    alt = parse_listing_overrides({"data": [{"date": "2026-09-07", "price": 100}]})
    assert alt["2026-09-07"]["price"] == 100.0
    assert alt["2026-09-07"]["min_stay"] == 1
    print("✅ Override payload parsing works")
    return True


def test_live_occupancy_rules():
    """1-unit uses listing_prices status; multi-unit uses reservation counts."""
    prices = parse_listing_prices([
        {"data": [
            {"date": "2026-09-07", "price": 200, "booking_status": "Booked", "unbookable": 0},
            {"date": "2026-09-08", "price": 200, "booking_status": "Available", "unbookable": 1},
        ]}
    ])
    assert prices["2026-09-07"]["booking_status"] == "Booked"
    assert prices["2026-09-08"]["unbookable"] is True

    one_unit = compute_nightly_occupancy(1, ["2026-09-07", "2026-09-08"], prices)
    assert one_unit["2026-09-07"]["booked"] == 1
    assert one_unit["2026-09-07"]["available"] is False
    assert one_unit["2026-09-08"]["blocked"] == 1
    assert one_unit["2026-09-08"]["vacant"] == 0

    reservations = [
        {
            "listing_id": "multi-1",
            "booking_status": "booked",
            "check_in": "2026-09-07",
            "check_out": "2026-09-09",
        },
        {
            "listing_id": "multi-1",
            "booking_status": "booked",
            "check_in": "2026-09-07",
            "check_out": "2026-09-08",
        },
        {
            "listing_id": "other",
            "booking_status": "booked",
            "check_in": "2026-09-07",
            "check_out": "2026-09-09",
        },
    ]
    reserved = count_reservations_by_date(reservations, "multi-1", ["2026-09-07", "2026-09-08"])
    assert reserved["2026-09-07"] == 2
    assert reserved["2026-09-08"] == 1

    # booking_status Booked must not be treated as a count of 6
    daily = {"2026-09-07": {"booking_status": "Booked", "unbookable": False}}
    multi = compute_nightly_occupancy(6, ["2026-09-07"], daily, reserved_by_date={"2026-09-07": 2})
    assert multi["2026-09-07"]["booked"] == 2
    assert multi["2026-09-07"]["vacant"] == 4
    assert multi["2026-09-07"]["available"] is True

    full = compute_nightly_occupancy(2, ["2026-09-07"], {}, reserved_by_date={"2026-09-07": 2})
    assert full["2026-09-07"]["vacant"] == 0
    assert full["2026-09-07"]["available"] is False
    print("✅ Live occupancy rules work")
    return True


def test_fully_booked_nights_are_unavailable():
    """Occupancy rule: No. Booked >= Units means the night is skipped."""
    calculator = RoomBuyoutCalculator()
    rates, availability, vacant = calculator._load_pl_daily_rates(
        "onera", ["2026-02-05"]
    )
    # Spyglass is fully booked on 2026-02-05 in the committed CSV (1 booked / 1 unit)
    key = "203812___364776_2026-02-05"
    if key in availability:
        assert availability[key] is False
        assert vacant[key] == 0
        print("✅ Fully booked nights are treated as unavailable")
    else:
        print("⚠️  Sample occupancy row not found; skipped assertion")
    return True


if __name__ == "__main__":
    success = (
        test_parse_listing_overrides()
        and test_live_occupancy_rules()
        and test_fully_booked_nights_are_unavailable()
        and test_basic_functionality()
    )
    exit(0 if success else 1)
