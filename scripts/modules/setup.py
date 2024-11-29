import re
import os
import json
from web3 import Web3
from io import BytesIO

import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

# Import custom modules from the scripts directory
# {main.py} is the core script that contains the main logic to run the bot
# {config.py} contains all the configuration settings for the bot
# {utils.py} contains utility functions that are used throughout the bot
# {firebase.py} contains all the Firebase functions to interact with the database
from scripts import main
from modules import config, utils, firebase
##

#region Bot Setup
def store_setup_message(context, message_id):
    if 'setup_bot_message' in context.chat_data:
        context.chat_data['setup_bot_message'].append(message_id)
    else:
        context.chat_data['setup_bot_message'] = [message_id]

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
    
    if utils.is_user_owner(update, context, user_id):
        query = update.callback_query
        query.answer()
        print(f"Exiting setup mode in group {update.effective_chat.id}")
        query.message.delete()
        context.chat_data['setup_stage'] = None
    else:
        print("User is not the owner.")

    if msg is not None:
        utils.track_message(msg)

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

def setup_start(update: Update, context: CallbackContext) -> None:
    msg = None
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    args = context.args

    if chat_type == "private":
        msg = update.message.reply_text("Please add me to a group to begin setup.")
        utils.track_message(msg)
        return

    if not utils.is_user_owner(update, context, user_id):
        msg = update.message.reply_text("You are not the owner of this group.")
        if msg is not None:
            utils.track_message(msg)
        return

    if not args: # Default setup when no arguments are passed
        setup_keyboard = [[InlineKeyboardButton("Setup", callback_data='setup_home')]]
        setup_markup = InlineKeyboardMarkup(setup_keyboard)
        msg = update.message.reply_text(
            "Click 'Setup' to manage your group.",
            reply_markup=setup_markup
        )
        store_setup_message(context, msg.message_id)
    else: # Handle each argument case
        arg = args[0].lower()  # Convert argument to lowercase for easier matching
        if arg == "home":
            setup_home(update, context)
        elif arg == "crypto":
            setup_crypto(update, context)
        elif arg == "commands":
            setup_commands(update, context)
        elif arg == "admin":
            setup_admin(update, context)
        elif arg == "auth" or arg == "authentication":
            setup_authentication(update, context)
        elif arg == "premium":
            setup_premium(update, context)
        else:
            msg = update.message.reply_text(f"Unknown setup option: {arg}")

    if msg is not None:
        utils.track_message(msg)

def setup_home_callback(update: Update, context: CallbackContext) -> None:
    query, user_id = utils.get_query_info(update)

    if utils.is_user_owner(update, context, user_id):
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
            setup_home(update, context)

