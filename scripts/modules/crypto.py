import os
import pytz
import json
import requests
import pandas as pd
import mplfinance as mpf
from decimal import Decimal
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

## Import the needed modules from the telegram library
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

## Import the needed modules from the config folder
# {config.py} - Environment variables and global variables used in the bot
# {utils.py} - Utility functions and variables used in the bot
# {firebase.py} - Firebase configuration and database initialization
from modules import config, utils, firebase
##

#region Crypto Logic
##
#
##
#region Chart
def fetch_ohlcv_data(time_frame, chain, liquidity_address):
    now = datetime.now()
    one_hour_ago = now - timedelta(hours=1)
    start_of_hour_timestamp = int(one_hour_ago.timestamp())
    chain_lowercase = chain.lower()
    if chain_lowercase == "ethereum":
        chain_lowercase = "eth"
    if chain_lowercase == "polygon":
        chain_lowercase = "polygon_pos"
    url = f"https://api.geckoterminal.com/api/v2/networks/{chain_lowercase}/pools/{liquidity_address}/ohlcv/{time_frame}" # TODO: REMOVE API
    params = {
        'aggregate': '1' + time_frame[0],  # '1m', '1h', '1d' depending on the time frame
        'before_timestamp': start_of_hour_timestamp,
        'limit': '60',  # Fetch only the last hour data
        'currency': 'usd'
    }
    print(f"Fetching OHLCV data from URL: {url} with params: {params}")
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        print("Failed to fetch data:", response.status_code, response.text)
        return None

def prepare_data_for_chart(ohlcv_data):
    ohlcv_list = ohlcv_data['data']['attributes']['ohlcv_list']
    data = [{
        'Date': pd.to_datetime(item[0], unit='s'),
        'Open': item[1],
        'High': item[2],
        'Low': item[3],
        'Close': item[4],
        'Volume': item[5]
    } for item in ohlcv_list]

    data_frame = pd.DataFrame(data)
    data_frame.sort_values('Date', inplace=True)
    data_frame.set_index('Date', inplace=True)
    return data_frame

def plot_candlestick_chart(data_frame, group_id):
    mc = mpf.make_marketcolors(
        up='#2dc60e',
        down='#ff0000',
        edge='inherit',
        wick='inherit',
        volume='inherit'
    )
    s = mpf.make_mpf_style(
        marketcolors=mc,
        rc={
            'font.size': 8,
            'axes.labelcolor': '#2dc60e',
            'axes.edgecolor': '#2dc60e',
            'xtick.color': '#2dc60e',
            'ytick.color': '#2dc60e',
            'grid.color': '#0f3e07',
            'grid.linestyle': '--',
            'figure.facecolor': 'black',
            'axes.facecolor': 'black'
        }
    )
    save_path = f'/tmp/candlestick_chart_{group_id}.png'
    mpf.plot(data_frame, type='candle', style=s, volume=True, savefig=save_path)
    print(f"Chart saved to {save_path}")
#endregion Chart
#
#region Buybot
MONITOR_INTERVAL = 20 # Interval for monitoring jobs (seconds)
scheduler = BackgroundScheduler()
def start_monitoring_groups():
    groups_snapshot = firebase.DATABASE.collection('groups').get()
    for group_doc in groups_snapshot:
        group_data = group_doc.to_dict()
        group_data['group_id'] = group_doc.id

        if group_data.get('premium', False):  # Check if premium is True
            schedule_group_monitoring(group_data)
        else:
            print(f"Group {group_data['group_id']} is not premium. Skipping monitoring.")

    scheduler.start()

def schedule_group_monitoring(group_data):
    group_id = str(group_data['group_id'])
    job_id = f"monitoring_{group_id}"
    token_info = group_data.get('token')

    if token_info:
        chain = token_info.get('chain')
        liquidity_address = token_info.get('liquidity_address')
        web3_instance = config.WEB3_INSTANCES.get(chain)

        if web3_instance and web3_instance.is_connected():
            existing_job = scheduler.get_job(job_id)  # Check for existing job with ID
            if existing_job:
                existing_job.remove()  # Remove existing job to update with new information

            scheduler.add_job(
                monitor_transfers,
                'interval',
                seconds=MONITOR_INTERVAL,
                args=[web3_instance, liquidity_address, group_data],
                id=job_id,  # Unique ID for the job
                timezone=pytz.utc  # Use the UTC timezone from the pytz library
            )
            print(f"Scheduled monitoring for premium group {group_id}")
        else:
            print(f"Web3 instance not connected for group {group_id} on chain {chain}")
    else:
        print(f"No token info found for group {group_id} - Not scheduling monitoring.")

