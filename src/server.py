from mcp.server.fastmcp import FastMCP
import httpx
import os
import logging
import sys
from typing import Any, Optional, Dict, Literal
from datetime import datetime, timedelta
from cache_service import tao_stats_cache

from models import (TradingViewData, PriceData, PriceHistoryData, PriceOHLCData,
                    AccountsListResponse, AccountHistoryResponse,
                    TransfersListResponse, ExchangeListResponse,
                    BlocksListData,  ExtrinsicsListData,
                    EventsListData, NetworkStatsData, NetworkStatsListData)

# Create an MCP server
mcp = FastMCP("TaoStats")

# API Configuration
TAOSTATS_API_BASE_URL = "https://api.taostats.io/api"
TAOSTATS_DTAO_API_BASE_URL = "https://api.taostats.io/api/dtao"
TAOSTATS_API_KEY = os.getenv("TAOSTATS_API_KEY")

# Configure logging to write to stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("financial-datasets-mcp")

# Helper function to validate API responses
def validate_response(data, model_class):
    """Validate API response data against Pydantic model.

    Args:
        data: Response data from the API
        model_class: Pydantic model class to validate against

    Returns:
        Validated data (either a single item or a list)
    """
    try:
        if isinstance(data, list):
            return [model_class(**item).dict() for item in data]
        return model_class(**data).dict()
    except Exception as e:
        # Validation failed, log the error and return original data
        logger.warning(f"Validation error: {e}")
        return data

def make_api_request(endpoint, params=None, version="v1", use_dtao=False):
    """Construct and send request to TaoStats API.

    Args:
        endpoint: API endpoint to access
        params: Request parameters (optional)
        version: API version (default v1)
        use_dtao: Whether to use the DTAO API base URL

    Returns:
        Response data from API
    """
    # Check if API key exists and log its status (redacting actual key value)
    api_key = os.getenv("TAOSTATS_API_KEY")
    if api_key:
        # Only log the first few characters to avoid exposing the full key
        masked_key = api_key[:4] + "..." if len(api_key) > 4 else "too short"
        logging.info(f"Using API key starting with: {masked_key}")
    else:
        logging.error("API KEY NOT FOUND! Set TAOSTATS_API_KEY environment variable.")
        # Return empty data instead of failing to prevent server crash
        return {"data": []}
    
    # Set up authorization headers - Use direct Authorization header without Bearer prefix
    headers = {"Authorization": api_key} if api_key else {}
    
    if use_dtao:
        # Format for DTAO API: https://api.taostats.io/api/dtao/{endpoint}/{version}
        url = f"{TAOSTATS_DTAO_API_BASE_URL}/{endpoint}"
        
    elif endpoint.startswith("dtao/"):
        # Legacy format for dtao endpoints
        url = f"{TAOSTATS_API_BASE_URL}/{endpoint}"
    else:
        # Format for API v1: https://api.taostats.io/api/{endpoint}/{version}
        url = f"{TAOSTATS_API_BASE_URL}/{endpoint}/{version}"
    
    # Debug log the request URL
    logging.info(f"Making request to URL: {url}")
    
    # Create a unique cache key based on endpoint, params, and version
    cache_key = f"{url}:{str(params)}"
    
    # Define the actual request function that will be called or cached
    def make_actual_request():
        try:
            # Add timeout to prevent hanging requests (5 seconds for connection, 120 seconds total)
            response = httpx.get(url, params=params, headers=headers, timeout=httpx.Timeout(connect=5.0, read=120.0, write=120.0, pool=120.0))
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as e:
            logging.error(f"Request timeout: {e}")
            logging.error(f"Request to {url} timed out after 120 seconds.")
            # Return empty data instead of raising an exception to prevent server crash
            return {"data": [], "error": "Request timed out"}
        except httpx.HTTPStatusError as e:
            logging.error(f"HTTP error: {e}")
            if e.response.status_code == 401:
                logging.error("401 Unauthorized: API key is invalid or not correctly set.")
                logging.error("Check your API key in the environment variables or MCP config.")
            # Return empty data instead of raising an exception to prevent server crash
            return {"data": []}
        except Exception as e:
            logging.error(f"Unexpected error during API request: {e}")
            # Return empty data instead of raising an exception to prevent server crash
            return {"data": []}
    
    # Use cache with appropriate settings for different endpoints
    # Long-lived data can be cached longer
    if any(k in endpoint for k in ['registration', 'historical', 'history']):
        # Historical data rarely changes, cache for 24 hours
        ttl = 24 * 60 * 60 * 1000  # 24 hours in milliseconds
    elif any(k in endpoint for k in ['neuron', 'subnet', 'stake']):
        # Semi-dynamic data, cache for 1 hour
        ttl = 60 * 60 * 1000  # 1 hour in milliseconds
    else:
        # More dynamic data, cache for 5 minutes
        ttl = 5 * 60 * 1000  # 5 minutes in milliseconds
    
    # Use the cache service
    return tao_stats_cache.with_cache(
        cache_key,
        make_actual_request,
        {
            'ttl': ttl,
            'fallback_to_cache': True,
            'fail_silently': True
        }
    )

