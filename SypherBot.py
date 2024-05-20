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
### /help - Get a list of commands
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
### /adminhelp - Get a list of admin commands
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

with open('config.json') as f:
    config = json.load(f)

# Load environment variables from .env file
load_dotenv()

# Get the Telegram API token from environment variables
TELEGRAM_TOKEN = os.getenv('BOT_API_TOKEN')
VERIFICATION_LETTERS = os.getenv('VERIFICATION_LETTERS')
CHAT_ID = os.getenv('CHAT_ID')
BASE_ENDPOINT = os.getenv('ENDPOINT')
BASESCAN_API_KEY = os.getenv('BASESCAN_API')

web3 = Web3(Web3.HTTPProvider(BASE_ENDPOINT))
contract_address = config['contractAddress']
pool_address = config['lpAddress']
abi = config['abi']

eth_address_pattern = re.compile(r'\b0x[a-fA-F0-9]{40}\b')
telegram_links_pattern = re.compile(r'https://t.me/\S+')

if web3.is_connected():
    network_id = web3.net.version
    print(f"Connected to Ethereum node on network {network_id}")
else:
    print("Failed to connect")

# Create a contract instance
contract = web3.eth.contract(address=contract_address, abi=abi)

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

#region Database Slash Commands
def filter(update, context):
    if is_user_admin(update, context):

        command_text = update.message.text[len('/filter '):].strip().lower()

        if not command_text:
            update.message.reply_text("Please provide some text to filter.")
            return
        
        # Create or update the document in the 'filtered-words' collection
        doc_ref = db.collection('filters').document(command_text)

        # Check if document exists
        doc = doc_ref.get()
        if doc.exists:
            update.message.reply_text(f"'{command_text}' is already filtered.")
        else:
            # If document does not exist, create it with initial values
            doc_ref.set({
                'text': command_text,
            })

            update.message.reply_text(f"'{command_text}' filtered!")

def remove_filter(update, context):
    if is_user_admin(update, context):

        command_text = update.message.text[len('/removefilter '):].strip().lower()

        if not command_text:
            update.message.reply_text("Please provide some text to remove.")
            return

        # Get the document in the 'filtered-words' collection
        doc_ref = db.collection('filters').document(command_text)

        # Check if document exists
        doc = doc_ref.get()
        if doc.exists:
            # If document exists, delete it
            doc_ref.delete()
            update.message.reply_text(f"'{command_text}' removed from filters!")
        else:
            update.message.reply_text(f"'{command_text}' is not in the filters.")

def filter_list(update, context):
    if is_user_admin(update, context):
        docs = db.collection('filters').stream()

        filters = [doc.id for doc in docs]
        message = "\n".join(filters)

        update.message.reply_text(message)

def warn(update, context):
    if is_user_admin(update, context):

        user_id = update.message.reply_to_message.from_user.id

        doc_ref = db.collection('warns').document(str(user_id))

        doc = doc_ref.get()
        if doc.exists:
            warnings = doc.to_dict()['warnings']
            doc_ref.update({
                'warnings': warnings + 1,
            })
            update.message.reply_text(f"{user_id} has been warned. Total warnings: {warnings + 1}")
            check_warns(update, context, user_id)
        else:
            doc_ref.set({
                'id': user_id,
                'warnings': 1,
            })
            update.message.reply_text(f"{user_id} has been warned. Total warnings: 1")

def check_warns(update, context, user_id):
    doc_ref = db.collection('warns').document(str(user_id))

    doc = doc_ref.get()
    if doc.exists:
        warnings = doc.to_dict()['warnings']

        if warnings >= 3:
            context.bot.kick_chat_member(update.message.chat.id, user_id)
            update.message.reply_text(f"Goodbye {user_id}!")
#endregion Database Slash Commands

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

#region Main Slash Commands
def start(update: Update, context: CallbackContext) -> None:
    if rate_limit_check():
        update.message.reply_text('Hello! I am Sypher Bot. For a list of commands, please use /help.')
    else:
        update.message.reply_text('Bot rate limit exceeded. Please try again later.')

