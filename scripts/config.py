import os
import re
import json
from web3 import Web3

#region Global Variables
TELEGRAM_TOKEN = os.getenv('BOT_API_TOKEN')

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')

BOT_USERNAME = "sypher_robot"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MATH_0 = int(os.getenv("MATH_0"))
MATH_1 = int(os.getenv("MATH_1"))
MATH_2 = int(os.getenv("MATH_2"))
MATH_3 = int(os.getenv("MATH_3"))
MATH_4 = int(os.getenv("MATH_4"))

WORD_0 = os.getenv("WORD_0")
WORD_1 = os.getenv("WORD_1")
WORD_2 = os.getenv("WORD_2")
WORD_3 = os.getenv("WORD_3")
WORD_4 = os.getenv("WORD_4")
WORD_5 = os.getenv("WORD_5")
WORD_6 = os.getenv("WORD_6")
WORD_7 = os.getenv("WORD_7")
WORD_8 = os.getenv("WORD_8")

RELAXED_TRUST = int(os.getenv('RELAXED_TRUST'))
MODERATE_TRUST = int(os.getenv('MODERATE_TRUST'))
STRICT_TRUST = int(os.getenv('STRICT_TRUST'))

ETH_ADDRESS_PATTERN = re.compile(r'\b0x[a-fA-F0-9]{40}\b')
URL_PATTERN = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
DOMAIN_PATTERN = re.compile(r'\b[\w\.-]+\.[a-zA-Z]{2,}\b')

BOT_RATE_LIMIT_MESSAGE_COUNT = 100  # Maximum number of allowed commands per {TIME_PERIOD}
BOT_RATE_LIMIT_TIME_PERIOD = 60  # Time period in (seconds)
GROUP_RATE_LIMIT_MESSAGE_COUNT = 25  # Maximum number of allowed commands per {TIME_PERIOD} per group
GROUP_RATE_LIMIT_TIME_PERIOD = 15  # Time period in (seconds) per group

ENDPOINTS = {
    "ARBITRUM": os.getenv('ARBITRUM_ENDPOINT'),
    "AVALANCHE": os.getenv('AVALANCHE_ENDPOINT'),
    "BASE": os.getenv('BASE_ENDPOINT'),
    "BSC": os.getenv('BSC_ENDPOINT'),
    "ETHEREUM": os.getenv('ETHEREUM_ENDPOINT'),
    "FANTOM": os.getenv('FANTOM_ENDPOINT'),
    "OPTIMISM": os.getenv('OPTIMISM_ENDPOINT'),
    "POLYGON": os.getenv('POLYGON_ENDPOINT')
}
WEBSOCKETS = {
    "ARBITRUM": os.getenv('ARBITRUM_WEBSOCKET'),
    "AVALANCHE": os.getenv('AVALANCHE_WEBSOCKET'),
    "BASE": os.getenv('BASE_WEBSOCKET'),
    "BSC": os.getenv('BSC_WEBSOCKET'),
    "ETHEREUM": os.getenv('ETHEREUM_WEBSOCKET'),
    "FANTOM": os.getenv('FANTOM_WEBSOCKET'),
    "OPTIMISM": os.getenv('OPTIMISM_WEBSOCKET'),
    "POLYGON": os.getenv('POLYGON_WEBSOCKET')
}
BLOCKSCANNERS = {
    "ARBITRUM": "arbiscan.io",
    "AVALANCHE": "snowtrace.io",
    "BASE": "basescan.org",
    "BSC": "bscscan.com",
    "ETHEREUM": "etherscan.io",
    "FANTOM": "ftmscan.com",
    "OPTIMISM": "optimistic.etherscan.io",
    "POLYGON": "polygonscan.com"
}
WETH_ADDRESSES = {
    "ARBITRUM": "0x82af49447d8a07e3bd95bd0d56f35241523fbab1",
    "BASE": "0x4200000000000000000000000000000000000006",
    "ETHEREUM": "0xC02aaa39b223FE8D0A0E5C4F27eAD9083C756Cc2",
    "OPTIMISM": "0x4200000000000000000000000000000000000006",
    "POLYGON": "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619"
}
NATIVE_TOKENS = {
    # "AVALANCHE": "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7", # TODO: Determine if WAVAX works as WETH
    # "BSC": "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c", # TODO: Determine if WBNB works as WETH
    # "FANTOM": "0x21be370d5312f44cb42ce377bc9b8a0cef1a4c83", # TODO: Determine if WFTM works as WETH
    # "MANTLE": "0x78c1b0C915c4FAA5FffA6CAbf0219DA63d7f4cb8", # TODO: Determine if WMNT works as WETH
}
#endregion Global Variables
##
#
##
#region Web3 Initialization
WEB3_INSTANCES = {network: Web3(Web3.HTTPProvider(endpoint)) for network, endpoint in ENDPOINTS.items()}
for network, web3_instance in WEB3_INSTANCES.items():
    if web3_instance.is_connected():
        print(f"Successfully connected to {network}")
    else:
        print(f"Failed to connect to {network}")

WEB3_WEBSOCKETS = {network: Web3(Web3.LegacyWebSocketProvider(endpoint)) for network, endpoint in WEBSOCKETS.items()}
for network, web3_instance in WEB3_WEBSOCKETS.items():
    if web3_instance.is_connected():
        print(f"Successfully connected to {network} via WebSocket")
    else:
        print(f"Failed to connect to {network} via WebSocket")
#endregion Web3 Initialization
##
#
##
#region Chainlink
ETH_WEB3_INSTANCE = WEB3_INSTANCES['ETHEREUM']
CHAINLINK_ETH_USD_ADDRESS = ETH_WEB3_INSTANCE.to_checksum_address('0x5f4ec3df9cbd43714fe2740f5e3616155c5b8419')

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CHAINLINK_ABI_PATH = os.path.join(BASE_DIR, "config", "chainlink.abi.json")

with open(CHAINLINK_ABI_PATH, "r") as abi_file:
    CHAINLINK_ABI = json.load(abi_file)
    
CHAINLINK_CONTRACT = ETH_WEB3_INSTANCE.eth.contract(address=CHAINLINK_ETH_USD_ADDRESS, abi=CHAINLINK_ABI)
#endregion Chainlink