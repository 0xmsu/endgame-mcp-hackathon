import pytest
import httpx
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.append(str(src_path))

from server import mcp, validate_response, make_api_request
from models import PriceData

class TestMCPInstance:
    """Test MCP instance creation and configuration."""
    
    def test_mcp_instance_exists(self):
        """Test that the MCP instance is created."""
        assert mcp is not None
        assert mcp.name == "TaoStats"

class TestValidateResponse:
    """Tests for the validate_response function."""
    
    def test_validate_single_item(self):
        """Test validating a single item response."""
        # Sample data that matches the PriceData model
        data = {
            "symbol": "TAO",
            "price": 123.45,
            "volume": 1000000,
            "timestamp": "2023-01-01T00:00:00Z"
        }
        
        # Validate the data against the PriceData model
        result = validate_response(data, PriceData)
        
        # Check that the result is a dict with correct values
        assert isinstance(result, dict)
        assert result["symbol"] == "TAO"
        assert result["price"] == 123.45
    
    def test_validate_list(self):
        """Test validating a list of items."""
        # Sample data with a list of items that match the PriceData model
        data = [
            {
                "symbol": "TAO",
                "price": 123.45,
                "volume": 1000000,
                "timestamp": "2023-01-01T00:00:00Z"
            },
            {
                "symbol": "TAO",
                "price": 124.56,
                "volume": 1100000,
                "timestamp": "2023-01-02T00:00:00Z"
            }
        ]
        
        # Validate the data against the PriceData model
        result = validate_response(data, PriceData)
        
        # Check that the result is a list of dicts with correct values
        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0], dict)
        assert result[0]["symbol"] == "TAO"
        assert result[0]["price"] == 123.45
        assert isinstance(result[1], dict)
        assert result[1]["symbol"] == "TAO"
        assert result[1]["price"] == 124.56
    
    def test_validate_invalid_data(self):
        """Test validating invalid data."""
        # Sample data that doesn't match the PriceData model
        data = {
            "symbol": "TAO",
            "price": "not a number",  # Invalid data type
            "volume": 1000000,
            "timestamp": "2023-01-01T00:00:00Z"
        }
        
        # Attempt to validate the invalid data - should return original data
        result = validate_response(data, PriceData)
        assert result == data

class TestMakeApiRequest:
    """Tests for the make_api_request function."""
    
    @patch('httpx.get')
    def test_make_api_request_default(self, mock_get):
        """Test make_api_request with default parameters."""
        # Configure the mock to return a successful response
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": "test_data"}
        mock_get.return_value = mock_response
        
        # Call the function with endpoint and params
        result = make_api_request("test_endpoint", params={"param1": "value1"})
        
        # Check that httpx.get was called correctly
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert "test_endpoint" in args[0]
        assert kwargs["params"] == {"param1": "value1"}
        assert "headers" in kwargs
        
        # Check the result
        assert result == {"data": "test_data"}
    
    @patch('httpx.get')
    def test_make_api_request_custom_version(self, mock_get):
        """Test make_api_request with custom API version."""
        # Configure the mock to return a successful response
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": "test_data"}
        mock_get.return_value = mock_response
        
        # Call the function with endpoint, params, and custom version
        result = make_api_request(
            "test_endpoint", 
            params={"param1": "value1"}, 
            version="v1"
        )
        
        # Check that httpx.get was called correctly
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert "test_endpoint" in args[0]
        assert kwargs["params"] == {"param1": "value1"}
        
        # Check the result
        assert result == {"data": "test_data"}
    
    @patch('httpx.get')
    def test_make_api_request_with_endpoint_suffix(self, mock_get):
        """Test make_api_request with endpoint suffix."""
        # Configure the mock to return a successful response
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": "test_data"}
        mock_get.return_value = mock_response
        
        # Call the function with endpoint, params, and endpoint_suffix
        result = make_api_request(
            "test_endpoint", 
            params={"param1": "value1"}, 
            endpoint_suffix="latest"
        )
        
        # Check that httpx.get was called correctly
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert "https://api.taostats.io/api/test_endpoint/v1/latest" == args[0]
        assert kwargs["params"] == {"param1": "value1"}
        
        # Check the result
        assert result == {"data": "test_data"}
    
    @patch('httpx.get')
    def test_make_api_request_error_response(self, mock_get):
        """Test make_api_request with error response."""
        # Create proper mock request and response objects
        mock_request = MagicMock()
        mock_request.url = "https://api.taostats.io/api/v1/test_endpoint"
        mock_request.method = "GET"
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.request = mock_request
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Client error '404 Not Found' for url 'https://api.taostats.io/api/v1/test_endpoint?param1=value1'",
            request=mock_request,
            response=mock_response
        )
        
        # Configure get mock
        mock_get.return_value = mock_response
        
        # Call the function and expect it to return empty data instead of raising an error
        result = make_api_request("test_endpoint", params={"param1": "value1"})
        
        # Check that we got an empty data response, not an exception
        assert result == {"data": []} 