def monitor_transfers(web3_instance, liquidity_address, group_data):
    abi_path = os.path.join(config.CONFIG_DIR, 'erc20.abi.json')

    with open(abi_path, 'r') as abi_file:
        abi = json.load(abi_file)
    
    contract_address = group_data['token']['contract_address']
    
    contract = web3_instance.eth.contract(address=contract_address, abi=abi)

    # Initialize static tracking of the last seen block
    if not hasattr(monitor_transfers, "last_seen_block"):
        lookback_range = 100 # Check the last block on boot
        monitor_transfers.last_seen_block = web3_instance.eth.block_number - lookback_range

    last_seen_block = monitor_transfers.last_seen_block
    latest_block = web3_instance.eth.block_number

    if last_seen_block >= latest_block:
        print(f"No new blocks to process for group {group_data['group_id']}.")
        return  # Exit if no new blocks

    print(f"Processing blocks {last_seen_block + 1} to {latest_block} for group {group_data['group_id']}")

    try:
        logs = contract.events.Transfer().get_logs( # Fetch Transfer events in the specified block range
            from_block=last_seen_block + 1,
            to_block=latest_block,
            argument_filters={'from': liquidity_address}
        )

        for log in logs: # Process each log
            handle_transfer_event(log, group_data)  # Pass the decoded log to your handler

        monitor_transfers.last_seen_block = latest_block # Update static last_seen_block

    except Exception as e:
        print(f"Error during transfer monitoring for group {group_data['group_id']}: {e}")