def setup_home(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_doc = utils.fetch_group_info(update, context, return_doc=True)

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
            InlineKeyboardButton("🚀 Premium 🚀", callback_data='setup_premium')
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
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

    group_doc.update({
        'group_info.group_link': group_link,
        'group_info.group_username': group_username,
    })
    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

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
    query, user_id = utils.get_query_info(update)
    chosen_callback = query.data

    if chosen_callback in SETUP_CALLBACK_DATA:
        if utils.is_user_owner(update, context, user_id):
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
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def reset_admin_settings(update: Update, context: CallbackContext) -> None:
    group_id = update.effective_chat.id  # Get the group ID
    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
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
    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = update.message.reply_text("Admin settings have been reset to default.")
    store_setup_message(context, msg.message_id)

    print(f"Admin settings for group {group_id} have been reset to: {new_admin_settings}")

    if msg is not None:
        utils.track_message(msg)

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
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def enable_mute(update: Update, context: CallbackContext) -> None:
    msg = None

    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
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
    
    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='✔️ Muting has been enabled in this group ✔️'
    )
    context.chat_data['setup_stage'] = None
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def disable_mute(update: Update, context: CallbackContext) -> None:
    msg = None

    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
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

    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='❌ Muting has been disabled in this group ❌'
    )
    context.chat_data['setup_stage'] = None
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)
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
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def enable_warn(update: Update, context: CallbackContext) -> None:
    msg = None

    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
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

    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='✔️ Warning has been enabled in this group ✔️'
    )
    context.chat_data['setup_stage'] = None
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def disable_warn(update: Update, context: CallbackContext) -> None:
    msg = None

    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
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

    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='❌ Warning has been disabled in this group ❌'
    )
    context.chat_data['setup_stage'] = None
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def set_max_warns(update: Update, context: CallbackContext) -> None:
    msg = None

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Please respond with the maximum number of warnings you want for the group.\n\n'
        '*Default Max Warns:* _3_',
        parse_mode='Markdown'
    )
    context.chat_data['setup_stage'] = 'set_max_warns'
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def handle_max_warns(update: Update, context: CallbackContext) -> None:
    group_doc = utils.fetch_group_info(update, context, return_doc=True)

    if update.message.text:
        try:
            max_warns = int(update.message.text)
        except ValueError:
            msg = context.bot.send_message(
                chat_id=update.effective_chat.id,
                text='Please enter a number.'
            )

            if msg is not None:
                utils.track_message(msg)
            return

        group_doc.update({
            'admin.max_warns': max_warns
        })
        utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Maximum number of warnings set to {max_warns}.'
        )
        store_setup_message(context, msg.message_id)

        if msg is not None:
            utils.track_message(msg)
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
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def enable_allowlist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
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
    
    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='✔️ Allowlisting has been enabled in this group ✔️'
    )

    context.chat_data['setup_stage'] = None
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def disable_allowlist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
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
    
    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='❌ Allowlisting has been disabled in this group ❌'
    )

    context.chat_data['setup_stage'] = None

    if msg is not None:
        utils.track_message(msg)

def setup_website(update: Update, context: CallbackContext) -> None:
    msg = None
    query, user_id = utils.get_query_info(update)

    if utils.is_user_owner(update, context, user_id):

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
        store_setup_message(context, msg.message_id)

        if msg is not None:
            utils.track_message(msg)

def handle_website_url(update: Update, context: CallbackContext) -> None:
    msg = None
    user_id = update.message.from_user.id

    if utils.is_user_owner(update, context, user_id):
        if context.chat_data.get('setup_stage') == 'website':
            website_url = update.message.text.strip()

            if config.URL_PATTERN.fullmatch(website_url):  # Use the global config.URL_PATTERN
                group_id = update.effective_chat.id
                print(f"Adding website URL {website_url} to group {group_id}")
                group_doc = utils.fetch_group_info(update, context, return_doc=True)
                group_doc.update({'group_info.website_url': website_url})
                utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
                context.chat_data['setup_stage'] = None

                if update.message is not None:
                    msg = update.message.reply_text("Website URL added successfully!")
                elif update.callback_query is not None:
                    msg = update.callback_query.message.reply_text("Website URL added successfully!")
            else:
                msg = update.message.reply_text("Please send a valid website URL! It must include 'https://' or 'http://'.")

        store_setup_message(context, msg.message_id)

        if msg is not None:
            utils.track_message(msg)

