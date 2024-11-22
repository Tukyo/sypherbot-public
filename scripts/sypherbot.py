import os
import re
import sys
import time
import pytz
import json
import random
import inspect
import requests
import telegram
import threading
import pandas as pd
import firebase_admin
import mplfinance as mpf
from web3 import Web3
from io import BytesIO
from scripts import config # Import the config module from the scripts folder
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
## This is the public version of the bot that was developed by Tukyo for the Sypher project.
## This bot has a customizable commands feature and admin controls, along with full charting, price, and buybot functionality.
## You may also set a custom contract address for the token you want to track; all other contracts will be blocked in your chat if enabled.
#
## https://desypher.net/ | https://tukyogames.com/ | https://tukyowave.com/ | https://tukyo.org/
#
#### Commands <<< These are the commands that are available to all users in the chat.
##
### /start - Start the bot
### /setup - Set up the bot for your group
### /commands | /help - Get a list of commands
### /play | /endgame - Start a mini-game of deSypher within Telegram & end any ongoing games
### /contract /ca - Contract address for the group token
### /buy | /purchase - Buy the token for the group
### /price - Get the price of the group token in USD
### /chart - Links to the token chart on various platforms
### /liquidity /lp - View the liquidity value of the group V3 pool
### /volume - 24-hour trading volume of the group token
### /website - Get links to related websites
### /report - Report a message to group admins
### /save - Save a message to your DMs
##
#
#### Admin Commands <<< These are the commands that are available to group admins only.
##
### /admincommands | /adminhelp - Get a list of admin commands
### /cleanbot | /clean | /cleanupbot | /cleanup - Clean all bot messages in the chat
### /clearcache - Clear the cache for the group
### /cleargames - Clear all active games in the chat
### /kick | /ban - Reply to a message to kick a user from the chat
### /mute | /unmute - Reply to a message to toggle mute for a user
### /mutelist - Check the mute list
### /warn - Reply to a message to warn a user
### /warnlist - Get a list of all warnings
### /clearwarns - Clear warnings for a specific user
### /warnings - Check warnings for a specific user
### /block - Block a user or contract address
### /removeblock /unblock /unfilter - Remove a user or contract address from the block list
### /blocklist /filterlist - View the block list
### /allow - Allow a specific user or contract
### /allowlist - View the allow list
##
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

RELAXED_TRUST = int(os.getenv('RELAXED_TRUST'))
MODERATE_TRUST = int(os.getenv('MODERATE_TRUST'))
STRICT_TRUST = int(os.getenv('STRICT_TRUST'))

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

firebase_admin.initialize_app(cred, { 'storageBucket': FIREBASE_STORAGE_BUCKET })

db = firestore.client()
bucket = storage.bucket()

print("Database: ", db)
print("Bucket: ", bucket)
print("Firebase initialized.")
#endregion Firebase

#region Classes
class AntiSpam:
    def __init__(self, rate_limit, time_window, mute_duration): # Check if a user is spamming, if they are mute them for a set duration
        self.rate_limit = rate_limit
        self.time_window = time_window
        self.mute_duration = mute_duration
        self.user_messages = defaultdict(list)
        self.blocked_users = defaultdict(lambda: 0)
        print(f"Initialized AntiSpam with rate_limit={rate_limit}, time_window={time_window}, mute_duration={mute_duration}")

    def is_spam(self, user_id, chat_id):
        current_time = time.time()
        key = (user_id, chat_id)

        # Check if user is still muted
        if current_time < self.blocked_users[key]:
            print(f"User {user_id} in chat {chat_id} is muted until {self.blocked_users[key]} (current time: {current_time})")
            return True
        
        # Clean up old messages and add the new one
        self.user_messages[key] = [msg_time for msg_time in self.user_messages[key] if current_time - msg_time < self.time_window]
        self.user_messages[key].append(current_time)
        
        # Check if user exceeds rate limit
        if len(self.user_messages[key]) > self.rate_limit:
            self.blocked_users[key] = current_time + self.mute_duration
            print(f"User {user_id} in chat {chat_id} is blocked until {self.blocked_users[key]} (block duration: {self.mute_duration} seconds)")
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

ANTI_SPAM_RATE_LIMIT = 5
ANTI_SPAM_TIME_WINDOW = 10
ANTI_SPAM_MUTE_DURATION = 60
ANTI_RAID_USER_AMOUNT = 50
ANTI_RAID_TIME_OUT = 10
ANTI_RAID_LOCKDOWN_TIME = 180

anti_spam = AntiSpam(rate_limit=ANTI_SPAM_RATE_LIMIT, time_window=ANTI_SPAM_TIME_WINDOW, mute_duration=ANTI_SPAM_MUTE_DURATION)
anti_raid = AntiRaid(user_amount=ANTI_RAID_USER_AMOUNT, time_out=ANTI_RAID_TIME_OUT, anti_raid_time=ANTI_RAID_LOCKDOWN_TIME)

scheduler = BackgroundScheduler()

BOT_USERNAME = "sypher_robot"

ETH_ADDRESS_PATTERN = re.compile(r'\b0x[a-fA-F0-9]{40}\b')
URL_PATTERN = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
DOMAIN_PATTERN = re.compile(r'\b[\w\.-]+\.[a-zA-Z]{2,}\b')

RATE_LIMIT_MESSAGE_COUNT = 100  # Maximum number of allowed commands per {TIME_PERIOD}
RATE_LIMIT_TIME_PERIOD = 60  # Time period in (seconds)
MONITOR_INTERVAL = 5 # Interval for monitoring jobs (seconds)
BLOB_EXPIRATION = 15 # Expiration time for uploaded files (minutes)

last_check_time = time.time()
command_count = 0

bot_messages = []
def track_message(message):
    bot_messages.append((message.chat.id, message.message_id))
    print(f"Tracked message: {message.message_id}")

#region LOGGING
bot = Bot(token=TELEGRAM_TOKEN)
LOG_CHAT = "-1002087245760"
LOGGING_TIMEZONE = "America/Los_Angeles"
MAX_TELEGRAM_MESSAGE_LENGTH = 4096
LOG_INTERVAL = 30
class TelegramLogger: # Batch all logs and send to the logging channel for debugging in telegram
    def __init__(self):
        self.original_stdout = sys.stdout  # Keep a reference to the original stdout
        self.original_stderr = sys.stderr # Keep a reference to the original stderr
        self.log_buffer = []  # Buffer to store logs
        self.flush_interval = LOG_INTERVAL  # Send logs every interval
        self.timer = Timer(self.flush_interval, self.flush_logs)  # Timer for batching
        self.timer.start()

    def write(self, message, from_stderr=False):
        if message.strip():  # Avoid sending empty lines
            pst_timezone = pytz.timezone(LOGGING_TIMEZONE)
            timestamp = datetime.now(pst_timezone).strftime("%Y-%m-%d %I:%M:%S %p PST")
            formatted_message = f"{timestamp} - {message.strip()}"
            if from_stderr: # Only append @Tukyowave for stderr messages
                formatted_message += " @Tukyowave"
            self.log_buffer.append(formatted_message)
        
        if from_stderr: # Write to the original stream
            self.original_stderr.write(message)
        else:
            self.original_stdout.write(message)

    def flush(self):
        if self.original_stdout:
            self.original_stdout.flush()
        if self.original_stderr:
            self.original_stderr.flush()

    def flush_logs(self):
        if self.log_buffer:
            combined_message = "\n\n".join(self.log_buffer)
            while combined_message:
                chunk = combined_message[:MAX_TELEGRAM_MESSAGE_LENGTH]
                bot.send_message(chat_id=LOG_CHAT, text=chunk)
                combined_message = combined_message[MAX_TELEGRAM_MESSAGE_LENGTH:]
            self.log_buffer = []

        self.timer = Timer(self.flush_interval, self.flush_logs) # Restart the timer
        self.timer.start()

    def stop(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None

logger = TelegramLogger()

class StdoutWrapper:
    def write(self, message):
        logger.write(message, from_stderr=False)

    def flush(self):
        logger.flush()

class StderrWrapper:
    def write(self, message):
        logger.write(message, from_stderr=True)

    def flush(self):
        logger.flush()

sys.stdout = StdoutWrapper()  # Redirect stdout
sys.stderr = StderrWrapper()  # Redirect stderr
#endregion LOGGING

#region Bot Logic
def bot_added_to_group(update: Update, context: CallbackContext) -> None:
    new_members = update.message.new_chat_members
    inviter = update.message.from_user

    if any(member.id != context.bot.id for member in new_members):
        return  # Bot wasn't added

    group_id = update.effective_chat.id
    group_type = update.effective_chat.type

    admins = context.bot.get_chat_administrators(group_id)  
    inviter_is_admin = any(admin.user.id == inviter.id for admin in admins)

    print(f"Bot added to group {group_id} by {inviter.id} ({inviter.username})")

    if group_type == "private":
        print(f"Bot added to a private chat by {inviter.id} ({inviter.username}). Ignoring.")
        update.message.reply_text("Sorry, I don't support private groups. You will need to remove me from your group, and add me back after you change the group type to public.")
        return  # Ignore private chats

    if group_type not in ["group", "supergroup"]:
        msg = update.message.reply_text("Sorry, I don't support private chats or channels.")
        print(f"Bot was added to a non-group chat type: {group_type}. Ignoring.")
        return  # Ignore private or unsupported chat types

    if inviter_is_admin:
        owner_id = inviter.id # Store group info only if the inviter is an admin
        owner_username = inviter.username
        print(f"Adding group {group_id} to database with owner {owner_id} ({owner_username})")
        chat_id = update.effective_chat.id
        group_doc = db.collection('groups').document(str(chat_id))
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
            },
            'commands':
            {
                'play': True,
                'website': True,
                'buy': True,
                'contract': True,
                'price': True,
                'chart': True,
                'liquidity': True,
                'volume': True
            }
        })
        clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

        print(f"Group {group_id} added to database.")

        group_counter = db.collection('stats').document('addedgroups')
        group_counter.update({'count': firestore.Increment(1)}) # Get the current added groups count and increment by 1

        bot_member = context.bot.get_chat_member(group_id, context.bot.id)  # Get bot's member info

        if bot_member.status == "administrator":
            setup_keyboard = [[InlineKeyboardButton("Setup", callback_data='setup_home')]] # Bot is admin, send the "Thank you" message
            setup_markup = InlineKeyboardMarkup(setup_keyboard)
            msg = update.message.reply_text(
                "Thank you for adding me to your group! Please click 'Setup' to continue.",
                reply_markup=setup_markup
            )
            store_message_id(context, msg.message_id)
            print(f"Sent setup message to group {group_id}")
        else: # Bot is not admin, send the "Give me admin perms" message
            setup_keyboard = [[InlineKeyboardButton("Setup", callback_data='setup_home')]]
            setup_markup = InlineKeyboardMarkup(setup_keyboard)
            msg = update.message.reply_text(
                "Hey, please give me admin permissions, then click 'Setup' to get started.",
                reply_markup=setup_markup
            )
            print(f"Bot does not have admin permissions in group: {group_id}")
            store_message_id(context, msg.message_id)
 
        if msg is not None:
            track_message(msg)

def bot_removed_from_group(update: Update, context: CallbackContext) -> None:
    left_member = update.message.left_chat_member

    if left_member.id != context.bot.id:  # User left, not bot
        delete_service_messages(update, context)
        return

    group_doc = fetch_group_info(update, context, return_doc=True) # Fetch the Firestore document reference directly

    if not group_doc:  # If group doesn't exist in Firestore, log and skip deletion
        print(f"Group {update.effective_chat.id} not found in database. No deletion required.")
        return

    if left_member.id == context.bot.id: # Bot left. not user
        print(f"Removing group {update.effective_chat.id} from database.")
        group_counter = db.collection('stats').document('removedgroups')
        group_counter = group_counter.update({'count': firestore.Increment(1)}) # Get the current removed groups count and increment by 1
        group_doc.delete()  # Directly delete the group document
        clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

#region Monitoring
def start_monitoring_groups():
    groups_snapshot = db.collection('groups').get()
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
#endregion Monitoring

def is_user_admin(update: Update, context: CallbackContext) -> bool:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if update.callback_query: # Check if the update has a callback_query
        user_id = update.callback_query.from_user.id
    else:
        user_id = update.effective_user.id

    if update.effective_chat.type == 'private':
        return False
    
    print(f"Checking if user is admin for chat {chat_id}")

    chat_admins = context.bot.get_chat_administrators(chat_id) # Check if the user is an admin in this chat
    user_is_admin = any(admin.user.id == user_id for admin in chat_admins)

    print(f"UserID: {user_id} - IsAdmin: {user_is_admin}")

    return user_is_admin

def is_user_owner(update: Update, context: CallbackContext, user_id: int) -> bool:
    chat_id = update.effective_chat.id

    if update.effective_chat.type == 'private':
        print("User is in a private chat.")
        return False

    print(f"Checking if user is owner for chat {chat_id}")

    group_data = fetch_group_info(update, context)

    if not group_data:
        print(f"No data found for group {chat_id}. Group may not be registered.")
        return False  # Default to False if no data is found

    user_is_owner = group_data['owner_id'] == user_id # Check if the user is the owner of this group

    print(f"UserID: {user_id} - OwnerID: {group_data['owner_id']} - IsOwner: {user_is_owner}")

    if not user_is_owner:
        print(f"User {user_id} is not the owner of group {chat_id}")

    return user_is_owner

def is_bot_or_admin(update: Update, context: CallbackContext, user_id: int, send_message: bool = True, message: str = "Nice try lol") -> bool:
    chat_id = update.effective_chat.id
    chat_admins = context.bot.get_chat_administrators(chat_id)
    admin_user_ids = [admin.user.id for admin in chat_admins]
    bot_id = context.bot.id

    if int(user_id) in admin_user_ids or int(user_id) == bot_id:
        if send_message:
            msg = update.message.reply_text(message)
            if msg is not None:
                track_message(msg)
        return True
    return False