def handle_transfer_event(event, group_data):
    fetched_data, group_doc = utils.fetch_group_info(
        update=None,  # No update object is available in this context
        context=None,  # No context object is used here
        return_both=True,
        group_id=group_data['group_id']
    )

    if fetched_data is None:
        print(f"Failed to fetch group data for group ID {group_data['group_id']}.")
        return
    
    buybot_config = fetched_data.get('premium_features', {}).get('buybot', {})
    minimum_buy_amount = buybot_config.get('minimumbuy', 1000)  # Default to 1000 if not set
    small_buy_amount = buybot_config.get('smallbuy', 2500)  # Default to 2500 if not set
    medium_buy_amount = buybot_config.get('mediumbuy', 5000) # Default to 5000

    amount = event['args']['value']
    tx_hash = event['transactionHash'].hex()

    if not tx_hash.startswith("0x"):
        tx_hash = "0x" + tx_hash

    decimals = group_data['token'].get('decimals', 18)  # Convert amount to token decimal
    token_amount = Decimal(amount) / (10 ** decimals)

    print(f"Received transfer event for {token_amount} tokens.")
    print(f"Transaction hash: {tx_hash}")
    
    chain = group_data['token']['chain'] # Fetch the USD price of the token using Uniswap V3 and Chainlink1
    lp_address = group_data['token']['liquidity_address']
    token_price_in_usd = get_token_price_in_usd(chain, lp_address)

    if token_price_in_usd is not None:
        token_price_in_usd = Decimal(token_price_in_usd)
        total_value_usd = token_amount * token_price_in_usd
        if total_value_usd < minimum_buy_amount:
            print(f"Ignoring small buy below the minimum threshold: ${total_value_usd:.2f}")
            return  # Ignore small buy events
        value_message = f" (${total_value_usd:.2f})"
        header_emoji, buyer_emoji = categorize_buyer(total_value_usd, small_buy_amount, medium_buy_amount)
    else:
        print("Failed to fetch token price in USD.")
        return

    token_name = group_data['token'].get('symbol', 'TOKEN')
    blockscanner = config.BLOCKSCANNERS.get(chain.upper())
    
    if blockscanner:
        transaction_link = f"https://{blockscanner}/tx/{tx_hash}"
        message = (
            f"{header_emoji} BUY ALERT {header_emoji}\n\n"
            f"{buyer_emoji} {token_amount:,.4f} {token_name}{value_message}"
        )
        print(f"Sending buy message with transaction link for group {group_data['group_id']}")

        keyboard = [[InlineKeyboardButton("View Transaction", url=transaction_link)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        send_buy_message(message, group_data['group_id'], reply_markup)
    else:
        message = ( # Fallback message when blockscanner is unknown
            f"{header_emoji} BUY ALERT {header_emoji}\n\n"
            f"{buyer_emoji} {token_amount:.4f} {token_name}{value_message}\n\n"
            f"Transaction hash: {tx_hash}"
        )
        print(f"Sending fallback buy message for group {group_data['group_id']}")
        send_buy_message(message, group_data['group_id'])

def categorize_buyer(usd_value, small_buy, medium_buy):
    if usd_value < small_buy:
        return "💸", "🐟"
    elif usd_value < medium_buy:
        return "💰", "🐬"
    else:
        return "🤑", "🐳"
    
def send_buy_message(text, group_id, reply_markup=None):
    msg = None
    bot = telegram.Bot(token=config.TELEGRAM_TOKEN)
    group_data = utils.fetch_group_info(None, None, group_id)
    
    if not utils.rate_limit_check(group_id):
        msg = bot.send_message(chat_id=group_id, text="Bot rate limit exceeded. Please try again later.")
        return
    
    try:
        if group_data and group_data.get('premium') and group_data.get('premium_features', {}).get('buybot_header'):
            buybot_header_url = group_data['premium_features'].get('buybot_header_url')

            if not buybot_header_url:
                print(f"No buybot header URL found for group {group_id}. Sending message without media.")

            print(f"Group {group_id} has premium features enabled, and has a buybot header uploaded... Determining media type.")
            
            if buybot_header_url.endswith('.gif') or buybot_header_url.endswith('.mp4'):
                msg = bot.send_animation(
                    chat_id=group_id,
                    animation=buybot_header_url,
                    caption=text,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
                print(f"Sending buybot message as animation for group {group_id}.")
            else:
                msg = bot.send_photo(
                    chat_id=group_id,
                    photo=buybot_header_url,
                    caption=text,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
                print(f"Sending buybot message as photo for group {group_id}.")
        else: # Default behavior: send as text-only message
            print(f"Group {group_id} does not have premium features or buybot header enabled. Sending message without media.")
            msg = bot.send_message(
                chat_id=group_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error sending message: {e}")

    if msg is not None:
        utils.track_message(msg)
#endregion Buybot
#
#region Price Fetching
def get_token_price_in_usd(chain, lp_address):
    try:
        eth_price_in_usd = check_eth_price() # Step 1: Get ETH price in USD using Chainlink
        if eth_price_in_usd is None:
            print("Failed to fetch ETH price from Chainlink.")
            return None

        pool_type = determine_pool_type(chain, lp_address)
        if pool_type not in ["v3", "v2"]:
            return None
        
        price_in_weth = get_uniswap_position_data(chain, lp_address, pool_type)

        if price_in_weth is None:
            print("Failed to fetch token price in WETH from Uniswap V3.")
            return None

        token_price_in_usd = price_in_weth * Decimal(eth_price_in_usd) # Step 3: Convert token price from WETH to USD
        print(f"Token price in USD: {token_price_in_usd}")
        return token_price_in_usd

    except Exception as e:
        print(f"Error fetching token price in USD: {e}")
        return None
    
def check_eth_price():
    try:
        latest_round_data = config.CHAINLINK_CONTRACT.functions.latestRoundData().call()
        price = latest_round_data[1] / 10 ** 8
        print(f"ETH price: ${price}")
        return price
    except Exception as e:
        print(f"Failed to get ETH price: {e}")
        return None

def determine_pool_type(chain, lp_address):
    try:
        web3_instance = config.WEB3_INSTANCES.get(chain)
        if not web3_instance:
            print(f"Web3 instance for chain {chain} not found or not connected.")
            return None
        
        abi_path = os.path.join(config.CONFIG_DIR, 'uniswap_v3.abi.json')
        with open(abi_path, 'r') as abi_file:
            abi = json.load(abi_file)

        address = web3_instance.to_checksum_address(lp_address)

        pair_contract = web3_instance.eth.contract(address=address, abi=abi)

        pair_contract.functions.slot0().call() # Attempt to call the slot0 function
        print("Pool is a Uniswap V3 pool.")
        return "v3"
    except Exception as e:
        if "execution reverted" in str(e) or "no data" in str(e):
            print("Pool is a Uniswap V2 pool.")
            return "v2"
        print(f"Error determining pool type: {e}")
        return None
    
def get_uniswap_position_data(chain, lp_address, pool_type):
    try:
        web3_instance = config.WEB3_INSTANCES.get(chain)
        if not web3_instance:
            print(f"Web3 instance for chain {chain} not found or not connected.")
            return None

        abi_path = os.path.join(config.CONFIG_DIR, f'uniswap_{pool_type}.abi.json')
        with open(abi_path, 'r') as abi_file:
            abi = json.load(abi_file)

        address = web3_instance.to_checksum_address(lp_address)
        pair_contract = web3_instance.eth.contract(address=address, abi=abi)

        erc20_abi_path = os.path.join(config.CONFIG_DIR, 'erc20.abi.json')
        with open(erc20_abi_path, 'r') as erc20_abi_file:
            erc20_abi = json.load(erc20_abi_file)

        if pool_type == "v2":
            reserves = pair_contract.functions.getReserves().call()
            reserve0 = Decimal(reserves[0])
            reserve1 = Decimal(reserves[1])
            print(f"Raw reserves: reserve0={reserve0}, reserve1={reserve1}")

            token0_address = pair_contract.functions.token0().call()
            token1_address = pair_contract.functions.token1().call()

            token0_contract = web3_instance.eth.contract(address=token0_address, abi=erc20_abi)
            token1_contract = web3_instance.eth.contract(address=token1_address, abi=erc20_abi)
            decimals0 = token0_contract.functions.decimals().call()
            decimals1 = token1_contract.functions.decimals().call()

            print(f"Token0 decimals: {decimals0}, Token1 decimals: {decimals1}")

            weth_address = config.WETH_ADDRESSES.get(chain).lower()
            print(f"WETH address on {chain}: {weth_address}")

            
            if token0_address.lower() == weth_address:
                reserve_weth = reserve0 / (10 ** decimals0)
                reserve_token = reserve1 / (10 ** decimals1)
            elif token1_address.lower() == weth_address:
                reserve_weth = reserve1 / (10 ** decimals1)
                reserve_token = reserve0 / (10 ** decimals0)
            else:
                print("Neither token0 nor token1 is WETH. Unable to calculate price.")
                return None

            print(f"Adjusted reserves: reserve_token={reserve_token}, reserve_weth={reserve_weth}")

            price_in_weth = reserve_weth / reserve_token # Calculate token price in WETH
            print(f"Token price in WETH (Uniswap V2): {price_in_weth:.18f}")
            return price_in_weth
        if pool_type == "v3":
            slot0 = pair_contract.functions.slot0().call()  # Fetch slot0 data (contains sqrtPriceX96)
            sqrt_price_x96 = slot0[0]
            print(f"Raw sqrtPriceX96: {sqrt_price_x96}")

            token0_address = pair_contract.functions.token0().call()
            token1_address = pair_contract.functions.token1().call()

            token0_contract = web3_instance.eth.contract(address=token0_address, abi=erc20_abi)
            token1_contract = web3_instance.eth.contract(address=token1_address, abi=erc20_abi)
            decimals0 = token0_contract.functions.decimals().call()
            decimals1 = token1_contract.functions.decimals().call()

            print(f"Token0 decimals: {decimals0}, Token1 decimals: {decimals1}")

            sqrt_price_x96_decimal = Decimal(sqrt_price_x96) # Adjust sqrtPriceX96 for price calculation
            price_in_weth = (sqrt_price_x96_decimal ** 2) / Decimal(2 ** 192)

            weth_address = config.WETH_ADDRESSES.get(chain).lower()
            print(f"WETH address on {chain}: {weth_address}")

            if token1_address.lower() == weth_address: # If token1 is WETH; price_in_weth is already correct
                price_in_weth_adjusted = price_in_weth * (10 ** (decimals0 - decimals1))
                print(f"Price of token0 in WETH: {price_in_weth_adjusted:.18f}")
            elif token0_address.lower() == weth_address: # If token0 is WETH; invert the price
                price_in_weth_adjusted = (1 / price_in_weth) * (10 ** (decimals1 - decimals0))
                print(f"Price of token1 in WETH: {price_in_weth_adjusted:.18f}")
            else:
                print("Neither token0 nor token1 is WETH. Unable to calculate price.")
                return None
            return price_in_weth_adjusted
        
    except Exception as e:
        print(f"Error fetching Uniswap {pool_type} reserves: {e}")
        return None
#endregion Price Fetching
##
#
##
#endregion Crypto Logic