def check_allowlist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_data = utils.fetch_group_info(update, context)

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
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def clear_allowlist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
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

    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='❌ Allowlist has been cleared in this group ❌'
    )
    context.chat_data['setup_stage'] = None
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)
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
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def enable_blocklist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
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

    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='✔️ Blocklisting has been enabled in this group ✔️'
    )
    context.chat_data['setup_stage'] = None
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def disable_blocklist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
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

    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='❌ Blocklisting has been disabled in this group ❌'
    )
    context.chat_data['setup_stage'] = None
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def check_blocklist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    group_data = utils.fetch_group_info(update, context)

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
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def clear_blocklist(update: Update, context: CallbackContext) -> None:
    msg = None

    group_id = update.effective_chat.id
    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
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

    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='❌ Blocklist has been cleared in this group ❌'
    )
    context.chat_data['setup_stage'] = None
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)
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
    group_data = utils.fetch_group_info(update, context)

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
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def toggle_command_status(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    chat_id = query.message.chat.id
    user_id = query.from_user.id

    if utils.is_user_owner(update, context, user_id):
        command = query.data.replace('toggle_', '')  # Extract the command name

        if command == "play": # Check if the command is "play"
            if not is_premium_group(update, context):
                print(f"Group {chat_id} is not premium. Cannot toggle 'play' command.")
                return

        group_doc = firebase.DATABASE.collection('groups').document(str(chat_id))
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
        utils.clear_group_cache(str(chat_id)) # Clear the cache on all database updates

        setup_commands(update, context)
    else:
        print("User is not the owner.")
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
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def simple_authentication(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
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
    
    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

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
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def math_authentication(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
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

    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

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
    store_setup_message(context, msg.message_id)


    if msg is not None:
        utils.track_message(msg)

def word_authentication(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
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

    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

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
    store_setup_message(context, msg.message_id)


    if msg is not None:
        utils.track_message(msg)

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
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def handle_timeout_callback(update: Update, context: CallbackContext) -> None:
    msg = None
    query, user_id = utils.get_query_info(update)

    if utils.is_user_owner(update, context, user_id):
        timeout_seconds = int(query.data.split('_')[1]) # Extract the timeout value from the callback_data

        group_id = update.effective_chat.id # Call set_verification_timeout with the group_id and timeout_seconds
        set_authentication_timeout(group_id, timeout_seconds)

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Authentication timeout set to {timeout_seconds // 60} minutes."
        )
        store_setup_message(context, msg.message_id)

        if msg is not None:
            utils.track_message(msg)

def set_authentication_timeout(group_id: int, timeout_seconds: int) -> None: # Sets the verification timeout for a specific group in the Firestore database.
    try:
        group_ref = firebase.DATABASE.collection('groups').document(str(group_id))

        group_ref.update({
            'verification_info.verification_timeout': timeout_seconds
        })

        print(f"Authentication timeout for group {group_id} set to {timeout_seconds} seconds")

    except Exception as e:
        print(f"Error setting verification timeout: {e}")

def check_authentication_settings(update: Update, context: CallbackContext) -> None:
    msg = None
    group_data = utils.fetch_group_info(update, context)

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
        store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)
#endregion Authentication Setup
##
#
##
#region Crypto Setup
def setup_crypto(update: Update, context: CallbackContext) -> None:
    msg = None

    group_data = utils.fetch_group_info(update, context)
    if not group_data:
        return

    token_data = group_data.get('token', {})
    setup_complete = token_data.get('setup_complete', False) # Check if token setup is complete

    if setup_complete:
        keyboard = [
            [
                InlineKeyboardButton("Check Token Details", callback_data='check_token_details'),
            ],
            [
                InlineKeyboardButton("❗ Reset Token Details ❗", callback_data='reset_token_details'),
            ],
            [
                InlineKeyboardButton("Back", callback_data='setup_home'),
            ]
        ]
    else:
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
        'Here you can setup your token details.\n\n'
        '• This functionality currently is only setup for WETH paired tokens.\n\n'
        '*⚠️ Updating Token Details ⚠️*\n'
        'Once you have setup a token, if you would like to add a different token, click *Reset Token Details* first.',
        parse_mode='markdown',
        reply_markup=reply_markup
    )
    context.chat_data['setup_stage'] = None
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def setup_contract(update: Update, context: CallbackContext) -> None:
    msg = None
    query, user_id = utils.get_query_info(update)

    if utils.is_user_owner(update, context, user_id):

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
        store_setup_message(context, msg.message_id)

        if msg is not None:
            utils.track_message(msg)

def handle_contract_address(update: Update, context: CallbackContext) -> None:
    msg = None
    user_id = update.message.from_user.id
    
    if utils.is_user_owner(update, context, user_id):
        if context.chat_data.get('setup_stage') == 'contract':
            eth_address_pattern = re.compile(r'\b0x[a-fA-F0-9]{40}\b')
            contract_address = update.message.text.strip()

            if eth_address_pattern.fullmatch(contract_address):
                checksum_address = Web3.to_checksum_address(contract_address)
                group_id = update.effective_chat.id
                print(f"Adding contract address {checksum_address} to group {group_id}")
                group_doc = utils.fetch_group_info(update, context, return_doc=True)
                group_doc.update({'token.contract_address': checksum_address})
                utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
                context.chat_data['setup_stage'] = None

                if update.message is not None:
                    msg = update.message.reply_text("Contract address added successfully!")
                elif update.callback_query is not None:
                    msg = update.callback_query.message.reply_text("Contract address added successfully!")
            
                complete_token_setup(group_id, context)
            else:
                msg = update.message.reply_text("Please send a valid Contract Address!")

        store_setup_message(context, msg.message_id)

        if msg is not None:
            utils.track_message(msg)

def setup_liquidity(update: Update, context: CallbackContext) -> None:
    msg = None
    query, user_id = utils.get_query_info(update)
    
    if utils.is_user_owner(update, context, user_id):
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
        store_setup_message(context, msg.message_id)
        print("Requesting liquidity address.")

        if msg is not None:
            utils.track_message(msg)

def handle_liquidity_address(update: Update, context: CallbackContext) -> None:
    msg = None
    user_id = update.message.from_user.id

    if utils.is_user_owner(update, context, user_id):
        msg = None
        if context.chat_data.get('setup_stage') == 'liquidity':
            eth_address_pattern = re.compile(r'\b0x[a-fA-F0-9]{40}\b')
            liquidity_address = update.message.text.strip()

            if eth_address_pattern.fullmatch(liquidity_address):
                checksum_address = Web3.to_checksum_address(liquidity_address)
                group_id = update.effective_chat.id
                print(f"Adding liquidity address {checksum_address} to group {group_id}")
                group_doc = utils.fetch_group_info(update, context, return_doc=True)
                group_doc.update({'token.liquidity_address': checksum_address})
                utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
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

        store_setup_message(context, msg.message_id)

        if msg is not None:
            utils.track_message(msg)

def setup_chain(update: Update, context: CallbackContext) -> None:
    msg = None
    query, user_id = utils.get_query_info(update)
    
    if utils.is_user_owner(update, context, user_id):

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
            [InlineKeyboardButton("Back", callback_data='setup_crypto')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        menu_change(context, update)

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Please choose your chain from the list.\n\n'
            '*Supported Networks:*\n'
            'Ethereum • Base • Arbitrum • Optimism\n\n'
            'All other networks are untested.\n\n'
            'We will be rolling out support for other chains and non WETH pairings shortly.',
            parse_mode='markdown',
            reply_markup=reply_markup
        )
        context.chat_data['setup_stage'] = 'chain'
        store_setup_message(context, msg.message_id)
        print("Requesting Chain.")

        if msg is not None:
            utils.track_message(msg)

def handle_chain(update: Update, context: CallbackContext) -> None:
    query, user_id = utils.get_query_info(update)

    if utils.is_user_owner(update, context, user_id):
        if context.chat_data.get('setup_stage') == 'chain':
            chain = update.callback_query.data.upper()  # Convert chain to uppercase
            group_id = update.effective_chat.id
            print(f"Adding chain {chain} to group {group_id}")
            group_doc = utils.fetch_group_info(update, context, return_doc=True)
            group_doc.update({'token.chain': chain})
            utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
            context.chat_data['setup_stage'] = None

            complete_token_setup(group_id, context)

            msg = query.message.reply_text("Chain has been saved.")

            store_setup_message(context, msg.message_id)

            if msg is not None:
                utils.track_message(msg)

def complete_token_setup(group_id: str, context: CallbackContext):
    msg = None
    group_doc = firebase.DATABASE.collection('groups').document(str(group_id))
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
    
    abi_path = os.path.join(config.CONFIG_DIR, 'erc20.abi.json')

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
        'token.decimals': decimals,
        'token.setup_complete': True
    })

    utils.clear_group_cache(str(group_id)) # Clear the cache on all database updates
    
    print(f"Added token name {token_name}, symbol {token_symbol}, and total supply {total_supply} to group {group_id}")

    if group_data.get('premium', False):  # Check if premium is True
        main.schedule_group_monitoring(group_data) # Instantly start monitoring the group
    else:
        print(f"Group {group_data['group_id']} is not premium. Skipping monitoring.")

    msg = context.bot.send_message(
        chat_id=group_id,
        text=f"*🎉 Token setup complete! 🎉*\n\n*Name:* {token_name}\n*Symbol:* {token_symbol}\n*Total Supply:* {total_supply}\n*Decimals:* {decimals}",
        parse_mode='Markdown'
    )

    if msg is not None:
        utils.track_message(msg)

