import os
import re
import time
import json
import random
import requests
import telegram
import threading
import pandas as pd
import firebase_admin
import mplfinance as mpf
from web3 import Web3
from decimal import Decimal
from dotenv import load_dotenv
from datetime import datetime, timedelta
from collections import deque, defaultdict
from firebase_admin import credentials, firestore
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
### /antiraid - Manage the anti-raid system
#### /antiraid end /anti-raid [user_amount] [time_out] [anti_raid_time]
### /mute /unmute - Reply to a message with this command to toggle mute for a user
### /kick - Reply to a message with this command to kick a user from the chat
### /warn - Reply to a message with this command to warn a user
### /filter - Filter a word or phrase from the chat
### /removefilter - Remove a word or phrase from the filter list
### /filterlist - Get a list of filtered words
#

load_dotenv()

TELEGRAM_TOKEN = os.getenv('BOT_API_TOKEN')

eth_address_pattern = re.compile(r'\b0x[a-fA-F0-9]{40}\b')
url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
domain_pattern = re.compile(r'\b[\w\.-]+\.[a-zA-Z]{2,}\b')

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

firebase_admin.initialize_app(cred)

db = firestore.client()

print("Firebase initialized.")
#endregion Firebase

#region Classes
class AntiSpam:
    def __init__(self, rate_limit, time_window, mute_time):
        self.rate_limit = rate_limit
        self.time_window = time_window
        self.mute_time = mute_time
        self.user_messages = defaultdict(list)
        self.blocked_users = defaultdict(lambda: 0)
        print(f"Initialized AntiSpam with rate_limit={rate_limit}, time_window={time_window}, mute_time={mute_time}")

    def is_spam(self, user_id):
        current_time = time.time()
        if current_time < self.blocked_users[user_id]:
            return True
        self.user_messages[user_id] = [msg_time for msg_time in self.user_messages[user_id] if current_time - msg_time < self.time_window]
        self.user_messages[user_id].append(current_time)
        if len(self.user_messages[user_id]) > self.rate_limit:
            self.blocked_users[user_id] = current_time + self.mute_time
            return True
        return False

    def time_to_wait(self, user_id):
        current_time = time.time()
        if current_time < self.blocked_users[user_id]:
            return int(self.blocked_users[user_id] - current_time)
        return 0

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

anti_spam = AntiSpam(rate_limit=5, time_window=10, mute_time=60)
anti_raid = AntiRaid(user_amount=25, time_out=30, anti_raid_time=180)

RATE_LIMIT = 100  # Maximum number of allowed commands
TIME_PERIOD = 60  # Time period in seconds
last_check_time = time.time()
command_count = 0

user_verification_progress = {}

bot_messages = []

def track_message(message):
    bot_messages.append((message.chat.id, message.message_id))
    print(f"Tracked message: {message.message_id}")

