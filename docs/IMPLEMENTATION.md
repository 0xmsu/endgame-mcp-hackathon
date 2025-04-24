
# Implementation Guide

## Architecture

The TaoStats MCP server is built on the ModelContextProtocol, which provides a standardized way to expose data and functionality to AI models and applications. The architecture follows a layered approach:

1. **Core Layer**: The FastMCP server that handles protocol negotiation, tool registration, and client communication.

2. **API Integration Layer**: Manages API integration with TaoStats, including authentication, request formatting, and response handling with proper timeout and error handling.

3. **Caching Layer**: Implements intelligent caching with TTL based on data volatility to improve performance and reduce API load.

4. **Tool Layer**: Exposes functionality through a collection of specialized functions organized by data category.

5. **Data Validation Layer**: Uses Pydantic models to validate API responses and ensure data integrity.

This modular design separates concerns and allows for easy extension with additional TaoStats API endpoints or other data sources.

## Components

### FastMCP Server
```python
mcp = FastMCP("TaoStats")
```
The central component that manages protocol communication and tool registration.

### API Client
```python
def make_api_request(endpoint, params=None, version="v1", use_dtao=False):
    # Set up authorization headers
    headers = {"Authorization": api_key} if api_key else {}
    
    # Construct URL based on endpoint type
    if use_dtao:
        url = f"{TAOSTATS_DTAO_API_BASE_URL}/{endpoint}"
    elif endpoint.startswith("dtao/"):
        url = f"{TAOSTATS_API_BASE_URL}/{endpoint}"
    else:
        url = f"{TAOSTATS_API_BASE_URL}/{endpoint}/{version}"
    
    # Make request with timeout handling
    response = httpx.get(url, params=params, headers=headers, 
                         timeout=httpx.Timeout(connect=5.0, read=120.0, write=120.0, pool=120.0))
    response.raise_for_status()
    return response.json()
```
A robust utility function that handles HTTP requests to the TaoStats API, including authentication, timeout configuration, and error handling.

### Caching Service
The server implements intelligent caching with different TTL values based on data volatility:
```python
# Use cache with appropriate settings for different endpoints
if any(k in endpoint for k in ['registration', 'historical', 'history']):
    # Historical data rarely changes, cache for 24 hours
    ttl = 24 * 60 * 60 * 1000  # 24 hours in milliseconds
elif any(k in endpoint for k in ['neuron', 'subnet', 'stake']):
    # Semi-dynamic data, cache for 1 hour
    ttl = 60 * 60 * 1000  # 1 hour in milliseconds
else:
    # More dynamic data, cache for 5 minutes
    ttl = 5 * 60 * 1000  # 5 minutes in milliseconds
```

### Tool Registry
The server implements the following tool categories:

1. **Price Tools**: Tools for accessing TAO price data.
   - `get_price_data(data_type, days, periods)` - Get current, historical, or OHLC price data.

2. **Wallet Tools**: Tools for accessing wallet and account data.
   - `get_wallet_data(data_type, address, ...)` - Get account details, history, transfers, and exchanges.

3. **Trading View Tools**: Tools for accessing chart data.
   - `get_trading_view_data(symbol, resolution, ...)` - Get candlestick data for trading charts.

4. **Blockchain Tools**: Tools for accessing core blockchain data.
   - `get_blocks_data(...)` - Access block data with filtering options.
   - `get_extrinsics_data(...)` - Access extrinsics (transactions) with filtering options.
   - `get_events_data(...)` - Access blockchain events with filtering options.

5. **Network Tools**: Tools for accessing network statistics.
   - `get_network_stats(data_type, ...)` - Get current or historical network statistics.

6. **Subnet Tools**: Tools for accessing subnet information.
   - `get_subnet_distribution(netuid, data_type)` - Get coldkey, IP, and incentive distribution.

### Data Validation
The server uses Pydantic models for data validation and schema enforcement:
```python
class PriceData(BaseModel):
    """Model for price data."""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    symbol: str
    price: float
    volume_24h: Optional[float] = None
    # Additional fields...
    
    @field_validator('price')
    @classmethod
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Price must be positive')
        return v
```

## Setup

### Prerequisites
- Python 3.11 or higher
- A valid TaoStats API key

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/masa-finance/endgame-mcp-hackathon.git
   cd endgame-mcp-hackathon
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set your TaoStats API key:
   ```
   export TAOSTATS_API_KEY="your-api-key-here"
   ```

### Running the Server

Start the server with:
```
python src/server.py
```

The server will begin listening for MCP client connections with a 180-second request timeout.

## Usage

### Connecting with an MCP Client

To connect to the server from Python code:

```python
from mcp import Client

client = Client("TaoStats")
```

### Using Tools

Once connected, you can use the tools directly:

```python
# Get current TAO price
price_data = client.get_price_data(data_type="current")

# Get account information
account_data = client.get_wallet_data(
    data_type="account", 
    address="5Hd2ze5ug8n1bo3UCAcQsf66VNjKqGos8u6apNfzcU86pg4N"
)

# Get trading view chart data
chart_data = client.get_trading_view_data(
    symbol="SUB-1", 
    resolution="1D",
    from_timestamp=1672531200,
    to_timestamp=1675209600
)

# Get recent blockchain blocks
blocks = client.get_blocks_data(limit=10, order="block_number_desc")

# Get network statistics
stats = client.get_network_stats(data_type="current")
```

### Error Handling

The server implements robust error handling for API requests, but clients should also implement appropriate error handling:

```python
try:
    price_data = client.get_price_data(data_type="current")
except Exception as e:
    print(f"Error fetching price data: {e}")
```

## Performance

### Response Time
- Average response time: < 1000ms for uncached requests (dependent on TaoStats API)
- Average response time: < 100ms for cached requests
- Tools with optional parameters (like `limit`) allow for tuning performance vs data completeness

### Caching
The implementation includes an intelligent caching system:
- Historical data (24-hour TTL): registration events, historical metrics 
- Semi-dynamic data (1-hour TTL): neuron data, subnet data, stake information
- Dynamic data (5-minute TTL): current prices, account balances, recent transactions

### Timeout Handling
The server implements a comprehensive timeout strategy:
- Connection timeout: 5 seconds
- Read/write/pool timeout: 120 seconds each
- Overall request timeout: 180 seconds

### Error Resilience
The API client catches and handles exceptions gracefully to prevent server crashes:
- Timeout exceptions return an empty data structure with error information
- HTTP errors (including authentication) are logged and return empty data
- Unexpected errors are caught, logged, and return empty data

## Testing

### Unit Tests
The project includes unit tests for each tool using pytest:

```python
@patch("httpx.get")
def test_get_price_data_current(self, mock_get):
    """Test getting current price data."""
    # Set up mock response
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": [{"symbol": "TAO", "price": 10.5}]}
    mock_get.return_value = mock_response
    
    # Call the function
    result = get_price_data(data_type="current")
    
    # Verify that httpx.get was called with expected args
    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert "price/latest" in args[0]
    assert kwargs["params"]["asset"] == "tao"
```

### API Validation Tests
Tests ensure that all API responses are properly validated against their Pydantic models.

### Error Handling Tests
The test suite includes specific tests for error conditions:
```python
def test_get_price_data_invalid_days(self):
    """Test getting price data with invalid days parameter."""
    # Call the function with negative days value and expect ValueError
    with pytest.raises(ValueError, match="Days must be positive"):
        get_price_data(data_type="history", days=-10)
```

### Running Tests
To run the test suite:
```
python -m pytest tests/
```