def check_token_details_callback(update: Update, context: CallbackContext) -> None:
    query, user_id = utils.get_query_info(update)

    update = Update(update.update_id, message=query.message)

    if query.data == 'check_token_details':
        if utils.is_user_owner(update, context, user_id):
            check_token_details(update, context)
        else:
            print("User is not the owner.")

def check_token_details(update: Update, context: CallbackContext) -> None:
    msg = None
    group_data = utils.fetch_group_info(update, context)

    if group_data is not None:
        token_info = group_data.get('token', {})
        chain = token_info.get('chain', 'none')
        contract_address = token_info.get('contract_address', 'none')
        liquidity_address = token_info.get('liquidity_address', 'none')
        name = token_info.get('name', 'none')
        symbol = token_info.get('symbol', 'none')
        total_supply = token_info.get('total_supply', 'none')

        if any(value == 'none' for value in [chain, contract_address, liquidity_address, name, symbol, total_supply]): # Check if any required field is missing
            msg = context.bot.send_message( # Send warning message if details are missing
                chat_id=update.effective_chat.id,
                text="*⚠️ Token Details Missing ⚠️*\n\n"
                        "Please complete token setup first!",
                parse_mode='Markdown'
            )
            if msg is not None:
                utils.track_message(msg)
            return  # Exit the function as details are incomplete

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
        store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def reset_token_details(update: Update, context: CallbackContext) -> None:
    msg = None
    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is not None:
        group_doc.update({
            'token': {}
        })

        utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*🔄 Token Details Reset 🔄*',
            parse_mode='Markdown'
        )

    if msg is not None:
        utils.track_message(msg)
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
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def is_premium_group(update: Update, context: CallbackContext) -> bool:
    group_id = update.effective_chat.id
    group_data = utils.fetch_group_info(update, context)
    
    if group_data is not None and group_data.get('premium') is not True:
        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="This feature is only available to premium users. Please contact @tukyowave for more information.",
            parse_mode='Markdown'
        )
        store_setup_message(context, msg.message_id)
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
        text="Please send a JPG, GIF or MP4 for the welcome message header that is less than 700x250px.",
        parse_mode='Markdown'
    )
    context.chat_data['expecting_welcome_message_header_image'] = True  # Flag to check in the image handler
    context.chat_data['setup_stage'] = 'welcome_message_header'
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def handle_welcome_message_image(update: Update, context: CallbackContext) -> None:
    if context.chat_data.get('expecting_welcome_message_header_image'):
        group_id = update.effective_chat.id
        result = utils.fetch_group_info(update, context, return_both=True)  # Fetch both group_data and group_doc
        if not result:
            print("Failed to fetch group info. No action taken.")
            return

        group_data, group_doc = result  # Unpack the tuple

        validation_result = validate_media(update)

        if not validation_result['valid']:
            msg = context.bot.send_message( # Send validation error to the user
                chat_id=update.effective_chat.id,
                text=validation_result['error'],
                parse_mode='Markdown'
            )
            if msg is not None:
                utils.track_message(msg)
            return

        file_stream = validation_result['file_stream']
        file_extension = validation_result['file_extension']

        filename = f'welcome_message_header_{group_id}.{file_extension}'
        filepath = f'sypherbot/public/welcome_message_header/{filename}'

        bucket = firebase.BUCKET  # Save to Firebase Storage
        blob = bucket.blob(filepath)
        # Determine the correct MIME type explicitly
        if file_extension == "gif":
            mime_type = "image/gif"
        elif file_extension in ["jpg", "png"]:
            mime_type = f"image/{file_extension}"
        elif file_extension == "mp4":
            mime_type = "video/mp4"
        else:
            mime_type = "application/octet-stream"  # Fallback for unknown types

        # Upload the file with the correct MIME type
        blob.upload_from_string(
            file_stream.getvalue(),
            content_type=mime_type
        )
        blob.make_public()  # Make the file publicly accessible

        welcome_message_url = blob.public_url  # Store the public URL
        print(f"Welcome message header URL: {welcome_message_url}")

        if group_data is not None:
            group_doc.update({
                'premium_features.welcome_header': True,
                'premium_features.welcome_header_url': welcome_message_url
            })
            utils.clear_group_cache(str(update.effective_chat.id))  # Clear the cache on all database updates

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Your welcome message header has been successfully uploaded!",
            parse_mode='Markdown'
        )
        context.chat_data['expecting_welcome_message_header_image'] = False  # Reset the flag
        context.chat_data['setup_stage'] = None
        store_setup_message(context, msg.message_id)

        if msg is not None:
            utils.track_message(msg)