def help(update: Update, context: CallbackContext) -> None:
    msg = None
    if rate_limit_check():
        keyboard = [
            [InlineKeyboardButton("/play", callback_data='help_play'),
            InlineKeyboardButton("/endgame", callback_data='help_endgame')],
            [InlineKeyboardButton("/tukyo", callback_data='help_tukyo'),
            InlineKeyboardButton("/tukyogames", callback_data='help_tukyogames')],
            [InlineKeyboardButton("/deSypher", callback_data='help_deSypher'),
            InlineKeyboardButton("/sypher", callback_data='help_sypher'),
            InlineKeyboardButton("/website", callback_data='help_website')],
            [InlineKeyboardButton("/price", callback_data='help_price'),
            InlineKeyboardButton("/chart", callback_data='help_chart')],
            [InlineKeyboardButton("/contract", callback_data='help_contract'),
            InlineKeyboardButton("/liquidity", callback_data='help_liquidity'),
            InlineKeyboardButton("/volume", callback_data='help_volume')],
            [InlineKeyboardButton("/whitepaper", callback_data='help_whitepaper'),]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = update.message.reply_text('Welcome to Sypher Bot! Below you will find all my commands:', reply_markup=reply_markup)
    else:
        msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
    if msg is not None:
        track_message(msg)

def help_buttons(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    update = Update(update.update_id, message=query.message)

    if query.data == 'help_play':
        play(update, context)
    elif query.data == 'help_endgame':
        end_game(update, context)
    # elif query.data == 'help_tukyo':
    #     tukyo(update, context)
    # elif query.data == 'help_tukyogames':
    #     tukyogames(update, context)
    # elif query.data == 'help_deSypher':
    #     deSypher(update, context)
    # elif query.data == 'help_whitepaper':
    #     whitepaper(update, context)
    # elif query.data == 'help_sypher':
    #     sypher(update, context)
    # elif query.data == 'help_contract':
    #     ca(update, context)
    # elif query.data == 'help_website':
    #     website(update, context)
    elif query.data == 'help_price':
        price(update, context)
    elif query.data == 'help_chart':
        chart(update, context)
    elif query.data == 'help_liquidity':
        liquidity(update, context)
    elif query.data == 'help_volume':
        volume(update, context)

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

# def tukyo(update: Update, context: CallbackContext) -> None:
#     msg = None
#     if rate_limit_check():
#         msg = update.message.reply_text(
#             'Tukyo is the developer of this bot, deSypher and other projects. There are many impersonators, the only real Tukyo on telegram is @tukyowave.\n'
#             '\n'
#             '| Socials |\n'
#             'Website: https://www.tukyo.org/\n'
#             'Twitter/X: https://twitter.com/TUKYOWAVE\n'
#             'Instagram: https://www.instagram.com/tukyowave/\n'
#             'Medium: https://tukyo.medium.com/\n'
#             'Youtube: https://www.youtube.com/tukyo\n'
#             'Spotify: https://sptfy.com/QGbt\n'
#             'Bandcamp: https://tukyo.bandcamp.com/\n'
#             'Github: https://github.com/tukyo\n'
#         )
#     else:
#         msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
#     if msg is not None:
#         track_message(msg)

# def tukyogames(update: Update, context: CallbackContext) -> None:
#     msg = None
#     if rate_limit_check():
#         msg = update.message.reply_text(
#             'Tukyo Games is a game development studio that is focused on bringing innovative blockchain technology to captivating and new game ideas. We use blockchain technology, without hindering the gaming experience.\n'
#             '\n'
#             'Website: https://tukyogames.com/ (Coming Soon)\n'
#             '\n'
#             '| Projects |\n'
#             'deSypher: https://desypher.net/\n'
#             'Super G.I.M.P. Girl: https://superhobogimpgirl.com/\n'
#             'Profectio: https://www.tukyowave.com/projects/profectio\n'
#         )
#     else:
#         msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
#     if msg is not None:
#         track_message(msg)

# def deSypher(update: Update, context: CallbackContext) -> None:
#     msg = None
#     if rate_limit_check():
#         msg = update.message.reply_text(
#             'deSypher is an Onchain puzzle game that can be played on Base. It is a game that requires SYPHER to play. The goal of the game is to guess the correct word in four attempts. Guess the correct word, or go broke!\n'
#             '\n'
#             'Website: https://desypher.net/\n'
#         )
#     else:
#         msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
#     if msg is not None:
#         track_message(msg)

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

# def ca(update: Update, context: CallbackContext) -> None:
#     msg = None
#     if rate_limit_check():
#         msg = update.message.reply_text(
#             '0x21b9D428EB20FA075A29d51813E57BAb85406620\n'
#         )
#     else:
#         msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
#     if msg is not None:
#         track_message(msg)

# def whitepaper(update: Update, context: CallbackContext) -> None:
#     if rate_limit_check():
#         msg = update.message.reply_text(
#         'https://desypher.net/whitepaper.html\n'
#         )
#     else:
#         msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
#     track_message(msg)

# def website(update: Update, context: CallbackContext) -> None:
#     msg = None
#     if rate_limit_check():
#         msg = update.message.reply_text(
#             'https://desypher.net/\n'
#         )
#     else:
#         msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
#     if msg is not None:
#         track_message(msg)

def report(update: Update, context: CallbackContext) -> None:
    admins= [
        '@tukyowave',
        '@jetLunar',
        '@pr0satoshi',
        '@dzhv_bradbrown',
        '@motorgala'
    ]

    chat_id = update.effective_chat.id
    CHAT_ID = int(os.getenv('CHAT_ID'))

    reported_user = update.message.reply_to_message.from_user.username

    if chat_id == CHAT_ID:
        if reported_user in admins:
            # If the reported user is an admin, send a message saying that admins cannot be reported
            context.bot.send_message(CHAT_ID, text="Nice try lol")
        else:
            admin_mentions = ' '.join(admins)

            report_message = f"Reported Message to admins.\n {admin_mentions}\n"
            # Send the message as plain text
            message = context.bot.send_message(CHAT_ID, text=report_message, disable_web_page_preview=True)

            # Immediately edit the message to remove the usernames, using Markdown for the new message
            context.bot.edit_message_text(chat_id=CHAT_ID, message_id=message.message_id, text="⚠️ Message Reported to Admins ⚠️", parse_mode='Markdown', disable_web_page_preview=True)
    else:
        update.message.reply_text("This command can only be used in the main chat.")

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
#endregion Main Slash Commands

#region Ethereum Logic
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

def get_liquidity():
    try:
        response = requests.get("https://api.geckoterminal.com/api/v2/networks/base/pools/0xB0fbaa5c7D28B33Ac18D9861D4909396c1B8029b")
        response.raise_for_status()
        data = response.json()
        # Navigate the JSON to find the liquidity in USD
        liquidity_usd = data['data']['attributes']['reserve_in_usd']
        return liquidity_usd
    except requests.RequestException as e:
        print(f"Failed to fetch liquidity data: {str(e)}")
        return None

def get_volume():
    try:
        response = requests.get("https://api.geckoterminal.com/api/v2/networks/base/pools/0xB0fbaa5c7D28B33Ac18D9861D4909396c1B8029b")
        response.raise_for_status()
        data = response.json()
        # Navigate the JSON to find the 24-hour volume in USD
        volume_24h_usd = data['data']['attributes']['volume_usd']['h24']
        return volume_24h_usd
    except requests.RequestException as e:
        print(f"Failed to fetch volume data: {str(e)}")
        return None

#region Chart
def fetch_ohlcv_data(time_frame):
    now = datetime.now()
    one_hour_ago = now - timedelta(hours=1)
    start_of_hour_timestamp = int(one_hour_ago.timestamp())
    
    url = f"https://api.geckoterminal.com/api/v2/networks/base/pools/0xB0fbaa5c7D28B33Ac18D9861D4909396c1B8029b/ohlcv/{time_frame}"
    params = {
        'aggregate': '1' + time_frame[0],  # '1m', '1h', '1d' depending on the time frame
        'before_timestamp': start_of_hour_timestamp,
        'limit': '60',  # Fetch only the last hour data
        'currency': 'usd'
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()  # Process this data as needed
    else:
        print("Failed to fetch data:", response.status_code)
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

def plot_candlestick_chart(data_frame):
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
    save_path = '/tmp/candlestick_chart.png'
    mpf.plot(data_frame, type='candle', style=s, volume=True, savefig=save_path)
    print(f"Chart saved to {save_path}")
#endregion Chart

#region Buybot
def monitor_transfers():
    transfer_filter = contract.events.Transfer.create_filter(fromBlock='latest', argument_filters={'from': pool_address})
    
    while True:
        for event in transfer_filter.get_new_entries():
            handle_transfer_event(event)
        time.sleep(10)

def handle_transfer_event(event):
    from_address = event['args']['from']
    amount = event['args']['value']
    
    # Check if the transfer is from the LP address
    if from_address.lower() == pool_address.lower():
        # Convert amount to SYPHER (from Wei)
        sypher_amount = web3.from_wei(amount, 'ether')

        # Fetch the USD price of SYPHER
        sypher_price_in_usd = get_token_price_in_fiat(contract_address, 'usd')
        if sypher_price_in_usd is not None:
            sypher_price_in_usd = Decimal(sypher_price_in_usd)
            total_value_usd = sypher_amount * sypher_price_in_usd
            if total_value_usd < 500:
                print("Ignoring small buy")
                return
            value_message = f" ({total_value_usd:.2f} USD)"
            header_emoji, buyer_emoji = categorize_buyer(total_value_usd)
        else:
            value_message = " (USD price not available)"
            header_emoji, buyer_emoji = "💸", "🐟"  # Default to Fish if unable to determine price

        # Format message with Markdown
        message = f"{header_emoji}SYPHER BUY{header_emoji}\n\n{buyer_emoji} {sypher_amount} SYPHER{value_message}"
        print(message)  # Debugging

        send_buy_message(message)

def categorize_buyer(usd_value):
    if usd_value < 2500:
        return "💸", "🐟"
    elif usd_value < 5000:
        return "💰", "🐬"
    else:
        return "🤑", "🐳"
    
def send_buy_message(text):
    msg = None
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    msg = bot.send_message(chat_id=CHAT_ID, text=text)
    if msg is not None:
        track_message(msg)
#endregion Buybot

#endregion Ethereum Logic

#region Ethereum Slash Commands
def price(update: Update, context: CallbackContext) -> None:
    msg = None
    if rate_limit_check():
        currency = context.args[0] if context.args else 'usd'
        currency = currency.lower()

        # Check if the provided currency is supported
        if currency not in ['usd', 'eur', 'jpy', 'gbp', 'aud', 'cad', 'mxn']:
            msg = update.message.reply_text("Unsupported currency. Please use 'usd', 'eur'. 'jpy', 'gbp', 'aud', 'cad' or 'mxn'.")
            return

        # Fetch and format the token price in the specified currency
        token_price_in_fiat = get_token_price_in_fiat(contract_address, currency)
        if token_price_in_fiat is not None:
            formatted_price = format(token_price_in_fiat, '.4f')
            msg = update.message.reply_text(f"SYPHER • {currency.upper()}: {formatted_price}")
        else:
            msg = update.message.reply_text(f"Failed to retrieve the price of the token in {currency.upper()}.")
    else:
        msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
    if msg is not None:
        track_message(msg)

def liquidity(update: Update, context: CallbackContext) -> None:
    msg = None
    if rate_limit_check():
        liquidity_usd = get_liquidity()
        if liquidity_usd:
            msg = update.message.reply_text(f"Liquidity: ${liquidity_usd}")
        else:
            msg = update.message.reply_text("Failed to fetch liquidity data.")
    else:
        msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
    if msg is not None:
        track_message(msg)

def volume(update, context):
    msg = None
    if rate_limit_check():
        volume_24h_usd = get_volume()
        if volume_24h_usd:
            msg = update.message.reply_text(f"24-hour trading volume in USD: ${volume_24h_usd}")
        else:
            msg = update.message.reply_text("Failed to fetch volume data.")
    else:
        msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
    if msg is not None:
        track_message(msg)

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
        msg = None
        ohlcv_data = fetch_ohlcv_data(time_frame)
        if ohlcv_data:
            data_frame = prepare_data_for_chart(ohlcv_data)
            plot_candlestick_chart(data_frame)
            msg = update.message.reply_photo(
                photo=open('/tmp/candlestick_chart.png', 'rb'),
                caption='\n[Dexscreener](https://dexscreener.com/base/0xb0fbaa5c7d28b33ac18d9861d4909396c1b8029b) • [Dextools](https://www.dextools.io/app/en/base/pair-explorer/0xb0fbaa5c7d28b33ac18d9861d4909396c1b8029b?t=1715831623074) • [CMC](https://coinmarketcap.com/dexscan/base/0xb0fbaa5c7d28b33ac18d9861d4909396c1b8029b/) • [CG](https://www.geckoterminal.com/base/pools/0xb0fbaa5c7d28b33ac18d9861d4909396c1b8029b?utm_source=coingecko)\n',
                parse_mode='Markdown'
            )
        else:
            msg = update.message.reply_text('Failed to fetch data or generate chart. Please try again later.')
    else:
        msg = update.message.reply_text('Bot rate limit exceeded. Please try again later.')
    
    if msg is not None:
        track_message(msg)
#endregion Ethereum Slash Commands

#region User Verification
def handle_new_user(update: Update, context: CallbackContext) -> None:
    msg = None
    for member in update.message.new_chat_members:
        user_id = member.id
        chat_id = update.message.chat.id

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

def start_verification_dm(user_id: int, context: CallbackContext) -> None:
    print("Sending verification message to user's DM.")
    verification_message = "Welcome to Tukyo Games! Please click the button to begin verification."
    keyboard = [[InlineKeyboardButton("Start Verification", callback_data='start_verification')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = context.bot.send_message(chat_id=user_id, text=verification_message, reply_markup=reply_markup)
    return message.message_id

def verification_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    callback_data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    query.answer()

    # Extract user_id from the callback_data
    _, callback_user_id = callback_data.split('_')
    callback_user_id = int(callback_user_id)

    if user_id != callback_user_id:
        return  # Do not process if the callback user ID does not match the button user ID

    if is_user_admin(update, context):
        return
    
    # Send a message to the user's DM to start the verification process
    start_verification_dm(user_id, context)
    
    # Optionally, you can edit the original message to indicate the button was clicked
    verification_started_message = query.edit_message_text(text="A verification message has been sent to your DMs. Please check your messages.")
    verification_started_id = verification_started_message.message_id

    job_queue = context.job_queue
    job_queue.run_once(delete_verification_message, 30, context={'chat_id': chat_id, 'message_id': verification_started_id})

def delete_verification_message(context: CallbackContext) -> None:
    job = context.job
    context.bot.delete_message(
        chat_id=job.context['chat_id'],
        message_id=job.context['message_id']
    )

def generate_verification_buttons() -> InlineKeyboardMarkup:
    all_letters = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    required_letters = list(VERIFICATION_LETTERS)
    
    for letter in required_letters:
        if letter in all_letters:
            all_letters.remove(letter)
    
    # Shuffle the remaining letters
    random.shuffle(all_letters)
    
    # Randomly select 11 letters from the shuffled list
    selected_random_letters = all_letters[:11]
    
    # Combine required letters with the random letters
    final_letters = required_letters + selected_random_letters
    
    # Shuffle the final list of 16 letters
    random.shuffle(final_letters)
    
    buttons = []
    row = []
    for i, letter in enumerate(final_letters):
        row.append(InlineKeyboardButton(letter, callback_data=f'verify_letter_{letter}'))
        if (i + 1) % 4 == 0:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(buttons)

def handle_start_verification(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    query.answer()

    # Initialize user verification progress
    user_verification_progress[user_id] = {
        'progress': [],
        'main_message_id': query.message.message_id,
        'chat_id': query.message.chat_id,
        'verification_message_id': query.message.message_id
    }

    verification_question = "Who is the lead developer at Tukyo Games?"
    reply_markup = generate_verification_buttons()

    # Edit the initial verification prompt
    context.bot.edit_message_text(
        chat_id=user_id,
        message_id=user_verification_progress[user_id]['verification_message_id'],
        text=verification_question,
        reply_markup=reply_markup
    )

def handle_verification_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    letter = query.data.split('_')[2]  # Get the letter from callback_data
    query.answer()

    # Update user verification progress
    if user_id in user_verification_progress:
        user_verification_progress[user_id]['progress'].append(letter)

        # Only check the sequence after the fifth button press
        if len(user_verification_progress[user_id]['progress']) == len(VERIFICATION_LETTERS):
            if user_verification_progress[user_id]['progress'] == list(VERIFICATION_LETTERS):
                context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_verification_progress[user_id]['verification_message_id'],
                    text="Verification successful, you may now return to chat!"
                )
                print("User successfully verified.")
                # Unmute the user in the main chat
                context.bot.restrict_chat_member(
                    chat_id=CHAT_ID,
                    user_id=user_id,
                    permissions=ChatPermissions(
                        can_send_messages=True,
                        can_send_media_messages=True,
                        can_send_other_messages=True,
                        can_send_videos=True,
                        can_send_photos=True,
                        can_send_audios=True
                    )
                )
                current_jobs = context.job_queue.get_jobs_by_name(str(user_id))
                for job in current_jobs:
                    job.schedule_removal()
            else:
                context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_verification_progress[user_id]['verification_message_id'],
                    text="Verification failed. Please try again.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Start Verification", callback_data='start_verification')]])
                )
                print("User failed verification prompt.")
            # Reset progress after verification attempt
            user_verification_progress.pop(user_id)
    else:
        context.bot.edit_message_text(
            chat_id=user_id,
            message_id=user_verification_progress[user_id]['verification_message_id'],
            text="Verification failed. Please try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Start Verification", callback_data='start_verification')]])
        )
        print("User failed verification prompt.")
        
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