def fetch_group_info(update: Update, context: CallbackContext, return_doc: bool = False, update_attr: bool = False, return_both: bool = False, group_id: str = None):
    if update is not None:
        if update.effective_chat.type == 'private' and group_id is None:
            print(f"Private chat detected when attempting to fetch group info. No group_id provided either.")
            return None  # Private chats have no group data and no group_id was provided

        if update_attr and group_id is None:  # Determines whether or not the group_id is fetched from a message update or chat
            print(f"group_id not manually provided, fetching from message.")
            group_id = str(update.message.chat.id)
        elif group_id is None:
            print(f"group_id not manually provided, fetching from chat.")
            group_id = str(update.effective_chat.id)
        else:
            print(f"group_id manually provided: {group_id}")
    elif group_id is None:
        print(f"Neither update nor group_id provided. Unable to fetch group info.")
        return None  # No valid source for group_id

    cached_info = fetch_cached_group_info(group_id)

    if cached_info: # Return cached data based on the flags
        if return_both:
            print(f"Returning cached document and data for group {group_id}")
            return cached_info["group_data"], cached_info["group_doc"]
        if return_doc:
            print(f"Returning cached document for group {group_id}")
            return cached_info["group_doc"]
        print(f"Returning cached data for group {group_id}")
        return cached_info["group_data"]

    group_doc = db.collection('groups').document(str(group_id))

    if return_doc:
        print(f"Fetching group_doc for group {group_id}")
    else:
        print(f"Fetching group_data for group {group_id}")

    try:
        doc_snapshot = group_doc.get()
        if doc_snapshot.exists:
            group_data = doc_snapshot.to_dict()

            cache_group_info(group_id, group_data, group_doc) # Cache the group data and document reference

            if return_both:
                print(f"Group document and data found for group {group_id}")
                return group_data, group_doc  # Return both the document reference and the data

            if return_doc:
                print(f"Group document found for group {group_id}")
                return group_doc  # Return the document reference
            else:
                print(f"Group data found for group {group_id}")
                return group_data  # Return the document data
        else:
            print(f"No data found for group {group_id}. Group may not be registered.")
            return None  # No data found for this group
    except Exception as e:
        print(f"Failed to fetch group info: {e}")
        return None  # Error fetching group data

def fetch_group_token(group_data: dict, update: Update, context: CallbackContext): # Fetches all token-related data from a pre-fetched group_data object.
    token_data = group_data.get('token')
    if not token_data:
        print("Token data not found for this group.")
        update.message.reply_text("Token data not found for this group.")
        return None

    print(f"All token data fetched: {token_data}")
    return token_data

def get_query_info(update, get_user=True):
    query = update.callback_query
    if query is None:
        print("Error: Callback query is None.", file=sys.stderr)
        return None if not get_user else (None, None)

    query.answer()  # Safely answer the query
    if get_user:
        if query.from_user is None:
            print("Error: No user information in callback query.", file=sys.stderr)
            return query, None
        print(f"Query data returned for user {query.from_user.id}")
        return query, query.from_user.id
    else:
        print(f"Query data returned without user_id")
        return query  # Return only the query if get_user is False

#region Caching
group_info_cache = {}
def cache_group_info(group_id: str, group_data: dict, group_doc: object) -> None: # Caches the group data and document reference for a specific group ID.
    group_id = str(group_id)
    group_info_cache[group_id] = {
        "group_data": group_data,
        "group_doc": group_doc
    }

    print(f"Cached info for group {group_id}.")

def fetch_cached_group_info(group_id: str) -> dict | None: # Retrieves cached group data and document reference for a specific group ID.
    group_id = str(group_id)
    cached_info = group_info_cache.get(group_id)

    if cached_info:
        print(f"Found cache for group {group_id}.")
        return cached_info
    else:
        print(f"No cache for group {group_id}.")
        return None

def clear_group_cache(group_id: str) -> None: # Clears the cache for a specific group ID.
    group_id = str(group_id)
    if group_id in group_info_cache:
        del group_info_cache[group_id]
        print(f"Cache cleared for group {group_id}.")
    else:
        print(f"No cache entry found for group {group_id}.")
#endregion Caching
##
#
##
#region Message Handling
def rate_limit_check(): # Later TODO: Implement rate limiting PER GROUP
    print("Checking rate limit...")
    global last_check_time, command_count
    current_time = time.time()

    # Reset count if time period has expired
    if current_time - last_check_time > RATE_LIMIT_TIME_PERIOD:
        command_count = 0
        last_check_time = current_time

    # Check if the bot is within the rate limit
    if command_count < RATE_LIMIT_MESSAGE_COUNT:
        command_count += 1
        return True
    else:
        return False

def handle_message(update: Update, context: CallbackContext) -> None:
    if not (update.message and update.message.from_user):
        print("Received a message with missing update or user information.")
        return
    
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    username = update.message.from_user.username or update.message.from_user.first_name    
    msg = update.message.text

    if not msg:
        print("No message text found.")
        return

    if is_user_admin(update, context):
        handle_setup_inputs_from_admin(update, context)
        handle_guess(update, context)
        return
    
    if update.effective_chat.type == 'private':
        handle_guess(update, context)
        return

    if anti_spam.is_spam(user_id, chat_id):
        handle_spam(update, context, chat_id, user_id, username)

    print(f"Message sent by user {user_id} in chat {chat_id}")

    detected_patterns = []
    if ETH_ADDRESS_PATTERN.search(msg):
        detected_patterns.append("eth_address")
    if URL_PATTERN.search(msg):
        detected_patterns.append("url")
    if DOMAIN_PATTERN.search(msg):
        detected_patterns.append("domain")

    if re.search(r"@\w+", msg): # Trigger trust check
        print(f"Detected mention in message: {msg}")
        if not check_if_trusted(update, context):
            print(f"User {user_id} is not trusted to tag others.")
            context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
            return
        else:
            print(f"User {user_id} is trusted to tag others.")

    if detected_patterns and msg is not None: # Check the allowlist if any patterns matched
        group_data = fetch_group_info(update, context)

        if not group_data or not group_data.get('admin', {}).get('allowlist', False):  # Default to False
            print("Allowlist check is disabled in admin settings. Skipping allowlist verification.")
            return

        allowlist = group_data.get('allowlist', [])
        group_info = group_data.get('group_info', {})

        group_website = group_info.get('website_url', None)

        for pattern in detected_patterns:
            if pattern == "eth_address":
                print(f"Detected crypto address in message: {msg}")
                delete_blocked_addresses(update, context)
                return
            elif pattern == "url":
                matched_url = URL_PATTERN.search(msg).group()  # Extract the detected URL
                normalized_msg = re.sub(r'^https?://', '', msg).strip().lower().rstrip('/')  # Normalize the URL
                print(f"Detected URL: {matched_url} - Normalized: {normalized_msg}")
                delete_blocked_links(update, context)
                return
            elif pattern == "domain":
                def extract_domain(url): # Extract the domain from the group's website_url
                    return re.sub(r'^https?://', '', url).split('/')[0]  # Strip scheme and path

                group_domain = extract_domain(group_website) if group_website else None

                if group_domain and msg.strip().lower() == group_domain.lower():  # Compare message to group domain
                    print(f"Domain matches group website: {msg}.")
                    return  # Skip deletion for matching group website domain
                
                if not is_allowed(msg, allowlist, DOMAIN_PATTERN):
                    print(f"Blocked domain: {msg}")
                    context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
                    return

    delete_blocked_addresses(update, context)
    delete_blocked_phrases(update, context)
    delete_blocked_links(update, context)
    handle_guess(update, context)

def handle_image(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    username = update.message.from_user.username or update.message.from_user.first_name
    msg = None

    if is_user_admin(update, context):
        handle_setup_inputs_from_admin(update, context)
        return
    
    print(f"Image sent by user {update.message.from_user.id} in chat {update.message.chat.id}")

    if msg is not None and re.search(r"@\w+", msg): # Trigger trust check
        print(f"Detected mention in message: {msg}")
        if not check_if_trusted(update, context):
            print(f"User {user_id} is not trusted to tag others.")
            context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
            return
        else:
            print(f"User {user_id} is trusted to tag others.")

    if anti_spam.is_spam(user_id, chat_id):
        handle_spam(update, context, chat_id, user_id, username)

    if msg is not None:
        track_message(msg)

def handle_document(update: Update, context: CallbackContext) -> None:
    if is_user_admin(update, context):
        handle_setup_inputs_from_admin(update, context)
        return
    
    print(f"Document sent by user {update.message.from_user.id} in chat {update.message.chat.id}")

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

    context.bot.restrict_chat_member( # Mute the spamming user
        chat_id=chat_id,
        user_id=user_id,
        permissions=ChatPermissions(can_send_messages=False)
    )

    print(f"User {username} has been muted for spamming in chat {chat_id}.")

    group_id = update.effective_chat.id
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    # Only send the message if the user is not in the unverified_users mapping
    if str(user_id) not in group_data.get('unverified_users', {}):
        auth_url = f"https://t.me/{BOT_USERNAME}?start=authenticate_{chat_id}_{user_id}"
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
        clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

def is_allowed(message, allowlist, pattern): # Check if any detected matches in the message are present in the allowlist.
    print(f"Pattern found, checking message: {message}")

    matches = pattern.findall(message)
    for match in matches:
        if match in allowlist:
            return True
    return False

def delete_blocked_addresses(update: Update, context: CallbackContext):
    print("Checking message for unallowed addresses...")
    
    message_text = update.message.text
    
    if message_text is None:
        print("No text in message.")
        return

    found_addresses = ETH_ADDRESS_PATTERN.findall(message_text)

    if not found_addresses:
        print("No addresses found in message.")
        return

    group_data = fetch_group_info(update, context)
    if group_data is None:
        return

    token_data = group_data.get('token', {})  # Get the 'token' dictionary
    allowed_addresses = [ # Retrieve the contract and LP addresses from the fetched group info
        token_data.get('contract_address', '').lower(),
        token_data.get('liquidity_address', '').lower()
    ]

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

    if not message_text:
        print("No text in message.")
        return

    # Regular expressions to find URLs and domains
    found_links = URL_PATTERN.findall(message_text)
    found_domains = DOMAIN_PATTERN.findall(message_text)

    if not found_links and not found_domains:
        print("No links or domains found in message.")
        return

    # Fetch the group-specific allowlist
    group_info = fetch_group_info(update, context)
    if not group_info:
        print("No group info available.")
        return

    # Directly use the allowlist as an array
    allowlist_items = group_info.get('allowlist', [])
    if not isinstance(allowlist_items, list):
        print("Allowlist is not in the correct format.")
        return

    # Normalize allowlist entries
    normalized_allowlist = [item.strip().lower().rstrip('/') for item in allowlist_items]

    # Combine found links and domains
    found_items = found_links + found_domains
    print(f"Found items: {found_items}")
    print(f"Normalized allowlist: {normalized_allowlist}")

    for item in found_items:
        # Normalize the found item for comparison
        normalized_item = item.lower().replace('http://', '').replace('https://', '').rstrip('/')
        print(f"Checking item: {normalized_item}")

        # Check if the item is in the allowlist
        if not any(normalized_item.startswith(allowed_item) for allowed_item in normalized_allowlist):
            try:
                update.message.delete()
                print(f"Deleted a message with unallowed item: {normalized_item}")
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

    group_info = fetch_group_info(update, context) # Fetch the group info to get the blocklist
    if not group_info:
        print("No group info available.")
        return

    admin_settings = group_info.get('admin', {}) # Check if blocklist is enabled
    if not admin_settings.get('blocklist', False):  # Default to False if not specified
        print("Blocklist is disabled for this group.")
        return

    blocklist_field = 'blocklist' # Get the blocklist as an array from the group info
    blocklist_items = group_info.get(blocklist_field, [])

    if not isinstance(blocklist_items, list): # Ensure blocklist_items is a list
        print("Blocklist is not properly formatted as an array.")
        return

    for phrase in blocklist_items: # Check each blocked phrase in the group's blocklist
        if re.search(rf'\b{re.escape(phrase)}\b', message_text): # Use regex
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
    if 'setup_bot_message' in context.chat_data:
        context.chat_data['setup_bot_message'].append(message_id)
    else:
        context.chat_data['setup_bot_message'] = [message_id]
#endregion Message Handling
#
##
#endregion Bot Logic
##
#
##
#region Bot Setup
def menu_change(context: CallbackContext, update: Update):
    messages_to_delete = [ 'setup_bot_message' ]

    print(f"Menu change detected in group {update.effective_chat.id}")

    for message_to_delete in messages_to_delete:
        if message_to_delete in context.chat_data:
            for message_id in context.chat_data[message_to_delete]:
                try:
                    context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=message_id
                    )
                except Exception as e:
                    if str(e) != "Message to delete not found":
                        print(f"Failed to delete message: {e}")
            context.chat_data[message_to_delete] = []

def exit_callback(update: Update, context: CallbackContext) -> None:
    msg = None
    user_id = update.effective_user.id
    
    if is_user_owner(update, context, user_id):
        query = update.callback_query
        query.answer()
        print(f"Exiting setup mode in group {update.effective_chat.id}")
        query.message.delete()
        context.chat_data['setup_stage'] = None
    else:
        print("User is not the owner.")

    if msg is not None:
        track_message(msg)

