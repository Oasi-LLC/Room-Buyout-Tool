#!/usr/bin/env python3
"""
Test script for Room Buyout Calculator backend
"""

from room_buyout_calculator import RoomBuyoutCalculator, RoomRate
from datetime import datetime

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
        room_rates = calculator.get_room_rates(property_name, start_date, end_date)
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


if __name__ == "__main__":
    success = test_basic_functionality()
    exit(0 if success else 1)