#region Admin Controls
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

def handle_message(update: Update, context: CallbackContext) -> None:
    
    delete_unallowed_addresses(update, context)
    delete_filtered_phrases(update, context)
    delete_blocked_links(update, context)

    handle_guess(update, context)

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

def delete_unallowed_addresses(update: Update, context: CallbackContext):
    print("Checking message for unallowed addresses...")

    message_text = update.message.text
    
    found_addresses = eth_address_pattern.findall(message_text)

    print(f"Found addresses: {found_addresses}")

    allowed_addresses = [config['contractAddress'].lower(), config['lpAddress'].lower()]

    print(f"Allowed addresses: {allowed_addresses}")

    for address in found_addresses:
        if address.lower() not in allowed_addresses:
            update.message.delete()
            break

def delete_filtered_phrases(update: Update, context: CallbackContext):
    print("Checking message for filtered phrases...")

    message_text = update.message.text.lower()  # Convert to lowercase for case-insensitive matching

    # Retrieve filtered words from Firestore
    docs = db.collection('filters').stream()

    filtered_phrases = [doc.id for doc in docs]
    
    for phrase in filtered_phrases:
        if phrase in message_text:
            print(f"Found filter: {phrase}")
            try:
                update.message.delete()
                print("Message deleted.")
            except Exception as e:  # Catch potential errors in message deletion
                print(f"Error deleting message: {e}")
            break  # Exit loop after deleting the message