@mcp.tool(description='Retrieve TAO/dTAO price data including current price, historical prices, and OHLC data for market analysis')
def get_price_data(data_type: Literal["current", "history", "ohlc"] = "current", 
                  days: int = 30, 
                  periods: str = "1d") -> Dict:
    """Get TAO price data with various options
    
    Args:
        data_type: Type of price data to retrieve ("current", "history", or "ohlc")
        days: Number of days for historical data (used with data_type="history")
        periods: Time period for OHLC data '1m', '1h', '1d' (used with data_type="ohlc")
    """
    # Validate input parameters
    if days <= 0:
        raise ValueError("Days must be positive")
    
    if data_type not in ["current", "history", "ohlc"]:
        raise ValueError(f"Invalid data_type: {data_type}")
    
    # Make API request based on data_type
    if data_type == "current":
        # For current price, just get the latest data
        params = {
            "asset": "tao"
        }
        
        response_data = make_api_request("price/latest", params)
        # API returns data within a "data" field
        if isinstance(response_data, dict) and "data" in response_data and response_data["data"]:
            # Return just the first item
            return validate_response(response_data["data"][0], PriceData)
        return response_data
    elif data_type == "history":
        # Convert days to timestamp range
        end_timestamp = int(datetime.now().timestamp())
        start_timestamp = end_timestamp - (days * 24 * 60 * 60)
        
        params = {
            "asset": "tao",
            "timestamp_start": start_timestamp,
            "timestamp_end": end_timestamp,
            "limit": 100,  # Reasonable limit for history data
            "order": "timestamp_desc"  # Most recent first
        }
        
        response_data = make_api_request("price/history", params)
        # API returns list of price points within a "data" field
        return validate_response(response_data, PriceHistoryData)
    elif data_type == "ohlc":
        # Convert days to timestamp range if needed
        end_timestamp = int(datetime.now().timestamp())
        start_timestamp = end_timestamp - (days * 24 * 60 * 60)
        
        params = {
            "asset": "tao",
            "period": periods,
            "timestamp_start": start_timestamp,
            "timestamp_end": end_timestamp,
            "limit": 100  # Reasonable limit for OHLC data
        }
        
        response_data = make_api_request("price/ohlc", params)
        # API returns OHLC data within a "data" field
        return validate_response(response_data, PriceOHLCData)
    else:
        raise ValueError(f"Invalid data_type: {data_type}")
    
