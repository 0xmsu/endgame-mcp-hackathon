
# Model Context Protocol Specification

## Protocol Overview

The TaoStats MCP server implements a Model Context Protocol for accessing Bittensor ecosystem data through the TaoStats API. This protocol allows AI models and applications to seamlessly query blockchain data, validator information, price data, and network statistics from the Bittensor network without having to manage API authentication or handle complex request formatting.

The protocol follows a tool-based approach, providing a set of specialized functions that abstract away the underlying API calls. It implements robust caching strategies, error handling, and timeout management to ensure reliable data access.

## Core Components

1. **FastMCP Core**: The central server component that handles protocol negotiation, client connections, and message routing.

2. **API Client Layer**: Handles authentication, request formatting, and error handling when communicating with the TaoStats API:
   ```python
   def make_api_request(endpoint, params=None, version="v1", use_dtao=False):
       # API request implementation with timeout handling
       response = httpx.get(url, params=params, headers=headers, 
                         timeout=httpx.Timeout(connect=5.0, read=120.0, write=120.0, pool=120.0))
       # Additional error handling...
   ```

3. **Tool Registry**: A collection of specialized functions that models can call to retrieve specific types of data:
   ```python
   @mcp.tool(description='Retrieve TAO/dTAO price data including current price, historical prices, and OHLC data')
   def get_price_data(data_type: Literal["current", "history", "ohlc"] = "current", days: int = 30):
       # Implementation...
   ```

4. **Caching System**: Intelligent caching with TTL based on data volatility to improve performance and reduce API load.

5. **Data Validation Layer**: Uses Pydantic models to validate and enforce data schemas.

## Interfaces

### Tool Interface

Tools are function-based interfaces that allow models to request specific data types from the TaoStats API:

```python
@mcp.tool(description='Retrieve blockchain blocks data with filtering options for block numbers, timestamps, and other attributes')
def get_blocks_data(block_start: Optional[int] = None,
                   block_end: Optional[int] = None,
                   timestamp_start: Optional[int] = None,
                   # Additional parameters...
                   ) -> Dict:
    """Get blockchain blocks data with various filtering options"""
    # Implementation...
```

Each tool:
- Is decorated with `@mcp.tool()` and includes a descriptive summary
- Features comprehensive documentation in the docstring
- Has strongly typed parameters with sensible defaults
- Implements validation for input parameters
- Returns structured data that follows consistent schemas

### Available Tools

The protocol provides the following tool categories:

1. **Price Tools**: `get_price_data` - Access current, historical, and OHLC price data
2. **Wallet Tools**: `get_wallet_data` - Access account details, history, and transfers
3. **Trading View Tools**: `get_trading_view_data` - Access chart data for market analysis
4. **Blockchain Tools**: 
   - `get_blocks_data` - Access block information
   - `get_extrinsics_data` - Access transaction data
   - `get_events_data` - Access event logs
5. **Network Tools**: `get_network_stats` - Access current and historical network statistics
6. **Subnet Tools**: `get_subnet_distribution` - Access subnet distribution information

## Data Flow

1. **Client Connection**: An AI model/application connects to the MCP server.

2. **Tool Call**: The client invokes a tool with specific parameters:
   ```python
   result = client.get_price_data(data_type="history", days=30)
   ```

3. **Parameter Validation**: The server validates all input parameters against expected types and value ranges.

4. **Cache Check**: The server checks if a cached response exists for the request.

5. **API Request**: If no cache exists, the server constructs and sends a request to the TaoStats API with appropriate headers and parameters.

6. **Response Processing**: The API response is validated against Pydantic models and processed.

7. **Cache Update**: The processed response is cached for future requests if appropriate.

8. **Result Return**: The validated data is returned to the client.

## Context Management

The TaoStats MCP server manages context effectively through:

1. **Comprehensive Documentation**: Each tool includes detailed documentation that explains its purpose, parameters, and return values.

2. **Typed Parameters**: All parameters use Python type hints to communicate expected values:
   ```python
   def get_trading_view_data(symbol: str = "SUB-1", 
                            resolution: str = "1D", 
                            from_timestamp: Optional[int] = None, 
                            to_timestamp: Optional[int] = None) -> Dict:
   ```

3. **Intelligent Defaults**: Tools provide sensible default values where appropriate to simplify common use cases.

4. **Consistent Error Handling**: The system provides meaningful error messages when validation fails:
   ```python
   if timestamp_start is not None and timestamp_end is not None and timestamp_start > timestamp_end:
       raise ValueError("timestamp_start must be less than or equal to timestamp_end")
   ```

5. **Result Validation**: Response data is validated against Pydantic models to ensure consistent structure and types.

## Integration Guidelines

To integrate with the TaoStats MCP server:

1. **Client Setup**: Initialize an MCP client pointing to the server:
   ```python
   from mcp import Client
   client = Client("TaoStats")
   ```

2. **Tool Discovery**: Explore available tools programmatically or via documentation.

3. **Tool Invocation**: Call tools with appropriate parameters:
   ```python
   # Get current TAO price
   price_data = client.get_price_data(data_type="current")
   
   # Get recent blocks
   blocks = client.get_blocks_data(limit=10, order="block_number_desc")
   ```

4. **Error Handling**: Implement appropriate error handling in client code:
   ```python
   try:
       result = client.get_wallet_data(data_type="account", address="5Hd2...")
   except ValueError as e:
       print(f"Parameter error: {e}")
   except Exception as e:
       print(f"Request failed: {e}")
   ```

5. **Performance Optimization**: Use parameter filtering to reduce response size and improve performance:
   ```python
   # Request only the needed data with appropriate filters
   transfers = client.get_wallet_data(
       data_type="transfers",
       from_address="5ABC...",
       timestamp_start=1672531200,
       timestamp_end=1675209600,
       limit=50
   )
   ```

6. **Respect Rate Limits**: The server implements caching to help with rate limits, but clients should still implement reasonable request patterns.