#region Bot Logic
def bot_added_to_group(update: Update, context: CallbackContext) -> None:
    new_members = update.message.new_chat_members
    if any(member.id != context.bot.id for member in new_members):
        return
    if any(member.id == context.bot.id for member in new_members):
        group_id = update.effective_chat.id
        print(f"Adding group {group_id} to database.")
        group_doc = db.collection('groups').document(str(group_id))
        group_doc.set({
            'group_id': group_id,
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
        else:
            # Bot is not admin, send the "Give me admin perms" message
            setup_keyboard = [[InlineKeyboardButton("Setup", callback_data='setup_home')]]
            setup_markup = InlineKeyboardMarkup(setup_keyboard)
            msg = update.message.reply_text(
                "Hey, please give me admin permissions, then click 'Setup' to get started.",
                reply_markup=setup_markup
            )
 
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

def is_user_admin(update: Update, context: CallbackContext) -> bool:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if update.effective_chat.type == 'private':
        print("User is in a private chat.")
        return False

    # Check if the user is an admin in this chat
    chat_admins = context.bot.get_chat_administrators(chat_id)
    user_is_admin = any(admin.user.id == user_id for admin in chat_admins)

    return user_is_admin

def fetch_group_info(update: Update, context: CallbackContext):
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

def handle_message(update: Update, context: CallbackContext) -> None:
    
    delete_blocked_addresses(update, context)
    delete_blocked_phrases(update, context)
    delete_blocked_links(update, context)

    handle_guess(update, context)

    handle_setup_inputs_from_user(update, context)

    if is_user_admin(update, context):
        return
    
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    username = update.message.from_user.username or update.message.from_user.first_name
    msg = None

    if anti_spam.is_spam(user_id):
        mute_time = anti_spam.mute_time  # Get the mute time from AntiSpam class
        msg = update.message.reply_text(f'{username}, you are spamming. You have been muted for {mute_time} seconds.')

        # Mute the user for the mute time
        until_date = int(time.time() + mute_time)
        context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )

        # Schedule job to unmute the user
        job_queue = context.job_queue
        job_queue.run_once(unmute_user, mute_time, context={'chat_id': chat_id, 'user_id': user_id})
    
    if msg is not None:
        track_message(msg)

def delete_blocked_addresses(update: Update, context: CallbackContext):
    if is_user_admin(update, context):
        # Don't block admin messages
        return
    
    print("Checking message for unallowed addresses...")

    group_data = fetch_group_info(update, context)
    if group_data is None:
        return
    
    message_text = update.message.text
    
    if message_text is None:
        print("No text in message.")
        return

    found_addresses = eth_address_pattern.findall(message_text)

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
    if is_user_admin(update, context):
        # Don't block admin messages
        return
    
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
    if is_user_admin(update, context):
        # Don't block admin messages
        return

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
#endregion Bot Logic

#region Bot Setup
def cancel_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    print("User pressed cancel, returning to home setup screen.")
    setup_home(update, context)
    context.user_data['setup_stage'] = None

def cancel_end_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    print("User pressed cancel, ending setup.")
    query.message.delete()
    context.user_data['setup_stage'] = None

def handle_setup_inputs_from_user(update: Update, context: CallbackContext) -> None:
    setup_stage = context.user_data.get('setup_stage')
    print("Checking if user is in setup mode.")
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
    elif setup_stage == 'setup_password_verification':
        handle_verification_question(update, context)
    elif setup_stage == 'setup_verification_question':
        handle_verification_answer(update, context)

def start(update: Update, context: CallbackContext) -> None:
    msg = None
    chat_type = update.effective_chat.type
    user_id = update.effective_user.id

    if chat_type == "private":
        if rate_limit_check():
            keyboard = [
                [InlineKeyboardButton("Add me to your group!", url=f"https://t.me/sypher_robot?startgroup=0")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            msg = update.message.reply_text(
                'Hello! I am Sypher Bot. If you are here to verify, now you may return to main chat.\n\n'
                'If you want me to manage you group, get started with the button below.',
                reply_markup=reply_markup
            )
        else:
            msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
    if msg is not None:
        track_message(msg)

def setup_home_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    # Check if the bot is an admin
    chat_member = context.bot.get_chat_member(update.effective_chat.id, context.bot.id)
    if not chat_member.can_invite_users:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Please give me admin permissions first!'
        )
        return

    update = Update(update.update_id, message=query.message)

    if query.data == 'setup_home':
        setup_home(update, context)

def setup_home(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    # Get the invite link
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
            InlineKeyboardButton("Verification", callback_data='setup_verification'),
            InlineKeyboardButton("Ethereum", callback_data='setup_ethereum')
        ],
        [InlineKeyboardButton("Cancel", callback_data='cancel_end')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Welcome to the setup home page. Please use the buttons below to setup your bot!',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None

    if msg is not None:
        track_message(msg)

def setup_ethereum_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    update = Update(update.update_id, message=query.message)

    if query.data == 'setup_ethereum':
        setup_ethereum(update, context)

def setup_ethereum(update: Update, context: CallbackContext) -> None:
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
            InlineKeyboardButton("Cancel", callback_data='cancel')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='This is the ethereum setup page. Here you can setup the Buybot, Pricebot and Chartbot functionality.\n\nYour ABI is required for the Buybot functionality to work.',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None

    if msg is not None:
        track_message(msg)

def setup_contract(update: Update, context: CallbackContext) -> None:
    msg = None
    query = update.callback_query
    query.answer()

    keyboard = [
        [InlineKeyboardButton("Cancel", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Please respond with your contract address.',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = 'contract'
    print("Requesting contract address.")

    if msg is not None:
        track_message(msg)

def handle_contract_address(update: Update, context: CallbackContext) -> None:
    msg = None
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
        
            complete_token_setup(group_id)
        else:
            msg = update.message.reply_text("Please send a valid Contract Address!")
            

    if msg is not None:
        track_message(msg)

def setup_liquidity(update: Update, context: CallbackContext) -> None:
    msg = None
    query = update.callback_query
    query.answer()

    keyboard = [
        [InlineKeyboardButton("Cancel", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Please respond with your liquidity address.',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = 'liquidity'
    print("Requesting liquidity address.")

    if msg is not None:
        track_message(msg)

def handle_liquidity_address(update: Update, context: CallbackContext) -> None:
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

            complete_token_setup(group_id)
        else:
            # Check if update.message is not None before using it
            if update.message is not None:
                msg = update.message.reply_text("Please send a valid Liquidity Address!")
            elif update.callback_query is not None:
                msg = update.callback_query.message.reply_text("Please send a valid Liquidity Address!")

    if msg is not None:
        track_message(msg)

def setup_ABI(update: Update, context: CallbackContext) -> None:
    msg = None
    query = update.callback_query
    query.answer()

    keyboard = [
        [InlineKeyboardButton("Cancel", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Please upload your ABI as a JSON file.\n\nExample file structure: ["function1(uint256)", "function2(string)"]',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = 'ABI'
    print("Requesting ABI file.")

    if msg is not None:
        track_message(msg)

def handle_ABI(update: Update, context: CallbackContext) -> None:
    msg = None
    if context.user_data.get('setup_stage') == 'ABI':
        document = update.message.document
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

                complete_token_setup(group_id)
        else:
            msg = update.message.reply_text("Please make sure the file is a JSON file.")
        

    if msg is not None:
        track_message(msg)

def setup_chain(update: Update, context: CallbackContext) -> None:
    msg = None
    query = update.callback_query
    query.answer()

    keyboard = [
        [
            InlineKeyboardButton("Ethereum", callback_data='ethereum'),
            InlineKeyboardButton("Base", callback_data='base')

        ],
        [
            InlineKeyboardButton("Arbitrum", callback_data='arbitrum'),
            InlineKeyboardButton("Optimism", callback_data='optimism'),
            InlineKeyboardButton("Polygon", callback_data='polygon')
        ],
        [
            InlineKeyboardButton("Fantom", callback_data='fantom'),
            InlineKeyboardButton("Avalanche", callback_data='avalanche'),
            InlineKeyboardButton("Binance", callback_data='binance')
        ],
        [
            InlineKeyboardButton("Aptos", callback_data='aptos'),
            InlineKeyboardButton("Harmony", callback_data='harmony'),
            InlineKeyboardButton("Mantle", callback_data='mantle')
        ],
        [InlineKeyboardButton("Cancel", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Please choose your chain from the list.',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = 'chain'
    print("Requesting Chain.")

    if msg is not None:
        track_message(msg)

def handle_chain(update: Update, context: CallbackContext) -> None:
    if context.user_data.get('setup_stage') == 'chain':
        chain = update.callback_query.data
        group_id = update.effective_chat.id
        print(f"Adding chain {chain} to group {group_id}")
        group_doc = db.collection('groups').document(str(group_id))
        group_doc.update({'token.chain': chain})
        context.user_data['setup_stage'] = None

        complete_token_setup(group_id)

def complete_token_setup(group_id: str):
    # Fetch the group data from Firestore
    group_doc = db.collection('groups').document(str(group_id))
    group_data = group_doc.get().to_dict()

    token_data = group_data.get('token')
    if not token_data:
        print("Token data not found for this group.")
        return

    # Get the contract address, ABI, and chain from the group data
    contract_address = token_data['contract_address']
    if contract_address is None:
        print(f"Contract address not found in group {group_id}, token setup incomplete.")
        return
    abi = token_data.get('abi')
    if abi is None:
        print(f"ABI not found in group {group_id}, token setup incomplete.")
        return
    else:
        abi = json.loads(abi)
    chain = token_data.get('chain')
    if chain is None:
        print(f"Chain not found in group {group_id}, token setup incomplete.")
        return

    # Determine the provider URL based on the chain
    provider_url = os.getenv(f'{chain.upper()}_ENDPOINT')
    if provider_url is None:
        print(f"Provider URL for chain {chain} not found in environment variables")
        return

    # Connect to the Ethereum network
    web3 = Web3(Web3.HTTPProvider(provider_url))

    # Create a contract object
    contract = web3.eth.contract(address=contract_address, abi=abi)

    # Call the name and symbol functions
    try:
        token_name = contract.functions.name().call()
        token_symbol = contract.functions.symbol().call()
    except Exception as e:
        print(f"Failed to get token name and symbol: {e}")
        return

    # Update the Firestore document with the token name and symbol
    group_doc.update({
        'token': {
            'name': token_name,
            'symbol': token_symbol,
        }
    })

    print(f"Added token name {token_name} and symbol {token_symbol} to group {group_id}")

def setup_verification_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    update = Update(update.update_id, message=query.message)

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
            InlineKeyboardButton("Math", callback_data='math_verification'),
            InlineKeyboardButton("Password", callback_data='password_verification')
        ],
        [InlineKeyboardButton("Cancel", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Please choose whether to enable or disable verification.\n\nYou may also choose the verification method for your group.\n\nMath will present a random simple math equation to the new user.\n\nIf you choose password, you will be prompted to enter a question, then an answer. The answer must be 5 letters.\n\nExample: "What is a red fruit that falls from a tree? [apple].',
        reply_markup=reply_markup
    )
    context.user_data['setup_stage'] = None

    if msg is not None:
        track_message(msg)

def enable_verification_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    update = Update(update.update_id, message=query.message)

    if query.data == 'enable_verification':
        enable_verification(update, context)

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
                'verification_type': 'none'
            }
        })
    else:
        group_doc.update({
            'verification_info': {
                'verification': True,
                'verification_type': 'none'
            }
        })

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Verification enabled for this group. Please choose a verification type.'
    )

    if msg is not None:
        track_message(msg)

def disable_verification_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    update = Update(update.update_id, message=query.message)

    if query.data == 'disable_verification':
        disable_verification(update, context)

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
        text='Verification disabled for this group.'
    )

    if msg is not None:
        track_message(msg)

def math_verification_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    update = Update(update.update_id, message=query.message)

    if query.data == 'math_verification':
        math_verification(update, context)

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
                'verification_type': 'math'
            }
        })
    else:
        group_doc.update({
            'verification_info': {
                'verification': True,
                'verification_type': 'math',
                'verification_question': 'none',
                'verification_answer': 'none'
            }
        })

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Math verification enabled for this group.'
    )

    if msg is not None:
        track_message(msg)

def password_verification_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    update = Update(update.update_id, message=query.message)

    if query.data == 'password_verification':
        password_verification(update, context)

def password_verification(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))

    group_data = group_doc.get().to_dict()

    if group_data is None:
        group_doc.set({
            'group_id': group_id,
            'verification_info': {
                'verification': True,
                'verification_type': 'password'
            }
        })
    else:
        group_doc.update({
            'verification_info': {
                'verification': True,
                'verification_type': 'password'
            }
        })

    # Set the state in user_data
    context.user_data['setup_stage'] = 'setup_password_verification'

    # Ask the question for new users
    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='What question would you like to use for verification?\n\nThis question will be presented to new users when they join your group.\n\nThey will need to answer the question with your five letter answer to gain access.'
    )

    if msg is not None:
        track_message(msg)
    
def handle_verification_question(update: Update, context: CallbackContext) -> None:
    msg = None
    # Store the question in user_data
    context.user_data['verification_question'] = update.message.text

    # Ask for the answer to the question
    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='What is the five letter answer to the question?'
    )

    context.user_data['setup_stage'] = 'setup_verification_question'

    if msg is not None:
        track_message(msg)

def handle_verification_answer(update: Update, context: CallbackContext) -> None:
    msg = None
    # Store the answer in user_data
    context.user_data['verification_answer'] = update.message.text

    # Update the database with the question and answer
    group_id = update.effective_chat.id
    group_doc = db.collection('groups').document(str(group_id))
    group_doc.update({
        'verification_info': {
            'verification': True,
            'verification_question': context.user_data['verification_question'],
            'verification_answer': context.user_data['verification_answer']
        }
    })

    # Clear the state in user_data
    context.user_data['setup_stage'] = None

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Password verification setup complete.'
    )

    if msg is not None:
        track_message(msg)
#endregion Bot Setup

#region Ethereum

#region Chart
def fetch_ohlcv_data(time_frame, chain, liquidity_address):
    now = datetime.now()
    one_hour_ago = now - timedelta(hours=1)
    start_of_hour_timestamp = int(one_hour_ago.timestamp())

    url = f"https://api.geckoterminal.com/api/v2/networks/{chain}/pools/{liquidity_address}/ohlcv/{time_frame}"
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

#endregion Ethereum

#region Admin Controls
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

def process_warns(update: Update, context: CallbackContext, user_id: str, warnings: int):
    msg = None
    if warnings >= 3:
        try:
            context.bot.kick_chat_member(update.message.chat.id, int(user_id))
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

        context.bot.kick_chat_member(chat_id=chat_id, user_id=user_id)
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
    if token_price_in_fiat is not None:
        formatted_price = format(token_price_in_fiat, '.4f')
        update.message.reply_text(f"SYPHER • {currency.upper()}: {formatted_price}") # TODO: Replace 'Sypher' with Token name from group
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
        url = f"https://api.geckoterminal.com/api/v2/networks/{chain}/pools/{lp_address}"
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
        url = f"https://api.geckoterminal.com/api/v2/networks/{chain}/pools/{lp_address}"
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

        group_id = str(update.effective_chat.id)  # Ensuring it's always the chat ID if not found in group_data
        ohlcv_data = fetch_ohlcv_data(time_frame, chain, liquidity_address)
        if ohlcv_data:
            data_frame = prepare_data_for_chart(ohlcv_data)
            plot_candlestick_chart(data_frame, group_id)  # Pass group_id here
            msg = update.message.reply_photo(
                photo=open(f'/tmp/candlestick_chart_{group_id}.png', 'rb'),
                caption=f"\n[Dexscreener](https://dexscreener.com/{chain}/{liquidity_address}) • [Dextools](https://www.dextools.io/app/{chain}/pair-explorer/{liquidity_address})\n",
                parse_mode='Markdown'
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












def unmute_user(context: CallbackContext) -> None:
    job = context.job
    context.bot.restrict_chat_member(
        chat_id=job.context['chat_id'],
        user_id=job.context['user_id'],
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_send_videos=True,
            can_send_photos=True,
            can_send_audios=True
            )
    )





def admin_commands(update: Update, context: CallbackContext) -> None:
    msg = None
    if is_user_admin(update, context):
        msg = update.message.reply_text(
            "*Admin commands:*\n"
            "*/cleanbot*\nCleans all bot messages\n"
            "*/cleargames*\nClear all active games\n"
            "*/antiraid*\nManage anti-raid settings\n"
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


def antiraid(update: Update, context: CallbackContext) -> None:
    msg = None
    args = context.args

    if is_user_admin(update, context):
        if not args:
            msg = update.message.reply_text("Usage: /antiraid end or /antiraid [user_amount] [time_out] [anti_raid_time]")
            return

        command = args[0]
        if command == 'end':
            if anti_raid.is_raid():
                anti_raid.anti_raid_end_time = 0
                msg = update.message.reply_text("Anti-raid timer ended. System reset to normal operation.")
                print("Anti-raid timer ended. System reset to normal operation.")
            else:
                msg = update.message.reply_text("No active anti-raid to end.")
        else:
            try:
                user_amount = int(args[0])
                time_out = int(args[1])
                anti_raid_time = int(args[2])
                anti_raid.user_amount = user_amount
                anti_raid.time_out = time_out
                anti_raid.anti_raid_time = anti_raid_time
                msg = update.message.reply_text(f"Anti-raid settings updated: user_amount={user_amount}, time_out={time_out}, anti_raid_time={anti_raid_time}")
                print(f"Updated AntiRaid settings to user_amount={user_amount}, time_out={time_out}, anti_raid_time={anti_raid_time}")
            except (IndexError, ValueError):
                msg = update.message.reply_text("Invalid arguments. Usage: /antiraid [user_amount] [time_out] [anti_raid_time]")
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
        print(f"User {update.effective_user.id} tried to use /antiraid but is not an admin in chat {update.effective_chat.id}.")
    
    if msg is not None:
        track_message(msg)

def toggle_mute(update: Update, context: CallbackContext, mute: bool) -> None:
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

        context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=not mute,
                can_send_media_messages=not mute,
                can_send_other_messages=not mute,
                can_send_videos=not mute,
                can_send_photos=not mute,
                can_send_audios=not mute
                )
        )

        action = "muted" if mute else "unmuted"
        msg = update.message.reply_text(f"User {username} has been {action}.")
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
    
    if msg is not None:
        track_message(msg)

def mute(update: Update, context: CallbackContext) -> None:
    toggle_mute(update, context, True)

def unmute(update: Update, context: CallbackContext) -> None:
    toggle_mute(update, context, False)



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


#region Main Slash Commands
# def sypher(update: Update, context: CallbackContext) -> None:
#     msg = None
#     if rate_limit_check():
#         msg = update.message.reply_text(
#             'SYPHER is the native token of deSypher. It is used to play the game, and can be earned by playing the game.\n'
#             '\n'
#             'Get SYPHER: [Uniswap](https://app.uniswap.org/#/swap?outputCurrency=0x21b9D428EB20FA075A29d51813E57BAb85406620)\n'
#             'BaseScan: [Link](https://basescan.org/token/0x21b9d428eb20fa075a29d51813e57bab85406620)\n'
#             'Contract Address: 0x21b9D428EB20FA075A29d51813E57BAb85406620\n'
#             'Total Supply: 1,000,000\n'
#             'Blockchain: Base\n'
#             'Liquidity: Uniswap\n'
#             'Ticker: SYPHER\n',
#             parse_mode='Markdown',
#             disable_web_page_preview=True
#         )
#     else:
#         msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
#     if msg is not None:
#         track_message(msg)
#endregion Main Slash Commands




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



#region Buybot
# def monitor_transfers():
#     transfer_filter = contract.events.Transfer.create_filter(fromBlock='latest', argument_filters={'from': pool_address})
    
#     while True:
#         for event in transfer_filter.get_new_entries():
#             handle_transfer_event(event)
#         time.sleep(10)

# def handle_transfer_event(event):
#     from_address = event['args']['from']
#     amount = event['args']['value']
    
#     # Check if the transfer is from the LP address
#     if from_address.lower() == pool_address.lower():
#         # Convert amount to SYPHER (from Wei)
#         sypher_amount = web3.from_wei(amount, 'ether')

#         # Fetch the USD price of SYPHER
#         sypher_price_in_usd = get_token_price_in_fiat(contract_address, 'usd')
#         if sypher_price_in_usd is not None:
#             sypher_price_in_usd = Decimal(sypher_price_in_usd)
#             total_value_usd = sypher_amount * sypher_price_in_usd
#             if total_value_usd < 500:
#                 print("Ignoring small buy")
#                 return
#             value_message = f" ({total_value_usd:.2f} USD)"
#             header_emoji, buyer_emoji = categorize_buyer(total_value_usd)
#         else:
            # print("Failed to fetch token price in USD.")

#         # Format message with Markdown
#         message = f"{header_emoji}SYPHER BUY{header_emoji}\n\n{buyer_emoji} {sypher_amount} SYPHER{value_message}"
#         print(message)  # Debugging

#         send_buy_message(message)

# def categorize_buyer(usd_value):
#     if usd_value < 2500:
#         return "💸", "🐟"
#     elif usd_value < 5000:
#         return "💰", "🐬"
#     else:
#         return "🤑", "🐳"
    
# def send_buy_message(text):
#     msg = None
#     bot = telegram.Bot(token=TELEGRAM_TOKEN)
#     msg = bot.send_message(chat_id=CHAT_ID, text=text)
#     if msg is not None:
#         track_message(msg)
#endregion Buybot


#region User Verification
def handle_new_user(update: Update, context: CallbackContext) -> None:
    bot_added_to_group(update, context)
    msg = None
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
            context.bot.kick_chat_member(chat_id=chat_id, user_id=user_id)
            return
        
        print("Allowing new user to join, antiraid is not active.")

        # Send the welcome message with the verification button
        welcome_message = (
            "Welcome to Tukyo Games!\n\n"
            "⚠️ Admins will NEVER DM YOU FIRST ⚠️\n\n"
            "To start verification, please click Initialize Bot, then send the bot a /start command in DM.\n\n"
            "After initializing the bot, return to the main chat and press 'Click Here to Verify'.\n"
        )

        keyboard = [
            [InlineKeyboardButton("Initialize Bot", url=f"https://t.me/deSypher_bot?start={user_id}")],
            [InlineKeyboardButton("Click Here to Verify", callback_data=f'verify_{user_id}')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)

        welcomeMessage = context.bot.send_message(chat_id=chat_id, text=welcome_message, reply_markup=reply_markup, parse_mode='Markdown')
        welcome_message_id = welcomeMessage.message_id
        context.chat_data['non_deletable_message_id'] = welcomeMessage.message_id

        # Start a verification timeout job
        job_queue = context.job_queue
        job_queue.run_once(verification_timeout, 600, context={'chat_id': chat_id, 'user_id': user_id, 'welcome_message_id': welcome_message_id}, name=str(user_id))

        update.message.delete()

    if msg is not None:
        track_message(msg)

# def start_verification_dm(user_id: int, context: CallbackContext) -> None:
#     print("Sending verification message to user's DM.")
#     verification_message = "Welcome to Tukyo Games! Please click the button to begin verification."
#     keyboard = [[InlineKeyboardButton("Start Verification", callback_data='start_verification')]]
#     reply_markup = InlineKeyboardMarkup(keyboard)

#     message = context.bot.send_message(chat_id=user_id, text=verification_message, reply_markup=reply_markup)
#     return message.message_id

# def verification_callback(update: Update, context: CallbackContext) -> None:
#     query = update.callback_query
#     callback_data = query.data
#     user_id = query.from_user.id
#     chat_id = query.message.chat_id
#     query.answer()

#     # Extract user_id from the callback_data
#     _, callback_user_id = callback_data.split('_')
#     callback_user_id = int(callback_user_id)

#     if user_id != callback_user_id:
#         return  # Do not process if the callback user ID does not match the button user ID

#     if is_user_admin(update, context):
#         return
    
#     # Send a message to the user's DM to start the verification process
#     start_verification_dm(user_id, context)
    
#     # Optionally, you can edit the original message to indicate the button was clicked
#     verification_started_message = query.edit_message_text(text="A verification message has been sent to your DMs. Please check your messages.")
#     verification_started_id = verification_started_message.message_id

#     job_queue = context.job_queue
#     job_queue.run_once(delete_verification_message, 30, context={'chat_id': chat_id, 'message_id': verification_started_id})

# def delete_verification_message(context: CallbackContext) -> None:
#     job = context.job
#     context.bot.delete_message(
#         chat_id=job.context['chat_id'],
#         message_id=job.context['message_id']
#     )

# def generate_verification_buttons() -> InlineKeyboardMarkup:
#     all_letters = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
#     required_letters = list(VERIFICATION_LETTERS)
    
#     for letter in required_letters:
#         if letter in all_letters:
#             all_letters.remove(letter)
    
#     # Shuffle the remaining letters
#     random.shuffle(all_letters)
    
#     # Randomly select 11 letters from the shuffled list
#     selected_random_letters = all_letters[:11]
    
#     # Combine required letters with the random letters
#     final_letters = required_letters + selected_random_letters
    
#     # Shuffle the final list of 16 letters
#     random.shuffle(final_letters)
    
#     buttons = []
#     row = []
#     for i, letter in enumerate(final_letters):
#         row.append(InlineKeyboardButton(letter, callback_data=f'verify_letter_{letter}'))
#         if (i + 1) % 4 == 0:
#             buttons.append(row)
#             row = []

#     if row:
#         buttons.append(row)

#     return InlineKeyboardMarkup(buttons)

# def handle_start_verification(update: Update, context: CallbackContext) -> None:
#     query = update.callback_query
#     user_id = query.from_user.id
#     query.answer()

#     # Initialize user verification progress
#     user_verification_progress[user_id] = {
#         'progress': [],
#         'main_message_id': query.message.message_id,
#         'chat_id': query.message.chat_id,
#         'verification_message_id': query.message.message_id
#     }

#     verification_question = "Who is the lead developer at Tukyo Games?"
#     reply_markup = generate_verification_buttons()

#     # Edit the initial verification prompt
#     context.bot.edit_message_text(
#         chat_id=user_id,
#         message_id=user_verification_progress[user_id]['verification_message_id'],
#         text=verification_question,
#         reply_markup=reply_markup
#     )

# def handle_verification_button(update: Update, context: CallbackContext) -> None:
#     query = update.callback_query
#     user_id = query.from_user.id
#     letter = query.data.split('_')[2]  # Get the letter from callback_data
#     query.answer()

#     # Update user verification progress
#     if user_id in user_verification_progress:
#         user_verification_progress[user_id]['progress'].append(letter)

#         # Only check the sequence after the fifth button press
#         if len(user_verification_progress[user_id]['progress']) == len(VERIFICATION_LETTERS):
#             if user_verification_progress[user_id]['progress'] == list(VERIFICATION_LETTERS):
#                 context.bot.edit_message_text(
#                     chat_id=user_id,
#                     message_id=user_verification_progress[user_id]['verification_message_id'],
#                     text="Verification successful, you may now return to chat!"
#                 )
#                 print("User successfully verified.")
#                 # Unmute the user in the main chat
#                 context.bot.restrict_chat_member(
#                     chat_id=CHAT_ID,
#                     user_id=user_id,
#                     permissions=ChatPermissions(
#                         can_send_messages=True,
#                         can_send_media_messages=True,
#                         can_send_other_messages=True,
#                         can_send_videos=True,
#                         can_send_photos=True,
#                         can_send_audios=True
#                     )
#                 )
#                 current_jobs = context.job_queue.get_jobs_by_name(str(user_id))
#                 for job in current_jobs:
#                     job.schedule_removal()
#             else:
#                 context.bot.edit_message_text(
#                     chat_id=user_id,
#                     message_id=user_verification_progress[user_id]['verification_message_id'],
#                     text="Verification failed. Please try again.",
#                     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Start Verification", callback_data='start_verification')]])
#                 )
#                 print("User failed verification prompt.")
#             # Reset progress after verification attempt
#             user_verification_progress.pop(user_id)
#     else:
#         context.bot.edit_message_text(
#             chat_id=user_id,
#             message_id=user_verification_progress[user_id]['verification_message_id'],
#             text="Verification failed. Please try again.",
#             reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Start Verification", callback_data='start_verification')]])
#         )
#         print("User failed verification prompt.")
        
def verification_timeout(context: CallbackContext) -> None:
    msg = None
    job = context.job
    context.bot.kick_chat_member(
        chat_id=job.context['chat_id'],
        user_id=job.context['user_id']
    )
    
    context.bot.delete_message(
        chat_id=job.context['chat_id'],
        message_id=job.context['welcome_message_id']
    )

    if msg is not None:
        track_message(msg)
#endregion User Verification





def main() -> None:
    # Create the Updater and pass it your bot's token
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    
    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher
    
    #region General Slash Command Handlers
    dispatcher.add_handler(CommandHandler("start", start))
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
    #endregion General Slash Command Handlers

    #region Admin Slash Command Handlers
    dispatcher.add_handler(CommandHandler("admincommands", admin_commands))
    dispatcher.add_handler(CommandHandler('cleanbot', cleanbot))
    dispatcher.add_handler(CommandHandler('cleargames', cleargames))
    # dispatcher.add_handler(CommandHandler('antiraid', antiraid))
    # dispatcher.add_handler(CommandHandler("mute", mute))
    # dispatcher.add_handler(CommandHandler("unmute", unmute))
    dispatcher.add_handler(CommandHandler("kick", kick))
    dispatcher.add_handler(CommandHandler("block", block))
    dispatcher.add_handler(CommandHandler("removeblock", remove_block))
    dispatcher.add_handler(CommandHandler("blocklist", blocklist))
    dispatcher.add_handler(CommandHandler("allow", allow))
    dispatcher.add_handler(CommandHandler("allowlist", allowlist))
    dispatcher.add_handler(CommandHandler("warn", warn))
    dispatcher.add_handler(CommandHandler("warnings", check_warnings))
    #endregion Admin Slash Command Handlers
    
    # Register the message handler for new users
    dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, handle_new_user))
    dispatcher.add_handler(MessageHandler(Filters.status_update.left_chat_member, bot_removed_from_group))
    dispatcher.add_handler(MessageHandler((Filters.text | Filters.document) & (~Filters.command), handle_message))

    # Add a handler for deleting service messages
    # dispatcher.add_handler(MessageHandler(Filters.status_update.left_chat_member, delete_service_messages))

    # Register the callback query handler for button clicks
    # dispatcher.add_handler(CallbackQueryHandler(verification_callback, pattern='^verify_\d+$'))
    # dispatcher.add_handler(CallbackQueryHandler(handle_start_verification, pattern='start_verification'))
    # dispatcher.add_handler(CallbackQueryHandler(handle_verification_button, pattern=r'verify_letter_[A-Z]'))
    dispatcher.add_handler(CallbackQueryHandler(setup_home_callback, pattern='^setup_home$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_ethereum, pattern='^setup_ethereum$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_contract, pattern='^setup_contract$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_liquidity, pattern='^setup_liquidity$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_ABI, pattern='^setup_ABI$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_chain, pattern='^setup_chain$'))
    dispatcher.add_handler(CallbackQueryHandler(cancel_callback, pattern='^cancel$'))
    dispatcher.add_handler(CallbackQueryHandler(handle_chain, pattern='^(ethereum|arbitrum|polygon|base|optimism|fantom|avalanche|binance|aptos|harmony|mantle)$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_verification, pattern='^setup_verification$'))
    dispatcher.add_handler(CallbackQueryHandler(enable_verification, pattern='^enable_verification$'))
    dispatcher.add_handler(CallbackQueryHandler(disable_verification, pattern='^disable_verification$'))
    dispatcher.add_handler(CallbackQueryHandler(math_verification, pattern='^math_verification$'))
    dispatcher.add_handler(CallbackQueryHandler(password_verification, pattern='^password_verification$'))
    dispatcher.add_handler(CallbackQueryHandler(handle_start_game, pattern='^startGame$'))
    dispatcher.add_handler(CallbackQueryHandler(command_buttons, pattern='^commands_'))

    # monitor_thread = threading.Thread(target=monitor_transfers)
    # monitor_thread.start()
    
    # Start the Bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()