@mcp.tool(description='Access wallet and account data including balances, transaction history, and token transfers')
def get_wallet_data(data_type: Literal["account", "account_history", "transfers", "exchanges"] = "transfers",
                   address: Optional[str] = None,
                   network: str = "finney",
                   order: Optional[str] = None,
                   block_number: Optional[int] = None,
                   block_start: Optional[int] = None,
                   block_end: Optional[int] = None,
                   timestamp_start: Optional[int] = None,
                   timestamp_end: Optional[int] = None,
                   from_address: Optional[str] = None,
                   to_address: Optional[str] = None,
                   transaction_hash: Optional[str] = None,
                   extrinsic_id: Optional[str] = None,
                   amount_min: Optional[str] = None,
                   amount_max: Optional[str] = None,
                   page: int = 1,
                   limit: int = 50,
                   days: int = 30) -> Dict:
    """Get wallet/account data with various options
    
    Args:
        data_type: Type of wallet data to retrieve ("account", "account_history", "transfers", "exchanges")
        address: SS58 address for account queries (required for account and account_history)
        network: Network to query (defaults to "finney")
        order: Order of results
        block_number: Specific block number to query
        block_start: Start of block range
        block_end: End of block range
        timestamp_start: Start of timestamp range in Unix timestamp (seconds)
        timestamp_end: End of timestamp range in Unix timestamp (seconds)
        from_address: Filter transfers by sender address (for transfers)
        to_address: Filter transfers by recipient address (for transfers)
        transaction_hash: Filter by transaction hash (for transfers)
        extrinsic_id: Filter by extrinsic ID (for transfers)
        amount_min: Minimum transfer amount (for transfers)
        amount_max: Maximum transfer amount (for transfers)
        page: Page number for pagination (defaults to 1)
        limit: Number of entries to return (max 200, defaults to 50)
        days: Number of days for historical data (deprecated)
    """
    # Validate input parameters
    if limit <= 0 or limit > 200:
        raise ValueError("Limit must be between 1 and 200")
        
    if page <= 0:
        raise ValueError("Page must be positive")
    
    if days <= 0:
        raise ValueError("Days must be positive")
    
    # Check if address is required for the selected data_type and validate format
    address_required = ["account", "account_history"]
    if data_type in address_required and address is None:
        raise ValueError(f"address is required for {data_type} data type")
        
    if address is not None and not address.startswith('5') and not address.startswith('0x'):
        raise ValueError(f"Invalid address format: {address}")
        
    if from_address is not None and not from_address.startswith('5') and not from_address.startswith('0x'):
        raise ValueError(f"Invalid from_address format: {from_address}")
        
    if to_address is not None and not to_address.startswith('5') and not to_address.startswith('0x'):
        raise ValueError(f"Invalid to_address format: {to_address}")
    
    # Set up parameters based on data_type
    if data_type == "account":
        # For accounts listing, include all filtering parameters
        params = {
            "network": network,
            "page": page,
            "limit": limit
        }
        
        # Add optional filter parameters if provided
        if address is not None:
            params["address"] = address
            
        if order is not None:
            params["order"] = order
            
        # Make API request for accounts list
        response_data = make_api_request("account/latest", params)
        return validate_response(response_data, AccountsListResponse)

    
    elif data_type == "account_history":
        # For account history
        params = {
            "network": network,
            "page": page,
            "limit": limit
        }
        
        # Add optional filter parameters if provided
        if block_number is not None:
            params["block_number"] = block_number
            
        if block_start is not None:
            params["block_start"] = block_start
            
        if block_end is not None:
            params["block_end"] = block_end
            
        if timestamp_start is not None:
            params["timestamp_start"] = timestamp_start
            
        if timestamp_end is not None:
            params["timestamp_end"] = timestamp_end
            
        if order is not None:
            params["order"] = order
        
        response_data = make_api_request(f"account/history", params)
        return validate_response(response_data, AccountHistoryResponse)
    
    elif data_type == "transfers":
        # For transfers
        params = {
            "network": network,
            "page": page,
            "limit": limit
        }
        
        # Add all possible filter parameters for transfers
        if address is not None:
            params["address"] = address
            
        if from_address is not None:
            params["from"] = from_address
            
        if to_address is not None:
            params["to"] = to_address
            
        if transaction_hash is not None:
            params["transaction_hash"] = transaction_hash
            
        if extrinsic_id is not None:
            params["extrinsic_id"] = extrinsic_id
            
        if amount_min is not None:
            params["amount_min"] = amount_min
            
        if amount_max is not None:
            params["amount_max"] = amount_max
            
        if block_number is not None:
            params["block_number"] = block_number
            
        if block_start is not None:
            params["block_start"] = block_start
            
        if block_end is not None:
            params["block_end"] = block_end
            
        if timestamp_start is not None:
            params["timestamp_start"] = timestamp_start
            
        if timestamp_end is not None:
            params["timestamp_end"] = timestamp_end
            
        if order is not None:
            params["order"] = order
            
        response_data = make_api_request("transfer", params)
        return validate_response(response_data, TransfersListResponse)
    
    elif data_type == "exchanges":
        # For exchanges
        params = {
            "network": network,
            "page": page,
            "limit": limit
        }
        
        if address is not None:
            params["address"] = address
            
        if block_number is not None:
            params["block_number"] = block_number
            
        if block_start is not None:
            params["block_start"] = block_start
            
        if block_end is not None:
            params["block_end"] = block_end
            
        if timestamp_start is not None:
            params["timestamp_start"] = timestamp_start
            
        if timestamp_end is not None:
            params["timestamp_end"] = timestamp_end
            
        if order is not None:
            params["order"] = order
        
        response_data = make_api_request("exchange", params)
        return validate_response(response_data, ExchangeListResponse)
    
    else:
        raise ValueError(f"Invalid data_type: {data_type}")