def setup_buybot_message_header(update: Update, context: CallbackContext) -> None:
    msg = None

    if not is_premium_group(update, context): return
    
    print("Requesting a Buybot message header.")

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please send a JPG, GIF or MP4 for the buybot message header that is less than 700x250px.",
        parse_mode='Markdown'
    )
    context.chat_data['expecting_buybot_header_image'] = True  # Flag to check in the image handler
    context.chat_data['setup_stage'] = 'buybot_message_header'
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def handle_buybot_message_image(update: Update, context: CallbackContext) -> None:
    if context.chat_data.get('expecting_buybot_header_image'):
        group_id = update.effective_chat.id
        result = utils.fetch_group_info(update, context, return_both=True)  # Fetch both group_data and group_doc
        if not result:
            print("Failed to fetch group info. No action taken.")
            return

        group_data, group_doc = result  # Unpack the tuple

        validation_result = validate_media(update)

        if not validation_result['valid']:
            msg = context.bot.send_message(  # Send validation error to the user
                chat_id=update.effective_chat.id,
                text=validation_result['error'],
                parse_mode='Markdown'
            )
            if msg is not None:
                utils.track_message(msg)
            return

        file_stream = validation_result['file_stream']
        file_extension = validation_result['file_extension']

        print(f"File size: {file_stream.getbuffer().nbytes} bytes.")

        filename = f'buybot_message_header_{group_id}.{file_extension}'
        filepath = f'sypherbot/public/buybot_message_header/{filename}'

        bucket = firebase.BUCKET  # Save to Firebase Storage
        blob = bucket.blob(filepath)

        # Determine the correct MIME type explicitly
        if file_extension == "gif":
            mime_type = "image/gif"
        elif file_extension in ["jpg", "png"]:
            mime_type = f"image/{file_extension}"
        elif file_extension == "mp4":
            mime_type = "video/mp4"
        else:
            mime_type = "application/octet-stream"  # Fallback for unknown types

        file_stream.seek(0)  # Ensure stream is at the beginning
        blob.upload_from_file(file_stream, content_type=mime_type)
        blob.make_public()  # Make the file publicly accessible

        buybot_header_url = blob.public_url  # Store the public URL
        print(f"Buybot header URL: {buybot_header_url}")

        if group_data is not None:
            group_doc.update({
                'premium_features.buybot_header': True,
                'premium_features.buybot_header_url': buybot_header_url
            })
            utils.clear_group_cache(str(update.effective_chat.id))  # Clear the cache on all database updates

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Your buybot message header has been successfully uploaded!",
            parse_mode='Markdown'
        )
        context.chat_data['expecting_buybot_header_image'] = False  # Reset the flag
        context.chat_data['setup_stage'] = None
        store_setup_message(context, msg.message_id)

        if msg is not None:
            utils.track_message(msg)