def handle_setup_inputs_from_admin(update: Update, context: CallbackContext) -> None:
    setup_stage = context.chat_data.get('setup_stage')
    print("Checking if chat is in setup mode.")
    if not setup_stage:
        print("Chat is not in setup mode.")
        return
    else:
        print(f"Chat is in setup stage: {setup_stage}")
    if setup_stage == 'contract':
        print(f"Received contract address in group {update.effective_chat.id}")
        handle_contract_address(update, context)
    elif setup_stage == 'liquidity':
        print(f"Received liquidity address in group {update.effective_chat.id}")
        handle_liquidity_address(update, context)
    elif setup_stage == 'website':
        print(f"Received website URL in group {update.effective_chat.id}")
        handle_website_url(update, context)
    elif setup_stage == 'welcome_message_header' and context.chat_data.get('expecting_welcome_message_header_image'):
        print(f"Received welcome message header image in group {update.effective_chat.id}")
        handle_welcome_message_image(update, context)
    elif setup_stage == 'buybot_message_header' and context.chat_data.get('expecting_buybot_header_image'):
        print(f"Received buybot message header image in group {update.effective_chat.id}")
        handle_buybot_message_image(update, context)
    elif context.chat_data.get('setup_stage') == 'set_max_warns':
        print(f"Received max warns number in group {update.effective_chat.id}")
        handle_max_warns(update, context)
    elif context.chat_data.get('setup_stage') == 'minimum_buy':
        print(f"Received minimum buy amount in group {update.effective_chat.id}")
        handle_minimum_buy(update, context)
    elif context.chat_data.get('setup_stage') == 'small_buy':
        print(f"Received small buy amount in group {update.effective_chat.id}")
        handle_small_buy(update, context)
    elif context.chat_data.get('setup_stage') == 'medium_buy':
        print(f"Received medium buy amount in group {update.effective_chat.id}")
        handle_medium_buy(update, context)

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
                keyboard = [ # General start command handling when not triggered via deep link
                    [InlineKeyboardButton("Add me to your group!", url=f"https://t.me/{BOT_USERNAME}?startgroup=0")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                msg = update.message.reply_text(
                    'Hello! I am Sypherbot. Please add me to your group to get started.',
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
        else:
            msg = update.message.reply_text("You are not the owner of this group.")

    if msg is not None:
        track_message(msg)

def setup_home_callback(update: Update, context: CallbackContext) -> None:
    query, user_id = get_query_info(update)

    if is_user_owner(update, context, user_id):
        chat_member = context.bot.get_chat_member(update.effective_chat.id, context.bot.id) # Check if the bot is an admin
        if not chat_member.can_invite_users:
            try:
                context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=context.chat_data.get('setup_bot_message', None),
                    text='Please give me admin permissions first!'
                )
                print(f"Bot does not have admin permissions in group: {update.effective_chat.id} - Editing message to request perms.")
            except telegram.error.BadRequest as e:
                if "message to edit not found" in str(e).lower():
                    context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="Please give me admin permissions first!"
                    )
                    print(f"Bot does not have admin permissions in group: {update.effective_chat.id} - Sending message to request perms.")
            return

        update = Update(update.update_id, message=query.message)

        if query.data == 'setup_home':
            setup_home(update, context, user_id)

def setup_home(update: Update, context: CallbackContext, user_id) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = fetch_group_info(update, context, return_doc=True)

    try:
        group_link = context.bot.export_chat_invite_link(group_id)
    except Exception as e:
        print(f"Error getting group link: {e}")
        group_link = None

    group_username = update.effective_chat.username # Get the group username
    if group_username is not None:
        group_username = "@" + group_username

    keyboard = [
        [
            InlineKeyboardButton("Admin", callback_data='setup_admin'),
            InlineKeyboardButton("Commands", callback_data='setup_commands')
        ],
        [
            InlineKeyboardButton("Authentication", callback_data='setup_authentication'),
            InlineKeyboardButton("Crypto", callback_data='setup_crypto')
        ],
        [
            InlineKeyboardButton("Premium", callback_data='setup_premium')
        ],
        [InlineKeyboardButton("Exit", callback_data='exit_setup')]
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
        'Configure Available Commands\n\n'
        '*🔒 Authentication:*\n'
        'Configure Auth Settings: Enable/Disable Auth, Auth Types [Simple, Math, Word], Auth Timeout & Check Current Auth Settings\n\n'
        '*📈 Crypto:*\n'
        'Configure Crypto Settings: Setup Token Details, Check Token Details or Reset Your Token Details.\n\n'
        '_Warning! Clicking "Reset Token Details" will reset all token details._\n\n'
        '*🚀 Premium:*\n'
        '🎨 Customize Your Bot\n'
        'Adjust the look and feel of your bot.\n'
        'Configure your Welcome Message Header and your Buybot Header.\n\n'
        '🔎 Group Monitoring:\n'
        'Buybot functionality.\n\n'
        '🚨 Sypher Trust:\n'
        'A smart system that dynamically adjusts the trust level of users based on their activity.',
        parse_mode='markdown',
        reply_markup=reply_markup
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

    group_doc.update({
        'group_info.group_link': group_link,
        'group_info.group_username': group_username,
    })
    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

SETUP_CALLBACK_DATA = [
    'setup_admin', 'reset_admin_settings',
    'setup_mute', 'enable_mute', 'disable_mute', 'check_mute_list',
    'setup_warn', 'enable_warn', 'disable_warn', 'check_warn_list', 'set_max_warns',
    'setup_allowlist', 'enable_allowlist', 'disable_allowlist', 'check_allowlist', 'clear_allowlist', 'setup_website',
    'setup_blocklist', 'enable_blocklist', 'disable_blocklist', 'check_blocklist', 'clear_blocklist',
    'setup_commands',
    'setup_authentication',
    'simple_authentication', 'math_authentication', 'word_authentication', 'timeout_authentication', 'check_authentication_settings',
    'setup_crypto', 'reset_token_details',
    'setup_premium',
    'setup_welcome_message_header', 'setup_buybot_message_header',
    'enable_sypher_trust', 'disable_sypher_trust', 'sypher_trust_preferences', 'sypher_trust_relaxed', 'sypher_trust_moderate', 'sypher_trust_strict',
    'setup_buybot'
] # Ensure callback data names match the function names so that you can access them dynamically via globals()
def handle_setup_callbacks(update: Update, context: CallbackContext) -> None:
    query, user_id = get_query_info(update)
    chosen_callback = query.data

    if chosen_callback in SETUP_CALLBACK_DATA:
        if is_user_owner(update, context, user_id):
            try:
                globals()[chosen_callback](update, context) # Dynamically invoke the function
                print(f"Callback {chosen_callback} handled.")
            except KeyError:
                print(f"Function {chosen_callback} does not exist.")
        else:
            print("User is not the owner.")
    else:
        print(f"Callback {chosen_callback} not found in SETUP_CALLBACK_DATA.")

#region Admin Setup
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
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def reset_admin_settings(update: Update, context: CallbackContext) -> None:
    group_id = update.effective_chat.id  # Get the group ID
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if not group_data: # Log if group data is missing
        print(f"No group data found for group ID {group_id}. Cannot reset admin settings.")
        update.message.reply_text("Group settings not found. Please ensure the group is properly registered.")
        return

    new_admin_settings = { # Reset admin settings
        'mute': False,
        'warn': False,
        'max_warns': 3,
        'allowlist': False,
        'blocklist': False
    }
    group_doc.update({'admin': new_admin_settings})
    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = update.message.reply_text("Admin settings have been reset to default.")
    store_message_id(context, msg.message_id)

    print(f"Admin settings for group {group_id} have been reset to: {new_admin_settings}")

    if msg is not None:
        track_message(msg)

#region Mute Setup
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
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def enable_mute(update: Update, context: CallbackContext) -> None:
    msg = None

    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

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
    
    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='✔️ Muting has been enabled in this group ✔️'
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def disable_mute(update: Update, context: CallbackContext) -> None:
    msg = None

    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

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

    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='❌ Muting has been disabled in this group ❌'
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def check_mute_list(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_data = fetch_group_info(update, context)

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
#
#region Warn Setup
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
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def enable_warn(update: Update, context: CallbackContext) -> None:
    msg = None

    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

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

    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='✔️ Warning has been enabled in this group ✔️'
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def disable_warn(update: Update, context: CallbackContext) -> None:
    msg = None

    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

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

    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='❌ Warning has been disabled in this group ❌'
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def check_warn_list(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [InlineKeyboardButton("Back", callback_data='setup_warn')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    group_id = update.effective_chat.id
    group_data = fetch_group_info(update, context)

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
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def set_max_warns(update: Update, context: CallbackContext) -> None:
    msg = None

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Please respond with the maximum number of warnings you want for the group.\n\n'
        '*Default Max Warns:* _3_',
        parse_mode='Markdown'
    )
    context.chat_data['setup_stage'] = 'set_max_warns'
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def handle_max_warns(update: Update, context: CallbackContext) -> None:
    group_doc = fetch_group_info(update, context, return_doc=True)

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
        clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Maximum number of warnings set to {max_warns}.'
        )
        store_message_id(context, msg.message_id)

        if msg is not None:
            track_message(msg)
#endregion Warn Setup
#
#region Allowlist Setup
def setup_allowlist(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [
            InlineKeyboardButton("Enable Allowlist", callback_data='enable_allowlist'),
            InlineKeyboardButton("Website", callback_data='setup_website'),
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
        'Here, you may add or remove links from the allowlist, check the current allowlist, disable allowlisting for links, or add your website link.\n\n'
        '_Please Note: If you disable link allowlisting, any links will be allowed in the group._\n\n'
        '*How To Allow Links:*\n'
        'To allow specific links in your group type: /allow <link>\n\n'
        '_Clearing the allowlist will remove all links and reset the allowlist._',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def enable_allowlist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is None:
        print(f"Creating new document for group {group_id}.")
        group_doc.set({
            'admin': {
                'allowlist': True
            }
        })
    else:
        print(f"Updating allowlisting for group {group_id}.")
        group_doc.update({
            'admin.allowlist': True
        })
    
    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='✔️ Allowlisting has been enabled in this group ✔️'
    )

    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def disable_allowlist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is None:
        print(f"Creating new document for group {group_id}.")
        group_doc.set({
            'admin': {
                'allowlist': False
            }
        })
    else:
        print(f"Updating allowlisting for group {group_id}.")
        group_doc.update({
            'admin.allowlist': False
        })
    
    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='❌ Allowlisting has been disabled in this group ❌'
    )

    context.chat_data['setup_stage'] = None

    if msg is not None:
        track_message(msg)

def setup_website(update: Update, context: CallbackContext) -> None:
    msg = None
    query, user_id = get_query_info(update)

    if is_user_owner(update, context, user_id):

        keyboard = [
            [InlineKeyboardButton("Back", callback_data='setup_allowlist')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        menu_change(context, update)

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Please respond with your website URL.',
            reply_markup=reply_markup
        )
        context.chat_data['setup_stage'] = 'website'
        print("Requesting website URL.")
        store_message_id(context, msg.message_id)

        if msg is not None:
            track_message(msg)

def handle_website_url(update: Update, context: CallbackContext) -> None:
    msg = None
    user_id = update.message.from_user.id

    if is_user_owner(update, context, user_id):
        if context.chat_data.get('setup_stage') == 'website':
            website_url = update.message.text.strip()

            if URL_PATTERN.fullmatch(website_url):  # Use the global URL_PATTERN
                group_id = update.effective_chat.id
                print(f"Adding website URL {website_url} to group {group_id}")
                group_doc = fetch_group_info(update, context, return_doc=True)
                group_doc.update({'group_info.website_url': website_url})
                clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
                context.chat_data['setup_stage'] = None

                if update.message is not None:
                    msg = update.message.reply_text("Website URL added successfully!")
                elif update.callback_query is not None:
                    msg = update.callback_query.message.reply_text("Website URL added successfully!")
            else:
                msg = update.message.reply_text("Please send a valid website URL! It must include 'https://' or 'http://'.")

        store_message_id(context, msg.message_id)

        if msg is not None:
            track_message(msg)

def check_allowlist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_data = fetch_group_info(update, context)

    allowlist_text = '*Current Allowlist:*\n\n'
    if group_data is None or 'allowlist' not in group_data or not group_data['allowlist']:
        allowlist_text += 'No links are currently allowed.'
    else:
        for link in group_data['allowlist']:
            allowlist_text += f'- {link}\n'

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=allowlist_text,
        parse_mode='Markdown'
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def clear_allowlist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is None:
        print(f"Creating new document for group {group_id}.")
        group_doc.set({
            'allowlist': []
        })
    else:
        print(f"Clearing allowlist for group {group_id}.")
        group_doc.update({
            'allowlist': []
        })

    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='❌ Allowlist has been cleared in this group ❌'
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)
#endregion Allowlist Setup
#
#region Blocklist Setup
def setup_blocklist(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [
            InlineKeyboardButton("Enable Blocklist", callback_data='enable_blocklist'),
            InlineKeyboardButton("Disable Blocklist", callback_data='disable_blocklist')
        ],
        [
            InlineKeyboardButton("Check Blocklist", callback_data='check_blocklist')
        ],
        [
            InlineKeyboardButton("❗ Clear Blocklist ❗", callback_data='clear_blocklist')
        ],
        [InlineKeyboardButton("Back", callback_data='setup_admin')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*⛔ Blocklist Setup ⛔*\n\n'
        'Here, you can view your current blocklist, or enable/disable the blocklist entirely.\n\n'
        '*How To Block Phrases:*\n'
        'To block specific phrases in your group type: /block <phrase>\n\n'
        '_Clearing the blocklist will remove all phrases and reset the blocklist._',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def enable_blocklist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is None:
        print(f"Creating new document for group {group_id}.")
        group_doc.set({
            'admin': {
                'blocklist': True
            }
        })
    else:
        print(f"Updating blocklisting for group {group_id}.")
        group_doc.update({
            'admin.blocklist': True
        })

    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='✔️ Blocklisting has been enabled in this group ✔️'
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def disable_blocklist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is None:
        print(f"Creating new document for group {group_id}.")
        group_doc.set({
            'admin': {
                'blocklist': False
            }
        })
    else:
        print(f"Updating blocklisting for group {group_id}.")
        group_doc.update({
            'admin.blocklist': False
        })

    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='❌ Blocklisting has been disabled in this group ❌'
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def check_blocklist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    group_data = fetch_group_info(update, context)

    if group_data is None:
        print(f"Failed to fetch blocklist data for group {group_id}.")
        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Error fetching blocklist data.',
            parse_mode='Markdown'
        )
        return

    blocklist_text = '*Current Blocklist:*\n\n'
    if group_data is None or 'blocklist' not in group_data or not group_data['blocklist']:
        print(f"No blocklist found for group {group_id}.")
        blocklist_text += 'No phrases are currently blocked.'
    else:
        for phrase in group_data['blocklist']:
            blocklist_text += f'- {phrase}\n'

    print(f"Sending blocklist data for group {group_id}.")
    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=blocklist_text,
        parse_mode='Markdown'
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def clear_blocklist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is None:
        print(f"Creating new document for group {group_id}.")
        group_doc.set({
            'blocklist': []
        })
    else:
        print(f"Clearing blocklist for group {group_id}.")
        group_doc.update({
            'blocklist': []
        })

    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='❌ Blocklist has been cleared in this group ❌'
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)
#endregion Blocklist Setup
#
##
#endregion Admin Setup
##
#
##
#region Commands Setup
def setup_commands(update: Update, context: CallbackContext) -> None:
    msg = None
    chat_id = update.effective_chat.id
    group_data = fetch_group_info(update, context)

    if not group_data:
        print(f"No group data found for group {chat_id}. Cannot set up commands.")
        return

    commands = group_data.get('commands', {})

    def get_button_text(command: str) -> str:
        status = "✅" if commands.get(command, True) else "❌"
        return f"{status} {command}"
    
    keyboard = [
        [InlineKeyboardButton(get_button_text("play"), callback_data='toggle_play')],
        [
            InlineKeyboardButton(get_button_text("website"), callback_data='toggle_website'),
            InlineKeyboardButton(get_button_text("contract"), callback_data='toggle_contract')
        ],
        [
            InlineKeyboardButton(get_button_text("price"), callback_data='toggle_price'),
            InlineKeyboardButton(get_button_text("buy"), callback_data='toggle_buy'),
            InlineKeyboardButton(get_button_text("chart"), callback_data='toggle_chart')
        ],
        [
            InlineKeyboardButton(get_button_text("liquidity"), callback_data='toggle_liquidity'),
            InlineKeyboardButton(get_button_text("volume"), callback_data='toggle_volume')
        ],
        [InlineKeyboardButton("Back", callback_data='setup_home')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*🤖 Command Setup 🤖*\n\n'
        'Here, you can enable or disable commands in your group. All commands are enabled by default.\n\n'
        'Clicking the button for each command below will disable or enable the command for your group.\n\n'
        '*How To Use Commands:*\n'
        'To use commands in your group type: /<command>. Users can also view all commands by typing /help or /commands.',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def toggle_command_status(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    chat_id = query.message.chat.id
    user_id = query.from_user.id

    if is_user_owner(update, context, user_id):
        command = query.data.replace('toggle_', '')  # Extract the command name

        if command == "play": # Check if the command is "play"
            if not is_premium_group(update, context):
                print(f"Group {chat_id} is not premium. Cannot toggle 'play' command.")
                return

        group_doc = db.collection('groups').document(str(chat_id))
        group_data = group_doc.get().to_dict()

        if not group_data:
            query.answer(text="Group data not found.", show_alert=True)
            return

        commands = group_data.get('commands', {})
        current_status = commands.get(command, True)  # Default to True if not set

        new_status = not current_status # Toggle the status
        group_doc.update({f'commands.{command}': new_status})
        print(f"Toggled command '{command}' to {new_status} for group {chat_id}")

        status_text = "enabled" if new_status else "disabled"
        query.answer(text=f"Command '{command}' is now {status_text}.", show_alert=False)
        clear_group_cache(str(chat_id)) # Clear the cache on all database updates

        setup_commands(update, context)
    else:
        print("User is not the owner.")

def check_command_status(update: Update, context: CallbackContext, command: str) -> bool:
    group_data = fetch_group_info(update, context)

    if not group_data:
        print(f"No group data found for group {update.effective_chat.id}. Defaulting '{command}' to disabled.")
        return False

    commands = group_data.get('commands', {})
    return commands.get(command, False)  # Default to False if the command is not explicitly set
#endregion Commands Setup
##
#
##
#region Authentication Setup
def setup_authentication(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [
            InlineKeyboardButton("Simple", callback_data='simple_authentication'),
            InlineKeyboardButton("Math", callback_data='math_authentication'),
            InlineKeyboardButton("Word", callback_data='word_authentication')
        ],
        [
            InlineKeyboardButton("Authentication Timeout", callback_data='timeout_authentication'),
            InlineKeyboardButton("Current Authentication Settings", callback_data='check_authentication_settings')
        ],
        [InlineKeyboardButton("Back", callback_data='setup_home')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*🌐 Authentication Setup 🌐*\n\nHere, you may choose the type of authentication to use for your group. The default is simple.', parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def simple_authentication(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is None:
        group_doc.set({
            'group_id': group_id,
            'verification_info': {
                'verification_type': 'simple',
                'verification_timeout': 600
            }
        })
    else:
        group_doc.update({
            'verification_info': {
                'verification_type': 'simple',
                'verification_timeout': 600
            }
        })
    
    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    menu_change(context, update)

    keyboard = [
        [InlineKeyboardButton("Back", callback_data='setup_authentication')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*🤡 Simple authentication enabled for this group 🤡*', parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def math_authentication(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is None:
        group_doc.set({
            'group_id': group_id,
            'verification_info': {
                'verification_type': 'math',
                'verification_timeout': 600
            }
        })
    else:
        group_doc.update({
            'verification_info': {
                'verification_type': 'math',
                'verification_timeout': 600
            }
        })

    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    keyboard = [
        [InlineKeyboardButton("Back", callback_data='setup_authentication')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*#️⃣ Math authentication enabled for this group #️⃣*',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)


    if msg is not None:
        track_message(msg)

def word_authentication(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is None:
        group_doc.set({
            'group_id': group_id,
            'verification_info': {
                'verification_type': 'word',
                'verification_timeout': 600
            }
        })
    else:
        group_doc.update({
            'verification_info': {
                'verification_type': 'word',
                'verification_timeout': 600
            }
        })

    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    context.chat_data['setup_stage'] = 'setup_word_verification'

    menu_change(context, update)

    keyboard = [
        [InlineKeyboardButton("Back", callback_data='setup_authentication')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = context.bot.send_message( # Ask the question for new users
        chat_id=update.effective_chat.id,
        text='*🈹 Word authentication enabled for this group 🈹*',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)


    if msg is not None:
        track_message(msg)

def timeout_authentication(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [
            InlineKeyboardButton("1 Minute", callback_data='auth_timeout_60'),
            InlineKeyboardButton("10 Minutes", callback_data='auth_timeout_600')
        ],
        [
            InlineKeyboardButton("30 Minutes", callback_data='auth_timeout_1800'),
            InlineKeyboardButton("60 Minutes", callback_data='auth_timeout_3600')
        ],
        [InlineKeyboardButton("Back", callback_data='setup_authentication')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Please choose the authentication timeout.',
        reply_markup=reply_markup
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def handle_timeout_callback(update: Update, context: CallbackContext) -> None:
    msg = None
    query, user_id = get_query_info(update)

    if is_user_owner(update, context, user_id):
        timeout_seconds = int(query.data.split('_')[1]) # Extract the timeout value from the callback_data

        group_id = update.effective_chat.id # Call set_verification_timeout with the group_id and timeout_seconds
        set_authentication_timeout(group_id, timeout_seconds)

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Authentication timeout set to {timeout_seconds // 60} minutes."
        )
        store_message_id(context, msg.message_id)

        if msg is not None:
            track_message(msg)

def set_authentication_timeout(group_id: int, timeout_seconds: int) -> None: # Sets the verification timeout for a specific group in the Firestore database.
    try:
        group_ref = db.collection('groups').document(str(group_id))

        group_ref.update({
            'verification_info.verification_timeout': timeout_seconds
        })

        print(f"Authentication timeout for group {group_id} set to {timeout_seconds} seconds")

    except Exception as e:
        print(f"Error setting verification timeout: {e}")

def check_authentication_settings(update: Update, context: CallbackContext) -> None:
    msg = None
    group_data = fetch_group_info(update, context)

    if group_data is not None:
        authentication_info = group_data.get('verification_info', {})
        authentication_type = authentication_info.get('verification_type', 'simple')
        authentication_timeout = authentication_info.get('verification_timeout', 000)

        menu_change(context, update)

        keyboard = [
            [InlineKeyboardButton("Back", callback_data='setup_authentication')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"*🔒 Current Authentication Settings 🔒*\n\nAuthentication: {authentication_type}\nTimeout: {authentication_timeout // 60} minutes",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        context.chat_data['setup_stage'] = None
        store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)
#endregion Authentication Setup
##
#
##
#region Crypto Setup
def setup_crypto(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [
            InlineKeyboardButton("Chain", callback_data='setup_chain')
        ],
        [
            InlineKeyboardButton("Contract", callback_data='setup_contract'),
            InlineKeyboardButton("Liquidity", callback_data='setup_liquidity')
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
        '• This functionality currently is only setup for ETH paired tokens.\n\n'
        '*⚠️ Updating Token Details ⚠️*\n'
        'To enter new token details, you must click *Reset Token Details* first.',
        parse_mode='markdown',
        reply_markup=reply_markup
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def setup_contract(update: Update, context: CallbackContext) -> None:
    msg = None
    query, user_id = get_query_info(update)

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
        context.chat_data['setup_stage'] = 'contract'
        print("Requesting contract address.")
        store_message_id(context, msg.message_id)

        if msg is not None:
            track_message(msg)

def handle_contract_address(update: Update, context: CallbackContext) -> None:
    msg = None
    user_id = update.message.from_user.id
    
    if is_user_owner(update, context, user_id):
        if context.chat_data.get('setup_stage') == 'contract':
            eth_address_pattern = re.compile(r'\b0x[a-fA-F0-9]{40}\b')
            contract_address = update.message.text.strip()

            if eth_address_pattern.fullmatch(contract_address):
                group_id = update.effective_chat.id
                print(f"Adding contract address {contract_address} to group {group_id}")
                group_doc = fetch_group_info(update, context, return_doc=True)
                group_doc.update({'token.contract_address': contract_address})
                clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
                context.chat_data['setup_stage'] = None

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
    query, user_id = get_query_info(update)
    
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
        context.chat_data['setup_stage'] = 'liquidity'
        store_message_id(context, msg.message_id)
        print("Requesting liquidity address.")

        if msg is not None:
            track_message(msg)

def handle_liquidity_address(update: Update, context: CallbackContext) -> None:
    msg = None
    user_id = update.message.from_user.id

    if is_user_owner(update, context, user_id):
        msg = None
        if context.chat_data.get('setup_stage') == 'liquidity':
            eth_address_pattern = re.compile(r'\b0x[a-fA-F0-9]{40}\b')
            liquidity_address = update.message.text.strip()

            if eth_address_pattern.fullmatch(liquidity_address):
                group_id = update.effective_chat.id
                print(f"Adding liquidity address {liquidity_address} to group {group_id}")
                group_doc = fetch_group_info(update, context, return_doc=True)
                group_doc.update({'token.liquidity_address': liquidity_address})
                clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
                context.chat_data['setup_stage'] = None

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

def setup_chain(update: Update, context: CallbackContext) -> None:
    msg = None
    query, user_id = get_query_info(update)
    
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
            text='Please choose your chain from the list.\n\n'
            'Currently only Base Mainnet + Uniswap V3 LP is *fully* supported. We will be rolling out support for other chains and LP positions shortly.',
            reply_markup=reply_markup
        )
        context.chat_data['setup_stage'] = 'chain'
        store_message_id(context, msg.message_id)
        print("Requesting Chain.")

        if msg is not None:
            track_message(msg)

def handle_chain(update: Update, context: CallbackContext) -> None:
    query, user_id = get_query_info(update)

    if is_user_owner(update, context, user_id):
        if context.chat_data.get('setup_stage') == 'chain':
            chain = update.callback_query.data.upper()  # Convert chain to uppercase
            group_id = update.effective_chat.id
            print(f"Adding chain {chain} to group {group_id}")
            group_doc = fetch_group_info(update, context, return_doc=True)
            group_doc.update({'token.chain': chain})
            clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
            context.chat_data['setup_stage'] = None

            complete_token_setup(group_id, context)

            msg = query.message.reply_text("Chain has been saved.")

            store_message_id(context, msg.message_id)

            if msg is not None:
                track_message(msg)

def complete_token_setup(group_id: str, context: CallbackContext):
    msg = None
    group_doc = db.collection('groups').document(str(group_id))
    group_data = group_doc.get().to_dict()

    token_data = group_data.get('token')
    if not token_data:
        print("Token data not found for this group.")
        return

    if 'chain' not in token_data:
        print(f"Chain not found in group {group_id}, token setup incomplete.")
        return
    chain = token_data.get('chain')
    
    if 'contract_address' not in token_data:
        print(f"Contract address not found in group {group_id}, token setup incomplete.")
        return
    contract_address = token_data['contract_address']

    if 'liquidity_address' not in token_data:
        print(f"Liquidity address not found in group {group_id}, token setup incomplete.")
        return

    web3 = config.WEB3_INSTANCES.get(chain) # Get the Web3 instance for the chain
    if not web3:
        print(f"Web3 provider not found for chain {chain}, token setup incomplete.")
        return
    
    base_dir = os.path.dirname(os.path.dirname(__file__))
    abi_path = os.path.join(base_dir, 'config', 'erc20.abi.json')

    with open(abi_path, 'r') as abi_file:
        abi = json.load(abi_file)

    contract = web3.eth.contract(address=contract_address, abi=abi)

    try: # Call the name, symbol, and decimals functions
        token_name = contract.functions.name().call()
        token_symbol = contract.functions.symbol().call()
        decimals = contract.functions.decimals().call()
        total_supply = contract.functions.totalSupply().call() / (10 ** decimals)
    except Exception as e:
        print(f"Failed to get token name, symbol, total supply and decimals: {e}")
        return
    
    group_doc.update({ # Update the Firestore document with the token name, symbol, and total supply
        'token.name': token_name,
        'token.symbol': token_symbol,
        'token.total_supply': total_supply,
        'token.decimals': decimals
    })

    clear_group_cache(str(group_id)) # Clear the cache on all database updates
    
    print(f"Added token name {token_name}, symbol {token_symbol}, and total supply {total_supply} to group {group_id}")

    if group_data.get('premium', False):  # Check if premium is True
        schedule_group_monitoring(group_data) # Instantly start monitoring the group
    else:
        print(f"Group {group_data['group_id']} is not premium. Skipping monitoring.")

    msg = context.bot.send_message(
        chat_id=group_id,
        text=f"*🎉 Token setup complete! 🎉*\n\n*Name:* {token_name}\n*Symbol:* {token_symbol}\n*Total Supply:* {total_supply}\n*Decimals:* {decimals}",
        parse_mode='Markdown'
    )

    if msg is not None:
        track_message(msg)

def check_token_details_callback(update: Update, context: CallbackContext) -> None:
    query, user_id = get_query_info(update)

    update = Update(update.update_id, message=query.message)

    if query.data == 'check_token_details':
        if is_user_owner(update, context, user_id):
            check_token_details(update, context)
        else:
            print("User is not the owner.")

def check_token_details(update: Update, context: CallbackContext) -> None:
    msg = None
    group_data = fetch_group_info(update, context)

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
        context.chat_data['setup_stage'] = None
        store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def reset_token_details(update: Update, context: CallbackContext) -> None:
    msg = None
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is not None:
        group_doc.update({
            'token': {}
        })

        clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*🔄 Token Details Reset 🔄*',
            parse_mode='Markdown'
        )

    if msg is not None:
        track_message(msg)
#endregion Crypto Setup
##
#
##
#region Premium Setup
def setup_premium(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [
            InlineKeyboardButton("Welcome Message Header", callback_data='setup_welcome_message_header'),
            InlineKeyboardButton("Buybot Message Header", callback_data='setup_buybot_message_header')
        ],
        [
            InlineKeyboardButton("Enable Trust System", callback_data='enable_sypher_trust'),
            InlineKeyboardButton("Disable Trust System", callback_data='disable_sypher_trust')
        ],
        [
            InlineKeyboardButton("Buybot Preferences", callback_data='setup_buybot')
        ],
        [
            InlineKeyboardButton("Trust Preferences", callback_data='sypher_trust_preferences'),
        ],
        [InlineKeyboardButton("Back", callback_data='setup_home')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*🚀 Premium Setup 🚀*\n\n'
        '🎨 Customize:\n'
        'Configure your *Welcome Message Header* and your *Buybot Header*.\n\n'
        '💰 Buybot Funcationality:\n'
        'Change settings for buybot (coming soon)\n\n'
        '🚨 Sypher Trust:\n'
        'Enable/Disable Trust System. Set Trust Preferences.',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def is_premium_group(update: Update, context: CallbackContext) -> bool:
    group_id = update.effective_chat.id
    group_data = fetch_group_info(update, context)
    
    if group_data is not None and group_data.get('premium') is not True:
        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="This feature is only available to premium users. Please contact @tukyowave for more information.",
            parse_mode='Markdown'
        )
        store_message_id(context, msg.message_id)
        print(f"{group_id} is not a premium group.")
        return False
    else:
        print(f"{group_id} is a premium group.")
        return True

#region Customization Setup
def setup_welcome_message_header(update: Update, context: CallbackContext) -> None:
    msg = None

    if not is_premium_group(update, context): return

    print("Requesting a welcome message header.")
    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please send a jpg image for the welcome message header that is less than 700x250px.",
        parse_mode='Markdown'
    )
    context.chat_data['expecting_welcome_message_header_image'] = True  # Flag to check in the image handler
    context.chat_data['setup_stage'] = 'welcome_message_header'
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def handle_welcome_message_image(update: Update, context: CallbackContext) -> None:
    msg = None
    if context.chat_data.get('expecting_welcome_message_header_image'):
        group_id = update.effective_chat.id
        result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
        if not result:
            print("Failed to fetch group info. No action taken.")
            return

        group_data, group_doc = result  # Unpack the tuple
        
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
                clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

            msg = context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Your welcome message header image has been successfully uploaded!",
                parse_mode='Markdown'
            )
            context.chat_data['expecting_welcome_message_header_image'] = False  # Reset the flag
            context.chat_data['setup_stage'] = None
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

def setup_buybot_message_header(update: Update, context: CallbackContext) -> None:
    msg = None

    if not is_premium_group(update, context): return
    
    print("Requesting a Buybot message header.")

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please send a jpg image for the buybot message header that is less than 700x250px.",
        parse_mode='Markdown'
    )
    context.chat_data['expecting_buybot_header_image'] = True  # Flag to check in the image handler
    context.chat_data['setup_stage'] = 'buybot_message_header'
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def handle_buybot_message_image(update: Update, context: CallbackContext) -> None:
    msg = None
    if context.chat_data.get('expecting_buybot_header_image'):
        group_id = update.effective_chat.id
        result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
        if not result:
            print("Failed to fetch group info. No action taken.")
            return

        group_data, group_doc = result  # Unpack the tuple
        
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
                clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

            msg = context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Your buybot message header image has been successfully uploaded!",
                parse_mode='Markdown'
            )
            context.chat_data['expecting_buybot_header_image'] = False  # Reset the flag
            context.chat_data['setup_stage'] = None
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
#endregion Customization Setup
##
#
##
#region Sypher Trust Setup
def enable_sypher_trust(update: Update, context: CallbackContext) -> None:
    msg = None
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if not is_premium_group(update, context): return

    if group_data is not None:
        group_doc.update({
            'premium_features.sypher_trust': True,
            'premium_features.sypher_trust_preferences': 'moderate'
        })
        clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*✔️ Trust System Enabled ✔️*',
            parse_mode='Markdown'
        )
        context.chat_data['setup_stage'] = None
        store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def disable_sypher_trust(update: Update, context: CallbackContext) -> None:
    msg = None
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple
    
    if not is_premium_group(update, context): return

    if group_data is not None:
        group_doc.update({
            'premium_features.sypher_trust': False
        })
        clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*❌ Trust System Disabled ❌*',
            parse_mode='Markdown'
        )
        context.chat_data['setup_stage'] = None
        store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def sypher_trust_preferences(update: Update, context: CallbackContext) -> None:
    msg = None

    if not is_premium_group(update, context): return

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
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def sypher_trust_relaxed(update: Update, context: CallbackContext) -> None:
    msg = None
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is not None:
        group_doc.update({
            'premium_features.sypher_trust_preferences': 'relaxed'
        })
        clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*🟢 Relaxed Trust Level Enabled 🟢*',
            parse_mode='Markdown'
        )
        store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def sypher_trust_moderate(update: Update, context: CallbackContext) -> None:
    msg = None
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is not None:
        group_doc.update({
            'premium_features.sypher_trust_preferences': 'moderate'
        })
        clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*🟡 Moderate Trust Level Enabled 🟡*',
            parse_mode='Markdown'
        )
        store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def sypher_trust_strict(update: Update, context: CallbackContext) -> None:
    msg = None
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is not None:
        group_doc.update({
            'premium_features.sypher_trust_preferences': 'strict'
        })
        clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*🔴 Strict Trust Level Enabled 🔴*',
            parse_mode='Markdown'
        )
        store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def check_if_trusted(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    group_id = str(update.effective_chat.id)

    group_data = fetch_group_info(update, context)
    if not group_data:
        print(f"No group data found for group {group_id}. Assuming Sypher Trust is not enabled.")
        return False

    sypher_trust_enabled = group_data.get('premium_features', {}).get('sypher_trust', False) # Verify if Sypher Trust is enabled
    if not sypher_trust_enabled:
        print(f"Sypher Trust is not enabled for group {group_id}. Allowing user {user_id}.")
        return True

    untrusted_users = group_data.get('untrusted_users', {}) # Check if the user is in untrusted_users
    user_data = untrusted_users.get(user_id)
    if not user_data:
        print(f"User {user_id} is not in untrusted_users for group {group_id}. Assuming trusted.")
        return True

    try: # Try to get user's time
        user_added_time = datetime.fromisoformat(user_data)
    except ValueError:
        print(f"Invalid timestamp format for user {user_id} in untrusted_users. Assuming untrusted.")
        return False

    current_time = datetime.now(timezone.utc)
    time_elapsed = current_time - user_added_time

    sypher_trust_preferences = group_data.get('premium_features', {}).get('sypher_trust_preferences', 'moderate') # Determine trust preferences, default to moderate
    trust_durations = {
        'relaxed': timedelta(days=RELAXED_TRUST),
        'moderate': timedelta(days=MODERATE_TRUST),
        'strict': timedelta(days=STRICT_TRUST),
    }
    trust_duration = trust_durations.get(sypher_trust_preferences)

    if not trust_duration:
        print(f"Invalid sypher trust preference: {sypher_trust_preferences}. Defaulting to untrusted.")
        return False

    if time_elapsed >= trust_duration: # Check if sufficient time has passed
        print(f"User {user_id} has been in untrusted_users for {time_elapsed}. Removing from untrusted_users.")
        db.collection('groups').document(group_id).update({f'untrusted_users.{user_id}': firestore.DELETE_FIELD})
        clear_group_cache(group_id) # Clear the cache on all database updates
        return True
    else:
        print(f"User {user_id} has been in untrusted_users for {time_elapsed}. Still untrusted.")
        return False
#endregion Sypher Trust Setup
##
#
##
#region Buybot Setup
def setup_buybot(update: Update, context: CallbackContext) -> None:
    msg = None

    if not is_premium_group(update, context): return

    keyboard = [
        [
            InlineKeyboardButton("Minimum Buy", callback_data='setup_minimum_buy'),
            InlineKeyboardButton("Small Buy", callback_data='setup_small_buy'),
            InlineKeyboardButton("Medium Buy", callback_data='setup_medium_buy'),
        ],
        [InlineKeyboardButton("Back", callback_data='setup_premium')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    menu_change(context, update)

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='*💰 Buybot Preferences 💰*\n\n'
        'Here you can setup the trigger zones for buys on your token!\n\n'
        '*Minimum Buy:*\n'
        'The minimum amount of tokens to trigger a buy.\n\n'
        '🐟 *Small Buy* 🐟\n'
        'Below this amount will be considered a small buy.\n\n'
        '🐬 *Medium Buy* 🐬\n'
        'Below this amount will be considered a medium buy.\n\n'
        '🐳 *Whale* 🐳\n'
        'Any buy above the medium buy amount will be considered a whale.',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    context.chat_data['setup_stage'] = None
    store_message_id(context, msg.message_id)

    if msg is not None:
        track_message(msg)

def setup_minimum_buy_callback(update: Update, context: CallbackContext) -> None:
    msg = None
    query, user_id = get_query_info(update)

    if is_user_owner(update, context, user_id):

        keyboard = [
            [InlineKeyboardButton("Back", callback_data='setup_buybot')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        menu_change(context, update) 

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Please respond with your minimum buy amount to trigger the buybot.',
            reply_markup=reply_markup
        )
        context.chat_data['setup_stage'] = 'minimum_buy'
        print("Requesting minumum buy amount.")
        store_message_id(context, msg.message_id)

        if msg is not None:
            track_message(msg)

def handle_minimum_buy(update: Update, context: CallbackContext) -> None:
    msg = None
    user_id = update.message.from_user.id
    
    if is_user_owner(update, context, user_id):
        if context.chat_data.get('setup_stage') == 'minimum_buy':
            group_id = update.effective_chat.id
            group_data = fetch_group_info(update, context)
            if group_data is not None:
                group_doc = db.collection('groups').document(str(group_id))
                group_doc.update({
                    'premium_features.buybot.minimumbuy': int(update.message.text)
                })
                msg = update.message.reply_text("Minimum buy value updated successfully!")
                clear_group_cache(str(group_id)) # Clear the cache on all database updates

        store_message_id(context, msg.message_id)

    else:
        print("User is not the owner.")

    if msg is not None:
        track_message(msg)

def setup_small_buy_callback(update: Update, context: CallbackContext) -> None:
    msg = None
    query, user_id = get_query_info(update)

    if is_user_owner(update, context, user_id):

        keyboard = [
            [InlineKeyboardButton("Back", callback_data='setup_buybot')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        menu_change(context, update) 

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Please respond with the maximum amount of tokens to trigger a small buy.',
            reply_markup=reply_markup
        )
        context.chat_data['setup_stage'] = 'small_buy'
        print("Requesting medium buy amount.")
        store_message_id(context, msg.message_id)

        if msg is not None:
            track_message(msg)

def handle_small_buy(update: Update, context: CallbackContext) -> None:
    msg = None
    user_id = update.message.from_user.id
    
    if is_user_owner(update, context, user_id):
        if context.chat_data.get('setup_stage') == 'small_buy':
            group_id = update.effective_chat.id
            group_data = fetch_group_info(update, context)
            if group_data is not None:
                group_doc = db.collection('groups').document(str(group_id))
                try:
                    group_doc.update({
                        'premium_features.buybot.smallbuy': int(update.message.text)
                    })
                    clear_group_cache(str(group_id))  # Clear the cache on all database updates
                    msg = update.message.reply_text("Small buy value updated successfully!")
                except Exception as e:
                    msg = update.message.reply_text(f"Error updating small buy value: {e}")
        
        if msg:
            store_message_id(context, msg.message_id)

    else:
        print("User is not the owner.")

    if msg is not None:
        track_message(msg)

def setup_medium_buy_callback(update: Update, context: CallbackContext) -> None:
    msg = None
    query, user_id = get_query_info(update)

    if is_user_owner(update, context, user_id):

        keyboard = [
            [InlineKeyboardButton("Back", callback_data='setup_buybot')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        menu_change(context, update) 

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Please respond with the maximum amount of tokens to trigger a medium buy.',
            reply_markup=reply_markup
        )
        context.chat_data['setup_stage'] = 'medium_buy'
        print("Requesting medium buy amount.")
        store_message_id(context, msg.message_id)

        if msg is not None:
            track_message(msg)

def handle_medium_buy(update: Update, context: CallbackContext) -> None:
    msg = None
    user_id = update.message.from_user.id
    
    if is_user_owner(update, context, user_id):
        if context.chat_data.get('setup_stage') == 'medium_buy':
            group_id = update.effective_chat.id
            group_data = fetch_group_info(update, context)
            if group_data is not None:
                group_doc = db.collection('groups').document(str(group_id))
                try:
                    group_doc.update({
                        'premium_features.buybot.mediumbuy': int(update.message.text)
                    })
                    clear_group_cache(str(group_id))  # Clear the cache on all database updates
                    msg = update.message.reply_text("Medium buy value updated successfully!")
                except Exception as e:
                    msg = update.message.reply_text(f"Error updating medium buy value: {e}")
        
        if msg:
            store_message_id(context, msg.message_id)

    else:
        print("User is not the owner.")

    if msg is not None:
        track_message(msg)
#endregion Buybot Setup
##
#
##
#endregion Premium Setup
##
#
##
#endregion Bot Setup
#
#region User Authentication
def handle_new_user(update: Update, context: CallbackContext) -> None:
    bot_added_to_group(update, context)
    msg = None
    group_id = update.message.chat.id
    result = fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple
    if group_data is None:
        group_name = "the group"  # Default text if group name not available
        print("Group data not found.")
    else:
        group_name = group_data.get('group_info', {}).get('group_username', "the group")

    sypher_trust_enabled = (
        group_data.get('premium_features', {}).get('sypher_trust') if group_data else False
    )

    updates = {} # Initialize the updates to send to the database at the end of the function
        
    for member in update.message.new_chat_members:
            user_id = member.id
            chat_id = update.message.chat.id

            if user_id == context.bot.id:
                return
            
            print(f"New user {user_id} joined group {chat_id}")

            context.bot.restrict_chat_member( # Mute the new user
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False)
            )

            print(f"User {user_id} restricted in group {chat_id}")

            if anti_raid.is_raid():
                msg = update.message.reply_text(f'Anti-raid triggered! Please wait {anti_raid.time_to_wait()} seconds before new users can join.')
                
                user_id = update.message.new_chat_members[0].id # Get the user_id of the user that just joined

                context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id) # Kick the user that just joined
                return
            else: # If not a raid
                print(f"No raid detected... Allowing user {user_id} to join.")

            current_time = datetime.now(timezone.utc).isoformat()  # Get the current date/time in ISO 8601 format

            if sypher_trust_enabled:
                print(f"Sypher Trust is enabled for group {group_id}. Adding user {user_id} to untrusted_users.")
                updates[f'untrusted_users.{user_id}'] = current_time
            
            auth_url = f"https://t.me/{BOT_USERNAME}?start=authenticate_{chat_id}_{user_id}"
            keyboard = [ [InlineKeyboardButton("Start Authentication", url=auth_url)] ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if group_data is not None and group_data.get('premium') and group_data.get('premium_features', {}).get('welcome_header'):
                blob = bucket.blob(f'sypherbot/public/welcome_message_header/welcome_message_header_{group_id}.jpg')
                welcome_image_url = blob.generate_signed_url(expiration=timedelta(minutes=BLOB_EXPIRATION))

                print(f"Group {group_id} has premium features enabled, and has a header uploaded... Sending welcome message with image.")

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
                print(f"Group {group_id} does not have premium features enabled. Sending welcome message without image.")

            updates[f'unverified_users.{user_id}'] = { # Collect updates for Firestore
                'timestamp': current_time,
                'challenge': None,  # Initializes with no challenge
                'join_message_id': msg.message_id
            }
            print(f"New user {user_id} added to unverified users in group {group_id} at {current_time}")

            context.job_queue.run_once( # Schedule the deletion of the join message after 5 minutes
                delete_join_message,
                when=300, # TODO: Make this after {verification_timeout}
                context={'chat_id': chat_id, 'message_id': msg.message_id, 'user_id': user_id}
            )

            if updates:
                group_doc.update(updates)
                clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

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
        authentication_info = group_data.get('verification_info', {})
        authentication_type = authentication_info.get('verification_type', 'simple')

        print(f"Authentication type: {authentication_type}")

        if str(user_id) in unverified_users: # Check if the user ID is in the KEYS of the unverified_users mapping
            if authentication_type == 'simple':
                authenticate_user(context, group_id, user_id)
            elif authentication_type == 'math' or authentication_type == 'word':
                authentication_challenge(
                    update, context, authentication_type, group_id, user_id
                )
            else:
                query.edit_message_text(text="Invalid authentication type configured.")
        else:
            query.edit_message_text(
                text="You are already verified, not a member or need to restart authentication."
            )
    else:
        query.edit_message_text(text="No such group exists.")

def authentication_challenge(update: Update, context: CallbackContext, authentication_type, group_id, user_id):
    group_doc = fetch_group_info(update, context, return_doc=True, group_id=group_id)

    if authentication_type == 'math':
        challenges = [MATH_0, MATH_1, MATH_2, MATH_3, MATH_4]
        index = random.randint(0, 4)
        math_challenge = challenges[index]

        blob = bucket.blob(f'sypherbot/private/auth/math_{index}.jpg')
        image_url = blob.generate_signed_url(expiration=timedelta(minutes=BLOB_EXPIRATION))

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

        group_doc.update({ # Update Firestore with the challenge
            f'unverified_users.{user_id}.challenge': math_challenge
        })
        clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
        print(f"Stored math challenge for user {user_id} in group {group_id}: {math_challenge}")

    elif authentication_type == 'word':
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
            photo=image_url,
            caption="Identify the correct word in the image:",
            reply_markup=reply_markup
        )
    
        group_doc.update({ # Update Firestore with the challenge
            f'unverified_users.{user_id}.challenge': word_challenge
        })
        clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
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

        if str(user_id) in group_data_dict.get('unverified_users', {}): # Check if the user is in the unverified users mapping
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

        if str(user_id) in group_data_dict.get('unverified_users', {}): # Check if the user is in the unverified users mapping
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
    # Always check the database when authenticating the user
    # This is to avoid using stale cached data
    group_doc = db.collection('groups').document(group_id)
    group_data = group_doc.get().to_dict()

    print(f"Authenticating user {user_id} in group {group_id}")

    if 'unverified_users' in group_data and user_id in group_data['unverified_users']:
        join_message_id = group_data['unverified_users'][user_id].get('join_message_id')
        if join_message_id:
            try: # Attempt to delete the join message
                context.bot.delete_message(
                    chat_id=int(group_id),
                    message_id=join_message_id
                )
                print(f"Deleted join message {join_message_id} for user {user_id} in group {group_id}")
            except Exception as e:
                print(f"Failed to delete join message {join_message_id} for user {user_id}: {e}")

        del group_data['unverified_users'][user_id]
        print(f"Removed user {user_id} from unverified users in group {group_id}")

        group_doc.set(group_data) # Write the updated group data back to Firestore
        clear_group_cache(str(group_id)) # Clear the cache on all database updates

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
    group_doc = fetch_group_info(update, context, return_doc=True)
    group_data = group_doc.get().to_dict() 

    if 'unverified_users' in group_data and user_id in group_data['unverified_users']:
        group_data['unverified_users'][user_id] = None

    print(f"Reset challenge for user {user_id} in group {group_id}")

    group_doc.set(group_data) # Write the updated group data back to Firestore
    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    context.bot.delete_message(
        chat_id=update.effective_chat.id,
        message_id=update.callback_query.message.message_id
    )

    context.bot.send_message( # Send a message to the user instructing them to start the authentication process again
        chat_id=user_id,
        text="Authentication failed. Please start the authentication process again by clicking on the 'Start Authentication' button."
    )

def delete_join_message(context: CallbackContext) -> None:
    job_data = context.job.context
    chat_id = job_data['chat_id']
    message_id = job_data['message_id']
    user_id = job_data['user_id']

    try:
        context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        print(f"Deleted join message {message_id} for user {user_id} in chat {chat_id}.")
    except Exception as e:
        print(f"Failed to delete join message {message_id} for user {user_id} in chat {chat_id}: {e}")
# endregion User Authentication
#
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
#
#region Buybot
def monitor_transfers(web3_instance, liquidity_address, group_data):
    base_dir = os.path.dirname(os.path.dirname(__file__))
    abi_path = os.path.join(base_dir, 'config', 'erc20.abi.json')

    with open(abi_path, 'r') as abi_file:
        abi = json.load(abi_file)
    
    contract_address = group_data['token']['contract_address']
    
    contract = web3_instance.eth.contract(address=contract_address, abi=abi)

    # Initialize static tracking of the last seen block
    if not hasattr(monitor_transfers, "last_seen_block"):
        lookback_range = 100 # Check the last 100 blocks on boot
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
    fetched_data, group_doc = fetch_group_info(
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
            f"{buyer_emoji} {token_amount:.4f} {token_name}{value_message}"
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
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    if rate_limit_check():
        try:
            msg = bot.send_message(chat_id=group_id, text=text, parse_mode='Markdown', reply_markup=reply_markup)
            if msg is not None:
                track_message(msg)
        except Exception as e:
            print(f"Error sending message: {e}")
    else:
        try:
            bot.send_message(chat_id=group_id, text="Bot rate limit exceeded. Please try again later.")
        except Exception as e:
            print(f"Error sending rate limit message: {e}")
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
        
        if pool_type == "v3":
            price_in_weth = get_uniswap_v3_position_data(chain, lp_address)
        elif pool_type == "v2":
            price_in_weth = get_uniswap_v2_price(chain, lp_address)

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
        
        base_dir = os.path.dirname(os.path.dirname(__file__))
        abi_path = os.path.join(base_dir, 'config', 'uniswap_v3.abi.json')
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
    
def get_uniswap_v3_position_data(chain, lp_address):
    try:
        web3_instance = config.WEB3_INSTANCES.get(chain)  # Connect to the Uniswap V3 liquidity pool
        if not web3_instance:
            print(f"Web3 instance for chain {chain} not found or not connected.")
            return None
        
        base_dir = os.path.dirname(os.path.dirname(__file__))
        abi_path = os.path.join(base_dir, 'config', 'uniswap_v3.abi.json')
        with open(abi_path, 'r') as abi_file:
            abi = json.load(abi_file)

        address = web3_instance.to_checksum_address(lp_address)

        pair_contract = web3_instance.eth.contract(address=address, abi=abi)

        slot0 = pair_contract.functions.slot0().call() # Fetch slot0 data (contains sqrtPriceX96)
        sqrt_price_x96 = slot0[0]

        print(f"Raw sqrtPriceX96: {sqrt_price_x96}")

        sqrt_price_x96_decimal = Decimal(sqrt_price_x96) # Use Decimal for precise calculations
        price_in_weth = (sqrt_price_x96_decimal ** 2) / Decimal(2 ** 192) 
        return price_in_weth
    except Exception as e:
        print(f"Error fetching Uniswap V3 position data: {e}")
        return None

def get_uniswap_v2_price(chain, lp_address):
    try:
        web3_instance = config.WEB3_INSTANCES.get(chain)
        if not web3_instance:
            print(f"Web3 instance for chain {chain} not found or not connected.")
            return None
        
        base_dir = os.path.dirname(os.path.dirname(__file__))

        univ2_abi_path = os.path.join(base_dir, 'config', 'uniswap_v2.abi.json')
        with open(univ2_abi_path, 'r') as univ2_abi_file:
            univ2_abi = json.load(univ2_abi_file)

        address = web3_instance.to_checksum_address(lp_address)

        pair_contract = web3_instance.eth.contract(address=address, abi=univ2_abi)

        reserves = pair_contract.functions.getReserves().call()
        reserve0 = Decimal(reserves[0])
        reserve1 = Decimal(reserves[1])
        print(f"Raw reserves: reserve0={reserve0}, reserve1={reserve1}")

        erc20_abi_path = os.path.join(base_dir, 'config', 'erc20.abi.json')
        with open(erc20_abi_path, 'r') as erc20_abi_file:
            your_erc20_abi = json.load(erc20_abi_file)

        token0_address = pair_contract.functions.token0().call()
        token0_contract = web3_instance.eth.contract(address=token0_address, abi=your_erc20_abi)
        decimals0 = token0_contract.functions.decimals().call()

        reserve0_adjusted = reserve0 / (10 ** decimals0)
        reserve1_adjusted = reserve1 / (10 ** 18)  # WETH has 18 decimals
        print(f"Adjusted reserves: reserve0={reserve0_adjusted}, reserve1={reserve1_adjusted}")

        price_in_weth = reserve1_adjusted / reserve0_adjusted
        print(f"Token price in WETH (Uniswap V2): {price_in_weth}")
        return price_in_weth
    except Exception as e:
        print(f"Error fetching Uniswap V2 reserves: {e}")
        return None
    
def get_token_price(update: Update, context: CallbackContext) -> None:
    print("Fetching token price using Uniswap V3...") #TODO: Remove line about v3 when v2 works

    args = context.args
    modifier = args[0].upper() if args else "USD"  # Default to "USD" if no modifier provided

    if modifier not in ["USD", "ETH"]:
        print(f"Invalid modifier: {modifier}")
        update.message.reply_text("Invalid modifier! Use /price USD or /price ETH.")
        return

    group_data = fetch_group_info(update, context)
    if group_data is None:
        return

    token_data = fetch_group_token(group_data, update, context)
    if not token_data:
        return

    lp_address = token_data["liquidity_address"]
    chain = token_data["chain"]

    if not lp_address or not chain:
        print("Liquidity address or chain not found for this group.")
        update.message.reply_text("Liquidity address or chain not found for this group.")
        return

    try:
        pool_type = determine_pool_type(chain, lp_address)
        if pool_type not in ["v3", "v2"]:
            update.message.reply_text("Failed to determine pool type.")
            return
        
        if modifier == "USD":
            token_price_in_usd = get_token_price_in_usd(chain, lp_address) # Use the existing get_token_price_in_usd function
            if token_price_in_usd is None:
                update.message.reply_text("Failed to fetch token price in USD.")
                return
            print(f"Token price in USD: {token_price_in_usd}")
            update.message.reply_text(f"${token_price_in_usd:.4f}")
        elif modifier == "ETH":
            if pool_type == "v3":
                price_in_weth = get_uniswap_v3_position_data(chain, lp_address)
            elif pool_type == "v2":
                price_in_weth = get_uniswap_v2_price(chain, lp_address)
            if price_in_weth is None:
                print("Failed to fetch Uniswap V3 position data.")
                update.message.reply_text("Failed to fetch Uniswap V3 position data.")
                return
            update.message.reply_text(f"{price_in_weth:.8f} ETH")
    except Exception as e:
        print(f"Unexpected error occurred: {e}")
        update.message.reply_text("An unexpected error occurred while fetching the token price.")
#endregion Price Fetching
##
#
##
#endregion Crypto Logic
#
#region Admin Controls
def admin_commands(update: Update, context: CallbackContext) -> None:
    msg = None
    if is_user_admin(update, context):
        msg = update.message.reply_text(
            "*Admin Commands:*\n"
            "*/admincommands | /adminhelp*\nList all admin commands\n"
            "*/cleanbot | /clean | /cleanupbot | /cleanup*\nClean all bot messages\n"
            "*/cleargames*\nClear all active games\n"
            "*/mute | /stfu*\nMute a user (reply to their message)\n"
            "*/unmute*\nUnmute a user (reply to their message)\n"
            "*/mutelist*\nView the list of muted users\n"
            "*/kick | /ban*\nKick a user (reply to their message)\n"
            "*/warn*\nWarn a user (reply to their message)\n"
            "*/warnlist*\nList all warnings in the chat\n"
            "*/clearwarns*\nClear warnings for a specific user (reply to their message)\n"
            "*/warnings*\nCheck warnings for a specific user (reply to their message)\n"
            "*/block | /filter*\nAdd something to the blocklist\n"
            "*/removeblock | /unblock | /unfilter*\nRemove something from the block list\n"
            "*/blocklist | /filterlist*\nView the block list\n"
            "*/allow*\nAllow a contract address, URL or domain\n"
            "*/allowlist*\nView the allow list\n",
            parse_mode='Markdown'
        )
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
    
    if msg is not None:
        track_message(msg)

def mute(update: Update, context: CallbackContext) -> None:
    msg = None
    chat_id = update.effective_chat.id

    if is_user_admin(update, context):
        group_doc = db.collection('groups').document(str(chat_id))
        group_data = group_doc.get().to_dict()

        if group_data is None or not group_data.get('admin', {}).get('mute', False):
            msg = update.message.reply_text("Muting is not enabled in this group.")
            if msg is not None:
                track_message(msg)
            return
        
        if update.message.reply_to_message is None:
            msg = update.message.reply_text("This command must be used in response to another message!")
            if msg is not None:
                track_message(msg)
            return
        reply_to_message = update.message.reply_to_message
        if reply_to_message:
            user_id = reply_to_message.from_user.id
            username = reply_to_message.from_user.username or reply_to_message.from_user.first_name

        if is_bot_or_admin(update, context, user_id): return

        context.bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=ChatPermissions(can_send_messages=False))
        msg = update.message.reply_text(f"User {username} has been muted.")

        group_doc.update({ # Add the user to the muted_users mapping in the database
            f'muted_users.{user_id}': datetime.now().isoformat()
        })
        clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
    
    if msg is not None:
        track_message(msg)

def unmute(update: Update, context: CallbackContext) -> None:
    msg = None
    chat_id = update.effective_chat.id

    group_doc = db.collection('groups').document(str(chat_id))
    group_data = group_doc.get().to_dict()

    if group_data is None or not group_data.get('admin', {}).get('mute', False):
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

                    group_doc.update({ # Remove the user from the muted_users mapping in the database
                        f'muted_users.{user_id}': firestore.DELETE_FIELD
                    })
                    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
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
    chat_id = update.effective_chat.id

    if is_user_admin(update, context):
        group_doc = db.collection('groups').document(str(chat_id))
        group_data = group_doc.get().to_dict()

        if group_data is None or not group_data.get('admin', {}).get('warn', False): # Check if warns enabled
            msg = update.message.reply_text("Warning system is not enabled in this group.")
            if msg is not None:
                track_message(msg)
            return
        
        if update.message.reply_to_message is None:
            msg = update.message.reply_text("This command must be used in response to another message!")
            if msg is not None:
                track_message(msg)
            return
        
        reply_to_message = update.message.reply_to_message
        if reply_to_message:
            user_id = str(reply_to_message.from_user.id)
            username = reply_to_message.from_user.username or reply_to_message.from_user.first_name

        if is_bot_or_admin(update, context, user_id): return
        
        try:
            doc_snapshot = group_doc.get()
            if doc_snapshot.exists:
                group_data = doc_snapshot.to_dict()
                warnings_dict = group_data.get('warnings', {})

                current_warnings = warnings_dict.get(user_id, 0) # Increment the warning count for the user
                current_warnings += 1
                warnings_dict[user_id] = current_warnings

                group_doc.update({'warnings': warnings_dict}) # Update the group document with the new warnings count
                clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
                msg = update.message.reply_text(f"{username} has been warned. Total warnings: {current_warnings}")

                process_warns(update, context, user_id, current_warnings) # Check if the user has reached the warning limit
            else:
                msg = update.message.reply_text("Group data not found.")
        except Exception as e:
            msg = update.message.reply_text(f"Failed to update warnings: {str(e)}")
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")

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
                    clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
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
        group_doc = fetch_group_info(update, context, return_doc=True)

        try:
            doc_snapshot = group_doc.get()
            if doc_snapshot.exists:
                group_data = doc_snapshot.to_dict()
                warnings_dict = group_data.get('warnings', {})

                current_warnings = warnings_dict.get(user_id, 0) # Get the warning count for the user

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

        if is_bot_or_admin(update, context, user_id): return

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

        group_doc = fetch_group_info(update, context, return_doc=True)
        blocklist_field = 'blocklist'

        try:
            doc_snapshot = group_doc.get()  # Fetch current blocklist from the group's document
            if doc_snapshot.exists:
                group_data = doc_snapshot.to_dict()
                current_blocklist = group_data.get(blocklist_field, [])

                if not isinstance(current_blocklist, list): # Ensure current_blocklist is a list
                    current_blocklist = []

                if command_text in current_blocklist:
                    msg = update.message.reply_text(f"'{command_text}' is already in the blocklist.")
                else:
                    current_blocklist.append(command_text)  # Add new blocked text to the list
                    group_doc.update({blocklist_field: current_blocklist})  # Update the blocklist in the group's document
                    msg = update.message.reply_text(f"'{command_text}' added to blocklist!")
                    clear_group_cache(str(update.effective_chat.id))  # Clear the cache on all database updates
                    print("Updated blocklist:", current_blocklist)
            else:
                group_doc.set({blocklist_field: [command_text]})  # If no blocklist exists, create it with the current command text
                msg = update.message.reply_text(f"'{command_text}' blocked!")
                clear_group_cache(str(update.effective_chat.id))  # Clear the cache on all database updates
                print("Created new blocklist with:", [command_text])

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
            msg = update.message.reply_text("Please provide a valid blocklist item to remove.")
            if msg is not None:
                track_message(msg)
            return

        group_doc = fetch_group_info(update, context, return_doc=True)
        blocklist_field = 'blocklist'

        try: # Use Firestore's arrayRemove to remove the item from the blocklist array
            group_doc.update({blocklist_field: firestore.ArrayRemove([command_text])})
            msg = update.message.reply_text(f"'{command_text}' removed from the blocklist!")
            clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
            print(f"Removed '{command_text}' from the blocklist.")
        
        except Exception as e:
            msg = update.message.reply_text(f"Failed to remove from blocklist: {str(e)}")
            print(f"Error removing from blocklist: {e}")

    if msg is not None:
        track_message(msg)

def blocklist(update: Update, context: CallbackContext):
    msg = None
    if is_user_admin(update, context):
        group_doc = fetch_group_info(update, context, return_doc=True)

        try:
            doc_snapshot = group_doc.get()
            if doc_snapshot.exists:
                group_data = doc_snapshot.to_dict()
                blocklist_field = 'blocklist'

                # Fetch blocklist as an array
                blocklist_items = group_data.get(blocklist_field, [])
                
                if isinstance(blocklist_items, list) and blocklist_items:
                    # Format the blocklist for display
                    message = "Current blocklist:\n" + "\n".join(blocklist_items)
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

        # Validate against patterns
        if not (ETH_ADDRESS_PATTERN.match(command_text) or 
                URL_PATTERN.match(command_text) or 
                DOMAIN_PATTERN.match(command_text)):
            msg = update.message.reply_text(
                "Invalid format. Only crypto addresses, URLs, or domain names can be added to the allowlist."
            )
            if msg is not None:
                track_message(msg)
            return

        group_doc = fetch_group_info(update, context, return_doc=True)
        allowlist_field = 'allowlist'

        try: # Use Firestore's arrayUnion to add the item to the allowlist array
            group_doc.update({allowlist_field: firestore.ArrayUnion([command_text])}) 
            msg = update.message.reply_text(f"'{command_text}' added to the allowlist!")
            clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
            print(f"Added '{command_text}' to allowlist.")

        except Exception as e:
            if 'NOT_FOUND' in str(e): # Handle the case where the document doesn't exist
                group_doc.set({allowlist_field: [command_text]})
                msg = update.message.reply_text(f"'{command_text}' added to a new allowlist!")
                clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
                print(f"Created new allowlist with: {command_text}")
            else:
                msg = update.message.reply_text(f"Failed to update allowlist: {str(e)}")
                print(f"Error updating allowlist: {e}")

    if msg is not None:
        track_message(msg)

def allowlist(update: Update, context: CallbackContext):
    msg = None
    if is_user_admin(update, context):
        group_doc = fetch_group_info(update, context, return_doc=True)

        try:
            doc_snapshot = group_doc.get() # Fetch the group's document
            if doc_snapshot.exists:
                group_data = doc_snapshot.to_dict()
                allowlist_field = 'allowlist'

                allowlist_items = group_data.get(allowlist_field, []) # Fetch allowlist as an array
                
                if isinstance(allowlist_items, list) and allowlist_items:
                    message = "Current allowlist:\n" + "\n".join(allowlist_items) # Format the allowlist for display
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

def clear_cache(update: Update, context: CallbackContext):
    msg = None
    if is_user_admin(update, context):
        clear_group_cache(str(update.effective_chat.id))
        msg = update.message.reply_text("Cache cleared.")
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
    
    if msg is not None:
        track_message(msg)
#endregion Admin Controls
#
#region User Controls
def commands(update: Update, context: CallbackContext) -> None:
    msg = None
    chat_id = str(update.effective_chat.id)

    if rate_limit_check():
        enabled_commands = []

        for command in ['play', 'website', 'buy', 'contract', 'price', 'chart', 'liquidity', 'volume']: # Check the status of each command
            if check_command_status(update, context, command):
                enabled_commands.append(command)

        if not enabled_commands: # Handle case where no commands are enabled
            msg = update.message.reply_text(
                "Sorry, you disabled all my commands!"
            )
        else:
            keyboard = [ # Generate dynamic keyboard for enabled commands
                [InlineKeyboardButton(f"/{cmd}", callback_data=f'commands_{cmd}')] for cmd in enabled_commands
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)

            base_dir = os.path.dirname(os.path.dirname(__file__))
            image_path = os.path.join(base_dir, 'assets', 'banner.jpg')

            with open(image_path, 'rb') as photo:
                context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption='Welcome to Sypherbot!\n\n'
                    'Below you will find all my enabled commands:',
                    reply_markup=reply_markup
                )
    else:
        msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')

    if msg is not None:
        track_message(msg)

def command_buttons(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    chat_id = str(query.message.chat.id)
    user_id = query.from_user.id

    update = Update(update.update_id, message=query.message)
    command_mapping = {
        'commands_play': 'play',
        'commands_buy' : 'buy',
        'commands_contract': 'contract',
        'commands_website': 'website',
        'commands_price': 'price',
        'commands_chart': 'chart',
        'commands_liquidity': 'liquidity',
        'commands_volume': 'volume'
    }

    command_key = query.data
    command_name = command_mapping.get(command_key)

    if command_name:
        if not check_command_status(update, context, command_name): # Check if the command is enabled
            query.message.reply_text(f"The /{command_name} command is currently disabled in this group.")
            print(f"User {user_id} attempted to use disabled command /{command_name}.")
            return

        if command_key == 'commands_play':
            play(update, context)
        elif command_key == 'commands_buy':
            buy(update, context)
        elif command_key == 'commands_contract':
            contract(update, context)
        elif command_key == 'commands_website':
            website(update, context)
        elif command_key == 'commands_price':
            get_token_price(update, context)
        elif command_key == 'commands_chart':
            chart(update, context)
        elif command_key == 'commands_liquidity':
            liquidity(update, context)
        elif command_key == 'commands_volume':
            volume(update, context)

def report(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    if not update.message.reply_to_message:
        context.bot.send_message(chat_id, text="You need to reply to a message to report it!")
        print(f"Report attempt in chat {chat_id} failed: No replied message.")
        return

    reported_user = update.message.reply_to_message.from_user.username

    chat_admins = context.bot.get_chat_administrators(chat_id) # Get the list of admins
    admin_usernames = [admin.user.username for admin in chat_admins if admin.user.username is not None]
    bot_username = context.bot.username
    print(f"Message from {reported_user} in chat {chat_id} reported to admins {admin_usernames}")

    if reported_user in admin_usernames or reported_user == bot_username:
        context.bot.send_message(chat_id, text="Nice try lol") # If the reported user is an admin, send a message saying that admins cannot be reported
    else:
        admin_mentions = ' '.join(['@' + username for username in admin_usernames])  # Add '@' for mentions

        report_message = f"Reported Message to admins.\n {admin_mentions}\n"
        message = context.bot.send_message(chat_id, text=report_message, disable_web_page_preview=True)  # Send the message as plain text

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

        try: # Send the message or media to the user's DM
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
    chat_id = str(update.effective_chat.id)

    if rate_limit_check():
        function_name = inspect.currentframe().f_code.co_name
        if not check_command_status(update, context, function_name):
            update.message.reply_text(f"The /{function_name} command is currently disabled in this group.")
            print(f"Attempted to use disabled command /play in group {chat_id}.")
            return
        
        keyboard = [[InlineKeyboardButton("Click Here to Start a Game!", callback_data='startGame')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        base_dir = os.path.dirname(os.path.dirname(__file__))
        photo_path = os.path.join(base_dir, 'assets', 'banner.gif')
        
        with open(photo_path, 'rb') as photo:
            context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo,
                caption='Welcome to deSypher! Click the button below to start a game!\n\nTo end an ongoing game, use the command /endgame.',
                reply_markup=reply_markup
            )
    else:
        update.message.reply_text('Bot rate limit exceeded. Please try again later.')

def end_game(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    key = f"{chat_id}_{user_id}"  # Unique key for each user-chat combination

    if key in context.chat_data: # Check if there's an ongoing game for this user in this chat
        if 'game_message_id' in context.chat_data[key]: # Delete the game message
            context.bot.delete_message(chat_id=chat_id, message_id=context.chat_data[key]['game_message_id'])
            print(f"Ending game for user {user_id} in chat {chat_id}")

        del context.chat_data[key] # Clear the game data
        update.message.reply_text("Your game has been deleted.")
    else:
        print(f"No active game found for user {user_id} in chat {chat_id}")
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

    
    if key not in context.chat_data or 'chosen_word' not in context.chat_data[key]: # Check if there's an ongoing game for this user in this chat
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
    base_dir = os.path.dirname(os.path.dirname(__file__))
    words_path  = os.path.join(base_dir, 'config', 'words.json')
    with open(words_path, 'r') as file:
        data = json.load(file)
        words = data['words']
        return random.choice(words)
#endregion Play Game

video_cache = {}
def send_rick_video(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    args = context.args

    if rate_limit_check():
        video_mapping = { # Map arguments to specific videos
            "alien": "assets/RICK_ALIEN.mp4",
            "duncan": "assets/RICK_DUNCAN.mp4",
            "saintlaurent": "assets/RICK_SAINTLAURENT.mp4",
            "shoenice": "assets/RICK_SHOENICE.mp4"
        }

        if not args:  # If no arguments are passed, send a random video
            video_path = random.choice(list(video_mapping.values()))
        else:
            video_key = args[0].lower() # Check if the argument matches a key in the mapping
            video_path = video_mapping.get(video_key)

        if not video_path: # If no match is found, send a default response
            keyboard = [[InlineKeyboardButton("Rick", url="https://www.instagram.com/bigf0ck/")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            context.bot.send_message(chat_id=chat_id, text="ALIEN", reply_markup=reply_markup)
            return

        if video_path in video_cache: # Use cached file_id if available
            file_id = video_cache[video_path]
            context.bot.send_video(chat_id=chat_id, video=file_id)
        else: 
            with open(video_path, 'rb') as video_file: # Upload the video and cache the file_id
                message = context.bot.send_video(chat_id=chat_id, video=video_file)
            file_id = message.video.file_id
            video_cache[video_path] = file_id
    else:
        update.message.reply_text('Bot rate limit exceeded. Please try again later.')

def buy(update: Update, context: CallbackContext) -> None:
    msg = None
    chat_id = str(update.effective_chat.id)

    if rate_limit_check():
        function_name = inspect.currentframe().f_code.co_name
        if not check_command_status(update, context, function_name):
            update.message.reply_text(f"The /{function_name} command is currently disabled in this group.")
            print(f"Attempted to use disabled command /play in group {chat_id}.")
            return
        
        group_data = fetch_group_info(update, context)
        if group_data is None:
            return
        
        token_data = fetch_group_token(group_data, update, context)
        if token_data is None:
            return
        
        token_name = token_data["name"]
        token_symbol = token_data["symbol"]
        contract_address = token_data["contract_address"]

        if not contract_address or not token_name or not token_symbol:
            update.message.reply_text(f"Unable to retrieve either the contract address, token name, or token symbol for this group.")
            return
        
        buy_link = f"https://app.uniswap.org/swap?outputCurrency={contract_address}"
        
        keyboard = [[InlineKeyboardButton(f"Buy {token_name} Here", url=buy_link)]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = update.message.reply_text(
            f"{token_name} • {token_symbol}",
            reply_markup=reply_markup
        )
    else:
        msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')

    if msg is not None:
        track_message(msg)

def contract(update: Update, context: CallbackContext) -> None:
    msg = None
    chat_id = str(update.effective_chat.id)

    if rate_limit_check():
        function_name = inspect.currentframe().f_code.co_name
        if not check_command_status(update, context, function_name):
            update.message.reply_text(f"The /{function_name} command is currently disabled in this group.")
            print(f"Attempted to use disabled command /play in group {chat_id}.")
            return
        
        group_data = fetch_group_info(update, context)
        if group_data is None:
            return
        
        token_data = fetch_group_token(group_data, update, context)
        if token_data is None:
            return

        contract_address = token_data["contract_address"]
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
    chat_id = str(update.effective_chat.id)
    group_data = fetch_group_info(update, context)

    if rate_limit_check():
        function_name = inspect.currentframe().f_code.co_name
        if not check_command_status(update, context, function_name):
            update.message.reply_text(f"The /{function_name} command is currently disabled in this group.")
            print(f"Attempted to use disabled command /play in group {chat_id}.")
            return
        
        if group_data is None:
            return

        token_data = fetch_group_token(group_data, update, context)
        if token_data is None:
            return

        chain = token_data["chain"]
        lp_address = token_data["liquidity_address"]
        if not lp_address or not chain:
            update.message.reply_text("Liquidity address or chain not found for this group.")
            return

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
    chat_id = str(update.effective_chat.id)

    if rate_limit_check():
        function_name = inspect.currentframe().f_code.co_name
        if not check_command_status(update, context, function_name):
            update.message.reply_text(f"The /{function_name} command is currently disabled in this group.")
            print(f"Attempted to use disabled command /play in group {chat_id}.")
            return

        if group_data is None:
            return
        
        token_data = fetch_group_token(group_data, update, context)
        if token_data is None:
            return

        chain = token_data["chain"]
        lp_address = token_data["liquidity_address"]
        if not lp_address or not chain:
            update.message.reply_text("Liquidity address or chain not found for this group.")
            return
        
        volume_24h_usd = get_volume(chain, lp_address)
        if volume_24h_usd:
            volume_24h_usd = float(volume_24h_usd) # Ensure the value is treated as a float for formatting
            msg = update.message.reply_text(f"24-hour trading volume in USD: ${volume_24h_usd:.4f}")
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
    chat_id = update.effective_chat.id
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
        function_name = inspect.currentframe().f_code.co_name
        if not check_command_status(update, context, function_name):
            update.message.reply_text(f"The /{function_name} command is currently disabled in this group.")
            print(f"Attempted to use disabled command /play in group {chat_id}.")
            return
        
        group_data = fetch_group_info(update, context)
        if group_data is None:
            return  # Early exit if no data is found
        
        token_data = fetch_group_token(group_data, update, context)
        if token_data is None:
            return
        
        chain = token_data["chain"]
        name = token_data["name"]
        symbol = token_data["symbol"]
        liquidity_address = token_data["liquidity_address"]
        if not chain or not name or not symbol or not liquidity_address:
            msg = update.message.reply_text("Full token data not found for this group.")
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
    chat_id = update.effective_chat.id
    
    if rate_limit_check():
        function_name = inspect.currentframe().f_code.co_name
        if not check_command_status(update, context, function_name):
            update.message.reply_text(f"The /{function_name} command is currently disabled in this group.")
            print(f"Attempted to use disabled command /play in group {chat_id}.")
            return
        
        group_data = fetch_group_info(update, context)
        if group_data is None:
            return  # Early exit if no data is found
        
        group_info = group_data.get('group_info')

        if group_info is None:
            msg = update.message.reply_text("Group info not found.")
            return
        
        group_website = group_info.get('website_url')

        if group_website is None:
            msg = update.message.reply_text("Group link not found.")
            return
        
        msg = update.message.reply_text(f"{group_website}")
    
    if msg is not None:
        track_message(msg)
#endregion User Controls

def main() -> None:
    updater = Updater(TELEGRAM_TOKEN, use_context=True) # Create the Updater and pass it the bot's token
    dispatcher = updater.dispatcher # Get the dispatcher to register handlers
    
    #region Slash Command Handlers
    #
    #region User Slash Command Handlers
    dispatcher.add_handler(CommandHandler(['commands', 'help'], commands))
    dispatcher.add_handler(CommandHandler("play", play))
    dispatcher.add_handler(CommandHandler("endgame", end_game))
    dispatcher.add_handler(CommandHandler(['contract', 'ca'], contract))
    dispatcher.add_handler(CommandHandler(['buy', 'purchase'], buy))
    dispatcher.add_handler(CommandHandler("price", get_token_price, pass_args=True))
    dispatcher.add_handler(CommandHandler("chart", chart))
    dispatcher.add_handler(CommandHandler(['liquidity', 'lp'], liquidity))
    dispatcher.add_handler(CommandHandler("volume", volume))
    dispatcher.add_handler(CommandHandler("website", website))
    dispatcher.add_handler(CommandHandler("report", report))
    dispatcher.add_handler(CommandHandler("save", save))
    dispatcher.add_handler(CommandHandler('rick', send_rick_video, pass_args=True))
    #endregion User Slash Command Handlers
    ##
    #region Admin Slash Command Handlers
    dispatcher.add_handler(CommandHandler(['start', 'setup'], start))
    dispatcher.add_handler(CommandHandler(['admincommands', 'adminhelp'], admin_commands))
    dispatcher.add_handler(CommandHandler(['cleanbot', 'clean', 'cleanupbot', 'cleanup'], cleanbot))
    dispatcher.add_handler(CommandHandler("clearcache", clear_cache))
    dispatcher.add_handler(CommandHandler('cleargames', cleargames))
    dispatcher.add_handler(CommandHandler(['kick', 'ban'], kick))
    dispatcher.add_handler(CommandHandler(['block', 'filter'], block))
    dispatcher.add_handler(CommandHandler(['removeblock', 'unblock', 'unfilter'], remove_block))
    dispatcher.add_handler(CommandHandler(['blocklist', 'filterlist'], blocklist))
    dispatcher.add_handler(CommandHandler("allow", allow))
    dispatcher.add_handler(CommandHandler("allowlist", allowlist))
    dispatcher.add_handler(CommandHandler(['mute', 'stfu'], mute))
    dispatcher.add_handler(CommandHandler("unmute", unmute))
    dispatcher.add_handler(CommandHandler("mutelist", check_mute_list))
    dispatcher.add_handler(CommandHandler("warn", warn))
    dispatcher.add_handler(CommandHandler("warnlist", check_warn_list))
    dispatcher.add_handler(CommandHandler('clearwarns', clear_warns_for_user))
    dispatcher.add_handler(CommandHandler("warnings", check_warnings))
    #endregion Admin Slash Command Handlers
    #
    #endregion Slash Command Handlers

    #region Callbacks
    #
    #region General Callbacks
    dispatcher.add_handler(CallbackQueryHandler(handle_start_game, pattern='^startGame$'))
    dispatcher.add_handler(CallbackQueryHandler(command_buttons, pattern='^commands_'))    
    #endregion General Callbacks
    ##
    #region Authentication Callbacks
    dispatcher.add_handler(CallbackQueryHandler(authentication_callback, pattern='^authenticate_'))
    dispatcher.add_handler(CallbackQueryHandler(callback_math_response, pattern='^mauth_'))
    dispatcher.add_handler(CallbackQueryHandler(callback_word_response, pattern='^wauth_'))
    #endregion Authentication Callbacks
    ##
    #region Buybot Callbacks
    dispatcher.add_handler(CallbackQueryHandler(setup_minimum_buy_callback, pattern='^setup_minimum_buy'))
    dispatcher.add_handler(CallbackQueryHandler(setup_small_buy_callback, pattern='^setup_small_buy'))
    dispatcher.add_handler(CallbackQueryHandler(setup_medium_buy_callback, pattern='^setup_medium_buy'))
    #endregion Callbacks
    
    #region Message Handlers
    dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, handle_new_user))
    dispatcher.add_handler(MessageHandler(Filters.status_update.left_chat_member, bot_removed_from_group))
    dispatcher.add_handler(MessageHandler((Filters.text) & (~Filters.command), handle_message))
    dispatcher.add_handler(MessageHandler(Filters.document, handle_document))
    dispatcher.add_handler(MessageHandler(Filters.photo, handle_image))
    #endregion Message Handlers

    #region Setup Callbacks
    dispatcher.add_handler(CallbackQueryHandler(setup_home_callback, pattern='^setup_home$'))
    dispatcher.add_handler(CallbackQueryHandler(handle_setup_callbacks, pattern='^(' + '|'.join(SETUP_CALLBACK_DATA) + ')$'))
    ##
    #region Command Setup Callbacks
    dispatcher.add_handler(CallbackQueryHandler(toggle_command_status, pattern=r'^toggle_(play|website|contract|price|buy|chart|liquidity|volume)$'))
    #endregion Command Setup Callbacks
    ##
    #region Crypto Setup Callbacks
    dispatcher.add_handler(CallbackQueryHandler(check_token_details_callback, pattern='^check_token_details$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_contract, pattern='^setup_contract$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_liquidity, pattern='^setup_liquidity$'))
    dispatcher.add_handler(CallbackQueryHandler(setup_chain, pattern='^setup_chain$'))
    dispatcher.add_handler(CallbackQueryHandler(exit_callback, pattern='^exit_setup$'))
    dispatcher.add_handler(CallbackQueryHandler(handle_chain, pattern='^(ethereum|arbitrum|polygon|base|optimism|fantom|avalanche|binance|harmony|mantle)$'))
    #endregion Crypto Setup Callbacks
    ##
    #region Authentication Setup Callbacks
    dispatcher.add_handler(CallbackQueryHandler(handle_timeout_callback, pattern='^auth_timeout_'))
    #endregion Authentication Setup Callbacks
    ##
    #
    #endregion Setup Callbacks

    updater.start_polling() # Start the Bot
    start_monitoring_groups() # Start monitoring premium groups
    updater.idle() # Run the bot until stopped

if __name__ == '__main__':
    main()