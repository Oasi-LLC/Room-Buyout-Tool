"""
API Configuration for Room Buyout Tool
"""
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file in tool directory
tool_dir = Path(__file__).parent.parent
env_path = tool_dir / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # No fallback - .env must be in tool directory for independence
    pass

# API Configuration
API_KEY = os.getenv('PRICELABS_API_KEY')
BASE_URL = os.getenv('API_BASE_URL', 'https://api.pricelabs.co/v1')

# Validation
if not API_KEY:
    raise ValueError("PRICELABS_API_KEY environment variable is required. Create a .env file with your API key.")

# Price Adjustment Configuration
ADJUSTMENT_PERCENTAGE = 5  # 5% adjustment
DEFAULT_CURRENCY = "USD"
DEFAULT_PMS = "cloudbeds"

# API Rate Limiting
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

# Logging Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
