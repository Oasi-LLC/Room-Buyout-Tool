# Room Buyout Calculator Tool

A **self-contained** tool for calculating individual room rates and total buyout costs for any property and date range. Perfect for determining the cost of booking multiple rooms for events, group stays, or property buyouts.

## 📖 What is This Tool?

This tool helps you:
- **Calculate total costs** for booking multiple rooms at a property
- **Find the cheapest available rooms** automatically
- **See detailed breakdowns** by night and by listing
- **Check real-time availability** based on actual reservations
- **Generate accurate quotes** for group bookings

### Example Use Case
You need to book 30 rooms for a wedding from September 7-9, 2026. This tool will:
1. Check all available rooms across all listings
2. Select the 30 cheapest available rooms
3. Calculate the total cost for all nights
4. Show you exactly which rooms were selected and their individual rates

## ✅ Fully Self-Contained

This tool has **zero dependencies** on external pricing tools. Everything needed is included:
- ✅ API client for pulling live rates from PriceLabs
- ✅ Configuration management
- ✅ Property configurations
- ✅ Data generation scripts
- ✅ Calculator backend
- ✅ Web interface (Streamlit)

## 📋 Prerequisites

Before you begin, make sure you have:
- **Python 3.9 or higher** installed
- **PriceLabs API Key** (required for pulling live data)
- **Property configuration** file (`config/properties.yaml`)

### Check Python Version
```bash
python3 --version
# Should show Python 3.9.x or higher
```

## 🚀 Complete Setup Guide

### Step 1: Clone or Download the Tool

If you have the tool directory, navigate to it:
```bash
cd /path/to/room_buyout_tool
```

### Step 2: Create a Virtual Environment (Recommended)

A virtual environment keeps dependencies isolated from your system Python:

```bash
# Create virtual environment
python3 -m venv venv

# Activate it (macOS/Linux)
source venv/bin/activate

# Activate it (Windows)
venv\Scripts\activate
```

You should see `(venv)` in your terminal prompt when activated.

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This installs:
- `pandas` - Data manipulation
- `numpy` - Numerical computing
- `pyyaml` - Configuration file parsing
- `python-dotenv` - Environment variable management
- `requests` - API calls
- `streamlit` - Web interface
- And their dependencies

### Step 4: Set Up API Key

1. Create a `.env` file in the tool directory:
   ```bash
   touch .env
   ```

2. Add your PriceLabs API key:
   ```
   PRICELABS_API_KEY=your_api_key_here
   API_BASE_URL=https://api.pricelabs.co/v1
   ```

   **Important**: Never commit the `.env` file to version control!

### Step 5: Verify Configuration

Check that `config/properties.yaml` exists and contains property definitions. This file defines:
- Property names and IDs
- Listing configurations
- Rate group mappings
- Adjustment rules

### Step 6: Generate Data (First Time)

Before using the calculator, you need to generate rate and occupancy data:

```bash
# Generate data for a single property
python generate_pl_daily.py onera

# Or generate for all properties
python generate_all_pl_daily.py
```

This creates `pl_daily_{property}.csv` files in `data/{property}/` directories.

**Note**: This step requires internet connection and API access. It may take several minutes depending on the number of listings.

### Step 7: Test the Installation

```bash
python test_backend.py
```

You should see:
```
✅ Config loaded. Found X properties
✅ Found X listings with rate data
✅ Selected X listings (X total rooms)
✅ Buyout calculated
```

## 🖥️ Using the Web Interface

The easiest way to use this tool is through the web interface.

### Starting the Web App

```bash
# Make sure virtual environment is activated
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate      # Windows

# Run the Streamlit app
streamlit run room_buyout_app.py
```

The app will open in your browser at `http://localhost:8501`

### Using the Web Interface

1. **Select Property**: Choose from the dropdown in the sidebar
2. **Choose Dates**: 
   - **Check-in Date**: When guests arrive
   - **Check-out Date**: When guests leave (this date is NOT charged)
3. **Select Mode**:
   - **Automatic (Cheapest)**: Tool automatically selects cheapest available rooms
   - **Manual Selection**: You choose specific listings and units