def validate_media(update, max_width=700, max_height=250, max_size=1000000):
    media = None
    file_extension = None
    file_stream = BytesIO()

    if update.message.photo:  # Handle photos (PNG, JPG)
        media = update.message.photo[-1]
        file_extension = "jpg"  # Assume JPG for Telegram photos
    elif update.message.animation:  # Handle GIFs
        media = update.message.animation
        file_extension = "gif"
    elif update.message.video:  # Handle MP4 videos
        media = update.message.video
        file_extension = "mp4"
    else:
        return {
            'valid': False,
            'media': None,
            'file_extension': None,
            'file_stream': None,
            'error': "Unsupported file type. Please upload a PNG, JPG, GIF, or MP4 file."
        }

    file = update.message.bot.get_file(media.file_id)  # Download the file
    file.download(out=file_stream)
    file_size = len(file_stream.getvalue())  # File size in bytes

    if hasattr(media, "width") and hasattr(media, "height"): # Validate dimensions and size
        if media.width <= max_width and media.height <= max_height and file_size <= max_size:
            return {
                'valid': True,
                'media': media,
                'file_extension': file_extension,
                'file_stream': file_stream,
                'error': None
            }

    error_message = f"Please ensure the media is less than {max_width}x{max_height} pixels"
    if file_size > max_size:
        error_message += f" and smaller than {max_size // 1000} KB"
    error_message += " and try again."

    return {
        'valid': False,
        'media': media,
        'file_extension': file_extension,
        'file_stream': None,
        'error': error_message
    }
