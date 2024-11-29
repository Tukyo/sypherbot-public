import sys
import time
import requests
from telegram import Update
from telegram.ext import CallbackContext
from cachetools import TTLCache

from firebase_admin import firestore
from datetime import datetime, timedelta, timezone

# Import the necessary modules from the modules folder
from modules import config, firebase

#region Message Tracking
bot_messages = []
def track_message(message):
    bot_messages.append((message.chat.id, message.message_id))
    print(f"Tracked message: {message.message_id}")
#endregion Message Tracking
##
#
##
#region User Permissions
admin_cache = TTLCache(maxsize=100, ttl=600) # Cache a list of up to 100 group's admins for 10 minutes
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

    if chat_id in admin_cache:
        print(f"Fetching admins from cache for chat {chat_id}")
        chat_admins = admin_cache[chat_id]
    else:
        print("Admins not in cache, fetching from Telegram...")
        try:
            chat_admins = context.bot.get_chat_administrators(chat_id, timeout=30) # Fetch from Telegram and cache the result
            admin_cache[chat_id] = chat_admins  # Store the result in the cache
        except Exception as e:
            print(f"Error fetching administrators: {e}")
            return False
        
    user_is_admin = any(admin.user.id == user_id for admin in chat_admins)
    print(f"UserID: {user_id} - IsAdmin: {user_is_admin}")
    return user_is_admin

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

def is_user_trusted(update: Update, context: CallbackContext) -> None:
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
        'relaxed': timedelta(days=config.RELAXED_TRUST),
        'moderate': timedelta(days=config.MODERATE_TRUST),
        'strict': timedelta(days=config.STRICT_TRUST),
    }
    trust_duration = trust_durations.get(sypher_trust_preferences)

    if not trust_duration:
        print(f"Invalid sypher trust preference: {sypher_trust_preferences}. Defaulting to untrusted.")
        return False

    if time_elapsed >= trust_duration: # Check if sufficient time has passed
        print(f"User {user_id} has been in untrusted_users for {time_elapsed}. Removing from untrusted_users.")
        firebase.DATABASE.collection('groups').document(group_id).update({f'untrusted_users.{user_id}': firestore.DELETE_FIELD})
        clear_group_cache(group_id) # Clear the cache on all database updates
        return True
    else:
        print(f"User {user_id} has been in untrusted_users for {time_elapsed}. Still untrusted.")
        return False

def is_reply_to_bot(update: Update, context: CallbackContext) -> bool:
    return ( # Check if the message is a reply to this bot
        update.message.reply_to_message and
        update.message.reply_to_message.from_user and
        update.message.reply_to_message.from_user.id == context.bot.id
    )
#endregion User Permissions
##
#
##
#region Group Data
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

    group_doc = firebase.DATABASE.collection('groups').document(str(group_id))

    if return_doc:
        print(f"Fetching group_doc for group {group_id}")
    else:
        print(f"Fetching group_data for group {group_id}")

    try:
        doc_snapshot = group_doc.get()
        if doc_snapshot.exists:
            group_data = doc_snapshot.to_dict()

            print(f"Fetched group data from Firestore: {group_data}")

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

def fetch_group_dictionary(update: Update, context: CallbackContext, general: bool = False):
    """
    Fetches and processes group data for a specific group ID. 
    Returns a modular dictionary structure with improved clarity and relevance.
    If `general` is True, returns only general group information.
    """
    group_data = fetch_group_info(update, context)
    if not group_data:
        print("No group data found. Returning default values.")
        return None

    if general:
        general_info = { # General group data structure
            "group_info": {
                "username": group_data.get("group_info", {}).get("group_username", "N/A"),
                "website": group_data.get("group_info", {}).get("website_url", "N/A"),
                "link": group_data.get("group_info", {}).get("group_link", "N/A"),
                "owner_username": group_data.get("owner_username", "N/A")
            },
            "premium": group_data.get("premium", False),
            "commands": {cmd: enabled for cmd, enabled in group_data.get("commands", {}).items()},
            "token_info": {
                "name": group_data.get("token", {}).get("name", "Unknown Token"),
                "symbol": group_data.get("token", {}).get("symbol", "N/A"),
                "chain": group_data.get("token", {}).get("chain", "N/A"),
                "liquidity_address": group_data.get("token", {}).get("liquidity_address", "N/A"),
                "contract_address": group_data.get("token", {}).get("contract_address", "N/A"),
                "decimals": group_data.get("token", {}).get("decimals", "N/A"),
            },
        }

        print(f"Fetched and processed general dictionary for group {group_data.get('group_id', 'Unknown Group ID')}: {general_info}")
        return general_info

    detailed_info = { # Detailed group data structure
        "group_info": {
            "id": group_data.get("group_id", "Unknown Group ID"),
            "username": group_data.get("group_info", {}).get("group_username", "N/A"),
            "website": group_data.get("group_info", {}).get("website_url", "N/A"),
            "link": group_data.get("group_info", {}).get("group_link", "N/A"),
            "owner_id": group_data.get("owner_id", "Unknown Owner"),
            "owner_username": group_data.get("owner_username", "N/A"),
        },
        "premium_features": {
            "enabled": group_data.get("premium", False),
            "welcome_header_url": group_data.get("premium_features", {}).get("welcome_header_url", None),
            "buybot_settings": group_data.get("premium_features", {}).get("buybot", {}),
            "sypher_trust": group_data.get("premium_features", {}).get("sypher_trust", False),
            "sypher_trust_preferences": group_data.get("premium_features", {}).get("sypher_trust_preferences", "default"),
        },
        "verification": {
            "type": group_data.get("verification_info", {}).get("verification_type", "N/A"),
            "timeout": group_data.get("verification_info", {}).get("verification_timeout", 0),
        },
        "admin_settings": {
            "max_warns": group_data.get("admin", {}).get("max_warns", 0),
            "allowlist_enabled": group_data.get("admin", {}).get("allowlist", False),
            "blocklist_enabled": group_data.get("admin", {}).get("blocklist", False),
        },
        "token_info": {
            "name": group_data.get("token", {}).get("name", "Unknown Token"),
            "symbol": group_data.get("token", {}).get("symbol", "N/A"),
            "chain": group_data.get("token", {}).get("chain", "N/A"),
            "liquidity_address": group_data.get("token", {}).get("liquidity_address", "N/A"),
            "contract_address": group_data.get("token", {}).get("contract_address", "N/A"),
            "decimals": group_data.get("token", {}).get("decimals", "N/A"),
            "setup_complete": group_data.get("token", {}).get("setup_complete", False),
            "total_supply": group_data.get("token", {}).get("total_supply", 0),
        },
        "untrusted_users": group_data.get("untrusted_users", {}),
        "unverified_users": group_data.get("unverified_users", {}),
        "warnings": group_data.get("warnings", {}),
    }

    print(f"Fetched and processed detailed dictionary for group {group_data.get('group_id', 'Unknown Group ID')}: {detailed_info}")
    return detailed_info