def delete_blocked_links(update: Update, context: CallbackContext):
    print("Checking message for unallowed Telegram links...")
    message_text = update.message.text
    found_links = telegram_links_pattern.findall(message_text)
    print(f"Found Telegram links: {found_links}")

    allowed_links = [
        'https://t.me/tukyogames',
        'https://t.me/tukyowave',
        'https://t.me/tukyogamesannouncements'
    ]

    for link in found_links:
        if link not in allowed_links:
            try:
                update.message.delete()
                print("Deleted a message with unallowed Telegram link.")
                return  # Stop further checking if a message is deleted
            except Exception as e:
                print(f"Failed to delete message: {e}")

def delete_service_messages(update, context):
    # Check if the message ID is marked as non-deletable
    non_deletable_message_id = context.chat_data.get('non_deletable_message_id')
    if update.message.message_id == non_deletable_message_id:
        return  # Do not delete this message

    if update.message.left_chat_member or update.message.new_chat_members:
        try:
            context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)
            print(f"Deleted service message in chat {update.message.chat_id}")
        except Exception as e:
            print(f"Failed to delete service message: {str(e)}")
#endregion Admin Controls

#region Admin Slash Commands
def admin_help(update: Update, context: CallbackContext) -> None:
    msg = None
    if is_user_admin(update, context):
        msg = update.message.reply_text(
            "Admin commands:\n"
            "/cleanbot - Cleans all bot messages\n"
            "/cleargames - Clear all active games\n"
            "/antiraid - Manage anti-raid settings\n"
            "/mute - Mute a user\n"
            "/unmute - Unmute a user\n"
            "/kick - Kick a user\n"
            "/warn - Warn a user\n"
            "/filter - Filter a word or phrase\n"
            "/removefilter - Remove a filtered word or phrase\n"
            "/filterlist - List all filtered words and phrases\n"
        )
    
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
#endregion Admin Slash Commands

