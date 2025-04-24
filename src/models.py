from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Dict, List, Optional, Union, Any, Literal
from datetime import datetime

# Pydantic models for validation
class PriceData(BaseModel):
    """Model for price data."""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    name: Optional[str] = None
    symbol: str
    slug: Optional[str] = None
    circulating_supply: Optional[str] = None
    max_supply: Optional[str] = None
    total_supply: Optional[str] = None
    last_updated: Optional[str] = None
    price: float
    volume_24h: Optional[float] = None
    market_cap: Optional[float] = None
    percent_change_1h: Optional[str] = None
    percent_change_24h: Optional[str] = None
    percent_change_7d: Optional[str] = None
    percent_change_30d: Optional[str] = None
    percent_change_60d: Optional[str] = None
    percent_change_90d: Optional[str] = None
    market_cap_dominance: Optional[str] = None
    fully_diluted_market_cap: Optional[str] = None
    
    @field_validator('price')
    @classmethod
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Price must be positive')
        return v
        
class PriceHistoryPoint(BaseModel):
    """Model for a single price history data point."""
    created_at: str
    updated_at: str
    name: str
    symbol: str
    slug: str
    circulating_supply: str
    max_supply: str
    total_supply: str
    last_updated: str
    price: float
    volume_24h: float
    market_cap: float
    percent_change_1h: str
    percent_change_24h: str
    percent_change_7d: str
    percent_change_30d: str
    percent_change_60d: str
    percent_change_90d: str
    market_cap_dominance: str
    fully_diluted_market_cap: str

class PriceHistoryData(BaseModel):
    """Model for price history data."""
    data: List[PriceHistoryPoint]
    
    @field_validator('data')
    @classmethod
    def data_must_not_be_empty(cls, v):
        if not v:
            raise ValueError('Price history data cannot be empty')
        return v

class NetworkSummaryData(BaseModel):
    """Model for network summary data."""
    total_issuance: str
    total_stake: str
    difficulty: float
    network_immunity: float
    registrations_per_block: float
    burn_rate: float
    tao_market_cap: Optional[float] = None
    tao_price: Optional[float] = None
    active_validators: int
    validator_count: int
    subnet_count: int

class BlockData(BaseModel):
    """Model for block data."""
    block_number: int
    hash: str
    parent_hash: str
    state_root: str
    extrinsics_root: str
    spec_name: str
    spec_version: int
    impl_name: str
    impl_version: int
    timestamp: str
    validator: Optional[str] = None
    events_count: int
    extrinsics_count: int
    calls_count: int
    
    @field_validator('block_number')
    @classmethod
    def block_number_must_be_positive(cls, v):
        if v < 0:
            raise ValueError('Block number must be non-negative')
        return v

class SubnetData(BaseModel):
    """Model for subnet data."""
    netuid: int
    name: Optional[str] = None
    subnet_owner: str
    max_allowed_validators: int
    min_allowed_weights: int
    immunity_period: int
    validator_count: int
    tempo: int
    total_stake: str
    emission_value: str
    
    @field_validator('netuid')
    @classmethod
    def netuid_must_be_non_negative(cls, v):
        if v < 0:
            raise ValueError('Subnet ID must be non-negative')
        return v

class ValidatorData(BaseModel):
    """Model for validator data."""
    hotkey: str
    coldkey: str
    stake: str
    total_stake: str
    validator_permits: Optional[List[int]] = None
    nominator_permits: Optional[List[int]] = None
    validator_trust: Optional[float] = None
    nominator_trust: Optional[float] = None
    incentive: Optional[float] = None
    consensus: Optional[float] = None
    dividends: Optional[float] = None
    emission: Optional[float] = None
    is_validator: bool = False
    is_nominator: bool = False
    subnets: Optional[List[int]] = None

    @field_validator('hotkey', 'coldkey')
    @classmethod
    def validate_address_format(cls, v):
        if not v.startswith('5'):  # Basic check for Substrate address format
            raise ValueError('Invalid SS58 address format')
        return v

class EVMAddressData(BaseModel):
    """Model for EVM address data."""
    address: str
    balance: str
    transactions: int
    last_transaction_timestamp: Optional[str] = None
    transfer_history: Optional[List[Dict[str, Any]]] = None

    @field_validator('address')
    @classmethod
    def validate_eth_address(cls, v):
        if not v.startswith('0x') or len(v) != 42:
            raise ValueError('Invalid Ethereum address format')
        return v