@mcp.tool(description='Retrieve Trading View chart data for subnet price analysis with customizable time ranges and resolutions')
def get_trading_view_data(symbol: str = "SUB-1", 
                         resolution: str = "1D", 
                         from_timestamp: Optional[int] = None, 
                         to_timestamp: Optional[int] = None) -> Dict:
    """Get Trading View chart data for TAO price history
    
    Args:
        symbol: SUB- followed by subnet netuid "SUB-19"
        resolution: Time resolution for chart data (e.g., possible values: 1,5,15,60 for minutes, 1D, 7D, 30D for days)
        from_timestamp: Start timestamp in seconds (if None, defaults to 30 days ago)
        to_timestamp: End timestamp in seconds (if None, defaults to current time)
    """
    # Set up default timestamps if not provided
    if from_timestamp is None:
        # Default to 30 days ago
        from_timestamp = int((datetime.now() - timedelta(days=30)).timestamp())
    
    if to_timestamp is None:
        # Default to current time
        to_timestamp = int(datetime.now().timestamp())
        
    # Validate input parameters
    if from_timestamp >= to_timestamp:
        raise ValueError("from_timestamp must be earlier than to_timestamp")
        
    # Set up parameters
    params = {
        "symbol": symbol,
        "resolution": resolution,
        "from": from_timestamp,
        "to": to_timestamp
    }
    
    response_data = make_api_request("tradingview/udf/history", params, use_dtao=True)
    
    # Check if response is empty or has the empty data structure
    if not response_data or (isinstance(response_data, dict) and response_data.get('data') == []):
        logging.warning(f"Empty response from Trading View API for params: {params}")
        # Return a minimal valid response instead of attempting validation
        return {
            "symbol": symbol,
            "resolution": resolution,
            "c": [],  # Close prices
            "h": [],  # High prices
            "l": [],  # Low prices
            "o": [],  # Open prices
            "t": [],  # Timestamps
            "v": [],  # Volumes
            "s": "no_data"  # Status
        }
    
    return validate_response(response_data, TradingViewData)

