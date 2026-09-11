#!/usr/bin/env python3
"""
Room Buyout Calculator - Streamlit Frontend
Easy-to-use web interface for calculating room buyout costs.
"""

import streamlit as st
import pandas as pd
from datetime import date, timedelta
from pathlib import Path
import sys
import os
from dotenv import load_dotenv

# Add current directory to path
tool_dir = Path(__file__).parent
sys.path.insert(0, str(tool_dir))

# Load environment variables
env_path = tool_dir / ".env"
if env_path.exists():
    load_dotenv(env_path)

from room_buyout_calculator import RoomBuyoutCalculator
from generate_pl_daily import generate_pl_daily_for_property, generate_pl_daily_for_property_batched, save_pl_daily_csv
from utils.date_manager import get_pl_daily_date_range
from utils.config import API_KEY

# Page configuration
st.set_page_config(
    page_title="Room Buyout Calculator",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .summary-box {
        background-color: #f0f2f6;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .metric-box {
        background-color: white;
        padding: 1rem;
        border-radius: 5px;
        border-left: 4px solid #1f77b4;
        margin: 0.5rem 0;
    }
    </style>
""", unsafe_allow_html=True)

def load_properties():
    """Load available properties from config"""
    try:
        calculator = RoomBuyoutCalculator()
        properties = list(calculator.properties_config.keys())
        # Filter to only show onera and wb1 (in case config has others)
        allowed_properties = ['onera', 'wb1']
        return [p for p in properties if p in allowed_properties]
    except Exception as e:
        st.error(f"Error loading properties: {e}")
        return []

def format_currency(amount):
    """Format amount as currency"""
    return f"${amount:,.2f}"


def load_live_stay_data(calculator, property_name, start_date, end_date):
    """Fetch live prices and occupancy once per property/stay; reuse across reruns."""
    cache = st.session_state.setdefault('live_stay_cache', {})
    key = f"{property_name}|{start_date}|{end_date}"
    if key in cache:
        return cache[key]

    status = st.empty()
    progress = st.progress(0)

    def on_progress(i, n, name):
        n = max(n, 1)
        status.text(f"Fetching live PriceLabs data ({i + 1}/{n}): {name}")
        progress.progress(min(1.0, (i + 1) / n))

    stay = calculator.fetch_live_stay_data(
        property_name, start_date, end_date, progress_callback=on_progress
    )
    status.empty()
    progress.empty()
    cache[key] = stay
    return stay


def live_data_source_caption(rate_source, occupancy_source):
    """Explain where quote prices vs occupancy came from."""
    rate_label = {
        'api': 'live PriceLabs listing overrides',
        'csv': 'local nightly_pulled_overrides.csv',
        'none': 'local pl_daily',
    }.get(rate_source, 'local pl_daily')
    occ_label = {
        'api': 'live PriceLabs listing_prices / reservation_data',
        'csv': 'local pl_daily',
        'none': 'local pl_daily',
    }.get(occupancy_source, 'local pl_daily')
    st.caption(f"Prices from {rate_label}. Occupancy from {occ_label}.")


def show_no_rate_data_error(property_display_name):
    st.error(f"❌ No rate data found for {property_display_name}.")
    if not API_KEY:
        st.info("💡 Live PriceLabs did not run because `PRICELABS_API_KEY` is not set. Add it to `.env` and restart Streamlit.")
    else:
        st.info("💡 No live rates came back for these dates, and local pl_daily does not cover this stay.")

def check_authentication():
    """Check if user is authenticated with @stayoasi.com email and password"""
    # Get password from environment variable (default to a secure password if not set)
    required_password = os.getenv('APP_PASSWORD', 'stayoasi2024')
    
    # Initialize authentication state
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'user_email' not in st.session_state:
        st.session_state.user_email = None
    
    # If already authenticated, return True
    if st.session_state.authenticated:
        return True
    
    # Show login form
    st.markdown('<div class="main-header">🔐 Login Required</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.info("Please sign in with your @stayoasi.com email address and password to access the Room Buyout Calculator.")
    
    with st.form("login_form"):
        email = st.text_input("Email Address", placeholder="your.name@stayoasi.com", type="default")
        password = st.text_input("Password", type="password", placeholder="Enter your password")
        submit_button = st.form_submit_button("Sign In", type="primary")
        
        if submit_button:
            email = email.strip().lower()
            password_input = password.strip()
            
            # Validate email domain
            if not email or not email.endswith("@stayoasi.com"):
                st.error("❌ Access denied. Please use a @stayoasi.com email address.")
            elif not password_input:
                st.error("❌ Please enter your password.")
            elif password_input != required_password:
                st.error("❌ Invalid password. Please try again.")
            else:
                # Both email and password are correct
                st.session_state.authenticated = True
                st.session_state.user_email = email
                st.success(f"✅ Welcome, {email}!")
                st.rerun()
    
    st.markdown("---")
    st.caption("This application is restricted to StayOasi team members only.")
    st.stop()
    
    return False

def main():
    # Check authentication first
    if not check_authentication():
        return
    
    # Initialize session state
    if 'manual_selection_active' not in st.session_state:
        st.session_state.manual_selection_active = False
    if 'manual_calculation_params' not in st.session_state:
        st.session_state.manual_calculation_params = None
    if 'show_buyout_results' not in st.session_state:
        st.session_state.show_buyout_results = False
    if 'buyout_data' not in st.session_state:
        st.session_state.buyout_data = None
    
    # Header
    st.markdown('<div class="main-header">🏨 Room Buyout Calculator</div>', unsafe_allow_html=True)
    
    # Show user info and logout button
    col1, col2 = st.columns([4, 1])
    with col1:
        st.caption(f"Signed in as: {st.session_state.user_email}")
    with col2:
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.user_email = None
            st.rerun()
    
    st.markdown("---")
    
    # Sidebar for inputs
    with st.sidebar:
        st.header("📋 Input Parameters")
        
        # Property selection
        properties = load_properties()
        if not properties:
            st.error("No properties found. Please check your configuration.")
            st.stop()
        
        property_name = st.selectbox(
            "Select Property",
            options=properties,
            help="Choose the property you want to calculate buyout costs for"
        )
        
        # Get property display name
        try:
            calculator = RoomBuyoutCalculator()
            prop_config = calculator.properties_config.get(property_name, {})
            property_display_name = prop_config.get('name', property_name)
            st.info(f"**Property:** {property_display_name}")
        except:
            property_display_name = property_name

        if not API_KEY:
            st.error(
                "PriceLabs API key is missing. Add `PRICELABS_API_KEY` to a `.env` file "
                "in this project folder and restart Streamlit."
            )
        
        st.markdown("---")
        
        # Date selection
        st.subheader("📅 Dates")
        
        # Default dates: today and 2 nights (check-in + 2 days)
        default_checkin = date.today()
        default_checkout = default_checkin + timedelta(days=2)
        
        # Set max date to a reasonable future date (e.g., 10 years from now)
        max_date = date.today() + timedelta(days=3650)  # ~10 years
        
        checkin_date = st.date_input(
            "Check-in Date",
            value=default_checkin,
            min_value=date.today(),
            max_value=max_date,
            help="The date guests will check in"
        )
        
        # Calculate default checkout based on checkin_date to ensure it's always valid
        # Use checkin_date + 2 days (2 nights), but ensure it's within bounds
        min_checkout = checkin_date + timedelta(days=1)
        calculated_default_checkout = checkin_date + timedelta(days=2)
        
        # Use the calculated default if it's valid, otherwise use min_checkout
        if calculated_default_checkout <= max_date and calculated_default_checkout >= min_checkout:
            checkout_default = calculated_default_checkout
        elif min_checkout <= max_date:
            checkout_default = min_checkout
        else:
            checkout_default = max_date
        
        checkout_date = st.date_input(
            "Check-out Date",
            value=checkout_default,
            min_value=min_checkout,
            max_value=max_date,
            help="The date guests will check out (this date is NOT charged)"
        )
        
        if checkout_date <= checkin_date:
            st.error("⚠️ Check-out date must be after check-in date")
            st.stop()
        
        # Calculate number of nights
        num_nights = (checkout_date - checkin_date).days
        st.info(f"**Nights:** {num_nights} night{'s' if num_nights != 1 else ''}")
        
        st.markdown("---")
        
        # Selection mode
        st.subheader("🎯 Selection Mode")
        selection_mode = st.radio(
            "How would you like to select rooms?",
            options=["Automatic (Cheapest)", "Manual Selection"],
            help="Automatic: Selects cheapest available rooms. Manual: You choose specific listings and units.",
            on_change=lambda: st.session_state.update({'manual_selection_submitted': False, 'manual_selections': []})
        )
        
        st.markdown("---")
        
        # Number of rooms (for automatic mode or as target for manual mode)
        if selection_mode == "Automatic (Cheapest)":
            st.subheader("🛏️ Rooms")
            num_rooms = st.number_input(
            "Number of Rooms Needed",
            min_value=1,
            value=30,
            step=1,
            help="How many rooms do you need for this buyout?"
        )
        else:
            st.subheader("🛏️ Manual Room Selection")
            st.info("Select specific listings and units in the main area, then click Calculate.")
        
        st.markdown("---")
        
        # Pull Fresh Data button
        st.subheader("🔄 Data Management")
        pull_data_button = st.button(
            "📥 Save Occupancy Fallback",
            help="Optional: write occupancy to local pl_daily in case live PriceLabs is unavailable. Calculate already fetches occupancy live.",
            use_container_width=True
        )
        
        if pull_data_button:
            st.session_state['pull_data_property'] = property_name
            st.session_state['pull_data_checkin'] = checkin_date
            st.session_state['pull_data_checkout'] = checkout_date
            st.session_state['pull_data_clicked'] = True
            st.rerun()
        
        st.markdown("---")
        
        # Calculate button - different behavior for automatic vs manual
        calculate_button = st.button(
            "🚀 Calculate Buyout",
            type="primary",
            use_container_width=True
        )
        
        # Handle calculate button click
        if calculate_button:
            if selection_mode == "Automatic (Cheapest)":
                # Automatic mode: calculate immediately
                st.session_state.manual_selection_active = False
                st.session_state.show_buyout_results = True
            else:
                # Manual mode: activate selection interface
                st.session_state.manual_selection_active = True
                st.session_state.manual_calculation_params = {
                    'property': property_name,
                    'property_display_name': property_display_name,
                    'checkin': checkin_date,
                    'checkout': checkout_date,
                    'mode': selection_mode
                }
                st.session_state.show_buyout_results = False
                st.session_state.buyout_data = None
    
    # Main content area
    # Check if we're in manual selection mode (persists across reruns)
    in_manual_selection = st.session_state.get('manual_selection_active', False)
    show_results = st.session_state.get('show_buyout_results', False)
    
    # Handle pull fresh data request (check this first, before other content)
    if st.session_state.get('pull_data_clicked', False):
        property_to_pull = st.session_state.get('pull_data_property', None)
        checkin_to_pull = st.session_state.get('pull_data_checkin', None)
        checkout_to_pull = st.session_state.get('pull_data_checkout', None)
        
        if property_to_pull:
            # Get property display name
            try:
                calculator = RoomBuyoutCalculator()
                prop_config = calculator.properties_config.get(property_to_pull, {})
                property_display_name_pull = prop_config.get('name', property_to_pull)
            except:
                property_display_name_pull = property_to_pull
            
            st.session_state['pull_data_clicked'] = False  # Reset flag
            
            # Use selected dates if available, otherwise fall back to default date range
            if checkin_to_pull and checkout_to_pull:
                start_date = checkin_to_pull.strftime('%Y-%m-%d')
                end_date = checkout_to_pull.strftime('%Y-%m-%d')
            else:
                # Fallback to default date range if dates not available
                start_date, end_date = get_pl_daily_date_range()
            
            st.subheader("🔄 Pulling Fresh Data")
            st.info(f"Pulling fresh data for **{property_display_name_pull}**...")
            st.info(f"📅 Date range: {start_date} to {end_date}")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                status_text.text("📊 Fetching reservations and rates from PriceLabs API...")
                progress_bar.progress(10)
                
                # Generate pl_daily data - use batch processing for onera
                if property_to_pull == 'onera':
                    status_text.text("📦 Processing in batches (onera has many listings)...")
                    pl_daily_data = generate_pl_daily_for_property_batched(property_to_pull, start_date, end_date)
                else:
                    status_text.text("📊 Processing listings...")
                    pl_daily_data = generate_pl_daily_for_property(property_to_pull, start_date, end_date)
                
                progress_bar.progress(90)
                
                if pl_daily_data:
                    # Save to CSV
                    status_text.text("💾 Saving data to file...")
                    filepath = save_pl_daily_csv(pl_daily_data, property_to_pull)
                    progress_bar.progress(100)
                    
                    status_text.empty()
                    progress_bar.empty()
                    
                    st.success(f"✅ Saved occupancy fallback for **{property_display_name_pull}**!")
                    st.info(f"📁 Data saved to: `{filepath}`")
                    st.info("💡 Calculate still fetches live occupancy and rates from PriceLabs.")
                    
                    st.session_state.pop('live_stay_cache', None)
                    if 'buyout_data' in st.session_state:
                        del st.session_state['buyout_data']
                    if 'show_buyout_results' in st.session_state:
                        st.session_state['show_buyout_results'] = False
                else:
                    progress_bar.empty()
                    status_text.empty()
                    st.error(f"❌ Failed to pull data for {property_display_name_pull}. Please check the API connection and try again.")
                    
            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                st.error(f"❌ Error pulling fresh data: {str(e)}")
                st.exception(e)
            
            st.markdown("---")
            st.stop()  # Stop here to show the results
    
    # Priority: Show results first if available, then selection interface
    # Show buyout results if available (for both automatic and manual modes)
    if show_results and st.session_state.buyout_data:
        buyout = st.session_state.buyout_data['buyout']
        property_display_name = st.session_state.buyout_data['property_display_name']
        checkin_date = st.session_state.buyout_data['checkin_date']
        checkout_date = st.session_state.buyout_data['checkout_date']
        dates = st.session_state.buyout_data['dates']
        
        # Display results
        st.success("✅ Buyout calculation complete!")
        st.markdown("---")
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Buyout Cost", format_currency(buyout['total_buyout']))
        with col2:
            st.metric("Total Rooms", f"{buyout['total_rooms']}")
        with col3:
            st.metric("Avg Rate per Room", format_currency(buyout['avg_rate_per_room']))
        with col4:
            st.metric("Avg Rate per Night", format_currency(buyout['avg_rate_per_night']))
        
        st.markdown("---")
        
        # Breakdown by night
        st.subheader("📊 Breakdown by Night")
        night_data = []
        for date_str, cost in buyout['breakdown_by_night'].items():
            night_data.append({'Date': date_str, 'Cost': cost})
        
        night_df = pd.DataFrame(night_data)
        night_df['Cost'] = night_df['Cost'].apply(lambda x: format_currency(x))
        st.dataframe(night_df, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        # Detailed breakdown by listing
        st.subheader("🏠 Detailed Breakdown by Listing")
        listing_data = []
        for listing in buyout['breakdown_by_listing']:
            selected_units = listing.get('selected_units', listing['available_units'])
            listing_data.append({
                'Listing Name': listing['listing_name'],
                'Selected Units': selected_units,
                'Available Units': listing['available_units'],
                'Total Cost': listing['total_cost'],
                'Avg per Night': listing['avg_rate_per_night']
            })
        
        listing_df = pd.DataFrame(listing_data)
        listing_df['Total Cost'] = listing_df['Total Cost'].apply(lambda x: format_currency(x))
        listing_df['Avg per Night'] = listing_df['Avg per Night'].apply(lambda x: format_currency(x))
        st.dataframe(listing_df, use_container_width=True, hide_index=True)
        
        # Expandable detailed view
        with st.expander("📋 View Detailed Rates per Night"):
            for listing in buyout['breakdown_by_listing']:
                st.markdown(f"### {listing['listing_name']}")
                selected_units = listing.get('selected_units', listing['available_units'])
                st.write(f"**Selected Units:** {selected_units} (Available: {listing['available_units']}, Total: {listing['total_units']})")
                
                rates_table = []
                for date_str, rate_per_room in sorted(listing['rate_per_room_per_night'].items()):
                    vacant = listing['vacant_units_by_date'].get(date_str, 0)
                    total_rate_for_selected = rate_per_room * selected_units
                    rates_table.append({
                        'Date': date_str,
                        'Rate per Room': format_currency(rate_per_room),
                        'Selected Units': selected_units,
                        'Total Rate (All Units)': format_currency(total_rate_for_selected),
                        'Vacant Units': vacant
                    })
                
                rates_df = pd.DataFrame(rates_table)
                st.dataframe(rates_df, use_container_width=True, hide_index=True)
                st.markdown("---")
        
        # Summary - Compact bullet point format
        st.markdown("---")
        st.markdown("### 📝 Summary")
        
        # Create a compact summary with bullet points (using individual writes to avoid markdown parsing issues)
        st.markdown(f"• **Property:** {property_display_name}")
        st.markdown(f"• **Check-in:** {checkin_date.strftime('%B %d, %Y')}")
        st.markdown(f"• **Check-out:** {checkout_date.strftime('%B %d, %Y')}")
        st.markdown(f"• **Nights:** {len(dates)}")
        st.markdown(f"• **Rooms Selected:** {buyout['total_rooms']}")
        st.markdown(f"• **Total Buyout Cost:** {format_currency(buyout['total_buyout'])}")
        st.markdown(f"• **Average Rate per Room:** {format_currency(buyout['avg_rate_per_room'])}")
        st.markdown(f"• **Average Rate per Night:** {format_currency(buyout['avg_rate_per_night'])}")
        
        # Back button (only for manual mode)
        if in_manual_selection:
            st.markdown("---")
            if st.button("🔙 Back to Modify Selection", use_container_width=True):
                st.session_state.show_buyout_results = False
                st.session_state.buyout_data = None
                # Keep manual_selection_active = True to show selection interface
                st.rerun()
    
    # If in manual selection mode, show selection interface (only if not showing results)
    elif in_manual_selection and st.session_state.manual_calculation_params:
        params = st.session_state.manual_calculation_params
        property_name = params['property']
        property_display_name = params['property_display_name']
        checkin_date = params['checkin']
        checkout_date = params['checkout']
        
        # Initialize calculator and get data
        calculator = RoomBuyoutCalculator()
        start_date = checkin_date.strftime('%Y-%m-%d')
        end_date = checkout_date.strftime('%Y-%m-%d')
        dates = calculator.generate_date_range(start_date, end_date)
        
        stay = load_live_stay_data(calculator, property_name, start_date, end_date)
        live_data_source_caption(stay['rate_source'], stay['occupancy_source'])
        room_rates = calculator.get_room_rates(
            property_name, 
            start_date, 
            end_date, 
            use_live_rates=True,
            live_rates=stay['live_rates'],
            use_live_occupancy=True,
            occupancy=stay['occupancy'],
        )
        
        if not room_rates:
            show_no_rate_data_error(property_display_name)
            st.stop()
        
        # Get available listings for display
        available_listings = calculator.get_available_listings_for_selection(room_rates, dates)
        
        # Manual selection interface
        st.subheader("📋 Select Rooms Manually")
        st.write("Choose which listings and how many units you want:")
        
        # Calculate total selected units in real-time from session state
        total_selected_units = 0
        for listing in available_listings:
            selection_key = f"units_{listing['listing_id']}"
            if selection_key in st.session_state:
                total_selected_units += st.session_state[selection_key]
        
        # Display real-time counter at top
        st.markdown("---")
        st.metric("📊 **Total Rooms Selected**", total_selected_units)
        st.markdown("---")
        
        # Display available listings with selection inputs (outside form for real-time updates)
        st.write("**Available Listings:**")
        
        for listing in available_listings:
            col1, col2, col3, col4 = st.columns([3, 1, 2, 1])
            with col1:
                st.write(f"**{listing['listing_name']}**")
                st.caption(f"ID: {listing['listing_id']}")
            with col2:
                max_units = listing['available_units']
                selection_key = f"units_{listing['listing_id']}"
                prev_value = st.session_state.get(selection_key, 0)
                
                # Use number_input with on_change for real-time counter updates
                units_selected = st.number_input(
                    "Units",
                    min_value=0,
                    max_value=max_units,
                    value=prev_value,
                    step=1,
                    key=selection_key,
                    label_visibility="collapsed",
                    on_change=st.rerun  # Rerun to update counter, but state persists
                )
                
            with col3:
                if units_selected > 0:
                    num_nights = len(dates)
                    total_cost_for_selected = listing['cost_per_room'] * num_nights * units_selected
                    st.write(f"Total Cost: {format_currency(total_cost_for_selected)}")
                    st.caption(f"({units_selected} units × {num_nights} nights)")
                else:
                    st.write(f"Available: {max_units}")
            with col4:
                st.caption(f"${listing['cost_per_room']:,.0f}/room/night")
        
        # Show updated counter at bottom
        current_total = sum(
            st.session_state.get(f"units_{listing['listing_id']}", 0) 
            for listing in available_listings
        )
        st.markdown("---")
        st.metric("📊 **Total Rooms Selected**", current_total)
        
        # Collect manual selections from session state
        manual_selections = []
        for listing in available_listings:
            selection_key = f"units_{listing['listing_id']}"
            units_selected = st.session_state.get(selection_key, 0)
            if units_selected > 0:
                manual_selections.append({
                    'listing_id': listing['listing_id'],
                    'units': units_selected
                })
        
        # Button to calculate with selected rooms
        st.markdown("---")
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🔙 Back", use_container_width=True):
                st.session_state.manual_selection_active = False
                st.session_state.show_buyout_results = False
                st.session_state.buyout_data = None
                st.rerun()
        
        with col2:
            calculate_with_selected = st.button(
                "✅ Calculate with Selected Rooms",
                type="primary",
                use_container_width=True
            )
        
        if calculate_with_selected:
            if not manual_selections:
                st.warning("⚠️ Please select at least one listing with units > 0")
                st.stop()
            
            # Calculate buyout with selected rooms
            try:
                selected, total_selected = calculator.select_rooms_manually(
                    room_rates,
                    manual_selections,
                    dates,
                    validate_availability=True
                )
                
                # Calculate buyout
                buyout = calculator.calculate_buyout(selected, dates)
                
                # Store results in session state
                st.session_state.buyout_data = {
                    'selected': selected,
                    'total_selected': total_selected,
                    'buyout': buyout,
                    'property_display_name': property_display_name,
                    'checkin_date': checkin_date,
                    'checkout_date': checkout_date,
                    'dates': dates
                }
                st.session_state.show_buyout_results = True
                st.rerun()
            except ValueError as e:
                st.error(f"❌ Selection Error: {str(e)}")
                st.stop()
    
    # Automatic mode calculation or initial state
    elif calculate_button and selection_mode == "Automatic (Cheapest)":
        with st.spinner("Calculating buyout costs... This may take a moment."):
            try:
                # Initialize calculator
                calculator = RoomBuyoutCalculator()
                
                # Convert dates to strings
                start_date = checkin_date.strftime('%Y-%m-%d')
                end_date = checkout_date.strftime('%Y-%m-%d')
                
                # Generate date range
                dates = calculator.generate_date_range(start_date, end_date)
                
                stay = load_live_stay_data(calculator, property_name, start_date, end_date)
                live_data_source_caption(stay['rate_source'], stay['occupancy_source'])
                room_rates = calculator.get_room_rates(
                    property_name, 
                    start_date, 
                    end_date, 
                    use_live_rates=True,
                    live_rates=stay['live_rates'],
                    use_live_occupancy=True,
                    occupancy=stay['occupancy'],
                )
                
                if not room_rates:
                    show_no_rate_data_error(property_display_name)
                    st.stop()
                
                # Get available listings for display
                available_listings = calculator.get_available_listings_for_selection(room_rates, dates)
                
                # Selection logic based on mode
                if selection_mode == "Automatic (Cheapest)":
                    # Select cheapest rooms
                    selected, total_selected = calculator.select_cheapest_rooms(
                        room_rates,
                        num_rooms,
                        dates,
                        only_available=True
                    )
                    
                    if total_selected < num_rooms:
                        st.warning(f"⚠️ Only {total_selected} rooms available (requested {num_rooms})")
                else:
                    # Manual selection mode - show selection interface (outside form for real-time updates)
                    st.subheader("📋 Select Rooms Manually")
                    st.write("Choose which listings and how many units you want:")
                    
                    # Calculate total selected units in real-time from session state
                    total_selected_units = 0
                    for listing in available_listings:
                        selection_key = f"units_{listing['listing_id']}"
                        if selection_key in st.session_state:
                            total_selected_units += st.session_state[selection_key]
                    
                    # Display real-time counter at top
                    st.markdown("---")
                    st.metric("📊 **Total Rooms Selected**", total_selected_units)
                    st.markdown("---")
                    
                    # Display available listings with selection inputs (outside form for real-time updates)
                    st.write("**Available Listings:**")
                    
                    for listing in available_listings:
                        col1, col2, col3, col4 = st.columns([3, 1, 2, 1])
                        with col1:
                            st.write(f"**{listing['listing_name']}**")
                            st.caption(f"ID: {listing['listing_id']}")
                        with col2:
                            max_units = listing['available_units']
                            selection_key = f"units_{listing['listing_id']}"
                            prev_value = st.session_state.get(selection_key, 0)
                            
                            # Use number_input outside form with on_change to trigger rerun for real-time counter
                            units_selected = st.number_input(
                                "Units",
                                min_value=0,
                                max_value=max_units,
                                value=prev_value,
                                step=1,
                                key=selection_key,
                                label_visibility="collapsed",
                                on_change=st.rerun  # Rerun on change to update counter in real-time
                            )
                            
                        with col3:
                            if units_selected > 0:
                                # Calculate total cost for selected units for the entire stay
                                num_nights = len(dates)
                                total_cost_for_selected = listing['cost_per_room'] * num_nights * units_selected
                                st.write(f"Total Cost: {format_currency(total_cost_for_selected)}")
                                st.caption(f"({units_selected} units × {num_nights} nights)")
                            else:
                                st.write(f"Available: {max_units}")
                        with col4:
                            # Show rate per room per night
                            st.caption(f"${listing['cost_per_room']:,.0f}/room/night")
                    
                    # Collect manual selections from session state
                    manual_selections = []
                    for listing in available_listings:
                        selection_key = f"units_{listing['listing_id']}"
                        units_selected = st.session_state.get(selection_key, 0)
                        if units_selected > 0:
                            manual_selections.append({
                                'listing_id': listing['listing_id'],
                                'units': units_selected
                            })
                    
                    # Show updated counter at bottom
                    current_total = sum(sel.get('units', 0) for sel in manual_selections)
                    st.markdown("---")
                    st.metric("📊 **Total Rooms Selected**", current_total)
                    
                    # Note: Calculate button is in sidebar, will use these selections when clicked
                    if not manual_selections:
                        st.info("👆 Select rooms above, then click 'Calculate Buyout' in the sidebar")
                        st.stop()
                    
                    # When calculate button is clicked, use the manual selections
                    try:
                        selected, total_selected = calculator.select_rooms_manually(
                            room_rates,
                            manual_selections,
                            dates,
                            validate_availability=True
                        )
                        st.success(f"✅ Selected {len(selected)} listings, {total_selected} total rooms")
                    except ValueError as e:
                        st.error(f"❌ Selection Error: {str(e)}")
                        st.stop()
                
                # Calculate buyout
                buyout = calculator.calculate_buyout(selected, dates)
                
                # Display results
                st.success("✅ Buyout calculation complete!")
                st.markdown("---")
                
                # Summary metrics
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric(
                        "Total Buyout Cost",
                        format_currency(buyout['total_buyout'])
                    )
                
                with col2:
                    st.metric(
                        "Total Rooms",
                        f"{buyout['total_rooms']}"
                    )
                
                with col3:
                    st.metric(
                        "Avg Rate per Room",
                        format_currency(buyout['avg_rate_per_room'])
                    )
                
                with col4:
                    st.metric(
                        "Avg Rate per Night",
                        format_currency(buyout['avg_rate_per_night'])
                    )
                
                st.markdown("---")
                
                # Breakdown by night
                st.subheader("📊 Breakdown by Night")
                night_data = []
                for date_str, cost in buyout['breakdown_by_night'].items():
                    night_data.append({
                        'Date': date_str,
                        'Cost': cost
                    })
                
                night_df = pd.DataFrame(night_data)
                night_df['Cost'] = night_df['Cost'].apply(lambda x: format_currency(x))
                st.dataframe(night_df, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                
                # Detailed breakdown by listing
                st.subheader("🏠 Detailed Breakdown by Listing")
                
                listing_data = []
                for listing in buyout['breakdown_by_listing']:
                    selected_units = listing.get('selected_units', listing['available_units'])
                    listing_data.append({
                        'Listing Name': listing['listing_name'],
                        'Selected Units': selected_units,
                        'Available Units': listing['available_units'],
                        'Total Cost': listing['total_cost'],
                        'Avg per Night': listing['avg_rate_per_night']
                    })
                
                listing_df = pd.DataFrame(listing_data)
                listing_df['Total Cost'] = listing_df['Total Cost'].apply(lambda x: format_currency(x))
                listing_df['Avg per Night'] = listing_df['Avg per Night'].apply(lambda x: format_currency(x))
                
                st.dataframe(
                    listing_df,
                    use_container_width=True,
                    hide_index=True
                )
                
                # Expandable detailed view
                with st.expander("📋 View Detailed Rates per Night"):
                    for listing in buyout['breakdown_by_listing']:
                        st.markdown(f"### {listing['listing_name']}")
                        selected_units = listing.get('selected_units', listing['available_units'])
                        st.write(f"**Selected Units:** {selected_units} (Available: {listing['available_units']}, Total: {listing['total_units']})")
                        
                        rates_table = []
                        for date_str, rate_per_room in sorted(listing['rate_per_room_per_night'].items()):
                            vacant = listing['vacant_units_by_date'].get(date_str, 0)
                            # Calculate total rate for all selected units
                            total_rate_for_selected = rate_per_room * selected_units
                            rates_table.append({
                                'Date': date_str,
                                'Rate per Room': format_currency(rate_per_room),
                                'Selected Units': selected_units,
                                'Total Rate (All Units)': format_currency(total_rate_for_selected),
                                'Vacant Units': vacant
                            })
                        
                        rates_df = pd.DataFrame(rates_table)
                        st.dataframe(rates_df, use_container_width=True, hide_index=True)
                        st.markdown("---")
                
                # Summary - Compact bullet point format
                st.markdown("---")
                st.markdown("### 📝 Summary")
                
                # Create a compact summary with bullet points (using individual writes to avoid markdown parsing issues)
                st.markdown(f"• **Property:** {property_display_name}")
                st.markdown(f"• **Check-in:** {checkin_date.strftime('%B %d, %Y')}")
                st.markdown(f"• **Check-out:** {checkout_date.strftime('%B %d, %Y')}")
                st.markdown(f"• **Nights:** {num_nights}")
                st.markdown(f"• **Rooms Requested:** {num_rooms}")
                st.markdown(f"• **Rooms Selected:** {buyout['total_rooms']}")
                st.markdown(f"• **Total Buyout Cost:** {format_currency(buyout['total_buyout'])}")
                st.markdown(f"• **Average Rate per Room:** {format_currency(buyout['avg_rate_per_room'])}")
                st.markdown(f"• **Average Rate per Night:** {format_currency(buyout['avg_rate_per_night'])}")
                
            except Exception as e:
                st.error(f"❌ Error calculating buyout: {str(e)}")
                st.exception(e)
    
    else:
        # Welcome message when not calculating
        st.markdown("""
        ### 👋 Welcome to the Room Buyout Calculator!
        
        This tool helps you calculate the total cost of booking multiple rooms for a property.
        
        **How to use:**
        1. Select a property from the sidebar
        2. Choose your check-in and check-out dates
        3. Enter the number of rooms you need
        4. Click "Calculate Buyout" to see the results
        
        **Features:**
        - ✅ Automatically selects the cheapest available rooms
        - ✅ Considers actual occupancy (excludes fully booked units)
        - ✅ Shows detailed breakdown by listing and by night
        - ✅ Displays individual room rates
        
        **Note:** Prices and occupancy are fetched live from PriceLabs when you calculate. Local pl_daily is only a fallback if the API is unavailable.
        """)
        
        # Show available properties
        st.markdown("### 📋 Available Properties")
        properties = load_properties()
        if properties:
            try:
                calculator = RoomBuyoutCalculator()
                prop_info = []
                for prop_key in properties:
                    prop_config = calculator.properties_config.get(prop_key, {})
                    prop_name = prop_config.get('name', prop_key)
                    total_units = prop_config.get('total_units', 'N/A')
                    prop_info.append({
                        'Property Key': prop_key,
                        'Property Name': prop_name,
                        'Total Units': total_units
                    })
                
                prop_df = pd.DataFrame(prop_info)
                st.dataframe(prop_df, use_container_width=True, hide_index=True)
            except:
                st.write(", ".join(properties))

if __name__ == "__main__":
    main()