def main() -> None:
    # Create the Updater and pass it your bot's token
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    
    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher
    
    #region General Slash Command Handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help))
    dispatcher.add_handler(CommandHandler("play", play))
    dispatcher.add_handler(CommandHandler("endgame", end_game))
    # dispatcher.add_handler(CommandHandler("tukyo", tukyo))
    # dispatcher.add_handler(CommandHandler("tukyogames", tukyogames))
    # dispatcher.add_handler(CommandHandler("desypher", deSypher))
    # dispatcher.add_handler(CommandHandler("sypher", sypher))
    # dispatcher.add_handler(CommandHandler("whitepaper", whitepaper))
    # dispatcher.add_handler(CommandHandler("contract", ca))
    # dispatcher.add_handler(CommandHandler("ca", ca))
    # dispatcher.add_handler(CommandHandler("tokenomics", sypher))
    # dispatcher.add_handler(CommandHandler("website", website))
    dispatcher.add_handler(CommandHandler("chart", chart))
    dispatcher.add_handler(CommandHandler("price", price))
    dispatcher.add_handler(CommandHandler("liquidity", liquidity))
    dispatcher.add_handler(CommandHandler("lp", liquidity))
    dispatcher.add_handler(CommandHandler("volume", volume))

    dispatcher.add_handler(CommandHandler("report", report))
    dispatcher.add_handler(CommandHandler("save", save))
    #endregion General Slash Command Handlers

    #region Admin Slash Command Handlers
    dispatcher.add_handler(CommandHandler("adminhelp", admin_help))
    dispatcher.add_handler(CommandHandler('cleanbot', cleanbot))
    dispatcher.add_handler(CommandHandler('cleargames', cleargames))
    dispatcher.add_handler(CommandHandler('antiraid', antiraid))
    dispatcher.add_handler(CommandHandler("mute", mute))
    dispatcher.add_handler(CommandHandler("unmute", unmute))
    dispatcher.add_handler(CommandHandler("kick", kick))
    dispatcher.add_handler(CommandHandler("filter", filter))
    dispatcher.add_handler(CommandHandler("removefilter", remove_filter))
    dispatcher.add_handler(CommandHandler("filterlist", filter_list))
    dispatcher.add_handler(CommandHandler("warn", warn))
    #endregion Admin Slash Command Handlers
    
    # Register the message handler for new users
    dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, handle_new_user))

    # Add a handler for deleting service messages
    dispatcher.add_handler(MessageHandler(Filters.status_update.left_chat_member, delete_service_messages))
    
    # Register the message handler for anti-spam
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    # Register the callback query handler for button clicks
    dispatcher.add_handler(CallbackQueryHandler(verification_callback, pattern='^verify_\d+$'))
    dispatcher.add_handler(CallbackQueryHandler(handle_start_verification, pattern='start_verification'))
    dispatcher.add_handler(CallbackQueryHandler(handle_verification_button, pattern=r'verify_letter_[A-Z]'))
    dispatcher.add_handler(CallbackQueryHandler(handle_start_game, pattern='^startGame$'))
    dispatcher.add_handler(CallbackQueryHandler(help_buttons, pattern='^help_'))

    monitor_thread = threading.Thread(target=monitor_transfers)
    monitor_thread.start()
    
    # Start the Bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()