class AccountAddress(BaseModel):
    """Model for account address with ss58 and hex formats."""
    ss58: str
    hex: str
    
    @field_validator('ss58')
    @classmethod
    def validate_ss58_address(cls, v):
        if not v.startswith('5'):  # Basic check for Substrate address format
            raise ValueError('Invalid SS58 address format')
        return v
    
    @field_validator('hex')
    @classmethod
    def validate_hex_address(cls, v):
        if not v.startswith('0x'):
            raise ValueError('Invalid hex address format')
        return v

class AccountInfoData(BaseModel):
    """Model for detailed account information."""
    address: AccountAddress
    network: str
    block_number: int
    timestamp: str
    rank: int
    balance_free: str
    balance_staked: str
    balance_staked_alpha_as_tao: str
    balance_staked_root: str
    balance_total: str
    balance_free_24hr_ago: Optional[str] = None
    balance_staked_24hr_ago: Optional[str] = None
    balance_staked_alpha_as_tao_24hr_ago: Optional[str] = None
    balance_staked_root_24hr_ago: Optional[str] = None
    balance_total_24hr_ago: Optional[str] = None
    created_on_date: str
    created_on_network: str
    coldkey_swap: Optional[str] = None

class AccountsListResponse(BaseModel):
    """Model for list of accounts response."""
    data: List[AccountInfoData]

class AccountHistoryData(BaseModel):
    """Model for account history data point."""
    address: AccountAddress
    network: str
    block_number: int
    timestamp: str
    rank: int
    balance_free: str
    balance_staked: str
    balance_staked_alpha_as_tao: str
    balance_staked_root: str
    balance_total: str
    created_on_date: str
    created_on_network: str
    coldkey_swap: Optional[str] = None

class AccountHistoryResponse(BaseModel):
    """Model for account history response."""
    data: List[AccountHistoryData]

class TransferData(BaseModel):
    """Model for new transfer data format."""
    id: str
    to: AccountAddress
    from_: AccountAddress = Field(..., alias="from")
    network: str
    block_number: int
    timestamp: str
    amount: str
    fee: str
    transaction_hash: str
    extrinsic_id: str

    @field_validator('amount', 'fee')
    @classmethod
    def amount_must_be_non_negative(cls, v):
        if float(v) < 0:
            raise ValueError('Amount must be non-negative')
        return v

class TransfersListResponse(BaseModel):
    """Model for transfers list response."""
    data: List[TransferData]

class Exchange(BaseModel):
    """Model for exchange data."""
    coldkey: AccountAddress
    name: str
    icon: Optional[str] = None

class ExchangeListResponse(BaseModel):
    """Model for exchanges list response."""
    data: List[Exchange]

class ErrorResponse(BaseModel):
    """Model for error responses."""
    error: str
    details: Optional[str] = None

class NetworkStatsData(BaseModel):
    """Model for network statistics data."""
    block_number: int
    timestamp: str
    issued: str
    staked: str
    accounts: int
    active_accounts: Optional[int] = None
    balance_holders: int
    active_balance_holders: Optional[int] = None
    extrinsics: int
    transfers: int
    subnets: int
    subnet_registration_cost: str

class NetworkStatsListData(BaseModel):
    """Model for network statistics list response."""
    data: List[NetworkStatsData]

class RuntimeVersionData(BaseModel):
    """Model for network runtime version data."""
    version: str
    spec_name: str
    spec_version: int
    impl_version: int
    transaction_version: int
    state_version: int
    timestamp: str

class ExtrinsicErrorData(BaseModel):
    """Model for extrinsic error data."""
    extra_info: Optional[str] = None
    name: str
    pallet: str

class ExtrinsicSignatureAddressData(BaseModel):
    """Model for extrinsic signature address data."""
    __kind: str
    value: str

class ExtrinsicSignatureData(BaseModel):
    """Model for extrinsic signature data."""
    __kind: str
    value: str

class ExtrinsicSignatureExtensionsData(BaseModel):
    """Model for extrinsic signature extensions data."""
    chargeTransactionPayment: str
    checkMetadataHash: Dict[str, Any]
    checkMortality: Dict[str, Any]
    checkNonce: int