@mcp.tool(description='Retrieve blockchain blocks data with filtering options for block numbers, timestamps, and other attributes')
def get_blocks_data(block_start: Optional[int] = None,
                   block_end: Optional[int] = None,
                   timestamp_start: Optional[int] = None,
                   timestamp_end: Optional[int] = None,
                   block_number: Optional[int] = None,
                   hash: Optional[str] = None,
                   spec_version: Optional[int] = None,
                   validator: Optional[str] = None,
                   order: Optional[str] = None,
                   page: int = 1,
                   limit: int = 50) -> Dict:
    """Get blockchain blocks data with various filtering options
    
    Args:
        block_start: Start of block range (inclusive)
        block_end: End of block range (inclusive)
        timestamp_start: Start of timestamp range in Unix timestamp (seconds since 1970-01-01) (inclusive)
        timestamp_end: End of timestamp range in Unix timestamp (seconds since 1970-01-01) (inclusive)
        block_number: Exact block number to fetch
        hash: Block hash to search for
        spec_version: Filter by specific runtime spec version
        validator: Filter by validator address
        order: Ordering of results (e.g., "block_number_desc")
        page: Page number for pagination (defaults to 1)
        limit: Number of entries to return (defaults to 50, max 200)
    """
    # Validate input parameters
    if limit <= 0 or limit > 200:
        raise ValueError("Limit must be between 1 and 200")
        
    if page <= 0:
        raise ValueError("Page must be positive")
    
    # Validate range parameters
    if block_start is not None and block_end is not None and block_start > block_end:
        raise ValueError("block_start must be less than or equal to block_end")
        
    if timestamp_start is not None and timestamp_end is not None and timestamp_start > timestamp_end:
        raise ValueError("timestamp_start must be less than or equal to timestamp_end")
    
    # Set up parameters
    params = {
        "page": page,
        "limit": limit
    }
    
    # Add filter parameters if provided
    if block_start is not None:
        params["block_start"] = block_start
        
    if block_end is not None:
        params["block_end"] = block_end
        
    if timestamp_start is not None:
        params["timestamp_start"] = timestamp_start
        
    if timestamp_end is not None:
        params["timestamp_end"] = timestamp_end
        
    if block_number is not None:
        params["block_number"] = block_number
        
    if hash is not None:
        params["hash"] = hash
        
    if spec_version is not None:
        params["spec_version"] = spec_version
        
    if validator is not None:
        params["validator"] = validator
        
    if order is not None:
        params["order"] = order
    
    # Make API request for blocks list
    response_data = make_api_request("block", params)
    return validate_response(response_data, BlocksListData)

@mcp.tool(description='Retrieve blockchain extrinsic (transaction) data with filtering options based on block, time, sender, or transaction type')
def get_extrinsics_data(block_number: Optional[int] = None,
                       block_start: Optional[int] = None,
                       block_end: Optional[int] = None,
                       timestamp_start: Optional[int] = None,
                       timestamp_end: Optional[int] = None,
                       hash: Optional[str] = None,
                       full_name: Optional[str] = None,
                       id: Optional[str] = None,
                       signer_address: Optional[str] = None,
                       page: int = 1,
                       limit: int = 50,
                       order: Optional[str] = None) -> Dict:
    """Get blockchain extrinsic (transaction) data with various filtering options
    
    Args:
        block_number: Specific block number to filter extrinsics
        block_start: Start of block range (inclusive)
        block_end: End of block range (inclusive)
        timestamp_start: Start of timestamp range in Unix timestamp (seconds)
        timestamp_end: End of timestamp range in Unix timestamp (seconds)
        hash: Extrinsic hash to search for
        full_name: Filter by full name of the extrinsic (e.g., "SubtensorModule.move_stake")
        id: Extrinsic ID to search for (e.g., "5416952-0028")
        signer_address: Filter by signer address
        page: Page number for pagination (defaults to 1)
        limit: Number of entries to return (defaults to 50, max 200)
        order: Ordering of results (e.g., "block_number_desc")
    """
    # Validate input parameters
    if limit <= 0 or limit > 200:
        raise ValueError("Limit must be between 1 and 200")
        
    if page <= 0:
        raise ValueError("Page must be positive")
    
    # Validate range parameters
    if block_start is not None and block_end is not None and block_start > block_end:
        raise ValueError("block_start must be less than or equal to block_end")
        
    if timestamp_start is not None and timestamp_end is not None and timestamp_start > timestamp_end:
        raise ValueError("timestamp_start must be less than or equal to timestamp_end")
    
    # Set up parameters
    params = {
        "page": page,
        "limit": limit
    }
    
    # Add filter parameters if provided
    if block_number is not None:
        params["block_number"] = block_number
        
    if block_start is not None:
        params["block_start"] = block_start
        
    if block_end is not None:
        params["block_end"] = block_end
        
    if timestamp_start is not None:
        params["timestamp_start"] = timestamp_start
        
    if timestamp_end is not None:
        params["timestamp_end"] = timestamp_end
        
    if hash is not None:
        params["hash"] = hash
        
    if full_name is not None:
        params["full_name"] = full_name
        
    if id is not None:
        params["id"] = id
        
    if signer_address is not None:
        params["signer_address"] = signer_address
        
    if order is not None:
        params["order"] = order
    
    # Make API request for extrinsics list
    response_data = make_api_request("extrinsic", params)
    return validate_response(response_data, ExtrinsicsListData)