4. **Enter Number of Rooms**: (for automatic mode)
5. **Click "Calculate Buyout"**

### Understanding the Results

The results show:
- **Total Buyout Cost**: Total amount for all rooms and nights
- **Total Rooms**: Number of rooms selected
- **Avg Rate per Room**: Average cost per room for the entire stay
- **Avg Rate per Night**: Average cost per night across all rooms
- **Breakdown by Night**: Cost for each individual night
- **Breakdown by Listing**: Which listings were selected and their costs

### Pulling Fresh Data

Click "📥 Pull Fresh Data" in the sidebar to:
- Fetch latest rates from PriceLabs API
- Update occupancy information
- Regenerate `pl_daily` files

**Note**: This may take several minutes for properties with many listings.

## 💻 Using the Python API

For programmatic access or integration with other tools:

### Basic Example

```python
from room_buyout_calculator import RoomBuyoutCalculator

# Initialize calculator
calculator = RoomBuyoutCalculator()

# Define your requirements
property_name = "onera"
start_date = "2026-09-07"  # Check-in (inclusive)
end_date = "2026-09-09"    # Check-out (exclusive - this date is NOT charged)
num_rooms = 30

# Generate date range
dates = calculator.generate_date_range(start_date, end_date)
print(f"Calculating for {len(dates)} nights: {dates}")

# Get room rates
room_rates = calculator.get_room_rates(
    property_name=property_name,
    start_date=start_date,
    end_date=end_date,
    use_live_rates=False  # Use pl_daily data (has occupancy info)
)

# Select cheapest rooms
selected, total_selected = calculator.select_cheapest_rooms(
    room_rates,
    num_rooms_needed=num_rooms,
    dates=dates,
    only_available=True  # Only select rooms available for all dates
)

# Calculate buyout
buyout = calculator.calculate_buyout(selected, dates)

# Display results
print(f"\n{'='*60}")
print("BUYOUT SUMMARY")
print(f"{'='*60}")
print(f"Total Buyout Cost: ${buyout['total_buyout']:,.2f}")
print(f"Total Rooms: {buyout['total_rooms']}")
print(f"Average Rate per Room: ${buyout['avg_rate_per_room']:.2f}")
print(f"Average Rate per Night: ${buyout['avg_rate_per_night']:.2f}")
```

### Manual Room Selection

```python
# Instead of automatic selection, choose specific listings
manual_selections = [
    {'listing_id': '203812___643760', 'units': 1},
    {'listing_id': '203812___643771', 'units': 2},
    # ... more selections
]

selected, total_selected = calculator.select_rooms_manually(
    room_rates,
    manual_selections,
    dates,
    validate_availability=True  # Check that rooms are actually available
)

buyout = calculator.calculate_buyout(selected, dates)
```

### Getting Available Listings

```python
# Get all available listings with details for manual selection
available_listings = calculator.get_available_listings_for_selection(room_rates, dates)

for listing in available_listings:
    print(f"{listing['listing_name']}: {listing['available_units']} units available")
    print(f"  Cost per room per night: ${listing['cost_per_room']:.2f}")
```

## 📊 Data Generation

### Generating pl_daily Files

The `pl_daily` files contain rate and occupancy data for each listing and date.

#### Single Property
```bash
# Use default date range (today to Jan 3, 2027)
python generate_pl_daily.py onera

# Custom date range
python generate_pl_daily.py onera 2026-09-01 2026-12-31
```

#### All Properties
```bash
# Generate for all properties in config
python generate_all_pl_daily.py

# With custom date range
python generate_all_pl_daily.py 2026-09-01 2026-12-31
```

### Understanding pl_daily Files

The generated CSV files (`data/{property}/pl_daily_{property}.csv`) contain:

| Column | Description |
|--------|-------------|
| `Listing ID` | Unique identifier for the listing |
| `PMS Name` | Property Management System (cloudbeds, hostaway, etc.) |
| `Date` | Date in ISO format |
| `Units` | Total number of units for this listing |
| `No. Booked` | Number of units currently booked |
| `No. Blocked` | Number of units blocked/unavailable |
| `Bookable Units` | Units - Blocked units |
| `nightly_revenue` | Rate per room per night |
| `Vacant Units` | Available units (Units - Booked - Blocked) |