class ExtrinsicSignatureInfoData(BaseModel):
    """Model for complete extrinsic signature information."""
    address: ExtrinsicSignatureAddressData
    signature: ExtrinsicSignatureData
    signedExtensions: ExtrinsicSignatureExtensionsData

class ExtrinsicData(BaseModel):
    """Model for extrinsic data."""
    timestamp: str
    block_number: int
    hash: str
    id: str
    index: int
    version: int
    signature: Optional[ExtrinsicSignatureInfoData] = None
    signer_address: Optional[str] = None
    tip: Optional[str] = None
    fee: Optional[str] = None
    success: bool
    error: Optional[ExtrinsicErrorData] = None
    call_id: str
    full_name: str
    call_args: Dict[str, Any]

class ExtrinsicsListData(BaseModel):
    """Model for extrinsics list response."""
    data: List[ExtrinsicData]

class CallData(BaseModel):
    """Model for call data."""
    hash: str
    block_num: int
    index: int
    module: str
    call: str
    args: Dict[str, Any]
    success: bool
    timestamp: str

class ProxyCallData(BaseModel):
    """Model for proxy call data."""
    hash: str
    block_num: int
    real: str
    proxy: str
    call_hash: str
    module: str
    call: str
    args: Dict[str, Any]
    success: bool
    timestamp: str
    
    @field_validator('real', 'proxy')
    @classmethod
    def validate_address_format(cls, v):
        if not v.startswith('5'):
            raise ValueError('Invalid SS58 address format')
        return v

class EventArgInfo(BaseModel):
    """Model for event argument information with nested __kind structures."""
    # Using a simple Dict instead of __root__ for Pydantic v2 compatibility
    class Config:
        extra = "allow"

class EventData(BaseModel):
    """Model for blockchain event data."""
    id: str
    extrinsic_index: int
    index: int
    phase: str
    pallet: str
    name: str
    full_name: str
    args: Union[Dict[str, Any], List[Any]]
    block_number: int
    extrinsic_id: str
    call_id: Optional[str] = None
    timestamp: str

class EventsListData(BaseModel):
    """Model for events list response."""
    data: List[EventData]

class TradingViewData(BaseModel):
    """Model for Trading View chart data."""
    symbol: str
    resolution: str
    c: List[float]  # Close prices
    h: List[float]  # High prices
    l: List[float]  # Low prices
    o: List[float]  # Open prices
    t: List[int]    # Timestamps
    v: List[float]  # Volumes
    s: str          # Status (e.g., "ok")

class PriceOHLCPoint(BaseModel):
    """Model for a single OHLC price data point."""
    period: str
    timestamp: str
    asset: str
    volume_24h: str
    open: str
    high: str
    low: str
    close: str

class PriceOHLCData(BaseModel):
    """Model for OHLC price data."""
    data: List[PriceOHLCPoint]
    
    @field_validator('data')
    @classmethod
    def data_must_not_be_empty(cls, v):
        if not v:
            raise ValueError('OHLC price data cannot be empty')
        return v

class TransactionData(BaseModel):
    """Model for transaction data."""
    hash: str
    block_num: int
    from_address: Optional[str] = None
    to_address: Optional[str] = None
    amount: Optional[str] = None
    module: str
    call: str
    success: bool
    timestamp: str

class WalletData(BaseModel):
    """Model for wallet data."""
    address: str
    balance: str
    transactions: List[Dict[str, Any]]
    stake: Optional[str] = None
    delegations: Optional[List[Dict[str, Any]]] = None
    rewards: Optional[List[Dict[str, Any]]] = None
    is_validator: bool = False
    is_delegator: bool = False

class ContractData(BaseModel):
    """Model for contract data."""
    address: str
    creator: Optional[str] = None
    creation_tx: Optional[str] = None
    creation_block: Optional[int] = None
    bytecode: str
    abi: Optional[List[Dict[str, Any]]] = None
    transactions: List[Dict[str, Any]]
    balance: str
    timestamp: str

class LogData(BaseModel):
    """Model for log data."""
    transaction_hash: str
    log_index: int
    address: str
    data: str
    topics: List[str]
    block_number: int
    timestamp: str

class BlocksListData(BaseModel):
    """Model for blocks list response."""
    data: List[BlockData] 