@mcp.tool(description='Retrieve blockchain event data with filtering options for block, type, timestamp, and related transactions')
def get_events_data(block_number: Optional[int] = None,
                   block_start: Optional[int] = None,
                   block_end: Optional[int] = None,
                   timestamp_start: Optional[int] = None,
                   timestamp_end: Optional[int] = None,
                   pallet: Optional[str] = None,
                   phase: Optional[str] = None,
                   name: Optional[str] = None,
                   full_name: Optional[str] = None,
                   extrinsic_id: Optional[str] = None,
                   call_id: Optional[str] = None,
                   id: Optional[str] = None,
                   page: int = 1,
                   limit: int = 50,
                   order: Optional[str] = None) -> Dict:
    """Get blockchain event data with various filtering options
    
    Args:
        block_number: Specific block number to filter events
        block_start: Start of block range (inclusive)
        block_end: End of block range (inclusive)
        timestamp_start: Start of timestamp range in Unix timestamp (seconds)
        timestamp_end: End of timestamp range in Unix timestamp (seconds)
        pallet: Filter by pallet name (e.g., "SubtensorModule", "Balances", "System")
        phase: Filter by event phase (e.g., "ApplyExtrinsic")
        name: Filter by event name (e.g., "StakeRemoved")
        full_name: Full name of the event (e.g., "SubtensorModule.StakeRemoved")
        extrinsic_id: Filter by extrinsic ID (e.g., "5416968-0023")
        call_id: Filter by call ID
        id: Event ID to search for (e.g., "5416968-0075")
        page: Page number for pagination (defaults to 1)
        limit: Number of entries to return (defaults to 50, max 200)
        order: Ordering of results (e.g., "block_number_desc")
    """
    # Validate input parameters
    if limit <= 0 or limit > 200:
        raise ValueError("Limit must be between 1 and 200")
        
    if page <= 0:
        raise ValueError("Page must be positive")
    
    # Validate range parameters
    if block_start is not None and block_end is not None and block_start > block_end:
        raise ValueError("block_start must be less than or equal to block_end")
        
    if timestamp_start is not None and timestamp_end is not None and timestamp_start > timestamp_end:
        raise ValueError("timestamp_start must be less than or equal to timestamp_end")
    
    # Set up parameters
    params = {
        "page": page,
        "limit": limit
    }
    
    # Add filter parameters if provided
    if block_number is not None:
        params["block_number"] = block_number
        
    if block_start is not None:
        params["block_start"] = block_start
        
    if block_end is not None:
        params["block_end"] = block_end
        
    if timestamp_start is not None:
        params["timestamp_start"] = timestamp_start
        
    if timestamp_end is not None:
        params["timestamp_end"] = timestamp_end
        
    if pallet is not None:
        params["pallet"] = pallet
        
    if phase is not None:
        params["phase"] = phase
        
    if name is not None:
        params["name"] = name
        
    if full_name is not None:
        params["full_name"] = full_name
        
    if extrinsic_id is not None:
        params["extrinsic_id"] = extrinsic_id
        
    if call_id is not None:
        params["call_id"] = call_id
        
    if id is not None:
        params["id"] = id
        
    if order is not None:
        params["order"] = order
    

    response_data = make_api_request("event", params)
    return validate_response(response_data, EventsListData)