### Data File Locations

```
data/
├── onera/
│   └── pl_daily_onera.csv
├── wb1/
│   └── pl_daily_wb1.csv
└── {property_name}/
    └── pl_daily_{property_name}.csv
```

## 🔧 Features Explained

### 1. Automatic Room Selection
- Sorts all available rooms by cost per room per night
- Selects cheapest rooms first until target number is reached
- Respects availability (won't select fully booked rooms)
- Handles multi-unit listings correctly

### 2. Availability Checking
- Uses actual reservation data from PriceLabs
- Checks `Vacant Units` for each date
- Only selects rooms available for ALL dates in the range
- Prevents selecting overbooked rooms

### 3. Multi-Unit Listings
- Some listings have multiple identical units (e.g., "King Room" with 6 units)
- Tool can select partial units (e.g., 3 out of 6 available)
- Calculates costs correctly for partial selections

### 4. Date Range Handling
- **Check-in date**: Included (guests stay this night)
- **Check-out date**: Excluded (guests leave, not charged)
- Example: Sept 7-9 means nights of Sept 7 and 8 only

### 5. Rate Priority
- **Primary**: Uses `pl_daily` data (has occupancy information)
- **Fallback**: Can use live rates if `pl_daily` unavailable
- **Override**: Live rates can override prices while keeping occupancy data

### 6. Error Handling
- Validates CSV file structure before processing
- Handles missing data gracefully
- Provides clear error messages
- Continues processing even if some rows fail

### 7. Rate Limiting
- Automatically handles API rate limits
- Implements exponential backoff
- Respects `Retry-After` headers
- Caches API responses to reduce calls

## 📁 Directory Structure

```
room_buyout_tool/
├── room_buyout_calculator.py    # Main calculator backend
├── room_buyout_app.py           # Streamlit web interface
├── generate_pl_daily.py         # Generate data for single property
├── generate_all_pl_daily.py     # Generate data for all properties
├── test_backend.py              # Test script
├── requirements.txt             # Python dependencies
├── .env                         # API credentials (create this)
├── README.md                     # This file
├── config/
│   └── properties.yaml          # Property configurations
├── utils/
│   ├── __init__.py
│   ├── config.py                # API configuration loader
│   ├── api_client.py            # PriceLabs API client with rate limiting
│   └── date_manager.py          # Date range management
└── data/
    └── {property_name}/
        └── pl_daily_{property}.csv  # Generated rate/occupancy data
```

## 🔑 Configuration

### Environment Variables (.env)

```env
PRICELABS_API_KEY=your_api_key_here
API_BASE_URL=https://api.pricelabs.co/v1
```

### Properties Configuration (config/properties.yaml)

This YAML file defines:
- **Property metadata**: Name, PMS type, total units
- **Listings**: ID, name, number of units, BATNA (Best Alternative to Negotiated Agreement)
- **Rate groups**: Which listings share pricing tiers
- **Adjustment rules**: Weekend pricing, min stay adjustments
- **Booking windows**: Definitions for booking window labels
- **Urgency bands**: Definitions for urgency calculations

Example structure:
```yaml
properties:
  onera:
    name: "Onera"
    pms: cloudbeds
    total_units: 38
    listings:
      - {name: "Cocoon", id: "203812___362535", batna: 189.00}
      # ... more listings
    rate_group_mapping:
      rate_1: ["203812___364781", "203812___364776"]
      # ... more rate groups
```

## 🧪 Testing

### Run Backend Tests
```bash
python test_backend.py
```

This verifies:
- ✅ Configuration loading
- ✅ Room rate retrieval
- ✅ Cheapest room selection
- ✅ Buyout calculation

### Manual Testing

1. **Test data generation**:
   ```bash
   python generate_pl_daily.py onera
   ```

2. **Test calculator**:
   ```python
   python -c "from room_buyout_calculator import RoomBuyoutCalculator; c = RoomBuyoutCalculator(); print('✅ Calculator works!')"
   ```

3. **Test web interface**:
   ```bash
   streamlit run room_buyout_app.py
   ```

## 🐛 Troubleshooting

### Common Issues

#### 1. "No properties found"
- **Cause**: `config/properties.yaml` missing or empty
- **Solution**: Ensure the file exists and contains property definitions

#### 2. "No rate data found"
- **Cause**: `pl_daily` files not generated
- **Solution**: Run `python generate_pl_daily.py {property_name}`

#### 3. "PRICELABS_API_KEY environment variable is required"
- **Cause**: `.env` file missing or API key not set
- **Solution**: Create `.env` file with `PRICELABS_API_KEY=your_key`

#### 4. "Rate limit exceeded"
- **Cause**: Too many API requests
- **Solution**: Wait a few minutes, the tool will automatically retry

#### 5. "numpy.dtype size changed" error
- **Cause**: NumPy/pandas version mismatch
- **Solution**: Reinstall dependencies: `pip install --force-reinstall -r requirements.txt`

#### 6. Streamlit app won't start
- **Cause**: Port 8501 already in use
- **Solution**: Kill the process or use different port: `streamlit run room_buyout_app.py --server.port 8502`

### Getting Help

1. Check error messages - they usually indicate the problem
2. Verify all prerequisites are met
3. Ensure data files are generated
4. Check API key is valid
5. Review configuration files

## 📚 Advanced Usage

### Custom Date Ranges

The default date range is today to January 3, 2027. To change this, edit `utils/date_manager.py`:

```python
def get_pl_daily_date_range():
    start_date = datetime.now().date()
    end_date = date(2027, 1, 3)  # Change this date
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')
```

### Batch Processing

For properties with many listings (like `onera`), the tool uses batch processing:
- Processes listings in batches of 6
- Adds delays between batches to respect rate limits
- Automatically retries failed batches

### Caching

API responses are cached for 5 minutes (300 seconds) by default. To clear cache:
```python
from utils.api_client import PriceLabsAPI
api = PriceLabsAPI()
api.clear_cache()
```

## 📦 Transferring to New Project

To move this tool to a new location:

1. Copy the entire `room_buyout_tool/` directory
2. Create a new virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set up `.env` with API key
5. Copy/configure `config/properties.yaml`
6. Generate data files:
   ```bash
   python generate_all_pl_daily.py
   ```

That's it! No other dependencies needed.

## 🔄 Updating Data

### When to Update

- **Daily**: For accurate availability (recommended)
- **Before major bookings**: To ensure latest rates
- **After rate changes**: To reflect new pricing

### How to Update

1. **Via Web Interface**: Click "📥 Pull Fresh Data" button
2. **Via Command Line**: `python generate_pl_daily.py {property_name}`
3. **All Properties**: `python generate_all_pl_daily.py`

## 📝 Notes

- **Check-out date is exclusive**: Standard hotel convention - guests don't pay for checkout day
- **Availability is date-specific**: A room available on one date may not be available on another
- **Rates can vary by date**: Weekend rates, seasonal pricing, etc.
- **Multi-unit listings**: Tool handles partial unit selection correctly
- **Data freshness**: Stale data may show incorrect availability

## 🎯 Quick Reference

### Command Cheat Sheet

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Generate data
python generate_pl_daily.py onera
python generate_all_pl_daily.py

# Run web app
streamlit run room_buyout_app.py

# Test
python test_backend.py
```

### Python API Cheat Sheet

```python
from room_buyout_calculator import RoomBuyoutCalculator

calc = RoomBuyoutCalculator()
dates = calc.generate_date_range("2026-09-07", "2026-09-09")
rates = calc.get_room_rates("onera", "2026-09-07", "2026-09-09")
selected, total = calc.select_cheapest_rooms(rates, 30, dates)
buyout = calc.calculate_buyout(selected, dates)
```

## 📄 License

This tool is self-contained and designed for internal use. Ensure you comply with PriceLabs API terms of service when using their API.

---

**Need help?** Check the troubleshooting section above or review the code comments for detailed explanations.