def fetch_group_token(group_data: dict, update: Update, context: CallbackContext): # Fetches all token-related data from a pre-fetched group_data object.
    token_data = group_data.get('token')
    if not token_data:
        print("Token data not found for this group.")
        update.message.reply_text("Token data not found for this group.")
        return None

    print(f"All token data fetched: {token_data}")
    return token_data

def fetch_command_status(update: Update, context: CallbackContext, command: str) -> bool:
    group_data = fetch_group_info(update, context)

    if not group_data:
        print(f"No group data found for group {update.effective_chat.id}. Defaulting '{command}' to disabled.")
        return False

    commands = group_data.get('commands', {})
    return commands.get(command, False)  # Default to False if the command is not explicitly set
#endregion Group Data
##
#
##
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
#region Querying
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

def get_username(update: Update) -> str:
    username = update.message.from_user.username or update.message.from_user.first_name or "Unknown User"
    print(f"Username fetched: {username}")

    return username
#endregion Querying
##
#
##
#region Rate Limiting
group_rate_limits = {}  # Store rate limits for each group
last_check_time = time.time()
command_count = 0
def rate_limit_check(chat_id: str) -> bool: # Later TODO: Implement rate limiting PER GROUP
    print("Checking rate limit...")
    global last_check_time, command_count
    global group_rate_limits

    current_time = time.time()

    if current_time - last_check_time > config.BOT_RATE_LIMIT_TIME_PERIOD: # Check and update bot-wide rate limit
        command_count = 0
        last_check_time = current_time

    if command_count >= config.BOT_RATE_LIMIT_MESSAGE_COUNT:
        print("Bot-wide rate limit exceeded.")
        return False

    if chat_id not in group_rate_limits: # Check and update group-specific rate limit
        group_rate_limits[chat_id] = {
            "last_check_time": 0,
            "command_count": 0
        }

    group_data = group_rate_limits[chat_id]

    if current_time - group_data["last_check_time"] > config.GROUP_RATE_LIMIT_TIME_PERIOD:
        group_data["command_count"] = 0
        group_data["last_check_time"] = current_time

    if group_data["command_count"] >= config.GROUP_RATE_LIMIT_MESSAGE_COUNT:
        print(f"Group {chat_id} rate limit exceeded.")
        return False

    # Increment counters if within limits
    command_count += 1
    group_data["command_count"] += 1

    return True
#endregion Rate Limiting
##
#
##
#region External APIs
## CONGECKO API
coingecko_api = "https://api.coingecko.com/api/v3/"
### Rate limit using free tier of 30 calls/min and a monthly cap of 10,000 calls
def fetch_trending_coins(update, context):
    try:
        response = requests.get(f"{coingecko_api}search/trending")
        response.raise_for_status()
        data = response.json()
        trending_coins = [item['item']['name'] for item in data['coins']]
        return trending_coins if trending_coins else ["No trending coins found."]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching trending coins: {e}")
        return ["Error: Unable to fetch trending coins due to a network issue."]
    except KeyError as e:
        print(f"Unexpected response structure: {e}")
        return ["Error: The API response format has changed, unable to process."]
def fetch_token_price(token):
    try:
        response = requests.get(f"{coingecko_api}simple/price?ids={token}&vs_currencies=usd")
        response.raise_for_status()
        data = response.json()
        return data[token]['usd'] if token in data and 'usd' in data[token] else f"Token price for {token} not available."
    except requests.exceptions.RequestException as e:
        print(f"Error fetching token price for {token}: {e}")
        return f"Error: Unable to fetch the price for {token} due to a network issue."
    except KeyError as e:
        print(f"Unexpected response structure for {token}: {e}")
        return f"Error: Response structure changed, unable to fetch price for {token}."
## ALTERNATIVE ME API
alternative_me_api = "https://api.alternative.me/"
### Rate limit 60 requests per minute over a 10 minute window
def fetch_fear_greed_index(update, context):
    try:
        response = requests.get(f"{alternative_me_api}fng/")
        response.raise_for_status()
        data = response.json()
        fng_index = data['data'][0]['value']
        return f"Fear & Greed Index: {fng_index}" if fng_index else "Fear & Greed Index data is unavailable."
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Fear & Greed Index: {e}")
        return "Error: Unable to fetch Fear & Greed Index due to a network issue."
    except KeyError as e:
        print(f"Unexpected response structure: {e}")
        return "Error: Response structure changed, unable to fetch Fear & Greed Index."
#endregion External APIs