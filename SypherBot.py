import os
import re
import time
import pytz
import json
import random
import requests
import telegram
import threading
import pandas as pd
import firebase_admin
import mplfinance as mpf
from web3 import Web3
from io import BytesIO
from decimal import Decimal
from functools import partial
from threading import Timer, Thread
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from collections import deque, defaultdict
from google.cloud.firestore_v1 import DELETE_FIELD
from firebase_admin import credentials, firestore, storage
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Bot, ChatMember
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters, CallbackQueryHandler, JobQueue

#
## This is the public version of the bot that was developed by Tukyo Games for the deSypher project.
## This bot has a customizable commands feature, and admin controls. Along with full charting, price and buybot functionality.
## You may also set a custom contract address for the token you want to track, all other contracts will be blocked in your chat if enabled.
# 
## https://desypher.net/
#
## Commands
### /start - Start the bot
### /commands - Get a list of commands
### /play - Start a mini-game of deSypher within Telegram
### /endgame - End your current game
### /contract /ca - Contract address for the SYPHER token
### /report - Report a message to group admins
### /save - Save a message to your DMs
## CUSTOM COMMANDS
### The rest of the commands you can create yourself. Use /createcommand to create a new command.
#
## Ethereum Commands
### /price - Get the price of the SYPHER token in USD
### /chart - Links to the token chart on various platforms
### /liquidity /lp - View the liquidity value of the SYPHER V3 pool
### /volume - 24-hour trading volume of the SYPHER token
#
## Admin Commands
### /admincommands - Get a list of admin commands
### /createcommand - Create a new command
### /cleanbot - Clean all bot messages in the chat
### /cleargames - Clear all active games in the chat
### /mute /unmute - Reply to a message with this command to toggle mute for a user
### /kick - Reply to a message with this command to kick a user from the chat
### /warn - Reply to a message with this command to warn a user
### /filter - Filter a word or phrase from the chat
### /removefilter - Remove a word or phrase from the filter list
### /filterlist - Get a list of filtered words
#

load_dotenv()

TELEGRAM_TOKEN = os.getenv('BOT_API_TOKEN')

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

endpoints = {
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

web3_instances = {network: Web3(Web3.HTTPProvider(endpoint)) for network, endpoint in endpoints.items()}

for network, web3_instance in web3_instances.items():
    if web3_instance.is_connected():
        print(f"Successfully connected to {network}")
    else:
        print(f"Failed to connect to {network}")

eth_web3 = web3_instances['ETHEREUM']
chainlink_address = eth_web3.to_checksum_address('0x5f4ec3df9cbd43714fe2740f5e3616155c5b8419')

chainlink_abi = """
    [
        {
            "inputs": [],
            "name": "latestRoundData",
            "outputs": [
                {"name": "roundId", "type": "uint80"},
                {"name": "answer", "type": "int256"},
                {"name": "startedAt", "type": "uint256"},
                {"name": "updatedAt", "type": "uint256"},
                {"name": "answeredInRound", "type": "uint80"}
            ],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    """
chainlink_contract = eth_web3.eth.contract(address=chainlink_address, abi=chainlink_abi)

def check_eth_price(update, context):
    try:
        latest_round_data = chainlink_contract.functions.latestRoundData().call()
        price = latest_round_data[1] / 10 ** 8
        print(f"ETH price: {price}")
        return price
    except Exception as e:
        print(f"Failed to get ETH price: {e}")
        return None

#region Firebase
FIREBASE_TYPE= os.getenv('FIREBASE_TYPE')
FIREBASE_PROJECT_ID = os.getenv('FIREBASE_PROJECT_ID')
FIREBASE_PRIVATE_KEY_ID= os.getenv('FIREBASE_PRIVATE_KEY_ID')
FIREBASE_PRIVATE_KEY = os.getenv('FIREBASE_PRIVATE_KEY').replace('\\n', '\n')
FIREBASE_CLIENT_EMAIL= os.getenv('FIREBASE_CLIENT_EMAIL')
FIREBASE_CLIENT_ID= os.getenv('FIREBASE_CLIENT_ID')
FIREBASE_AUTH_URL= os.getenv('FIREBASE_AUTH_URL')
FIREBASE_TOKEN_URI= os.getenv('FIREBASE_TOKEN_URI')
FIREBASE_AUTH_PROVIDER_X509_CERT_URL= os.getenv('FIREBASE_AUTH_PROVIDER_X509_CERT_URL')
FIREBASE_CLIENT_X509_CERT_URL= os.getenv('FIREBASE_CLIENT_X509_CERT_URL')
FIREBASE_STORAGE_BUCKET = os.getenv('FIREBASE_STORAGE_BUCKET')

cred = credentials.Certificate({
    "type": FIREBASE_TYPE,
    "project_id": FIREBASE_PROJECT_ID,
    "private_key_id": FIREBASE_PRIVATE_KEY_ID,
    "private_key": FIREBASE_PRIVATE_KEY,
    "client_email": FIREBASE_CLIENT_EMAIL,
    "client_id": FIREBASE_CLIENT_ID,
    "auth_uri": FIREBASE_AUTH_URL,
    "token_uri": FIREBASE_TOKEN_URI,
    "auth_provider_x509_cert_url": FIREBASE_AUTH_PROVIDER_X509_CERT_URL,
    "client_x509_cert_url": FIREBASE_CLIENT_X509_CERT_URL
})

firebase_admin.initialize_app(cred, {
    'storageBucket': FIREBASE_STORAGE_BUCKET
})

db = firestore.client()
bucket = storage.bucket()

print("Database: ", db)
print("Bucket: ", bucket)
print("Firebase initialized.")
#endregion Firebase

#region Classes
class AntiSpam:
    def __init__(self, rate_limit, time_window):
        self.rate_limit = rate_limit
        self.time_window = time_window
        self.user_messages = defaultdict(list)
        self.blocked_users = defaultdict(lambda: 0)
        print(f"Initialized AntiSpam with rate_limit={rate_limit}, time_window={time_window}")

    def is_spam(self, user_id, chat_id):
        current_time = time.time()
        key = (user_id, chat_id)
        if current_time < self.blocked_users[key]:
            return True
        self.user_messages[key] = [msg_time for msg_time in self.user_messages[key] if current_time - msg_time < self.time_window]
        self.user_messages[key].append(current_time)
        if len(self.user_messages[key]) > self.rate_limit:
            self.blocked_users[key] = current_time
            print(f"User {user_id} in chat {chat_id} is blocked until {self.blocked_users[key]}")
            return True
        return False

class AntiRaid:
    def __init__(self, user_amount, time_out, anti_raid_time):
        self.user_amount = user_amount
        self.time_out = time_out
        self.anti_raid_time = anti_raid_time
        self.join_times = deque()
        self.anti_raid_end_time = 0
        print(f"Initialized AntiRaid with user_amount={user_amount}, time_out={time_out}, anti_raid_time={anti_raid_time}")

    def is_raid(self):
        current_time = time.time()
        if current_time < self.anti_raid_end_time:
            return True

        self.join_times.append(current_time)
        print(f"User joined at time {current_time}. Join times: {list(self.join_times)}")
        while self.join_times and current_time - self.join_times[0] > self.time_out:
            self.join_times.popleft()

        if len(self.join_times) >= self.user_amount:
            self.anti_raid_end_time = current_time + self.anti_raid_time
            self.join_times.clear()
            print(f"Raid detected. Setting anti-raid end time to {self.anti_raid_end_time}. Cleared join times.")
            return True

        print(f"No raid detected. Current join count: {len(self.join_times)}")
        return False

    def time_to_wait(self):
        current_time = time.time()
        if current_time < self.anti_raid_end_time:
            return int(self.anti_raid_end_time - current_time)
        return 0
#endregion Classes

anti_spam = AntiSpam(rate_limit=5, time_window=10)
anti_raid = AntiRaid(user_amount=25, time_out=30, anti_raid_time=180)

scheduler = BackgroundScheduler()

eth_address_pattern = re.compile(r'\b0x[a-fA-F0-9]{40}\b')
url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
domain_pattern = re.compile(r'\b[\w\.-]+\.[a-zA-Z]{2,}\b')

RATE_LIMIT = 100  # Maximum number of allowed commands
TIME_PERIOD = 60  # Time period in seconds
last_check_time = time.time()
command_count = 0

bot_messages = []

def track_message(message):
    bot_messages.append((message.chat.id, message.message_id))
    print(f"Tracked message: {message.message_id}")

#region Bot Logic
def bot_added_to_group(update: Update, context: CallbackContext) -> None:
    new_members = update.message.new_chat_members
    inviter = update.message.from_user

    if any(member.id != context.bot.id for member in new_members):
        return  # Bot wasn't added

    group_id = update.effective_chat.id
    admins = context.bot.get_chat_administrators(group_id)  
    inviter_is_admin = any(admin.user.id == inviter.id for admin in admins)

    if inviter_is_admin:
        # Store group info only if the inviter is an admin
        owner_id = inviter.id
        owner_username = inviter.username
        print(f"Adding group {group_id} to database with owner {owner_id} ({owner_username})")
        group_doc = db.collection('groups').document(str(group_id))
        group_doc.set({
            'group_id': group_id,
            'owner_id': owner_id,
            'owner_username': owner_username,
            'premium': False,
            'premium_features':
            {
                'sypher_trust': False
            },
            'admin':
            {
                'mute': False,
                'warn': False,
                'max_warns': 3,
                'allowlist': False,
                'blocklist': False
            }
        })

        bot_member = context.bot.get_chat_member(group_id, context.bot.id)  # Get bot's member info

        if bot_member.status == "administrator":
            # Bot is admin, send the "Thank you" message
            setup_keyboard = [[InlineKeyboardButton("Setup", callback_data='setup_home')]]
            setup_markup = InlineKeyboardMarkup(setup_keyboard)
            msg = update.message.reply_text(
                "Thank you for adding me to your group! Please click 'Setup' to continue.",
                reply_markup=setup_markup
            )
            store_message_id(context, msg.message_id)
        else:
            # Bot is not admin, send the "Give me admin perms" message
            setup_keyboard = [[InlineKeyboardButton("Setup", callback_data='setup_home')]]
            setup_markup = InlineKeyboardMarkup(setup_keyboard)
            msg = update.message.reply_text(
                "Hey, please give me admin permissions, then click 'Setup' to get started.",
                reply_markup=setup_markup
            )
            store_message_id(context, msg.message_id)
 
        if msg is not None:
            track_message(msg)

def bot_removed_from_group(update: Update, context: CallbackContext) -> None:
    left_member = update.message.left_chat_member
    if left_member.id != context.bot.id:
        delete_service_messages(update, context)
    if left_member.id == context.bot.id:
        group_id = update.effective_chat.id
        print(f"Removing group {group_id} from database.")
        group_doc = db.collection('groups').document(str(group_id))
        group_doc.delete()
        delete_service_messages(update, context)

def start_monitoring_groups():
    groups_snapshot = db.collection('groups').get()
    for group_doc in groups_snapshot:
        group_data = group_doc.to_dict()
        group_data['group_id'] = group_doc.id
        print("Remove this code to start monitoring groups.")
        # schedule_group_monitoring(group_data)

    scheduler.start()

def schedule_group_monitoring(group_data):
    group_id = str(group_data['group_id'])
    job_id = f"monitoring_{group_id}"
    token_info = group_data.get('token')

    if token_info:
        chain = token_info.get('chain')
        liquidity_address = token_info.get('liquidity_address')
        web3_instance = web3_instances.get(chain)

        if web3_instance and web3_instance.is_connected():
            # Check for existing job with ID
            existing_job = scheduler.get_job(job_id)
            if existing_job:
                # Remove existing job to update with new information
                existing_job.remove()

            scheduler.add_job(
                monitor_transfers,
                'interval',
                seconds=10,
                args=[web3_instance, liquidity_address, group_data],
                id=job_id,  # Unique ID for the job
                timezone=pytz.utc  # Use the UTC timezone from the pytz library
            )

def is_user_admin(update: Update, context: CallbackContext) -> bool:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Check if the update has a callback_query
    if update.callback_query:
        user_id = update.callback_query.from_user.id
    else:
        user_id = update.effective_user.id

    if update.effective_chat.type == 'private':
        return False
    
    print(f"Checking if user is admin for chat {chat_id}")

    # Check if the user is an admin in this chat
    chat_admins = context.bot.get_chat_administrators(chat_id)
    user_is_admin = any(admin.user.id == user_id for admin in chat_admins)

    return user_is_admin

def is_user_owner(update: Update, context: CallbackContext, user_id: int) -> bool:
    chat_id = update.effective_chat.id

    if update.effective_chat.type == 'private':
        print("User is in a private chat.")
        return False
    
    print(f"Checking if user is owner for chat {chat_id}")

    # Retrieve the group document from the database
    group_doc = db.collection('groups').document(str(chat_id))
    group_data = group_doc.get().to_dict()

    # Check if the user is the owner of this group
    user_is_owner = group_data['owner_id'] == user_id

    print(f"UserID: {user_id} - OwnerID: {group_data['owner_id']} - IsOwner: {user_is_owner}")

    if not user_is_owner:
        print("User is not the owner of this group.")

    return user_is_owner

def fetch_group_info(update: Update, context: CallbackContext):
    if update.effective_chat.type == 'private':
        return None
    
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    try:
        doc_snapshot = group_doc.get()
        if doc_snapshot.exists:
            return doc_snapshot.to_dict()
        else:
            update.message.reply_text("Group data not found.")
    except Exception as e:
        update.message.reply_text(f"Failed to fetch group info: {str(e)}")
    
    return None

#region Message Handling
def rate_limit_check():
    global last_check_time, command_count
    current_time = time.time()

    # Reset count if time period has expired
    if current_time - last_check_time > TIME_PERIOD:
        command_count = 0
        last_check_time = current_time

    # Check if the bot is within the rate limit
    if command_count < RATE_LIMIT:
        command_count += 1
        return True
    else:
        return False

def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    username = update.message.from_user.username or update.message.from_user.first_name
    msg = None

    if is_user_admin(update, context):
        handle_setup_inputs_from_admin(update, context)
        handle_guess(update, context)
        return
    
    if update.effective_chat.type == 'private':
        handle_guess(update, context)
        return

    if anti_spam.is_spam(user_id, chat_id):
        handle_spam(update, context, chat_id, user_id, username)

    delete_blocked_addresses(update, context)
    delete_blocked_phrases(update, context)
    delete_blocked_links(update, context)

    handle_guess(update, context)
    
    if msg is not None:
        track_message(msg)

def handle_image(update: Update, context: CallbackContext) -> None:
    if is_user_admin(update, context):
        handle_setup_inputs_from_admin(update, context)
        return

    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    username = update.message.from_user.username or update.message.from_user.first_name
    msg = None

    if anti_spam.is_spam(user_id, chat_id):
        handle_spam(update, context, chat_id, user_id, username)

    if msg is not None:
        track_message(msg)

def handle_spam(update: Update, context: CallbackContext, chat_id, user_id, username) -> None:
    if user_id == context.bot.id:
        return

    # Mute the spamming user
    context.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=ChatPermissions(can_send_messages=False)
    )

    print(f"User {username} has been muted for spamming in chat {chat_id}.")

    group_id = update.message.chat.id
    group_doc = db.collection('groups').document(str(group_id))

    # Get the group document
    group_data = group_doc.get().to_dict()

    # Only send the message if the user is not in the unverified_users mapping
    if str(user_id) not in group_data.get('unverified_users', {}):
        auth_url = f"https://t.me/sypher_robot?start=authenticate_{chat_id}_{user_id}"
        keyboard = [
            [InlineKeyboardButton("Remove Restrictions", url=auth_url)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        context.bot.send_message(
            chat_id=chat_id,
            text=f"@{username}, you have been muted for spamming. Press the button below to re-authenticate.",
            reply_markup=reply_markup
        )

        current_time = datetime.now(timezone.utc).isoformat()  # Get the current date/time in ISO 8601 format
        user_data = {
            str(user_id): {
                'timestamp': current_time,
                'challenge': None  # Initializes with no challenge
            }
        }
        group_doc.update({'unverified_users': user_data})  # Update the document with structured data
        print(f"New user {user_id} added to unverified users in group {group_id} at {current_time}")

def delete_blocked_addresses(update: Update, context: CallbackContext):
    print("Checking message for unallowed addresses...")

    group_data = fetch_group_info(update, context)
    if group_data is None:
        return
    
    message_text = update.message.text
    
    if message_text is None:
        print("No text in message.")
        return

    found_addresses = eth_address_pattern.findall(message_text)

    if not found_addresses:
        print("No addresses found in message.")
        return

    # Retrieve the contract and LP addresses from the fetched group info
    allowed_addresses = [group_data.get('contract_address', '').lower(), group_data.get('liquidity_address', '').lower()]

    print(f"Found addresses: {found_addresses}")
    print(f"Allowed addresses: {allowed_addresses}")

    for address in found_addresses:
        if address.lower() not in allowed_addresses:
            update.message.delete()
            print("Deleted a message containing unallowed address.")
            break

def delete_blocked_links(update: Update, context: CallbackContext):
    print("Checking message for unallowed links...")
    message_text = update.message.text

    if message_text is None:
        print("No text in message.")
        return

    # Fetch the group-specific allowlist
    group_info = fetch_group_info(update, context)
    if not group_info:
        print("No group info available.")
        return

    allowlist_field = 'allowlist'
    allowlist_string = group_info.get(allowlist_field, "")
    allowlist_items = [item.strip() for item in allowlist_string.split(',') if item.strip()]

    # Regular expression to match all URLs
    found_links = url_pattern.findall(message_text)
    
    # Regular expression to match any word with .[domain]
    found_domains = domain_pattern.findall(message_text)

    if not found_links and not found_domains:
        print("No links or domains found in message.")
        return

    # Combine the found links and domains
    found_items = found_links + found_domains
    print(f"Found items: {found_items}")

    for item in found_items:
        normalized_item = item.replace('http://', '').replace('https://', '')
        if not any(normalized_item.startswith(allowed_item) for allowed_item in allowlist_items):
            try:
                update.message.delete()
                print("Deleted a message with unallowed item.")
                return  # Stop further checking if a message is deleted
            except Exception as e:
                print(f"Failed to delete message: {e}")

def delete_blocked_phrases(update: Update, context: CallbackContext):
    print("Checking message for filtered phrases...")
    message_text = update.message.text

    if message_text is None:
        print("No text in message.")
        return

    message_text = message_text.lower()

    # Fetch the group info to get the blocklist
    group_info = fetch_group_info(update, context)
    if not group_info:
        print("No group info available.")
        return

    # Get the blocklist from the group info
    blocklist_field = 'blocklist'
    blocklist_string = group_info.get(blocklist_field, "")
    blocklist_items = [item.strip() for item in blocklist_string.split(',') if item.strip()]

    # Check each blocked phrase in the group's blocklist
    for phrase in blocklist_items:
        if phrase in message_text:
            print(f"Found blocked phrase: {phrase}")
            try:
                update.message.delete()
                print("Message deleted due to blocked phrase.")
            except Exception as e:
                print(f"Error deleting message: {e}")
            break  # Exit loop after deleting the message to prevent multiple deletions for one message

def delete_service_messages(update, context):
    non_deletable_message_id = context.chat_data.get('non_deletable_message_id')
    if update.message.message_id == non_deletable_message_id:
        return  # Do not delete this message

    if update.message.left_chat_member or update.message.new_chat_members:
        try:
            context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)
            print(f"Deleted service message in chat {update.message.chat_id}")
        except Exception as e:
            print(f"Failed to delete service message: {str(e)}")

def store_message_id(context, message_id):
    if 'setup_bot_message' in context.user_data:
        context.user_data['setup_bot_message'].append(message_id)
    else:
        context.user_data['setup_bot_message'] = [message_id]
#endregion Message Handling

#endregion Bot Logic

#region Bot Setup
def menu_change(context: CallbackContext, update: Update):
    messages_to_delete = [
        'setup_bot_message'
    ]

    for message_to_delete in messages_to_delete:
        if message_to_delete in context.user_data:
            for message_id in context.user_data[message_to_delete]:
                try:
                    context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=message_id
                    )
                except Exception as e:
                    if str(e) != "Message to delete not found":
                        print(f"Failed to delete message: {e}")
            context.user_data[message_to_delete] = []

