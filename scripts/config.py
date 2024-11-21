import os
import json
from web3 import Web3

ENDPOINTS = {
    "ARBITRUM": os.getenv('ARBITRUM_ENDPOINT'),
    "AVALANCHE": os.getenv('AVALANCHE_ENDPOINT'),
    "BASE": os.getenv('BASE_ENDPOINT'),
    "BSC": os.getenv('BSC_ENDPOINT'),
    "ETHEREUM": os.getenv('ETHEREUM_ENDPOINT'),
    "FANTOM": os.getenv('FANTOM_ENDPOINT'),
    "HARMONY": os.getenv('HARMONY_ENDPOINT'),
    "MANTLE": os.getenv('MANTLE_ENDPOINT'),
    "OPTIMISM": os.getenv('OPTIMISM_ENDPOINT'),
    "POLYGON": os.getenv('POLYGON_ENDPOINT')
}

WEBSOCKETS = { # Later, TODO: Add websockets that are commented out
    "ARBITRUM": os.getenv('ARBITRUM_WEBSOCKET'),
    # "AVALANCHE": os.getenv('AVALANCHE_WEBSOCKET'),
    "BASE": os.getenv('BASE_WEBSOCKET'),
    # "BSC": os.getenv('BSC_WEBSOCKET'),
    "ETHEREUM": os.getenv('ETHEREUM_WEBSOCKET'),
    "FANTOM": os.getenv('FANTOM_WEBSOCKET'),
    # "HARMONY": os.getenv('HARMONY_WEBSOCKET'),
    # "MANTLE": os.getenv('MANTLE_WEBSOCKET'),
    "OPTIMISM": os.getenv('OPTIMISM_WEBSOCKET'),
    "POLYGON": os.getenv('POLYGON_WEBSOCKET')
}

BLOCKSCANNERS = { #Later TODO: Add ones that are commented out
    "ARBITRUM": "arbiscan.io",
    # "AVALANCHE": "snowtrace.io",
    "BASE": "basescan.org",
    # "BSC": "bscscan.com",
    "ETHEREUM": "etherscan.io",
    "FANTOM": "ftmscan.com",
    # "HARMONY": "explorer.harmony.one",
    # "MANTLE": "mantlescan.info",
    "OPTIMISM": "optimistic.etherscan.io",
    "POLYGON": "polygonscan.com"
}

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

# region Chainlink
ETH_WEB3_INSTANCE = WEB3_INSTANCES['ETHEREUM']
CHAINLINK_ETH_USD_ADDRESS = ETH_WEB3_INSTANCE.to_checksum_address('0x5f4ec3df9cbd43714fe2740f5e3616155c5b8419')

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CHAINLINK_ABI_PATH = os.path.join(BASE_DIR, "config", "chainlink.abi.json")

with open(CHAINLINK_ABI_PATH, "r") as abi_file:
    CHAINLINK_ABI = json.load(abi_file)
    
CHAINLINK_CONTRACT = ETH_WEB3_INSTANCE.eth.contract(address=CHAINLINK_ETH_USD_ADDRESS, abi=CHAINLINK_ABI)
#endregion Chainlink