#endregion Customization Setup
##
#
##
#region Sypher Trust Setup
def enable_sypher_trust(update: Update, context: CallbackContext) -> None:
    msg = None
    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
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
        utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*✔️ Trust System Enabled ✔️*',
            parse_mode='Markdown'
        )
        context.chat_data['setup_stage'] = None
        store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def disable_sypher_trust(update: Update, context: CallbackContext) -> None:
    msg = None
    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple
    
    if not is_premium_group(update, context): return

    if group_data is not None:
        group_doc.update({
            'premium_features.sypher_trust': False
        })
        utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*❌ Trust System Disabled ❌*',
            parse_mode='Markdown'
        )
        context.chat_data['setup_stage'] = None
        store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

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
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def sypher_trust_relaxed(update: Update, context: CallbackContext) -> None:
    msg = None
    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is not None:
        group_doc.update({
            'premium_features.sypher_trust_preferences': 'relaxed'
        })
        utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*🟢 Relaxed Trust Level Enabled 🟢*',
            parse_mode='Markdown'
        )
        store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def sypher_trust_moderate(update: Update, context: CallbackContext) -> None:
    msg = None
    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is not None:
        group_doc.update({
            'premium_features.sypher_trust_preferences': 'moderate'
        })
        utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*🟡 Moderate Trust Level Enabled 🟡*',
            parse_mode='Markdown'
        )
        store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def sypher_trust_strict(update: Update, context: CallbackContext) -> None:
    msg = None
    result = utils.fetch_group_info(update, context, return_both=True) # Fetch both group_data and group_doc
    if not result:
        print("Failed to fetch group info. No action taken.")
        return

    group_data, group_doc = result  # Unpack the tuple

    if group_data is not None:
        group_doc.update({
            'premium_features.sypher_trust_preferences': 'strict'
        })
        utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

        msg = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='*🔴 Strict Trust Level Enabled 🔴*',
            parse_mode='Markdown'
        )
        store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)
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
    store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def setup_minimum_buy_callback(update: Update, context: CallbackContext) -> None:
    msg = None
    query, user_id = utils.get_query_info(update)

    if utils.is_user_owner(update, context, user_id):

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
        store_setup_message(context, msg.message_id)

        if msg is not None:
            utils.track_message(msg)