@mcp.tool(description='Retrieve network statistics data including blockchain metrics, account numbers, and economic indicators')
def get_network_stats(data_type: Literal["current", "history"] = "current",
                     block_number: Optional[int] = None,
                     block_start: Optional[int] = None,
                     block_end: Optional[int] = None,
                     timestamp_start: Optional[int] = None,
                     timestamp_end: Optional[int] = None,
                     frequency: str = "by_day",
                     page: int = 1,
                     limit: int = 50,
                     order: Optional[str] = None) -> Dict:
    """Get network statistics data with options for current or historical data
    
    Args:
        data_type: Type of stats data to retrieve ("current" or "history")
        block_number: Specific block number to filter stats (for history)
        block_start: Start of block range (inclusive, for history)
        block_end: End of block range (inclusive, for history)
        timestamp_start: Start of timestamp range in Unix timestamp (seconds, for history)
        timestamp_end: End of timestamp range in Unix timestamp (seconds, for history)
        frequency: Data frequency (defaults to "by_day", for history)
        page: Page number for pagination (defaults to 1, for history)
        limit: Number of entries to return (defaults to 50, max 200, for history)
        order: Ordering of results (e.g., "block_number_desc", for history)
    """
    # Validate input parameters
    if data_type not in ["current", "history"]:
        raise ValueError(f"Invalid data_type: {data_type}")
        
    if data_type == "history":
        if limit <= 0 or limit > 200:
            raise ValueError("Limit must be between 1 and 200")
            
        if page <= 0:
            raise ValueError("Page must be positive")
        
        # Validate range parameters
        if block_start is not None and block_end is not None and block_start > block_end:
            raise ValueError("block_start must be less than or equal to block_end")
            
        if timestamp_start is not None and timestamp_end is not None and timestamp_start > timestamp_end:
            raise ValueError("timestamp_start must be less than or equal to timestamp_end")
    
    # Handle current stats request
    if data_type == "current":
        response_data = make_api_request("stats/latest")
        if isinstance(response_data, dict) and "data" in response_data and response_data["data"]:
            return validate_response(response_data["data"][0], NetworkStatsData)
        return response_data
    
    # Handle historical stats request
    else:
        # Set up parameters
        params = {
            "page": page,
            "limit": limit,
            "frequency": frequency
        }
        
        # Add filter parameters if provided
        if block_number is not None:
            params["block_number"] = block_number
            
        if block_start is not None:
            params["block_start"] = block_start
            
        if block_end is not None:
            params["block_end"] = block_end
            
        if timestamp_start is not None:
            params["timestamp_start"] = timestamp_start
            
        if timestamp_end is not None:
            params["timestamp_end"] = timestamp_end
            
        if order is not None:
            params["order"] = order
        
        # Make API request for stats history
        response_data = make_api_request("stats/history", params)
        return validate_response(response_data, NetworkStatsListData)

@mcp.tool(description='Get distribution statistics about subnets including coldkey distribution and IP distribution')
def get_subnet_distribution(netuid: int = 1,
                          data_type: Literal["coldkey_distribution", "ip_distribution", "miner_incentive"] = "coldkey_distribution") -> Dict:
    """Get distribution statistics for a specific subnet
    
    Args:
        netuid: Subnet ID (required)
        data_type: Type of distribution to query ("coldkey_distribution", "ip_distribution", or "miner_incentive")
    """
    # Validate netuid
    if netuid < 0:
        raise ValueError("Subnet ID must be non-negative")
    
    # Set up parameters
    params = {
        "netuid": netuid
    }
    
    # Make API request based on data_type
    if data_type == "coldkey_distribution":
        response_data = make_api_request("subnet/distribution/coldkey", params, version="v1")
        return response_data
    
    elif data_type == "ip_distribution":
        response_data = make_api_request("subnet/distribution/ip", params, version="v1")
        return response_data
    
    elif data_type == "miner_incentive":
        response_data = make_api_request("subnet/distribution/incentive", params, version="v1")
        return response_data
    
    else:
        raise ValueError(f"Invalid data_type: {data_type}")


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')