def cancel_callback(update: Update, context: CallbackContext) -> None:
    msg = None
    query = update.callback_query
    query.answer()
    print("User pressed cancel, exiting setup.")
    query.message.delete()
    msg = context.bot.send_message(chat_id=update.effective_chat.id, text="Setup cancelled.")
    context.user_data['setup_stage'] = None

    if msg is not None:
        track_message(msg)

def handle_setup_inputs_from_admin(update: Update, context: CallbackContext) -> None:
    setup_stage = context.user_data.get('setup_stage')
    print("Checking if user is in setup mode.")
    if not setup_stage:
        return
    if setup_stage == 'contract':
        handle_contract_address(update, context)
    elif setup_stage == 'liquidity':
        handle_liquidity_address(update, context)
    elif setup_stage == 'ABI':
        if update.message.text:
            update.message.reply_text("Please upload the ABI as a JSON file.")
            pass
        elif update.message.document:
            handle_ABI(update, context)
    elif setup_stage == 'welcome_message_header' and context.user_data.get('expecting_welcome_message_header_image'):
        handle_welcome_message_image(update, context)
    elif setup_stage == 'buybot_message_header' and context.user_data.get('expecting_buybot_header_image'):
        handle_buybot_message_image(update, context)
    elif context.user_data.get('setup_stage') == 'set_max_warns':
        handle_max_warns(update, context)