def handle_minimum_buy(update: Update, context: CallbackContext) -> None:
    msg = None
    user_id = update.message.from_user.id
    
    if utils.is_user_owner(update, context, user_id):
        if context.chat_data.get('setup_stage') == 'minimum_buy':
            group_id = update.effective_chat.id
            group_data = utils.fetch_group_info(update, context)
            if group_data is not None:
                group_doc = firebase.DATABASE.collection('groups').document(str(group_id))
                group_doc.update({
                    'premium_features.buybot.minimumbuy': int(update.message.text)
                })
                msg = update.message.reply_text("Minimum buy value updated successfully!")
                utils.clear_group_cache(str(group_id)) # Clear the cache on all database updates

        store_setup_message(context, msg.message_id)

    else:
        print("User is not the owner.")

    if msg is not None:
        utils.track_message(msg)

def setup_small_buy_callback(update: Update, context: CallbackContext) -> None:
    msg = None
    query, user_id = utils.get_query_info(update)

    if utils.is_user_owner(update, context, user_id):

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
        store_setup_message(context, msg.message_id)

        if msg is not None:
            utils.track_message(msg)

def handle_small_buy(update: Update, context: CallbackContext) -> None:
    msg = None
    user_id = update.message.from_user.id
    
    if utils.is_user_owner(update, context, user_id):
        if context.chat_data.get('setup_stage') == 'small_buy':
            group_id = update.effective_chat.id
            group_data = utils.fetch_group_info(update, context)
            if group_data is not None:
                group_doc = firebase.DATABASE.collection('groups').document(str(group_id))
                try:
                    group_doc.update({
                        'premium_features.buybot.smallbuy': int(update.message.text)
                    })
                    utils.clear_group_cache(str(group_id))  # Clear the cache on all database updates
                    msg = update.message.reply_text("Small buy value updated successfully!")
                except Exception as e:
                    msg = update.message.reply_text(f"Error updating small buy value: {e}")
        
        if msg:
            store_setup_message(context, msg.message_id)

    else:
        print("User is not the owner.")

    if msg is not None:
        utils.track_message(msg)

def setup_medium_buy_callback(update: Update, context: CallbackContext) -> None:
    msg = None
    query, user_id = utils.get_query_info(update)

    if utils.is_user_owner(update, context, user_id):

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
        store_setup_message(context, msg.message_id)

        if msg is not None:
            utils.track_message(msg)

def handle_medium_buy(update: Update, context: CallbackContext) -> None:
    msg = None
    user_id = update.message.from_user.id
    
    if utils.is_user_owner(update, context, user_id):
        if context.chat_data.get('setup_stage') == 'medium_buy':
            group_id = update.effective_chat.id
            group_data = utils.fetch_group_info(update, context)
            if group_data is not None:
                group_doc = firebase.DATABASE.collection('groups').document(str(group_id))
                try:
                    group_doc.update({
                        'premium_features.buybot.mediumbuy': int(update.message.text)
                    })
                    utils.clear_group_cache(str(group_id))  # Clear the cache on all database updates
                    msg = update.message.reply_text("Medium buy value updated successfully!")
                except Exception as e:
                    msg = update.message.reply_text(f"Error updating medium buy value: {e}")
        
        if msg:
            store_setup_message(context, msg.message_id)

    else:
        print("User is not the owner.")

    if msg is not None:
        utils.track_message(msg)
#endregion Buybot Setup
##
#
##
#endregion Premium Setup
##
#
##
#endregion Bot Setup