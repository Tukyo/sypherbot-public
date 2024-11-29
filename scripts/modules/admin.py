## Import the needed modules from the telegram library
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
##
#
## Import the needed modules from the config folder
# {config.py} - Environment variables and global variables used in the bot
# {utils.py} - Utility functions and variables used in the bot
# {firebase.py} - Firebase configuration and database initialization
# {setup.py} - Setup and configuration functions for the bot
from modules import config, utils, firebase, setup

from firebase_admin import firestore
from datetime import datetime

#region Admin Controls
def admin_commands(update: Update, context: CallbackContext) -> None:
    msg = None
    if utils.is_user_admin(update, context):
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
            "*/block*\nAdd something to the blocklist\n"
            "*/removeblock | /unblock*\nRemove something from the block list\n"
            "*/blocklist*\nView the block list\n"
            "*/allow*\nAllow a contract address, URL or domain\n"
            "*/allowlist*\nView the allow list\n",
            parse_mode='Markdown'
        )
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
    
    if msg is not None:
        utils.track_message(msg)

def mute(update: Update, context: CallbackContext) -> None:
    msg = None
    chat_id = update.effective_chat.id

    if utils.is_user_admin(update, context):
        group_doc = firebase.DATABASE.collection('groups').document(str(chat_id))
        group_data = group_doc.get().to_dict()

        if group_data is None or not group_data.get('admin', {}).get('mute', False):
            msg = update.message.reply_text("Muting is not enabled in this group.")
            if msg is not None:
                utils.track_message(msg)
            return
        
        if update.message.reply_to_message is None:
            msg = update.message.reply_text("This command must be used in response to another message!")
            if msg is not None:
                utils.track_message(msg)
            return
        reply_to_message = update.message.reply_to_message
        if reply_to_message:
            user_id = reply_to_message.from_user.id
            username = reply_to_message.from_user.username or reply_to_message.from_user.first_name

        if utils.is_bot_or_admin(update, context, user_id): return

        context.bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=ChatPermissions(can_send_messages=False))
        msg = update.message.reply_text(f"User {username} has been muted.")

        group_doc.update({ # Add the user to the muted_users mapping in the database
            f'muted_users.{user_id}': datetime.now().isoformat()
        })
        utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
    
    if msg is not None:
        utils.track_message(msg)

def unmute(update: Update, context: CallbackContext) -> None:
    msg = None
    chat_id = update.effective_chat.id

    group_doc = firebase.DATABASE.collection('groups').document(str(chat_id))
    group_data = group_doc.get().to_dict()

    if group_data is None or not group_data.get('admin', {}).get('mute', False):
        msg = update.message.reply_text("Admins are not allowed to use the unmute command in this group.")
        if msg is not None:
            utils.track_message(msg)
        return

    if utils.is_user_admin(update, context):
        if not context.args:
            msg = update.message.reply_text("You must provide a username to unmute.")
            if msg is not None:
                utils.track_message(msg)
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
                    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
                    break
            except Exception:
                continue
        else:
            msg = update.message.reply_text("Can't find that user.")
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
    
    if msg is not None:
        utils.track_message(msg)

def check_mute_list(update: Update, context: CallbackContext) -> None:
    msg = None
    group_id = update.effective_chat.id
    group_data = utils.fetch_group_info(update, context)

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
    setup.store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def warn(update: Update, context: CallbackContext):
    msg = None
    chat_id = update.effective_chat.id

    if utils.is_user_admin(update, context):
        group_doc = firebase.DATABASE.collection('groups').document(str(chat_id))
        group_data = group_doc.get().to_dict()

        if group_data is None or not group_data.get('admin', {}).get('warn', False): # Check if warns enabled
            msg = update.message.reply_text("Warning system is not enabled in this group.")
            if msg is not None:
                utils.track_message(msg)
            return
        
        if update.message.reply_to_message is None:
            msg = update.message.reply_text("This command must be used in response to another message!")
            if msg is not None:
                utils.track_message(msg)
            return
        
        reply_to_message = update.message.reply_to_message
        if reply_to_message:
            user_id = str(reply_to_message.from_user.id)
            username = reply_to_message.from_user.username or reply_to_message.from_user.first_name

        if utils.is_bot_or_admin(update, context, user_id): return
        
        try:
            doc_snapshot = group_doc.get()
            if doc_snapshot.exists:
                group_data = doc_snapshot.to_dict()
                warnings_dict = group_data.get('warnings', {})

                current_warnings = warnings_dict.get(user_id, 0) # Increment the warning count for the user
                current_warnings += 1
                warnings_dict[user_id] = current_warnings

                group_doc.update({'warnings': warnings_dict}) # Update the group document with the new warnings count
                utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
                msg = update.message.reply_text(f"{username} has been warned. Total warnings: {current_warnings}")

                process_warns(update, context, user_id, current_warnings) # Check if the user has reached the warning limit
            else:
                msg = update.message.reply_text("Group data not found.")
        except Exception as e:
            msg = update.message.reply_text(f"Failed to update warnings: {str(e)}")
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")

    if msg is not None:
        utils.track_message(msg)