def start(update: Update, context: CallbackContext) -> None:
    msg = None
    args = update.message.text.split() if update.message.text else []  # Split by space first
    command_args = args[1].split('_') if len(args) > 1 else []  # Handle parameters after "/start"
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    print(f"Received args: {command_args} - User ID: {user_id} - Chat Type: {chat_type}")

    if chat_type == "private":
        if rate_limit_check():
            if len(command_args) == 3 and command_args[0] == 'authenticate':
                group_id = command_args[1]
                user_id_from_link = command_args[2]
                print(f"Attempting to authenticate user {user_id_from_link} for group {group_id}")

                group_doc = db.collection('groups').document(group_id)
                group_data = group_doc.get()
                if group_data.exists:
                    unverified_users = group_data.to_dict().get('unverified_users', {})
                    print(f"Unverified users list: {unverified_users}")
                    if str(user_id_from_link) in unverified_users:

                        keyboard = [[InlineKeyboardButton("Authenticate", callback_data=f'authenticate_{group_id}_{user_id_from_link}')]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        msg = update.message.reply_text('Press the button below to start authentication.', reply_markup=reply_markup)

                    else:
                        msg = update.message.reply_text('You are already verified or not a member.')
                else:
                    msg = update.message.reply_text('No such group exists.')
            else:
                # General start command handling when not triggered via deep link
                keyboard = [
                    [InlineKeyboardButton("Add me to your group!", url=f"https://t.me/sypher_robot?startgroup=0")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                msg = update.message.reply_text(
                    'Hello! I am Sypher Bot. Please add me to your group to get started.',
                    reply_markup=reply_markup
                )
        else:
            msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    else:
        if is_user_owner(update, context, user_id):
            setup_keyboard = [[InlineKeyboardButton("Setup", callback_data='setup_home')]]
            setup_markup = InlineKeyboardMarkup(setup_keyboard)
            msg = update.message.reply_text(
                "Click 'Setup' to manage your group.",
                reply_markup=setup_markup
            )
            store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def setup_home_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    if is_user_owner(update, context, user_id):
        # Check if the bot is an admin
        chat_member = context.bot.get_chat_member(update.effective_chat.id, context.bot.id)
        if not chat_member.can_invite_users:
            context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=context.user_data['setup_bot_message'],
                text='Please give me admin permissions first!'
            )
            return

        update = Update(update.update_id, message=query.message)

        if query.data == 'setup_home':
            setup_home(update, context, user_id)

def setup_home(update: Update, context: CallbackContext, user_id) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    try:
        group_link = context.bot.export_chat_invite_link(group_id)
    except Exception as e:
        print(f"Error getting group link: {e}")
        group_link = None

    # Get the group username
    group_username = update.effective_chat.username
    if group_username is not None:
        group_username = "@" + group_username

    # Update the group document
    group_doc.update({
        'group_info': {
            'group_link': group_link,
            'group_username': group_username,
        }
    })

    keyboard = [
        [
            InlineKeyboardButton("Admin", callback_data='setup_admin'),
            InlineKeyboardButton("Commands", callback_data='setup_custom_commands')
        ],
        [
            InlineKeyboardButton("Authentication", callback_data='setup_verification'),
            InlineKeyboardButton("Crypto", callback_data='setup_crypto')
        ],
        [
            InlineKeyboardButton("Premium", callback_data='setup_premium')
        ],
        [InlineKeyboardButton("Cancel", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*🏠 Setup Home 🏠*\n\n'
        'Please use the buttons below to setup your bot!\n\n'
        '*👑 Admin:*\n'
        'Configure Admin Settings: Mute, Warn, Allowlist & Blocklist\n\n'
        '_Warning! Clicking "Reset Admin Settings" will reset all admin settings._\n\n'
        '*🤖 Commands:*\n'
        'Configure Custom Commands & Default Commands\n\n'
        '*🔒 Authentication:*\n'
        'Configure Auth Settings: Enable/Disable Auth, Auth Types [Simple, Math, Word], Auth Timeout & Check Current Auth Settings\n\n'
        '*📈 Crypto:*\n'
        'Configure Crypto Settings: Setup Token Details, Check Token Details or Reset Your Token Details.\n\n'
        '_Warning! Clicking "Reset Token Details" will reset all token details._\n\n'
        '*🚀 Premium:*\n'
        '🎨 Customize Your Bot:\n'
        'Adjust the look and feel of your bot. Configure your Welcome Message Header and your Buybot Header.\n',
        # '🚨 Sypher Trust:\n'
        # 'A smart system that dynamically adjusts the trust level of users based on their activity.',
        parse_mode='markdown',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

#region Admin Setup
def setup_admin_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if is_user_owner(update, context, user_id):
        if query.data == 'setup_admin':
            setup_admin(update, context)
    else:
        print("User is not the owner.")

def setup_admin(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [
            InlineKeyboardButton("Mute", callback_data='setup_mute'),
            InlineKeyboardButton("Warn", callback_data='setup_warn')
        ],
        [
            InlineKeyboardButton("Allowlist", callback_data='setup_allowlist'),
            InlineKeyboardButton("Blocklist", callback_data='setup_blocklist')
        ],
        [
            InlineKeyboardButton("❗ Reset Admin Settings ❗", callback_data='reset_admin_settings')
        ],
        [InlineKeyboardButton("Back", callback_data='setup_home')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*👑 Admin Setup 👑*\n\n'
        'Here, you may configure all admin settings for your group.\n\n'
        '*Mute:* Enable/Disable Mute, Check Mute List\n'
        '*Warn:* Enable/Disable Warn, Check Warn List, Max Warns\n\n'
        '*Allowlist:* Add/Remove Links from Allowlist, Check Allowlist or Disable Allowlisting for Links\n'
        '*Blocklist:* Add/Remove Phrases from Blocklist, Check Blocklist\n\n'
        '_Warning! Clicking "Reset Admin Settings" will reset all admin settings._',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

#region Mute Setup
def setup_mute_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'setup_mute':
        if is_user_owner(update, context, user_id):
            setup_mute(update, context)
        else:
            print("User is not the owner.")

def setup_mute(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [
            InlineKeyboardButton("Enable Muting", callback_data='enable_mute'),
            InlineKeyboardButton("Disable Muting", callback_data='disable_mute')
        ],
        [
            InlineKeyboardButton("Mute List", callback_data='check_mute_list')
        ],
        [InlineKeyboardButton("Back", callback_data='setup_admin')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*🔇 Mute Setup 🔇*\n\n'
        'Here, you may choose to enable/disable mute perms in your group. It is on by default.\n'
        'You may also check the list of currently muted users.',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def enable_mute_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'enable_mute':
        if is_user_owner(update, context, user_id):
            enable_mute(update, context)
        else:
            print("User is not the owner.")

def enable_mute(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is None:
        group_doc.set({
            'admin': {
                'mute': True
            }
        })
    else:
        group_doc.update({
            'admin.mute': True
        })

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='✔️ Muting has been enabled in this group ✔️'
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def disable_mute_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'disable_mute':
        if is_user_owner(update, context, user_id):
            disable_mute(update, context)
        else:
            print("User is not the owner.")

def disable_mute(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is None:
        group_doc.set({
            'admin': {
                'mute': False
            }
        })
    else:
        group_doc.update({
            'admin.mute': False
        })

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='❌ Muting has been disabled in this group ❌'
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def check_mute_list_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'check_mute_list':
        if is_user_owner(update, context, user_id):
            check_mute_list(update, context)
        else:
            print("User is not the owner.")

def check_mute_list(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    mute_list_text = '*Current Mute List:*\n\n'
    if group_data is None or 'muted_users' not in group_data or not group_data['muted_users']:
        mute_list_text += 'No users are currently muted.'
    else:
        for user_id, mute_date in group_data['muted_users'].items():
            try:
                user_info = context.bot.get_chat_member(chat_id=group_id, user_id=user_id).user
                username = user_info.username
                first_name = user_info.first_name
                last_name = user_info.last_name

                if username:
                    mute_list_text += f'- @{username} • {mute_date}\n'
                elif first_name or last_name:
                    mute_list_text += f'- {first_name or ""} {last_name or ""} • {mute_date}\n'
                else:
                    mute_list_text += f'- {user_id} • {mute_date}\n'
            except Exception:
                print(f"Failed to get user info for {user_id}")
                continue

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=mute_list_text,
        parse_mode='Markdown'
    )
    context.bot_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)
#endregion Mute Setup

#region Warn Setup
def setup_warn_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'setup_warn':
        if is_user_owner(update, context, user_id):
            setup_warn(update, context)
        else:
            print("User is not the owner.")

def setup_warn(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [
            InlineKeyboardButton("Enable Warnings", callback_data='enable_warn'),
            InlineKeyboardButton("Disable Warnings", callback_data='disable_warn'),
            InlineKeyboardButton("Max Warns", callback_data='set_max_warns')
        ],
        [
            InlineKeyboardButton("Warned Users List", callback_data='check_warn_list'),
        ],
        [InlineKeyboardButton("Back", callback_data='setup_admin')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*⚠️ Warn Setup ⚠️*\n\n'
        'Here, you may choose to enable/disable warn perms in your group. It is on by default. You may also set the maximum warns before a user is punished.\n\n'
        '*Default Max Warns:* _3_',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def enable_warn_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'enable_warn':
        if is_user_owner(update, context, user_id):
            enable_warn(update, context)
        else:
            print("User is not the owner.")

def enable_warn(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is None:
        group_doc.set({
            'admin': {
                'warn': True
            }
        })
    else:
        group_doc.update({
            'admin.warn': True
        })

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='✔️ Warning has been enabled in this group ✔️'
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def disable_warn_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'disable_warn':
        if is_user_owner(update, context, user_id):
            disable_warn(update, context)
        else:
            print("User is not the owner.")

def disable_warn(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is None:
        group_doc.set({
            'admin': {
                'warn': False
            }
        })
    else:
        group_doc.update({
            'admin.warn': False
        })

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='❌ Warning has been disabled in this group ❌'
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def check_warn_list_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'check_warn_list':
        if is_user_owner(update, context, user_id):
            check_warn_list(update, context)
        else:
            print("User is not the owner.")

def check_warn_list(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [InlineKeyboardButton("Back", callback_data='setup_warn')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    warn_list_text = '*Current Warned Users List:*\n\n'
    if group_data is None or 'warnings' not in group_data or not group_data['warnings']:
        warn_list_text += 'No users are currently warned.'
    else:
        for user_id, warn_count in group_data['warnings'].items():
            try:
                user_info = context.bot.get_chat_member(chat_id=group_id, user_id=user_id).user
                username = user_info.username
                first_name = user_info.first_name
                last_name = user_info.last_name

                if username:
                    warn_list_text += f'@{username} • {warn_count} warns\n'
                elif first_name or last_name:
                    warn_list_text += f'{first_name or ""} {last_name or ""} • {warn_count} warns\n'
                else:
                    warn_list_text += f'{user_id} • {warn_count} warns\n'
            except Exception:
                print(f"Failed to get user info for {user_id}")
                continue

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=warn_list_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def set_max_warns_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'set_max_warns':
        if is_user_owner(update, context, user_id):
            set_max_warns(update, context)
        else:
            print("User is not the owner.")

def set_max_warns(update: Update, context: CallbackContext) -> None:
    msg = None

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Please respond with the maximum number of warnings you want for the group.\n\n'
        '*Default Max Warns:* _3_',
        parse_mode='Markdown'
    )
    context.user_data['setup_stage'] = 'set_max_warns'
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def handle_max_warns(update: Update, context: CallbackContext) -> None:
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    if update.message.text:
        try:
            max_warns = int(update.message.text)
        except ValueError:
            msg = context.bot.send_message(
                chat_id=update.effective_chat.id,
                text='Please enter a number.'
            )

            if msg is not None:
                track_message(msg)
            return

        group_doc.update({
            'admin.max_warns': max_warns
        })

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Maximum number of warnings set to {max_warns}.'
        )
        store_message_id(context, msg.message_id)

        if msg is not None:
            track_message(msg)
#endregion Warn Setup

#region Allowlist Setup
def setup_allowlist_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'setup_allowlist':
        if is_user_owner(update, context, user_id):
            setup_allowlist(update, context)
        else:
            print("User is not the owner.")

def setup_allowlist(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [
            InlineKeyboardButton("Enable Allowlist", callback_data='enable_allowlist'),
            InlineKeyboardButton("Disable Allowlist", callback_data='disable_allowlist')
        ],
        [
            InlineKeyboardButton("Check Allowlist", callback_data='check_allowlist')
        ],
        [
            InlineKeyboardButton("❗ Clear Allowlist ❗", callback_data='clear_allowlist')
        ],
        [InlineKeyboardButton("Back", callback_data='setup_admin')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*✅ Allowlist Setup ✅*\n\n'
        'Here, you may add or remove links from the allowlist, check the current allowlist or disable allowlisting for links.\n\n'
        '_Please Note: If you disable link allowlisting, any links will be allowed in the group._\n\n'
        '*How To Allow Links:*\n'
        'To allow specific links in your group type: /allow <link>\n\n'
        '_Clearing the allowlist will remove all links and reset the allowlist._',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def enable_allowlist_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'enable_allowlist':
        if is_user_owner(update, context, user_id):
            enable_allowlist(update, context)
        else:
            print("User is not the owner.")

def enable_allowlist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is None:
        group_doc.set({
            'admin': {
                'allowlisting': True
            }
        })
    else:
        group_doc.update({
            'admin.allowlisting': True
        })

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='✔️ Allowlisting has been enabled in this group ✔️'
    )
    context.user_data['setup_stage'] = None
    context.user_data['enable_allowlist_message'] = msg.message_id
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def disable_allowlist_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'disable_allowlist':
        if is_user_owner(update, context, user_id):
            disable_allowlist(update, context)
        else:
            print("User is not the owner.")

def disable_allowlist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is None:
        group_doc.set({
            'admin': {
                'allowlisting': False
            }
        })
    else:
        group_doc.update({
            'admin.allowlisting': False
        })

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='❌ Allowlisting has been disabled in this group ❌'
    )
    context.user_data['setup_stage'] = None
    context.user_data['disable_allowlist_message'] = msg.message_id

    if msg is not None:
        track_message(msg)

#endregion Allowlist Setup

#region Blocklist Setup
def setup_blocklist_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'setup_blocklist':
        if is_user_owner(update, context, user_id):
            setup_blocklist(update, context)
        else:
            print("User is not the owner.")

def setup_blocklist(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [InlineKeyboardButton("Back", callback_data='setup_admin')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*⛔ Blocklist Setup ⛔*',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

#endregion Blocklist Setup

def reset_admin_settings_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'reset_admin_settings':
        if is_user_owner(update, context, user_id):
            reset_admin_settings(update, context)
        else:
            print("User is not the owner.")

def reset_admin_settings(update: Update, context: CallbackContext) -> None:
    msg = None
    # group_id = update.effective_chat.id
    # group_doc = db.collection('groups').document(str(group_id))

    print("Resetting admin settings...")

    if msg is not None:
        track_message(msg)

#endregion Admin Setup

#region Commands Setup
# TODO: Put command setup logic here
#endregion Commands Setup

#region Authentication Setup
def setup_verification_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if is_user_owner(update, context, user_id):
        if query.data == 'setup_verification':
            setup_verification(update, context)

def setup_verification(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [
            InlineKeyboardButton("Enable", callback_data='enable_verification'),
            InlineKeyboardButton("Disable", callback_data='disable_verification')
        ],
        [
            InlineKeyboardButton("Simple", callback_data='simple_verification'),
            InlineKeyboardButton("Math", callback_data='math_verification'),
            InlineKeyboardButton("Word", callback_data='word_verification')
        ],
        [
            InlineKeyboardButton("Authentication Timeout", callback_data='timeout_verification'),
            InlineKeyboardButton("Current Authentication Settings", callback_data='check_verification_settings')
        ],
        [InlineKeyboardButton("Back", callback_data='setup_home')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*🌐 Authentication Setup 🌐*\n\nYou may enable or disable authentication. Once enabled, please choose an authentication type.', parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def enable_verification_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'enable_verification':
        if is_user_owner(update, context, user_id):
            enable_verification(update, context)
        else:
            print("User is not the owner.")

def enable_verification(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is None:
        group_doc.set({
            'group_id': group_id,
            'verification_info': {
                'verification': True,
                'verification_type': 'none',
                'verification_timeout': 600
            }
        })
    else:
        group_doc.update({
            'verification_info': {
                'verification': True,
                'verification_type': 'none',
                'verification_timeout': 600
            }
        })

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Authentication enabled for this group.\n\n*❗ Please choose an authentication type ❗*', parse_mode='Markdown'
    )
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def disable_verification_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'disable_verification':
        if is_user_owner(update, context, user_id):
            disable_verification(update, context)
        else:
            print("User is not the owner.")

def disable_verification(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is None:
        group_doc.set({
            'group_id': group_id,
            'verification_info': {
                'verification': False,
                'verification_type': 'none'
            }
        })
    else:
        group_doc.update({
            'verification_info': {
                'verification': False,
                'verification_type': 'none'
            }
        })

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*❗ Authentication disabled for this group ❗*', parse_mode='Markdown'
    )
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def simple_verification_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'simple_verification':
        if is_user_owner(update, context, user_id):
            simple_verification(update, context)
        else:
            print("User is not the owner.")

def simple_verification(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is None:
        group_doc.set({
            'group_id': group_id,
            'verification_info': {
                'verification': True,
                'verification_type': 'simple',
                'verification_timeout': 600
            }
        })
    else:
        group_doc.update({
            'verification_info': {
                'verification': True,
                'verification_type': 'simple',
                'verification_timeout': 600
            }
        })

    menu_change(context, update)

    keyboard = [
        [InlineKeyboardButton("Back", callback_data='setup_verification')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*🤡 Simple authentication enabled for this group 🤡*', parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def math_verification_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'math_verification':
        if is_user_owner(update, context, user_id):
            math_verification(update, context)
        else:
            print("User is not the owner.")

def math_verification(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is None:
        group_doc.set({
            'group_id': group_id,
            'verification_info': {
                'verification': True,
                'verification_type': 'math',
                'verification_timeout': 600
            }
        })
    else:
        group_doc.update({
            'verification_info': {
                'verification': True,
                'verification_type': 'math',
                'verification_timeout': 600
            }
        })

    keyboard = [
        [InlineKeyboardButton("Back", callback_data='setup_verification')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*#️⃣ Math authentication enabled for this group #️⃣*',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)


    if msg is not None:
        track_message(msg)

def word_verification_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'word_verification':
        if is_user_owner(update, context, user_id):
            word_verification(update, context)
        else:
            print("User is not the owner.")

def word_verification(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is None:
        group_doc.set({
            'group_id': group_id,
            'verification_info': {
                'verification': True,
                'verification_type': 'word',
                'verification_timeout': 600
            }
        })
    else:
        group_doc.update({
            'verification_info': {
                'verification': True,
                'verification_type': 'word',
                'verification_timeout': 600
            }
        })

    # Set the state in user_data
    context.user_data['setup_stage'] = 'setup_word_verification'

    menu_change(context, update)

    keyboard = [
        [InlineKeyboardButton("Back", callback_data='setup_verification')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Ask the question for new users
    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*🈹 Word authentication enabled for this group 🈹*',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)


    if msg is not None:
        track_message(msg)

def timeout_verification_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'timeout_verification':
        if is_user_owner(update, context, user_id):
            timeout_verification(update, context)
        else:
            print("User is not the owner.")

def timeout_verification(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [
            InlineKeyboardButton("1 Minute", callback_data='vtimeout_60'),
            InlineKeyboardButton("10 Minutes", callback_data='vtimeout_600')
        ],
        [
            InlineKeyboardButton("30 Minutes", callback_data='vtimeout_1800'),
            InlineKeyboardButton("60 Minutes", callback_data='vtimeout_3600')
        ],
        [InlineKeyboardButton("Back", callback_data='setup_verification')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Please choose the authentication timeout.',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def handle_timeout_callback(update: Update, context: CallbackContext) -> None:
    msg = None
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    if is_user_owner(update, context, user_id):
        # Extract the timeout value from the callback_data
        timeout_seconds = int(query.data.split('_')[1])

        # Call set_verification_timeout with the group_id and timeout_seconds
        group_id = update.effective_chat.id
        set_verification_timeout(group_id, timeout_seconds)

        # Send a confirmation message to the user
        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Authentication timeout set to {timeout_seconds // 60} minutes."
        )
        store_message_id(context, msg.message_id)

        if msg is not None:
            track_message(msg)

def set_verification_timeout(group_id: int, timeout_seconds: int) -> None:
    # Sets the verification timeout for a specific group in the Firestore database.
    try:
        group_ref = db.collection('groups').document(str(group_id))

        group_ref.update({
            'verification_info.verification_timeout': timeout_seconds
        })

        print(f"Authentication timeout for group {group_id} set to {timeout_seconds} seconds")

    except Exception as e:
        print(f"Error setting verification timeout: {e}")

def check_verification_settings_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'check_verification_settings':
        if is_user_owner(update, context, user_id):
            check_verification_settings(update, context)
        else:
            print("User is not the owner.")

def check_verification_settings(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is not None:
        verification_info = group_data.get('verification_info', {})
        verification = verification_info.get('verification', False)
        verification_type = verification_info.get('verification_type', 'none')
        verification_timeout = verification_info.get('verification_timeout', 000)

        menu_change(context, update)

        keyboard = [
            [InlineKeyboardButton("Back", callback_data='setup_verification')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"*🔒 Current Authentication Settings 🔒*\n\nAuthentication: {verification}\nType: {verification_type}\nTimeout: {verification_timeout // 60} minutes",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        context.user_data['setup_stage'] = None
        store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)
#endregion Authentication Setup

#region Ethereum Setup
def setup_crypto_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if is_user_owner(update, context, user_id):
        setup_crypto(update, context)

def setup_crypto(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [
            InlineKeyboardButton("Contract", callback_data='setup_contract'),
            InlineKeyboardButton("Liquidity", callback_data='setup_liquidity')
        ],
        [
            InlineKeyboardButton("Chain", callback_data='setup_chain'),
            InlineKeyboardButton("ABI", callback_data='setup_ABI')
        ],
        [
            InlineKeyboardButton("Check Token Details", callback_data='check_token_details'),
        ],
        [
            InlineKeyboardButton("❗ Reset Token Details ❗", callback_data='reset_token_details')
        ],
        [
            InlineKeyboardButton("Back", callback_data='setup_home')
        ]
        
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*🔑 Crypto Setup 🔑*\n\n'
        'Here you can setup the Buybot, Pricebot and Chartbot functionality.\n\n'
        '*Please Note:*\n'
        '• ABI is *required* for the Buybot functionality to work and for token details to propagate correctly.\n'
        '• Currently, this functionality is only setup for ETH paired tokens.\n\n'
        '*⚠️ Updating Token Details ⚠️*\n'
        'To enter new token details, you must click *Reset Token Details* first.',
        parse_mode='markdown',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def setup_contract(update: Update, context: CallbackContext) -> None:
    msg = None
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    if is_user_owner(update, context, user_id):

        keyboard = [
            [InlineKeyboardButton("Back", callback_data='setup_crypto')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        menu_change(context, update) 

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Please respond with your contract address.',
            reply_markup=reply_markup
        )
        context.user_data['setup_stage'] = 'contract'
        print("Requesting contract address.")
        store_message_id(context, msg.message_id)

        if msg is not None:
            track_message(msg)

def handle_contract_address(update: Update, context: CallbackContext) -> None:
    msg = None
    user_id = update.message.from_user.id
    
    if is_user_owner(update, context, user_id):
        if context.user_data.get('setup_stage') == 'contract':
            eth_address_pattern = re.compile(r'\b0x[a-fA-F0-9]{40}\b')
            contract_address = update.message.text.strip()

            if eth_address_pattern.fullmatch(contract_address):
                group_id = update.effective_chat.id
                print(f"Adding contract address {contract_address} to group {group_id}")
                group_doc = db.collection('groups').document(str(group_id))
                group_doc.update({'token.contract_address': contract_address})
                context.user_data['setup_stage'] = None

                if update.message is not None:
                    msg = update.message.reply_text("Contract address added successfully!")
                elif update.callback_query is not None:
                    msg = update.callback_query.message.reply_text("Contract address added successfully!")
            
                complete_token_setup(group_id, context)
            else:
                msg = update.message.reply_text("Please send a valid Contract Address!")

        store_message_id(context, msg.message_id)

        if msg is not None:
            track_message(msg)

def setup_liquidity(update: Update, context: CallbackContext) -> None:
    msg = None
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    
    if is_user_owner(update, context, user_id):
        keyboard = [
            [InlineKeyboardButton("Back", callback_data='setup_crypto')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        menu_change(context, update)

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Please respond with your liquidity address.',
            reply_markup=reply_markup
        )
        context.user_data['setup_stage'] = 'liquidity'
        store_message_id(context, msg.message_id)
        print("Requesting liquidity address.")

        if msg is not None:
            track_message(msg)

def handle_liquidity_address(update: Update, context: CallbackContext) -> None:
    msg = None
    user_id = update.message.from_user.id

    if is_user_owner(update, context, user_id):
        msg = None
        if context.user_data.get('setup_stage') == 'liquidity':
            eth_address_pattern = re.compile(r'\b0x[a-fA-F0-9]{40}\b')
            liquidity_address = update.message.text.strip()

            if eth_address_pattern.fullmatch(liquidity_address):
                group_id = update.effective_chat.id
                print(f"Adding liquidity address {liquidity_address} to group {group_id}")
                group_doc = db.collection('groups').document(str(group_id))
                group_doc.update({'token.liquidity_address': liquidity_address})
                context.user_data['setup_stage'] = None

                # Check if update.message is not None before using it
                if update.message is not None:
                    msg = update.message.reply_text("Liquidity address added successfully!")
                elif update.callback_query is not None:
                    msg = update.callback_query.message.reply_text("Liquidity address added successfully!")

                complete_token_setup(group_id, context)
            else:
                # Check if update.message is not None before using it
                if update.message is not None:
                    msg = update.message.reply_text("Please send a valid Liquidity Address!")
                elif update.callback_query is not None:
                    msg = update.callback_query.message.reply_text("Please send a valid Liquidity Address!")

        store_message_id(context, msg.message_id)

        if msg is not None:
            track_message(msg)

def setup_ABI(update: Update, context: CallbackContext) -> None:
    msg = None
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    
    if is_user_owner(update, context, user_id):

        keyboard = [
            [InlineKeyboardButton("Example abi.json", callback_data='example_abi')],
            [InlineKeyboardButton("Back", callback_data='setup_crypto')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        menu_change(context, update)

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*📝 ABI Setup 📝*\n\nPlease upload your ABI in .json format.\n\n *Example file syntax:*\n```\n[\n    {\n        "inputs": [],\n        "stateMutability": "nonpayable",\n        "type": "constructor"\n    },\n    {\n        "anonymous": false,\n        "inputs": [\n            {\n                "indexed": true,\n                "internalType": "address",\n                "name": "owner",\n                "type": "address"\n            },\n            {\n                "indexed": true,\n                "internalType": "address",\n                "name": "spender",\n                "type": "address"\n            },\n            {\n                "indexed": false,\n                "internalType": "uint256",\n                "name": "value",\n                "type": "uint256"\n            }\n        ],\n        "name": "Approval",\n       "type": "event"\n    }\n]\n```',
            parse_mode='markdown',
            reply_markup=reply_markup
        )
        context.user_data['setup_stage'] = 'ABI'
        store_message_id(context, msg.message_id)
        print("Requesting ABI file.")

        if msg is not None:
            track_message(msg)

def handle_ABI(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id

    if is_user_owner(update, context, user_id):
        msg = None
        if context.user_data.get('setup_stage') == 'ABI':
            document = update.message.document
            print(f"MIME type: {document.mime_type}")
            if document.mime_type == 'application/json':
                file = context.bot.getFile(document.file_id)
                file.download('temp_abi.json')
                with open('temp_abi.json', 'r') as file:
                    abi = json.load(file)  # Parse the ABI
                    group_id = update.effective_chat.id
                    print(f"Adding ABI to group {group_id}")
                    group_doc = db.collection('groups').document(str(group_id))
                    group_doc.update({'token.abi': abi})
                    context.user_data['setup_stage'] = None
                    msg = update.message.reply_text("ABI has been successfully saved.")

                    complete_token_setup(group_id, context)
            else:
                msg = update.message.reply_text("Make sure the file is a JSON file, and you are using a desktop device.")
            
        store_message_id(context, msg.message_id)

        if msg is not None:
            track_message(msg)

def send_example_abi(update: Update, context: CallbackContext) -> None:
    msg = None
    query = update.callback_query
    query.answer()

    with open('abi.json', 'rb') as file:
        msg = context.bot.send_document(
            chat_id=update.effective_user.id,
            document=file,
            filename='abi.json',
            caption='Here is an example ABI file.'
        )
    
    msg = query.message.reply_text("Example ABI file sent to your DM.")

    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def setup_chain(update: Update, context: CallbackContext) -> None:
    msg = None
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    
    if is_user_owner(update, context, user_id):

        keyboard = [
            [
                InlineKeyboardButton("Ethereum", callback_data='ethereum'),
                InlineKeyboardButton("Base", callback_data='base')

            ],
            [
                InlineKeyboardButton("Arbitrum", callback_data='arbitrum'),
                InlineKeyboardButton("Optimism", callback_data='optimism')
            ],
            [
                InlineKeyboardButton("Polygon", callback_data='polygon'),
                InlineKeyboardButton("Fantom", callback_data='fantom'),
                InlineKeyboardButton("Avalanche", callback_data='avalanche')
            ],
            [
                InlineKeyboardButton("Binance", callback_data='binance'),
                InlineKeyboardButton("Harmony", callback_data='harmony'),
                InlineKeyboardButton("Mantle", callback_data='mantle')
            ],
            [InlineKeyboardButton("Back", callback_data='setup_crypto')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        menu_change(context, update)

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Please choose your chain from the list.',
            reply_markup=reply_markup
        )
        context.user_data['setup_stage'] = 'chain'
        store_message_id(context, msg.message_id)
        print("Requesting Chain.")

        if msg is not None:
            track_message(msg)

def handle_chain(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    if is_user_owner(update, context, user_id):
        if context.user_data.get('setup_stage') == 'chain':
            chain = update.callback_query.data.upper()  # Convert chain to uppercase
            group_id = update.effective_chat.id
            print(f"Adding chain {chain} to group {group_id}")
            group_doc = db.collection('groups').document(str(group_id))
            group_doc.update({'token.chain': chain})
            context.user_data['setup_stage'] = None

            complete_token_setup(group_id, context)

            msg = query.message.reply_text("Chain has been saved.")

            store_message_id(context, msg.message_id)

            if msg is not None:
                track_message(msg)

def complete_token_setup(group_id: str, context: CallbackContext):
    msg = None
    # Fetch the group data from Firestore
    group_doc = db.collection('groups').document(str(group_id))
    group_data = group_doc.get().to_dict()

    token_data = group_data.get('token')
    if not token_data:
        print("Token data not found for this group.")
        return

    # Get the contract address, ABI, and chain from the group data
    if 'abi' not in token_data:
        print(f"ABI not found in group {group_id}, token setup incomplete.")
        return
    abi = token_data.get('abi')
    
    if 'contract_address' not in token_data:
        print(f"Contract address not found in group {group_id}, token setup incomplete.")
        return
    contract_address = token_data['contract_address']

    if 'chain' not in token_data:
        print(f"Chain not found in group {group_id}, token setup incomplete.")
        return
    chain = token_data.get('chain')

    # Get the Web3 instance for the chain
    web3 = web3_instances.get(chain)
    if not web3:
        print(f"Web3 provider not found for chain {chain}, token setup incomplete.")
        return

    # Create a contract object
    contract = web3.eth.contract(address=contract_address, abi=abi)

    # Call the name, symbol, and decimals functions
    try:
        token_name = contract.functions.name().call()
        token_symbol = contract.functions.symbol().call()
        decimals = contract.functions.decimals().call()
        total_supply = contract.functions.totalSupply().call() / (10 ** decimals)
    except Exception as e:
        print(f"Failed to get token name, symbol, total supply and decimals: {e}")
        return
    
    # Update the Firestore document with the token name, symbol, and total supply
    group_doc.update({
        'token.name': token_name,
        'token.symbol': token_symbol,
        'token.total_supply': total_supply,
        'token.decimals': decimals
    })
    
    print(f"Added token name {token_name}, symbol {token_symbol}, and total supply {total_supply} to group {group_id}")

    # schedule_group_monitoring(group_data)

    msg = context.bot.send_message(
        chat_id=group_id,
        text=f"*🎉 Token setup complete! 🎉*\n\n*Name:* {token_name}\n*Symbol:* {token_symbol}\n*Total Supply:* {total_supply}\n*Decimals:* {decimals}",
        parse_mode='Markdown'
    )

    if msg is not None:
        track_message(msg)

def check_token_details_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'check_token_details':
        if is_user_owner(update, context, user_id):
            check_token_details(update, context)
        else:
            print("User is not the owner.")

def check_token_details(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is not None:
        token_info = group_data.get('token', {})
        chain = token_info.get('chain', 'none')
        contract_address = token_info.get('contract_address', 'none')
        liquidity_address = token_info.get('liquidity_address', 'none')
        name = token_info.get('name', 'none')
        symbol = token_info.get('symbol', 'none')
        total_supply = token_info.get('total_supply', 'none')

        menu_change(context, update)

        keyboard = [
            [InlineKeyboardButton("Back", callback_data='setup_crypto')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"*📜 Current Token Details 📜*\n\n*Name:* {name}\n*Symbol:* {symbol}\n*Chain:* {chain}\n*Total Supply:*\n{total_supply}\n*CA:*\n{contract_address}\n*LP:*\n{liquidity_address}",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        context.user_data['setup_stage'] = None
        store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def reset_token_details_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'reset_token_details':
        if is_user_owner(update, context, user_id):
            reset_token_details(update, context)
        else:
            print("User is not the owner.")

def reset_token_details(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is not None:
        group_doc.update({
            'token': {}
        })

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*🔄 Token Details Reset 🔄*',
            parse_mode='Markdown'
        )

    if msg is not None:
        track_message(msg)
#endregion Ethereum Setup

#region Premium Setup
def setup_premium_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'setup_premium':
        if is_user_owner(update, context, user_id):
            setup_premium(update, context)

def setup_premium(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [
            InlineKeyboardButton("Welcome Message Header", callback_data='setup_welcome_message_header'),
            InlineKeyboardButton("Buybot Message Header", callback_data='setup_buybot_message_header')
        ],
        # [
        #     InlineKeyboardButton("Enable Trust System", callback_data='enable_sypher_trust'),
        #     InlineKeyboardButton("Disable Trust System", callback_data='disable_sypher_trust')
        # ],
        # [
        #     InlineKeyboardButton("Trust Preferences", callback_data='sypher_trust_preferences'),
        # ],
        [InlineKeyboardButton("Back", callback_data='setup_home')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*🚀 Premium Setup 🚀*\n\n'
        '🎨 Customize:\n'
        'Configure your *Welcome Message Header* and your *Buybot Header*.\n',
        # '🚨 Sypher Trust:\n'
        # 'Enable/Disable Trust System. Set Trust Preferences.',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def setup_welcome_message_header_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'setup_welcome_message_header':
        if is_user_owner(update, context, user_id):
            setup_welcome_message_header(update, context)
        else:
            print("User is not the owner.")

def setup_welcome_message_header(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))
    group_data = group_doc.get().to_dict()

    if group_data is not None and group_data.get('premium') is not True:
        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="This feature is only available to premium users. Please contact @tukyowave for more information.",
            parse_mode='Markdown'
        )
        store_message_id(context, msg.message_id)
        print("User does not have premium.")
        return

    print("Requesting a welcome message header.")
    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please send a jpg image for the welcome message header that is less than 700x250px.",
        parse_mode='Markdown'
    )
    context.user_data['expecting_welcome_message_header_image'] = True  # Flag to check in the image handler
    context.user_data['setup_stage'] = 'welcome_message_header'
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def handle_welcome_message_image(update: Update, context: CallbackContext) -> None:
    msg = None
    if context.user_data.get('expecting_welcome_message_header_image'):
        group_id = update.effective_chat.id
        group_doc = db.collection('groups').document(str(group_id))

        group_data = group_doc.get().to_dict()
        
        photo = update.message.photo[-1]  # Get the highest resolution photo
        file = context.bot.get_file(photo.file_id)

        # Download the image to check file size
        image_stream = BytesIO()
        file.download(out=image_stream)
        file_size = len(image_stream.getvalue())  # Get the size of the file in bytes

        if photo.width <= 700 and photo.height <= 250 and file_size <= 100000:  # File size less than 100 KB
            filename = f'welcome_message_header_{group_id}.jpg'
            filepath = f'sypherbot/public/welcome_message_header/{filename}'

            # Save to Firebase Storage
            bucket = storage.bucket()
            blob = bucket.blob(filepath)
            blob.upload_from_string(
                image_stream.getvalue(),
                content_type='image/jpeg'
            )

            if group_data is not None:
                group_doc.update({
                    'premium_features.welcome_header': True
                })

            msg = context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Your welcome message header image has been successfully uploaded!",
                parse_mode='Markdown'
            )
            context.user_data['expecting_welcome_message_header_image'] = False  # Reset the flag
            context.user_data['setup_stage'] = None
            store_message_id(context, msg.message_id)
        else:
            error_message = "Please ensure the image is less than 700x250 pixels"
            if file_size > 100000:
                error_message += " and smaller than 100 KB"
            error_message += " and try again."
            msg = context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=error_message,
                parse_mode='Markdown'
            )
            store_message_id(context, msg.message_id)
        if msg is not None:
            track_message(msg)

def setup_buybot_message_header_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'setup_buybot_message_header':
        if is_user_owner(update, context, user_id):
            setup_buybot_message_header(update, context)
        else:
            print("User is not the owner.")

def setup_buybot_message_header(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))
    group_data = group_doc.get().to_dict()

    if group_data is not None and group_data.get('premium') is not True:
        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="This feature is only available to premium users. Please contact @tukyowave for more information.",
            parse_mode='Markdown'
        )
        store_message_id(context, msg.message_id)
        print("User does not have premium.")
        return
    
    print("Requesting a Buybot message header.")

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please send a jpg image for the buybot message header that is less than 700x250px.",
        parse_mode='Markdown'
    )
    context.user_data['expecting_buybot_header_image'] = True  # Flag to check in the image handler
    context.user_data['setup_stage'] = 'buybot_message_header'
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def handle_buybot_message_image(update: Update, context: CallbackContext) -> None:
    msg = None
    if context.user_data.get('expecting_buybot_header_image'):
        group_id = update.effective_chat.id
        group_doc = db.collection('groups').document(str(group_id))

        group_data = group_doc.get().to_dict()
        
        photo = update.message.photo[-1]  # Get the highest resolution photo
        file = context.bot.get_file(photo.file_id)

        # Download the image to check file size
        image_stream = BytesIO()
        file.download(out=image_stream)
        file_size = len(image_stream.getvalue())  # Get the size of the file in bytes

        # Check dimensions adn filesize
        if photo.width <= 700 and photo.height <= 250 and file_size <= 100000:
            filename = f'buybot_message_header_{group_id}.jpg'
            filepath = f'sypherbot/public/buybot_message_header/{filename}'

            # Save to Firebase Storage
            bucket = storage.bucket()
            blob = bucket.blob(filepath)
            image_stream = BytesIO()
            file.download(out=image_stream)
            blob.upload_from_string(
                image_stream.getvalue(),
                content_type='image/jpeg'
            )

            if group_data is not None:
                group_doc.update({
                    'premium_features.buybot_header': True
                })

            msg = context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Your buybot message header image has been successfully uploaded!",
                parse_mode='Markdown'
            )
            context.user_data['expecting_buybot_header_image'] = False  # Reset the flag
            context.user_data['setup_stage'] = None
            store_message_id(context, msg.message_id)
        else:
            error_message = "Please ensure the image is less than 700x250 pixels"
            if file_size > 100000:
                error_message += " and smaller than 100 KB"
            error_message += " and try again."
            msg = context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=error_message,
                parse_mode='Markdown'
            )
            store_message_id(context, msg.message_id)
        if msg is not None:
            track_message(msg)

def enable_sypher_trust_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'enable_sypher_trust':
        if is_user_owner(update, context, user_id):
            enable_sypher_trust(update, context)
        else:
            print("User is not the owner.")

def enable_sypher_trust(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is not None and group_data.get('premium') is not True:
        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="This feature is only available to premium users. Please contact @tukyowave for more information.",
            parse_mode='Markdown'
        )
        store_message_id(context, msg.message_id)
        print("User does not have premium.")
        return

    if group_data is not None:
        group_doc.update({
            'premium_features.sypher_trust': True,
            'premium_features.sypher_trust_preferences': 'moderate'
        })

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*✔️ Trust System Enabled ✔️*',
            parse_mode='Markdown'
        )
        context.user_data['setup_stage'] = None
        store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def disable_sypher_trust_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'disable_sypher_trust':
        if is_user_owner(update, context, user_id):
            disable_sypher_trust(update, context)
        else:
            print("User is not the owner.")

def disable_sypher_trust(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is not None and group_data.get('premium') is not True:
        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="This feature is only available to premium users. Please contact @tukyowave for more information.",
            parse_mode='Markdown'
        )
        store_message_id(context, msg.message_id)
        print("User does not have premium.")
        return

    if group_data is not None:
        group_doc.update({
            'premium_features.sypher_trust': False
        })

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*❌ Trust System Disabled ❌*',
            parse_mode='Markdown'
        )
        context.user_data['setup_stage'] = None
        store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def sypher_trust_preferences_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'sypher_trust_preferences':
        if is_user_owner(update, context, user_id):
            sypher_trust_preferences(update, context)
        else:
            print("User is not the owner.")

def sypher_trust_preferences(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is not None and group_data.get('premium') is not True:
        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="This feature is only available to premium users. Please contact @tukyowave for more information.",
            parse_mode='Markdown'
        )
        store_message_id(context, msg.message_id)
        print("User does not have premium.")
        return
    keyboard = [
        [
            InlineKeyboardButton("Relaxed", callback_data='sypher_trust_relaxed'),
            InlineKeyboardButton("Moderate", callback_data='sypher_trust_moderate'),
            InlineKeyboardButton("Strict", callback_data='sypher_trust_strict')
        ],
        [InlineKeyboardButton("Back", callback_data='setup_premium')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*🚨 Trust Preferences 🚨*\n\n'
        'The sypher trust system dynamically allows users in your group to send [@username] tags.\n'
        'A common theme in crypto telegram groups is a new user joining and sending a message like this:\n\n'
        '_Huge pump incoming, join @username for details!!_\n\n'
        'This feature *blocks users from tagging other users or groups* until their trust has been earned in the group.\n\n'
        '• *Relaxed:* Trust users more easily, allow tagging of other groups and members quickest.\n'
        '• *Moderate:* A bit more strict, the default setting for the sypher trust system. Trust users after interaction with the group.\n'
        '• *Strict:* Strictest trust. Only allow users to be trusted after genuine activity in your group.',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def sypher_trust_relaxed_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'sypher_trust_relaxed':
        if is_user_owner(update, context, user_id):
            sypher_trust_relaxed(update, context)
        else:
            print("User is not the owner.")

def sypher_trust_relaxed(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is not None:
        group_doc.update({
            'premium_features.sypher_trust_preferences': 'relaxed'
        })

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*🟢 Relaxed Trust Level Enabled 🟢*',
            parse_mode='Markdown'
        )
        store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def sypher_trust_moderate_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'sypher_trust_moderate':
        if is_user_owner(update, context, user_id):
            sypher_trust_moderate(update, context)
        else:
            print("User is not the owner.")

def sypher_trust_moderate(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is not None:
        group_doc.update({
            'premium_features.sypher_trust_preferences': 'moderate'
        })

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*🟡 Moderate Trust Level Enabled 🟡*',
            parse_mode='Markdown'
        )
        store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def sypher_trust_strict_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)

    if query.data == 'sypher_trust_strict':
        if is_user_owner(update, context, user_id):
            sypher_trust_strict(update, context)
        else:
            print("User is not the owner.")

def sypher_trust_strict(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is not None:
        group_doc.update({
            'premium_features.sypher_trust_preferences': 'strict'
        })

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*🔴 Strict Trust Level Enabled 🔴*',
            parse_mode='Markdown'
        )
        store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

#endregion Premium Setup

#endregion Bot Setup

#region User Authentication
def handle_new_user(update: Update, context: CallbackContext) -> None:
    bot_added_to_group(update, context)
    msg = None
    group_id = update.message.chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = fetch_group_info(update, context)
    if group_data is None:
        group_name = "the group"  # Default text if group name not available
    else:
        group_name = group_data.get('group_info', {}).get('group_username', "the group")
        
    for member in update.message.new_chat_members:
            user_id = member.id
            chat_id = update.message.chat.id

            if user_id == context.bot.id:
                return

            # Mute the new user
            context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False)
            )

            if anti_raid.is_raid():
                msg = update.message.reply_text(f'Anti-raid triggered! Please wait {anti_raid.time_to_wait()} seconds before new users can join.')
                
                # Get the user_id of the user that just joined
                user_id = update.message.new_chat_members[0].id

                # Kick the user that just joined
                context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                return

            current_time = datetime.now(timezone.utc).isoformat()  # Get the current date/time in ISO 8601 format
            
            group_doc.update({f'unverified_users.{user_id}': { # Update only the specific user's data within the unverified_users map
                'timestamp': current_time,
                'challenge': None  # Initializes with no challenge
            }})
            print(f"New user {user_id} added to unverified users in group {group_id} at {current_time}")

            auth_url = f"https://t.me/sypher_robot?start=authenticate_{chat_id}_{user_id}"
            keyboard = [
                [InlineKeyboardButton("Start Authentication", url=auth_url)]
            ]
            if group_data is not None and group_data.get('premium') and group_data.get('premium_features', {}).get('welcome_header'):

                blob = bucket.blob(f'sypherbot/public/welcome_message_header/welcome_message_header_{group_id}.jpg')

                welcome_image_url = blob.generate_signed_url(expiration=timedelta(minutes=15))

                # print(f"Welcome image URL: {welcome_image_url}")

                reply_markup = InlineKeyboardMarkup(keyboard)
                msg = update.message.reply_photo(
                    photo=welcome_image_url,
                    caption=f"Welcome to {group_name}! Please press the button below to authenticate.",
                    reply_markup=reply_markup
                )
            else:
                msg = update.message.reply_text(
                    f"Welcome to {group_name}! Please press the button below to authenticate.",
                    reply_markup=reply_markup
                )

    if msg is not None:
        track_message(msg)
            
def authentication_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    _, group_id, user_id = query.data.split('_')

    print(f"Authenticating user {user_id} for group {group_id}")

    group_doc = db.collection('groups').document(group_id)
    group_data = group_doc.get().to_dict()

    if group_data:
        unverified_users = group_data.get('unverified_users', {})  # Get as dictionary
        verification_info = group_data.get('verification_info', {})
        verification_type = verification_info.get('verification_type', 'simple')

        print(f"Authentication type: {verification_type}")

        # Check if the user ID is in the KEYS of the unverified_users mapping
        if str(user_id) in unverified_users:  
            if verification_type == 'simple':
                authenticate_user(context, group_id, user_id)
            elif verification_type == 'math' or verification_type == 'word':
                authentication_challenge(
                    update, context, verification_type, group_id, user_id
                )
            else:
                query.edit_message_text(text="Invalid authentication type configured.")
        else:
            query.edit_message_text(
                text="You are already verified, not a member or need to restart authentication."
            )
    else:
        query.edit_message_text(text="No such group exists.")

def authentication_challenge(update: Update, context: CallbackContext, verification_type, group_id, user_id):
    group_doc = db.collection('groups').document(group_id)

    if verification_type == 'math':
        challenges = [MATH_0, MATH_1, MATH_2, MATH_3, MATH_4]
        index = random.randint(0, 4)
        math_challenge = challenges[index]

        blob = bucket.blob(f'sypherbot/private/auth/math_{index}.jpg')
        image_url = blob.generate_signed_url(expiration=timedelta(minutes=15))

        print(f"image_url: {image_url}")

        response = requests.get(image_url)
        print(f"Response: {response}")

        print(f"Math challenge: {math_challenge}")

        keyboard = [
            [
                InlineKeyboardButton("1", callback_data=f'mauth_{user_id}_{group_id}_1'),
                InlineKeyboardButton("2", callback_data=f'mauth_{user_id}_{group_id}_2'),
                InlineKeyboardButton("3", callback_data=f'mauth_{user_id}_{group_id}_3')
            ],
            [
                InlineKeyboardButton("4", callback_data=f'mauth_{user_id}_{group_id}_4'),
                InlineKeyboardButton("5", callback_data=f'mauth_{user_id}_{group_id}_5'),
                InlineKeyboardButton("6", callback_data=f'mauth_{user_id}_{group_id}_6')
            ],
            [
                InlineKeyboardButton("7", callback_data=f'mauth_{user_id}_{group_id}_7'),
                InlineKeyboardButton("8", callback_data=f'mauth_{user_id}_{group_id}_8'),
                InlineKeyboardButton("9", callback_data=f'mauth_{user_id}_{group_id}_9')
            ],
            [
                InlineKeyboardButton("0", callback_data=f'mauth_{user_id}_{group_id}_0')
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=image_url,
            caption="What is the answer to this math equation?",
            reply_markup=reply_markup
        )

        # print(f"image_path: {image_url}")

        # Update Firestore with the challenge
        group_doc.update({
            f'unverified_users.{user_id}.challenge': math_challenge
        })
        print(f"Stored math challenge for user {user_id} in group {group_id}: {math_challenge}")

    elif verification_type == 'word':
        challenges = [WORD_0, WORD_1, WORD_2, WORD_3, WORD_4, WORD_5, WORD_6, WORD_7, WORD_8]
        original_challenges = challenges.copy()  # Copy the original list before shuffling
        random.shuffle(challenges)
        word_challenge = challenges[0]  # The word challenge is the first word in the shuffled list
        index = original_challenges.index(word_challenge)  # Get the index of the word challenge in the original list

        blob = bucket.blob(f'sypherbot/private/auth/word_{index}.jpg')
        image_url = blob.generate_signed_url(expiration=timedelta(minutes=15), version="v4")
    
        keyboard = []

        print(f"Word challenge: {word_challenge}")
    
        num_buttons_per_row = 3
        for i in range(0, len(challenges), num_buttons_per_row):
            row = [InlineKeyboardButton(word, callback_data=f'wauth_{user_id}_{group_id}_{word}') 
                for word in challenges[i:i + num_buttons_per_row]]
            keyboard.append(row)
    
        reply_markup = InlineKeyboardMarkup(keyboard)
    
        context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=open(image_url),
            caption="Identify the correct word in the image:",
            reply_markup=reply_markup
        )

        # print(f"image_path: {image_url}")
    
        # Update Firestore with the challenge
        group_doc.update({
            f'unverified_users.{user_id}.challenge': word_challenge
        })
        print(f"Stored word challenge for user {user_id} in group {group_id}: {word_challenge}")
    
    else:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Invalid authentication type. Please try again."
        )

def callback_word_response(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    print("Processing word response.")

    _, user_id, group_id, response = query.data.split('_')
    user_id = str(user_id)
    group_id = str(group_id)

    print(f"User ID: {user_id} - Group ID: {group_id} - Response: {response}")

    group_doc = db.collection('groups').document(group_id)
    group_data = group_doc.get()

    if group_data.exists:
        group_data_dict = group_data.to_dict()

        # Check if the user is in the unverified users mapping
        if str(user_id) in group_data_dict.get('unverified_users', {}):
            user_challenge_data = group_data_dict['unverified_users'][str(user_id)] # Get the user's challenge data
            challenge_answer = user_challenge_data.get('challenge')  # Extract only the challenge value as the required answer

            print(f"Challenge answer: {challenge_answer}")

            if response == challenge_answer:
                authenticate_user(context, group_id, user_id)
            else:
                authentication_failed(update, context, group_id, user_id)

        else:
            query.edit_message_caption(
                caption="Authentication data not found. Please start over or contact an admin."
            )
    else:
        query.edit_message_caption(
            caption="Group data not found. Please start over or contact an admin."
        )

def callback_math_response(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    print("Processing math response.")

    _, user_id, group_id, response = query.data.split('_')
    user_id = str(user_id)
    group_id = str(group_id)
    response = int(response)

    print(f"User ID: {user_id} - Group ID: {group_id} - Response: {response}")

    group_doc = db.collection('groups').document(group_id)
    group_data = group_doc.get()

    if group_data.exists:
        group_data_dict = group_data.to_dict()

        # Check if the user is in the unverified users mapping
        if str(user_id) in group_data_dict.get('unverified_users', {}):
            user_challenge_data = group_data_dict['unverified_users'][str(user_id)] # Get the user's challenge data
            challenge_answer = user_challenge_data.get('challenge')  # Extract only the challenge value as the required answer

            print(f"Challenge answer: {challenge_answer}")

            if response == challenge_answer:
                authenticate_user(context, group_id, user_id)
            else:
                authentication_failed(update, context, group_id, user_id)
        else:
            query.edit_message_caption(
                caption="Authentication data not found. Please start over or contact an admin."
            )
    else:
        query.edit_message_caption(
            caption="Group data not found. Please start over or contact an admin."
        )

def authenticate_user(context, group_id, user_id):
    print(f"Authenticating user {user_id} in group {group_id}")
    group_doc = db.collection('groups').document(group_id)

    # Get the current group document
    group_data = group_doc.get().to_dict()

    if 'unverified_users' in group_data and user_id in group_data['unverified_users']:
        del group_data['unverified_users'][user_id]

    print(f"Removed user {user_id} from unverified users in group {group_id}")

    # Write the updated group data back to Firestore
    group_doc.set(group_data)

    context.bot.send_message(
        chat_id=user_id,
        text="Authentication successful! You may now participate in the group chat."
    )

    # Lift restrictions in the group chat for the authenticated user
    context.bot.restrict_chat_member(
        chat_id=int(group_id),
        user_id=int(user_id),
        permissions=ChatPermissions(
            can_send_messages=True,
            can_add_web_page_previews=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_invite_users=False
        )
    )
    print(f"User {user_id} authenticated. Restrictions lifted in group {group_id}")

def authentication_failed(update: Update, context: CallbackContext, group_id, user_id):
    print(f"Authentication failed for user {user_id} in group {group_id}")
    group_doc = db.collection('groups').document(group_id)

    # Get the current group document
    group_data = group_doc.get().to_dict()

    if 'unverified_users' in group_data and user_id in group_data['unverified_users']:
        group_data['unverified_users'][user_id] = None

    print(f"Reset challenge for user {user_id} in group {group_id}")

    # Write the updated group data back to Firestore
    group_doc.set(group_data)

    # Delete the original message
    context.bot.delete_message(
        chat_id=update.effective_chat.id,
        message_id=update.callback_query.message.message_id
    )

    # Send a message to the user instructing them to start the authentication process again
    context.bot.send_message(
        chat_id=user_id,
        text="Authentication failed. Please start the authentication process again by clicking on the 'Start Authentication' button."
    )

# def clear_unverified_users(context: CallbackContext):
#     # Get current time
#     now = datetime.now(timezone.utc)
#     print("Clearing unverified users in all groups")

#     # Get all group documents that potentially have unverified users
#     group_docs = db.collection('groups').where('unverified_users', '!=', {}).get()

#     for group_doc in group_docs:
#         group_id = group_doc.id
#         group_data = group_doc.to_dict()
#         unverified_users = group_data.get('unverified_users', {})

#         # Prepare update data for Firestore
#         update_data = {}

#         for user_id, user_info in unverified_users.items():
#             user_time = datetime.fromisoformat(user_info['timestamp'])
#             # Check if the user has been unverified for too long (e.g., more than 10 minutes)
#             if (now - user_time).total_seconds() > 60:
#                 try:
#                     # Attempt to kick the unverified user
#                     context.bot.ban_chat_member(chat_id=group_id, user_id=user_id)
#                     print(f"Kicked unverified user {user_id} from group {group_id}")
#                     # Mark for clearing from the database
#                     update_data[f'unverified_users.{user_id}'] = firestore.DELETE_FIELD
#                 except Exception as e:
#                     print(f"Failed to kick user {user_id} from group {group_id}: {e}")

#         # Clear the unverified_users mapping in the group document if necessary
#         if update_data:
#             group_doc.reference.update(update_data)

#     # Wait for some time before next run, consider using a scheduled job instead of sleep
#     time.sleep(60)

# endregion User Authentication

#region Ethereum Logic

#region Chart
def fetch_ohlcv_data(time_frame, chain, liquidity_address):
    now = datetime.now()
    one_hour_ago = now - timedelta(hours=1)
    start_of_hour_timestamp = int(one_hour_ago.timestamp())
    chain_lowercase = chain.lower()

    url = f"https://api.geckoterminal.com/api/v2/networks/{chain_lowercase}/pools/{liquidity_address}/ohlcv/{time_frame}"
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

#region Buybot
def monitor_transfers(web3_instance, liquidity_address, group_data):
    contract_address = group_data['token']['contract_address']
    abi = group_data['token']['abi']
    contract = web3_instance.eth.contract(address=contract_address, abi=abi)

    block_to_check = 14896750
    
    print(f"Checking transfers from block {block_to_check} for group {group_data['group_id']}")

    # --- Filter for events in the specific block ---
    transfer_filter = contract.events.Transfer.createFilter(
        fromBlock=block_to_check,
        toBlock=block_to_check,  # Only check this specific block
        argument_filters={'from': liquidity_address}
    )

    for event in transfer_filter.get_new_entries():
        handle_transfer_event(event, group_data)

def handle_transfer_event(event, group_data):
    amount = event['args']['value']
    web3_instance = web3_instances.get(group_data['token']['chain'])
    
    # Convert amount to token decimal
    decimals = group_data['token'].get('decimals', 18)
    token_amount = Decimal(amount) / (10 ** decimals)

    print(f"Received transfer event for {token_amount} tokens.")

    # # Fetch the USD price of the token
    # token_price_in_usd = get_token_price_in_fiat(group_data['token']['contract_address'], 'usd', web3_instance)
    # if token_price_in_usd is not None:
    #     token_price_in_usd = Decimal(token_price_in_usd)
    #     total_value_usd = token_amount * token_price_in_usd
    #     if total_value_usd < 500:
    #         print("Ignoring small buy")
    #         return
    #     value_message = f" ({total_value_usd:.2f} USD)"
    #     header_emoji, buyer_emoji = categorize_buyer(total_value_usd)
    # else:
    #     print("Failed to fetch token price in USD.")
    #     return

    # # Format message with Markdown
    # message = f"{header_emoji} BUY ALERT {header_emoji}\n\n{buyer_emoji} {token_amount} TOKEN{value_message}"
    # print(f"Sending buy message for group {group_data['group_id']}")
    # send_buy_message(message, group_data['group_id'])

# def categorize_buyer(usd_value):
#     if usd_value < 2500:
#         return "💸", "🐟"
#     elif usd_value < 5000:
#         return "💰", "🐬"
#     else:
#         return "🤑", "🐳"
    
# def send_buy_message(text, group_id):
#     bot = telegram.Bot(token=TELEGRAM_TOKEN)
#     msg = bot.send_message(chat_id=group_id, text=text, parse_mode='Markdown')
#     if msg is not None:
#         track_message(msg)

#endregion Buybot

#region Price Fetching
def get_token_price_in_weth(contract_address):
    apiUrl = f"https://api.dexscreener.com/latest/dex/tokens/{contract_address}"
    try:
        response = requests.get(apiUrl)
        response.raise_for_status()
        data = response.json()
        
        if data['pairs'] and len(data['pairs']) > 0:
            # Find the pair with WETH as the quote token
            weth_pair = next((pair for pair in data['pairs'] if pair['quoteToken']['symbol'] == 'WETH'), None)
            
            if weth_pair:
                price_in_weth = weth_pair['priceNative']
                return price_in_weth
            else:
                print("No WETH pair found for this token.")
                return None
        else:
            print("No pairs found for this token.")
            return None
    except requests.RequestException as e:
        print(f"Error fetching token price from DexScreener: {e}")
        return None
    
def get_weth_price_in_fiat(currency):
    apiUrl = f"https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies={currency}"
    try:
        response = requests.get(apiUrl)
        response.raise_for_status()  # This will raise an exception for HTTP errors
        data = response.json()
        return data['ethereum'][currency]
    except requests.RequestException as e:
        print(f"Error fetching WETH price from CoinGecko: {e}")
        return None
    
def get_token_price_in_fiat(contract_address, currency):
    # Fetch price of token in WETH
    token_price_in_weth = get_token_price_in_weth(contract_address)
    if token_price_in_weth is None:
        print("Could not retrieve token price in WETH.")
        return None

    # Fetch price of WETH in the specified currency
    weth_price_in_fiat = get_weth_price_in_fiat(currency)
    if weth_price_in_fiat is None:
        print(f"Could not retrieve WETH price in {currency}.")
        return None

    # Calculate token price in the specified currency
    token_price_in_fiat = float(token_price_in_weth) * weth_price_in_fiat
    return token_price_in_fiat
#endregion Price Fetching

#endregion Ethereum Logic

#region Admin Controls
def mute(update: Update, context: CallbackContext) -> None:
    msg = None
    chat_id = update.effective_chat.id

    group_doc = db.collection('groups').document(str(chat_id))
    group_data = group_doc.get().to_dict()

    if group_data is None or not group_data.get('admin', {}).get('mute_command', False):
        msg = update.message.reply_text("Admins are not allowed to use the mute command in this group.")
        if msg is not None:
            track_message(msg)
        return

    if is_user_admin(update, context):
        if update.message.reply_to_message is None:
            msg = update.message.reply_text("This command must be used in response to another message!")
            if msg is not None:
                track_message(msg)
            return
        reply_to_message = update.message.reply_to_message
        if reply_to_message:
            user_id = reply_to_message.from_user.id
            username = reply_to_message.from_user.username or reply_to_message.from_user.first_name

        context.bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=ChatPermissions(can_send_messages=False))
        msg = update.message.reply_text(f"User {username} has been muted.")

        # Add the user to the muted_users mapping in the database
        group_doc.update({
            f'muted_users.{user_id}': datetime.now().isoformat()
        })
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
    
    if msg is not None:
        track_message(msg)

def unmute(update: Update, context: CallbackContext) -> None:
    msg = None
    chat_id = update.effective_chat.id

    group_doc = db.collection('groups').document(str(chat_id))
    group_data = group_doc.get().to_dict()

    if group_data is None or not group_data.get('admin', {}).get('mute_command', False):
        msg = update.message.reply_text("Admins are not allowed to use the unmute command in this group.")
        if msg is not None:
            track_message(msg)
        return

    if is_user_admin(update, context):
        if not context.args:
            msg = update.message.reply_text("You must provide a username to unmute.")
            if msg is not None:
                track_message(msg)
            return
        username_to_unmute = context.args[0].lstrip('@')

        for user_id in group_data.get('muted_users', {}):
            try:
                user_info = context.bot.get_chat_member(chat_id=chat_id, user_id=user_id).user
                if user_info.username == username_to_unmute:
                    context.bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=ChatPermissions(can_send_messages=True))
                    msg = update.message.reply_text(f"User @{username_to_unmute} has been unmuted.")

                    # Remove the user from the muted_users mapping in the database
                    group_doc.update({
                        f'muted_users.{user_id}': firestore.DELETE_FIELD
                    })
                    break
            except Exception:
                continue
        else:
            msg = update.message.reply_text("Can't find that user.")
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
    
    if msg is not None:
        track_message(msg)

def warn(update: Update, context: CallbackContext):
    msg = None
    if is_user_admin(update, context) and update.message.reply_to_message:
        user_id = str(update.message.reply_to_message.from_user.id)
        group_id = str(update.effective_chat.id)
        group_doc = db.collection('groups').document(group_id)
        
        try:
            doc_snapshot = group_doc.get()
            if doc_snapshot.exists:
                group_data = doc_snapshot.to_dict()
                warnings_dict = group_data.get('warnings', {})
                
                # Increment the warning count for the user
                current_warnings = warnings_dict.get(user_id, 0)
                current_warnings += 1
                warnings_dict[user_id] = current_warnings

                # Update the group document with the new warnings count
                group_doc.update({'warnings': warnings_dict})
                msg = update.message.reply_text(f"{user_id} has been warned. Total warnings: {current_warnings}")
                
                # Check if the user has reached the warning limit
                process_warns(update, context, user_id, current_warnings)

            else:
                msg = update.message.reply_text("Group data not found.")
        
        except Exception as e:
            msg = update.message.reply_text(f"Failed to update warnings: {str(e)}")

    if msg is not None:
        track_message(msg)

def clear_warns_for_user(update: Update, context: CallbackContext):
    msg = None
    chat_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(chat_id))
    group_data = group_doc.get().to_dict()

    if is_user_admin(update, context):
        if not context.args:
            msg = update.message.reply_text("You must provide a username to clear warnings.")
            if msg is not None:
                track_message(msg)
            return
        username_to_clear = context.args[0].lstrip('@')

        for user_id in group_data.get('warnings', {}):
            try:
                user_info = context.bot.get_chat_member(chat_id=chat_id, user_id=user_id).user
                if user_info.username == username_to_clear:
                    # Remove the user from the warnings mapping
                    group_doc.update({
                        f'warnings.{user_id}': firestore.DELETE_FIELD
                    })
                    msg = update.message.reply_text(f"Warnings cleared for @{username_to_clear}.")
                    break
            except Exception:
                continue
        else:
            msg = update.message.reply_text("Can't find that user.")
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
    
    if msg is not None:
        track_message(msg)

def process_warns(update: Update, context: CallbackContext, user_id: str, warnings: int):
    msg = None
    if warnings >= 3:
        try:
            context.bot.ban_chat_member(update.message.chat.id, int(user_id))
            msg = update.message.reply_text(f"Goodbye {user_id}!")
        except Exception as e:
            msg = update.message.reply_text(f"Failed to kick {user_id}: {str(e)}")
        
    if msg is not None:
        track_message(msg)

def check_warnings(update: Update, context: CallbackContext):
    msg = None
    if is_user_admin(update, context) and update.message.reply_to_message:
        user_id = str(update.message.reply_to_message.from_user.id)
        group_id = str(update.effective_chat.id)
        group_doc = db.collection('groups').document(group_id)

        try:
            doc_snapshot = group_doc.get()
            if doc_snapshot.exists:
                group_data = doc_snapshot.to_dict()
                warnings_dict = group_data.get('warnings', {})

                # Get the warning count for the user
                current_warnings = warnings_dict.get(user_id, 0)

                msg = update.message.reply_text(f"{user_id} has {current_warnings} warnings.")

            else:
                msg = update.message.reply_text("Group data not found.")

        except Exception as e:
            msg = update.message.reply_text(f"Failed to check warnings: {str(e)}")

    if msg is not None:
        track_message(msg)

def kick(update: Update, context: CallbackContext) -> None:
    msg = None
    chat_id = update.effective_chat.id

    if is_user_admin(update, context):
        if update.message.reply_to_message is None:
            msg = update.message.reply_text("This command must be used in response to another message!")
            if msg is not None:
                track_message(msg)
            return
        reply_to_message = update.message.reply_to_message
        if reply_to_message:
            user_id = reply_to_message.from_user.id
            username = reply_to_message.from_user.username or reply_to_message.from_user.first_name

        context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        msg = update.message.reply_text(f"User {username} has been kicked.")
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
    
    if msg is not None:
        track_message(msg)

def block(update: Update, context: CallbackContext):
    msg = None
    if is_user_admin(update, context):
        command_text = update.message.text[len('/block '):].strip().lower()

        if not command_text:
            msg = update.message.reply_text("Please provide some text to block.")
            return

        group_id = str(update.effective_chat.id)
        group_doc = db.collection('groups').document(group_id)
        blocklist_field = 'blocklist'

        try:
            # Fetch current blocklist from the group's document
            doc_snapshot = group_doc.get()
            if doc_snapshot.exists:
                group_data = doc_snapshot.to_dict()
                current_blocklist = group_data.get(blocklist_field, "")
                new_blocklist = current_blocklist + command_text + ", "

                # Update the blocklist in the group's document
                group_doc.update({blocklist_field: new_blocklist})
                msg = update.message.reply_text(f"'{command_text}' added to blocklist!")
                print("Updated blocklist:", new_blocklist)

            else:
                # If no blocklist exists, create it with the current command text
                group_doc.set({blocklist_field: command_text + ", "})
                msg = update.message.reply_text(f"'{command_text}' blocked!")
                print("Created new blocklist with:", command_text)

        except Exception as e:
            msg = update.message.reply_text(f"Failed to update blocklist: {str(e)}")
            print(f"Error updating blocklist: {e}")

    if msg is not None:
        track_message(msg)

def remove_block(update: Update, context: CallbackContext):
    msg = None
    if is_user_admin(update, context):
        command_text = update.message.text[len('/removeblock '):].strip().lower()

        if not command_text:
            msg = update.message.reply_text("Please provide some text to remove.")
            return

        group_id = str(update.effective_chat.id)
        group_doc = db.collection('groups').document(group_id)
        blocklist_field = 'blocklist'

        try:
            # Fetch the current blocklist from the group's document
            doc_snapshot = group_doc.get()
            if doc_snapshot.exists:
                group_data = doc_snapshot.to_dict()
                current_blocklist = group_data.get(blocklist_field, "")
                # Create a list from the blocklist string, remove the word, and convert back to string
                blocklist_items = current_blocklist.split(', ')
                if command_text in blocklist_items:
                    blocklist_items.remove(command_text)
                    new_blocklist = ', '.join(blocklist_items)
                    # Update the blocklist in the group's document
                    group_doc.update({blocklist_field: new_blocklist})
                    msg = update.message.reply_text(f"'{command_text}' removed from blocklist!")
                    print("Updated blocklist after removal:", new_blocklist)
                else:
                    msg = update.message.reply_text(f"'{command_text}' is not in the blocklist.")

            else:
                msg = update.message.reply_text("No blocklist found for this group.")

        except Exception as e:
            msg = update.message.reply_text(f"Failed to remove from blocklist: {str(e)}")
            print(f"Error removing from blocklist: {e}")

    if msg is not None:
        track_message(msg)

def blocklist(update: Update, context: CallbackContext):
    msg = None
    if is_user_admin(update, context):
        group_id = str(update.effective_chat.id)
        group_doc = db.collection('groups').document(group_id)

        try:
            doc_snapshot = group_doc.get()
            if doc_snapshot.exists:
                group_data = doc_snapshot.to_dict()
                blocklist_field = 'blocklist'
                current_blocklist = group_data.get(blocklist_field, "")
                
                if current_blocklist:
                    # Split the blocklist string by commas and strip spaces
                    blocklist_items = [item.strip() for item in current_blocklist.split(',') if item.strip()]
                    message = "\n".join(blocklist_items)
                    update.message.reply_text(message)
                else:
                    msg = update.message.reply_text("The blocklist is currently empty.")
            else:
                msg = update.message.reply_text("No blocklist found for this group.")
        
        except Exception as e:
            msg = update.message.reply_text(f"Failed to retrieve blocklist: {str(e)}")
            print(f"Error retrieving blocklist: {e}")

    if msg is not None:
        track_message(msg)

def allow(update: Update, context: CallbackContext):
    msg = None
    if is_user_admin(update, context):
        command_text = update.message.text[len('/allow '):].strip()

        # Normalize the URL by removing the 'http://' or 'https://'
        if command_text.startswith('http://'):
            command_text = command_text[7:]
        elif command_text.startswith('https://'):
            command_text = command_text[8:]

        group_id = str(update.effective_chat.id)
        group_doc = db.collection('groups').document(group_id)
        allowlist_field = 'allowlist'

        try:
            # Fetch current allowlist from the group's document
            doc_snapshot = group_doc.get()
            if doc_snapshot.exists:
                group_data = doc_snapshot.to_dict()
                current_allowlist = group_data.get(allowlist_field, "")
                new_allowlist = current_allowlist + command_text + ", "

                # Update the allowlist in the group's document
                group_doc.update({allowlist_field: new_allowlist})
                msg = update.message.reply_text(f"'{command_text}' added to allowlist!")
                print("Updated allowlist:", new_allowlist)

            else:
                # If no allowlist exists, create it with the current command text
                group_doc.set({allowlist_field: command_text + ", "})
                msg = update.message.reply_text(f"'{command_text}' allowlisted!")
                print("Created new allowlist with:", command_text)

        except Exception as e:
            msg = update.message.reply_text(f"Failed to update allowlist: {str(e)}")
            print(f"Error updating allowlist: {e}")

    if msg is not None:
        track_message(msg)

def allowlist(update: Update, context: CallbackContext):
    msg = None
    if is_user_admin(update, context):
        group_id = str(update.effective_chat.id)
        group_doc = db.collection('groups').document(group_id)

        try:
            doc_snapshot = group_doc.get()
            if doc_snapshot.exists:
                group_data = doc_snapshot.to_dict()
                allowlist_field = 'allowlist'
                current_allowlist = group_data.get(allowlist_field, "")
                
                if current_allowlist:
                    # Split the allowlist string by commas and strip spaces
                    allowlist_items = [item.strip() for item in current_allowlist.split(',') if item.strip()]
                    message = "\n".join(allowlist_items)
                    update.message.reply_text(message)
                else:
                    msg = update.message.reply_text("The allowlist is currently empty.")
            else:
                msg = update.message.reply_text("No allowlist found for this group.")
        
        except Exception as e:
            msg = update.message.reply_text(f"Failed to retrieve allowlist: {str(e)}")
            print(f"Error retrieving allowlist: {e}")

    if msg is not None:
        track_message(msg)

def cleargames(update: Update, context: CallbackContext) -> None:
    msg = None
    chat_id = update.effective_chat.id

    if is_user_admin(update, context):
        keys_to_delete = [key for key in context.chat_data.keys() if key.startswith(f"{chat_id}_")]
        for key in keys_to_delete:
            del context.chat_data[key]
            print(f"Deleted key: {key}")
    
        msg = update.message.reply_text("All active games have been cleared.")
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
        print(f"User {update.effective_user.id} tried to clear games but is not an admin in chat {update.effective_chat.id}.")
    
    if msg is not None:
        track_message(msg)

def cleanbot(update: Update, context: CallbackContext):
    global bot_messages
    if is_user_admin(update, context):
        chat_id = update.effective_chat.id

        messages_to_delete = [msg_id for cid, msg_id in bot_messages if cid == chat_id]

        for msg_id in messages_to_delete:
            try:
                context.bot.delete_message(chat_id, msg_id)
            except Exception as e:
                print(f"Failed to delete message {msg_id}: {str(e)}")  # Handle errors

        bot_messages = [(cid, msg_id) for cid, msg_id in bot_messages if cid != chat_id]
#endregion Admin Controls

#region User Controls
def report(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    reported_user = update.message.reply_to_message.from_user.username

    # Get the list of admins
    chat_admins = context.bot.get_chat_administrators(chat_id)
    admin_usernames = ['@' + admin.user.username for admin in chat_admins if admin.user.username is not None]

    if reported_user in admin_usernames:
        # If the reported user is an admin, send a message saying that admins cannot be reported
        context.bot.send_message(chat_id, text="Nice try lol")
    else:
        admin_mentions = ' '.join(admin_usernames)

        report_message = f"Reported Message to admins.\n {admin_mentions}\n"
        # Send the message as plain text
        message = context.bot.send_message(chat_id, text=report_message, disable_web_page_preview=True)

        # Immediately edit the message to remove the usernames, using Markdown for the new message
        context.bot.edit_message_text(chat_id=chat_id, message_id=message.message_id, text="⚠️ Message Reported to Admins ⚠️", parse_mode='Markdown', disable_web_page_preview=True)

def save(update: Update, context: CallbackContext):
    msg = None
    if rate_limit_check():
        target_message = update.message.reply_to_message
        if target_message is None:
            msg = update.message.reply_text("Please reply to the message you want to save with /save.")
            return

        user = update.effective_user
        if user is None:
            msg = update.message.reply_text("Could not identify the user.")
            return

        # Determine the type of the message
        content = None
        content_type = None
        if target_message.text:
            content = target_message.text
            content_type = 'text'
        elif target_message.photo:
            content = target_message.photo[-1].file_id
            content_type = 'photo'
        elif target_message.audio:
            content = target_message.audio.file_id
            content_type = 'audio'
        elif target_message.document:
            content = target_message.document.file_id
            content_type = 'document'
        elif target_message.animation:
            content = target_message.animation.file_id
            content_type = 'animation'
        elif target_message.video:
            content = target_message.video.file_id
            content_type = 'video'
        elif target_message.voice:
            content = target_message.voice.file_id
            content_type = 'voice'
        elif target_message.video_note:
            content = target_message.video_note.file_id
            content_type = 'video_note'
        elif target_message.sticker:
            content = target_message.sticker.file_id
            content_type = 'sticker'
        elif target_message.contact:
            content = target_message.contact
            content_type = 'contact'
        elif target_message.location:
            content = target_message.location
            content_type = 'location'
        else:
            msg = update.message.reply_text("The message format is not supported.")
            return

        # Send the message or media to the user's DM
        try:
            if content_type == 'text':
                context.bot.send_message(chat_id=user.id, text=content)
            elif content_type in ['photo', 'audio', 'document', 'animation', 'video', 'voice', 'video_note', 'sticker']:
                send_function = getattr(context.bot, f'send_{content_type}')
                send_function(chat_id=user.id, **{content_type: content})
            elif content_type == 'contact':
                context.bot.send_contact(chat_id=user.id, phone_number=content.phone_number, first_name=content.first_name, last_name=content.last_name)
            elif content_type == 'location':
                context.bot.send_location(chat_id=user.id, latitude=content.latitude, longitude=content.longitude)
            

            msg = update.message.reply_text("Check your DMs.")
        except Exception as e:
            msg = update.message.reply_text(f"Failed to send DM: {str(e)}")
    else:
        msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')

    if msg is not None:
        track_message(msg)

#region Play Game
def play(update: Update, context: CallbackContext) -> None:
    if rate_limit_check():
        keyboard = [[InlineKeyboardButton("Click Here to Start a Game!", callback_data='startGame')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        base_dir = os.path.dirname(__file__)
        photo_path = os.path.join(base_dir, 'assets', 'banner.gif')
        
        with open(photo_path, 'rb') as photo:
            context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo, caption='Welcome to deSypher! Click the button below to start a game!', reply_markup=reply_markup)
    else:
        update.message.reply_text('Bot rate limit exceeded. Please try again later.')

def end_game(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    key = f"{chat_id}_{user_id}"  # Unique key for each user-chat combination

    # Check if there's an ongoing game for this user in this chat
    if key in context.chat_data:
        # Delete the game message
        if 'game_message_id' in context.chat_data[key]:
            context.bot.delete_message(chat_id=chat_id, message_id=context.chat_data[key]['game_message_id'])

        # Clear the game data
        del context.chat_data[key]
        update.message.reply_text("Your game has been deleted.")
    else:
        update.message.reply_text("You don't have an ongoing game.")

def handle_start_game(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    if query.data == 'startGame':
        user_id = query.from_user.id
        first_name = query.from_user.first_name  # Get the user's first name
        chat_id = query.message.chat_id
        key = f"{chat_id}_{user_id}"

        # Check if the user already has an ongoing game
        if key in context.chat_data:
            # Delete the old message
            context.bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
            # Send a new message
            context.bot.send_message(chat_id=chat_id, text="You already have an active game. Please use the command */endgame* to end your previous game before starting a new one!", parse_mode='Markdown')
            return

        word = fetch_random_word()
        print(f"Chosen word: {word} for key: {key}")

        # Initialize the game state for this user in this chat
        if key not in context.chat_data:
            context.chat_data[key] = {
                'chosen_word': word,
                'guesses': [],
                'game_message_id': None,
                'chat_id': chat_id,
                'player_name': first_name
            }

        num_rows = 4
        row_template = "⬛⬛⬛⬛⬛"
        game_layout = "\n".join([row_template for _ in range(num_rows)])
        
        # Delete the old message
        context.bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)

        # Send a new message with the game layout and store the message ID
        game_message = context.bot.send_message(chat_id=chat_id, text=f"*{first_name}'s Game*\nPlease guess a five letter word!\n\n{game_layout}", parse_mode='Markdown')
        context.chat_data[key]['game_message_id'] = game_message.message_id
        
        print(f"Game started for {first_name} in {chat_id} with message ID {game_message.message_id}")

def handle_guess(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    key = f"{chat_id}_{user_id}"
    msg = None

    if key not in context.chat_data:
        # No active game found for key
        return
    
    player_name = context.chat_data[key].get('player_name', 'Player')

    # Check if there's an ongoing game for this user in this chat
    if key not in context.chat_data or 'chosen_word' not in context.chat_data[key]:
        # print(f"No active game found for key: {key}")
        return

    user_guess = update.message.text.lower()
    chosen_word = context.chat_data[key].get('chosen_word')

    # Check if the guess is not 5 letters and the user has an active game
    if len(user_guess) != 5 or not user_guess.isalpha():
        print(f"Invalid guess length: {len(user_guess)}")
        msg = update.message.reply_text("Please guess a five letter word containing only letters!")
        return

    if 'guesses' not in context.chat_data[key]:
        context.chat_data[key]['guesses'] = []
        print(f"Initialized guesses list for key: {key}")

    context.chat_data[key]['guesses'].append(user_guess)
    print(f"Updated guesses list: {context.chat_data[key]['guesses']}")

    # Check the guess and build the game layout
    def get_game_layout(guesses, chosen_word):
        layout = []
        for guess in guesses:
            row = ""
            for i, char in enumerate(guess):
                if char == chosen_word[i]:
                    row += "🟩"  # Correct letter in the correct position
                elif char in chosen_word:
                    row += "🟨"  # Correct letter in the wrong position
                else:
                    row += "🟥"  # Incorrect letter
            layout.append(row + " - " + guess)

        while len(layout) < 4:
            layout.append("⬛⬛⬛⬛⬛")
        
        return "\n".join(layout)

    # Delete the previous game message
    if 'game_message_id' in context.chat_data[key]:
        try:
            context.bot.delete_message(chat_id=chat_id, message_id=context.chat_data[key]['game_message_id'])
        except telegram.error.BadRequest:
            print("Message to delete not found")

    # Update the game layout
    game_layout = get_game_layout(context.chat_data[key]['guesses'], chosen_word)

    # Check if it's not the 4th guess and the user hasn't guessed the word correctly before sending the game message
    if len(context.chat_data[key]['guesses']) < 4 and user_guess != chosen_word:
        game_message = context.bot.send_message(chat_id=chat_id, text=f"*{player_name}'s Game*\nPlease guess a five letter word!\n\n{game_layout}", parse_mode='Markdown')
    
        # Store the new message ID
        context.chat_data[key]['game_message_id'] = game_message.message_id

    # Check if the user has guessed the word correctly
    if user_guess == chosen_word:
        # Delete the previous game message
        if 'game_message_id' in context.chat_data[key]:
            try:
                context.bot.delete_message(chat_id=chat_id, message_id=context.chat_data[key]['game_message_id'])
            except telegram.error.BadRequest:
                print("Message to delete not found")

        # Update the game layout
        game_layout = get_game_layout(context.chat_data[key]['guesses'], chosen_word)
        game_message = context.bot.send_message(chat_id=chat_id, text=f"*{player_name}'s Final Results:*\n\n{game_layout}\n\nCongratulations! You've guessed the word correctly!\n\nIf you enjoyed this, you can play the game with SYPHER tokens on the [website](https://desypher.net/).", parse_mode='Markdown')
        print("User guessed the word correctly. Clearing game data.")
        del context.chat_data[key]
    elif len(context.chat_data[key]['guesses']) >= 4:
        # Delete the previous game message
        if 'game_message_id' in context.chat_data[key]:
            try:
                context.bot.delete_message(chat_id=chat_id, message_id=context.chat_data[key]['game_message_id'])
            except telegram.error.BadRequest:
                print("Message to delete not found")

        # Update the game layout
        game_layout = get_game_layout(context.chat_data[key]['guesses'], chosen_word)
        game_message = context.bot.send_message(chat_id=chat_id, text=f"*{player_name}'s Final Results:*\n\n{game_layout}\n\nGame over! The correct word was: {chosen_word}\n\nTry again on the [website](https://desypher.net/), you'll probably have a better time playing with SPYHER tokens.", parse_mode='Markdown')

        print(f"Game over. User failed to guess the word {chosen_word}. Clearing game data.")
        del context.chat_data[key]
    if msg is not None:
        track_message(msg)

def fetch_random_word() -> str:
    with open('words.json', 'r') as file:
        data = json.load(file)
        words = data['words']
        return random.choice(words)
#endregion Play Game

def price(update: Update, context: CallbackContext) -> None:
    # Fetch group-specific contract information
    group_data = fetch_group_info(update, context)
    if group_data is None:
        return  # Early exit if no data found
    
    token_data = group_data.get('token')
    if not token_data:
        update.message.reply_text("Token data not found for this group.")
        return

    contract_address = token_data.get('contract_address')

    if not contract_address:
        update.message.reply_text("Contract address not found for this group.")
        return

    # Proceed with price fetching
    currency = context.args[0].lower() if context.args else 'usd'
    if currency not in ['usd', 'eur', 'jpy', 'gbp', 'aud', 'cad', 'mxn']:
        update.message.reply_text("Unsupported currency. Please use 'usd', 'eur', 'jpy', 'gbp', 'aud', 'cad', or 'mxn'.")
        return
    
    token_price_in_fiat = get_token_price_in_fiat(contract_address, currency)
    
    symbol = token_data.get('symbol')
    if not symbol:
        formatted_price = format(token_price_in_fiat, '.4f')
        update.message.reply_text(f"{currency.upper()}: {formatted_price}")
        return

    if token_price_in_fiat is not None:
        formatted_price = format(token_price_in_fiat, '.4f')
        update.message.reply_text(f"{symbol} • {currency.upper()}: {formatted_price}")
    else:
        update.message.reply_text(f"Failed to retrieve the price of the token in {currency.upper()}.")

def ca(update: Update, context: CallbackContext) -> None:
    msg = None
    if rate_limit_check():
        group_data = fetch_group_info(update, context)
        if group_data is None:
            return  # Early exit if no data is found
        
        token_data = group_data.get('token')
        if not token_data:
            update.message.reply_text("Token data not found for this group.")
            return

        contract_address = token_data.get('contract_address')

        if not contract_address:
            update.message.reply_text("Contract address not found for this group.")
            return
        
        msg = update.message.reply_text(contract_address)

    else:
        msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
    if msg is not None:
        track_message(msg)

def liquidity(update: Update, context: CallbackContext) -> None:
    msg = None
    group_data = fetch_group_info(update, context)
    if group_data is None:
        return

    token_data = group_data.get('token')
    if not token_data:
        update.message.reply_text("Token data not found for this group.")
        return

    lp_address = token_data.get('liquidity_address')
    chain = token_data.get('chain')

    if not lp_address or not chain:
        update.message.reply_text("Liquidity address or chain not found for this group.")
        return

    if rate_limit_check():
        liquidity_usd = get_liquidity(chain, lp_address)
        if liquidity_usd:
            msg = update.message.reply_text(f"Liquidity: ${liquidity_usd}")
        else:
            msg = update.message.reply_text("Failed to fetch liquidity data.")
    else:
        msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
    if msg is not None:
        track_message(msg)

def get_liquidity(chain, lp_address):
    try:
        chain_lower = chain.lower()
        url = f"https://api.geckoterminal.com/api/v2/networks/{chain_lower}/pools/{lp_address}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        liquidity_usd = data['data']['attributes']['reserve_in_usd']
        return liquidity_usd
    except requests.RequestException as e:
        print(f"Failed to fetch liquidity data: {str(e)}")
        return None
    
def volume(update: Update, context: CallbackContext) -> None:
    msg = None
    group_data = fetch_group_info(update, context)

    if group_data is None:
        return
    
    token_data = group_data.get('token')
    if not token_data:
        update.message.reply_text("Token data not found for this group.")
        return

    lp_address = token_data.get('liquidity_address')
    chain = token_data.get('chain')    

    if not lp_address or not chain:
        update.message.reply_text("Liquidity address or chain not found for this group.")
        return

    if rate_limit_check():
        volume_24h_usd = get_volume(chain, lp_address)
        if volume_24h_usd:
            msg = update.message.reply_text(f"24-hour trading volume in USD: ${volume_24h_usd}")
        else:
            msg = update.message.reply_text("Failed to fetch volume data.")
    else:
        msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
    if msg is not None:
        track_message(msg)
    
def get_volume(chain, lp_address):
    try:
        chain_lower = chain.lower()
        url = f"https://api.geckoterminal.com/api/v2/networks/{chain_lower}/pools/{lp_address}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        volume_24h_usd = data['data']['attributes']['volume_usd']['h24']
        return volume_24h_usd
    except requests.RequestException as e:
        print(f"Failed to fetch volume data: {str(e)}")
        return None

def chart(update: Update, context: CallbackContext) -> None:
    args = context.args
    time_frame = 'minute'  # default to minute if no argument is provided
    
    if args:
        interval_arg = args[0].lower()
        if interval_arg == 'h':
            time_frame = 'hour'
        elif interval_arg == 'd':
            time_frame = 'day'
        elif interval_arg == 'm':
            time_frame = 'minute'
        else:
            msg = update.message.reply_text('Invalid time frame specified. Please use /chart with m, h, or d.')
            return
        
    if rate_limit_check():
        # Fetch group-specific contract information
        group_data = fetch_group_info(update, context)
        if group_data is None:
            return  # Early exit if no data is found
        
        token_data = group_data.get('token')
        if not token_data:
            update.message.reply_text("Token data not found for this group.")
            return   
        chain = token_data.get('chain')
        if not chain:
            update.message.reply_text("Chain not found for this group.")
            return
        liquidity_address = token_data.get('liquidity_address')
        if not liquidity_address:
            update.message.reply_text("Contract address not found for this group.")
            return
        name = token_data.get('name')
        if not name:
            update.message.reply_text("Token name not found for this group.")
            return
        symbol = token_data.get('symbol')
        if not symbol:
            update.message.reply_text("Token symbol not found for this group.")
            return

        group_id = str(update.effective_chat.id)  # Ensuring it's always the chat ID if not found in group_data
        ohlcv_data = fetch_ohlcv_data(time_frame, chain, liquidity_address)
        
        if ohlcv_data:
            chain_lower = chain.lower()
            data_frame = prepare_data_for_chart(ohlcv_data)
            plot_candlestick_chart(data_frame, group_id)  # Pass group_id here

            dexscreener_url = f"https://dexscreener.com/{chain_lower}/{liquidity_address}"
            dextools_url = f"https://www.dextools.io/app/{chain_lower}/pair-explorer/{liquidity_address}"

            keyboard = [
                [
                    InlineKeyboardButton("Dexscreener", url=dexscreener_url),
                    InlineKeyboardButton("Dextools", url=dextools_url),
                ]
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)

            msg = update.message.reply_photo(
                photo=open(f'/tmp/candlestick_chart_{group_id}.png', 'rb'),
                caption=f"*{name}* • *{symbol}* • {time_frame.capitalize()} Chart",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        else:
            msg = update.message.reply_text('Failed to fetch data or generate chart. Please try again later.')
    else:
        msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
    if msg is not None:
        track_message(msg)

def website(update: Update, context: CallbackContext) -> None:
    msg = None
    if rate_limit_check():
        group_data = fetch_group_info(update, context)
        if group_data is None:
            return  # Early exit if no data is found
        
        group_info = group_data.get('group_info')

        if group_info is None:
            msg = update.message.reply_text("Group info not found.")
            return
        
        group_website = group_info.get('group_website')

        if group_website is None:
            msg = update.message.reply_text("Group link not found.")
            return
        
        msg = update.message.reply_text(f"{group_website}")
    
    if msg is not None:
        track_message(msg)
#endregion User Controls



#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#




def admin_commands(update: Update, context: CallbackContext) -> None:
    msg = None
    if is_user_admin(update, context):
        msg = update.message.reply_text(
            "*Admin commands:*\n"
            "*/cleanbot*\nCleans all bot messages\n"
            "*/cleargames*\nClear all active games\n"
            "*/mute*\nMute a user\n"
            "*/unmute*\nUnmute a user\n"
            "*/kick*\nKick a user\n"
            "*/warn*\nWarn a user\n"
            "*/filter*\nFilter a word or phrase\n"
            "*/removefilter*\nRemove a filtered word or phrase\n"
            "*/filterlist*\nList all filtered words and phrases\n",
            parse_mode='Markdown'
        )
    
    if msg is not None:
        track_message(msg)

def commands(update: Update, context: CallbackContext) -> None:
    msg = None
    if rate_limit_check():
        keyboard = [
            [
                InlineKeyboardButton("/play", callback_data='commands_play'),
                InlineKeyboardButton("/endgame", callback_data='commands_endgame')
            ],
            [
                InlineKeyboardButton("/website", callback_data='commands_website'),
                InlineKeyboardButton("/contract", callback_data='commands_contract')
            ],
            [
                InlineKeyboardButton("/price", callback_data='commands_price'),
                InlineKeyboardButton("/chart", callback_data='commands_chart')
            ],
            [
                InlineKeyboardButton("/liquidity", callback_data='commands_liquidity'),
                InlineKeyboardButton("/volume", callback_data='commands_volume')
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = update.message.reply_text('Welcome to Sypher Bot! Below you will find all my commands:', reply_markup=reply_markup)
    else:
        msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
    if msg is not None:
        track_message(msg)

def command_buttons(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    update = Update(update.update_id, message=query.message)

    if query.data == 'commands_play':
        play(update, context)
    elif query.data == 'commands_endgame':
        end_game(update, context)
    elif query.data == 'commands_contract':
        ca(update, context)
    elif query.data == 'commands_website':
        website(update, context)
    elif query.data == 'commands_price':
        price(update, context)
    elif query.data == 'commands_chart':
        chart(update, context)
    elif query.data == 'commands_liquidity':
        liquidity(update, context)
    elif query.data == 'commands_volume':
        volume(update, context)








def main() -> None:
    # Create the Updater and pass it your bot's token
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    
    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # dispatcher.add_handler(MessageHandler(Filters.status_update.left_chat_member, delete_service_messages))
    
    # General Slash Command Handlers
    dispatcher.add_handler(CommandHandler("commands", commands))
    dispatcher.add_handler(CommandHandler("play", play))
    dispatcher.add_handler(CommandHandler("endgame", end_game))
    dispatcher.add_handler(CommandHandler("contract", ca))
    dispatcher.add_handler(CommandHandler("ca", ca))
    dispatcher.add_handler(CommandHandler("price", price))
    dispatcher.add_handler(CommandHandler("chart", chart))
    dispatcher.add_handler(CommandHandler("liquidity", liquidity))
    dispatcher.add_handler(CommandHandler("lp", liquidity))
    dispatcher.add_handler(CommandHandler("volume", volume))
    dispatcher.add_handler(CommandHandler("report", report))
    dispatcher.add_handler(CommandHandler("save", save))

    # Admin Slash Command Handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("setup", start))
    dispatcher.add_handler(CommandHandler("admincommands", admin_commands))
    dispatcher.add_handler(CommandHandler('cleanbot', cleanbot))
    dispatcher.add_handler(CommandHandler('cleargames', cleargames))
    dispatcher.add_handler(CommandHandler("kick", kick))
    dispatcher.add_handler(CommandHandler("block", block))
    dispatcher.add_handler(CommandHandler("removeblock", remove_block))
    dispatcher.add_handler(CommandHandler("blocklist", blocklist))
    dispatcher.add_handler(CommandHandler("allow", allow))
    dispatcher.add_handler(CommandHandler("allowlist", allowlist))
    dispatcher.add_handler(CommandHandler("mute", mute))
    dispatcher.add_handler(CommandHandler("unmute", unmute))
    dispatcher.add_handler(CommandHandler("mutelist", check_mute_list))
    dispatcher.add_handler(CommandHandler("warn", warn))
    dispatcher.add_handler(CommandHandler("warnlist", check_warn_list))
    dispatcher.add_handler(CommandHandler('clearwarns', clear_warns_for_user))
    dispatcher.add_handler(CommandHandler("warnings", check_warnings))


    dispatcher.add_handler(CommandHandler("test", check_eth_price))

    # General Callbacks
    dispatcher.add_handler(CallbackQueryHandler(handle_start_game, pattern='^startGame$'))
    dispatcher.add_handler(CallbackQueryHandler(command_buttons, pattern='^commands_'))    
    
    # Register the message handler for new users
    dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, handle_new_user))
    dispatcher.add_handler(MessageHandler(Filters.status_update.left_chat_member, bot_removed_from_group))
    dispatcher.add_handler(MessageHandler((Filters.text | Filters.document) & (~Filters.command), handle_message))
    dispatcher.add_handler(MessageHandler(Filters.photo, handle_image))

    # Authentication Callbacks
    dispatcher.add_handler(CallbackQueryHandler(authentication_callback, pattern='^authenticate_'))
    dispatcher.add_handler(CallbackQueryHandler(callback_math_response, pattern='^mauth_'))
    dispatcher.add_handler(CallbackQueryHandler(callback_word_response, pattern='^wauth_'))
    
    # Setup Callback
    dispatcher.add_handler(CallbackQueryHandler(setup_home_callback, pattern='^setup_home$'))

    # Setup Admin Callbacks
    dispatcher.add_handler(CallbackQueryHandler(setup_admin_callback, pattern='^setup_admin$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_mute_callback, pattern='^setup_mute$'))
    dispatcher.add_handler(CallbackQueryHandler(enable_mute_callback, pattern='^enable_mute$'))
    dispatcher.add_handler(CallbackQueryHandler(disable_mute_callback, pattern='^disable_mute$'))
    dispatcher.add_handler(CallbackQueryHandler(check_mute_list_callback, pattern='^check_mute_list$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_warn_callback, pattern='^setup_warn$'))
    dispatcher.add_handler(CallbackQueryHandler(enable_warn_callback, pattern='^enable_warn$'))
    dispatcher.add_handler(CallbackQueryHandler(disable_warn_callback, pattern='^disable_warn$'))
    dispatcher.add_handler(CallbackQueryHandler(check_warn_list_callback, pattern='^check_warn_list$'))
    dispatcher.add_handler(CallbackQueryHandler(set_max_warns_callback, pattern='^set_max_warns$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_blocklist_callback, pattern='^setup_blocklist$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_allowlist_callback, pattern='^setup_allowlist$'))
    dispatcher.add_handler(CallbackQueryHandler(reset_admin_settings_callback, pattern='^reset_admin_settings$'))
    
    # Setup Crypto Callbacks
    dispatcher.add_handler(CallbackQueryHandler(setup_crypto_callback, pattern='^setup_crypto$'))
    dispatcher.add_handler(CallbackQueryHandler(check_token_details_callback, pattern='^check_token_details$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_contract, pattern='^setup_contract$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_liquidity, pattern='^setup_liquidity$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_ABI, pattern='^setup_ABI$'))
    dispatcher.add_handler(CallbackQueryHandler(send_example_abi, pattern='^example_abi$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_chain, pattern='^setup_chain$'))
    dispatcher.add_handler(CallbackQueryHandler(cancel_callback, pattern='^cancel$'))
    dispatcher.add_handler(CallbackQueryHandler(handle_chain, pattern='^(ethereum|arbitrum|polygon|base|optimism|fantom|avalanche|binance|harmony|mantle)$'))
    dispatcher.add_handler(CallbackQueryHandler(reset_token_details_callback, pattern='^reset_token_details$'))

    # Setup Authentication Callbacks
    dispatcher.add_handler(CallbackQueryHandler(setup_verification_callback, pattern='^setup_verification$'))
    dispatcher.add_handler(CallbackQueryHandler(check_verification_settings_callback, pattern='^check_verification_settings$'))
    dispatcher.add_handler(CallbackQueryHandler(enable_verification_callback, pattern='^enable_verification$'))
    dispatcher.add_handler(CallbackQueryHandler(disable_verification_callback, pattern='^disable_verification$'))
    dispatcher.add_handler(CallbackQueryHandler(simple_verification_callback, pattern='^simple_verification$'))
    dispatcher.add_handler(CallbackQueryHandler(math_verification_callback, pattern='^math_verification$'))
    dispatcher.add_handler(CallbackQueryHandler(word_verification_callback, pattern='^word_verification$'))
    dispatcher.add_handler(CallbackQueryHandler(timeout_verification_callback, pattern='^timeout_verification$'))
    dispatcher.add_handler(CallbackQueryHandler(handle_timeout_callback, pattern='^vtimeout_'))

    # Setup Premium Callbacks
    dispatcher.add_handler(CallbackQueryHandler(setup_premium_callback, pattern='^setup_premium$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_welcome_message_header_callback, pattern='^setup_welcome_message_header$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_buybot_message_header_callback, pattern='^setup_buybot_message_header$'))
    dispatcher.add_handler(CallbackQueryHandler(enable_sypher_trust_callback, pattern='^enable_sypher_trust$'))
    dispatcher.add_handler(CallbackQueryHandler(disable_sypher_trust_callback, pattern='^disable_sypher_trust$'))
    dispatcher.add_handler(CallbackQueryHandler(sypher_trust_preferences_callback, pattern='^sypher_trust_preferences$'))
    dispatcher.add_handler(CallbackQueryHandler(sypher_trust_relaxed_callback, pattern='^sypher_trust_relaxed$'))
    dispatcher.add_handler(CallbackQueryHandler(sypher_trust_moderate_callback, pattern='^sypher_trust_moderate$'))
    dispatcher.add_handler(CallbackQueryHandler(sypher_trust_strict_callback, pattern='^sypher_trust_strict$'))

    # Start the Bot
    updater.start_polling()

    # Start Threads
    # clear_unverified_users_with_context = partial(clear_unverified_users, context=updater.dispatcher)
    # monitoring_thread = threading.Thread(target=clear_unverified_users_with_context)
    # monitoring_thread.start()
    start_monitoring_groups()

    # Run the bot until stopped
    updater.idle()

if __name__ == '__main__':
    main()