def clear_warns_for_user(update: Update, context: CallbackContext):
    msg = None
    chat_id = update.effective_chat.id
    group_doc = firebase.DATABASE.collection('groups').document(str(chat_id))
    group_data = group_doc.get().to_dict()

    if utils.is_user_admin(update, context):
        if not context.args:
            msg = update.message.reply_text("You must provide a username to clear warnings.")
            if msg is not None:
                utils.track_message(msg)
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
                    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
                    msg = update.message.reply_text(f"Warnings cleared for @{username_to_clear}.")
                    break
            except Exception:
                continue
        else:
            msg = update.message.reply_text("Can't find that user.")
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
    
    if msg is not None:
        utils.track_message(msg)

def check_warn_list(update: Update, context: CallbackContext) -> None:
    msg = None
    keyboard = [
        [InlineKeyboardButton("Back", callback_data='setup_warn')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    group_id = update.effective_chat.id
    group_data = utils.fetch_group_info(update, context)

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
    setup.store_setup_message(context, msg.message_id)

    if msg is not None:
        utils.track_message(msg)

def process_warns(update: Update, context: CallbackContext, user_id: str, warnings: int):
    msg = None
    if warnings >= 3:
        try:
            context.bot.ban_chat_member(update.message.chat.id, int(user_id))
            msg = update.message.reply_text(f"Goodbye {user_id}!")
        except Exception as e:
            msg = update.message.reply_text(f"Failed to kick {user_id}: {str(e)}")
        
    if msg is not None:
        utils.track_message(msg)

def check_warnings(update: Update, context: CallbackContext):
    msg = None
    if utils.is_user_admin(update, context) and update.message.reply_to_message:
        user_id = str(update.message.reply_to_message.from_user.id)
        group_doc = utils.fetch_group_info(update, context, return_doc=True)

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
        utils.track_message(msg)

def kick(update: Update, context: CallbackContext) -> None:
    msg = None
    chat_id = update.effective_chat.id

    if utils.is_user_admin(update, context):
        if update.message.reply_to_message is None:
            msg = update.message.reply_text("This command must be used in response to another message!")
            if msg is not None:
                utils.track_message(msg)
            return
        reply_to_message = update.message.reply_to_message
        if reply_to_message:
            user_id = reply_to_message.from_user.id
            username = reply_to_message.from_user.username or reply_to_message.from_user.first_name

        if utils.is_bot_or_admin(update, context, user_id): return

        context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        msg = update.message.reply_text(f"User {username} has been kicked.")
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
    
    if msg is not None:
        utils.track_message(msg)

def block(update: Update, context: CallbackContext):
    msg = None
    if utils.is_user_admin(update, context):
        command_text = update.message.text[len('/block '):].strip().lower()

        if not command_text:
            msg = update.message.reply_text("Please provide some text to block.")
            return

        group_doc = utils.fetch_group_info(update, context, return_doc=True)
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
                    utils.clear_group_cache(str(update.effective_chat.id))  # Clear the cache on all database updates
                    print("Updated blocklist:", current_blocklist)
            else:
                group_doc.set({blocklist_field: [command_text]})  # If no blocklist exists, create it with the current command text
                msg = update.message.reply_text(f"'{command_text}' blocked!")
                utils.clear_group_cache(str(update.effective_chat.id))  # Clear the cache on all database updates
                print("Created new blocklist with:", [command_text])

        except Exception as e:
            msg = update.message.reply_text(f"Failed to update blocklist: {str(e)}")
            print(f"Error updating blocklist: {e}")

    if msg is not None:
        utils.track_message(msg)

def remove_block(update: Update, context: CallbackContext):
    msg = None
    if utils.is_user_admin(update, context):
        command_text = update.message.text[len('/removeblock '):].strip().lower()

        if not command_text:
            msg = update.message.reply_text("Please provide a valid blocklist item to remove.")
            if msg is not None:
                utils.track_message(msg)
            return

        group_doc = utils.fetch_group_info(update, context, return_doc=True)
        blocklist_field = 'blocklist'

        try: # Use Firestore's arrayRemove to remove the item from the blocklist array
            group_doc.update({blocklist_field: firestore.ArrayRemove([command_text])})
            msg = update.message.reply_text(f"'{command_text}' removed from the blocklist!")
            utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
            print(f"Removed '{command_text}' from the blocklist.")
        
        except Exception as e:
            msg = update.message.reply_text(f"Failed to remove from blocklist: {str(e)}")
            print(f"Error removing from blocklist: {e}")

    if msg is not None:
        utils.track_message(msg)

def blocklist(update: Update, context: CallbackContext):
    msg = None
    if utils.is_user_admin(update, context):
        group_doc = utils.fetch_group_info(update, context, return_doc=True)

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
        utils.track_message(msg)

def allow(update: Update, context: CallbackContext):
    msg = None
    if utils.is_user_admin(update, context):
        command_text = update.message.text[len('/allow '):].strip()

        # Validate against patterns
        if not (config.ETH_ADDRESS_PATTERN.match(command_text) or 
                config.URL_PATTERN.match(command_text) or 
                config.DOMAIN_PATTERN.match(command_text)):
            msg = update.message.reply_text(
                "Invalid format. Only crypto addresses, URLs, or domain names can be added to the allowlist."
            )
            if msg is not None:
                utils.track_message(msg)
            return

        group_doc = utils.fetch_group_info(update, context, return_doc=True)
        allowlist_field = 'allowlist'

        try: # Use Firestore's arrayUnion to add the item to the allowlist array
            group_doc.update({allowlist_field: firestore.ArrayUnion([command_text])}) 
            msg = update.message.reply_text(f"'{command_text}' added to the allowlist!")
            utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
            print(f"Added '{command_text}' to allowlist.")

        except Exception as e:
            if 'NOT_FOUND' in str(e): # Handle the case where the document doesn't exist
                group_doc.set({allowlist_field: [command_text]})
                msg = update.message.reply_text(f"'{command_text}' added to a new allowlist!")
                utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
                print(f"Created new allowlist with: {command_text}")
            else:
                msg = update.message.reply_text(f"Failed to update allowlist: {str(e)}")
                print(f"Error updating allowlist: {e}")

    if msg is not None:
        utils.track_message(msg)

def allowlist(update: Update, context: CallbackContext):
    msg = None
    if utils.is_user_admin(update, context):
        group_doc = utils.fetch_group_info(update, context, return_doc=True)

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
        utils.track_message(msg)

def cleargames(update: Update, context: CallbackContext) -> None:
    msg = None
    chat_id = update.effective_chat.id

    if utils.is_user_admin(update, context):
        keys_to_delete = [key for key in context.chat_data.keys() if key.startswith(f"{chat_id}_")]
        for key in keys_to_delete:
            del context.chat_data[key]
            print(f"Deleted key: {key}")
    
        msg = update.message.reply_text("All active games have been cleared.")
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
        print(f"User {update.effective_user.id} tried to clear games but is not an admin in chat {update.effective_chat.id}.")
    
    if msg is not None:
        utils.track_message(msg)

def cleanbot(update: Update, context: CallbackContext):
    global bot_messages
    if utils.is_user_admin(update, context):
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
    if utils.is_user_admin(update, context):
        utils.clear_group_cache(str(update.effective_chat.id))
        msg = update.message.reply_text("Cache cleared.")
    else:
        msg = update.message.reply_text("You must be an admin to use this command.")
    
    if msg is not None:
        utils.track_message(msg)
#endregion Admin Controls