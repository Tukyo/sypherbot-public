import random
import requests
from datetime import timedelta

## Import the needed modules from the telegram library
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
##
## Import the needed modules from the config folder
# {config.py} - Environment variables and global variables used in the bot
# {utils.py} - Utility functions and variables used in the bot
# {firebase.py} - Firebase configuration and database initialization
from modules import config, utils, firebase

#region User Authentication
def authentication_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    _, group_id, user_id = query.data.split('_')

    print(f"Authenticating user {user_id} for group {group_id}")

    group_doc = firebase.DATABASE.collection('groups').document(group_id)
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
    group_doc = utils.fetch_group_info(update, context, return_doc=True, group_id=group_id)

    if authentication_type == 'math':
        challenges = [config.MATH_0, config.MATH_1, config.MATH_2, config.MATH_3, config.MATH_4]
        index = random.randint(0, 4)
        math_challenge = challenges[index]

        blob = firebase.BUCKET.blob(f'sypherbot/private/auth/math_{index}.jpg')
        image_url = blob.generate_signed_url(expiration=timedelta(minutes=firebase.BLOB_EXPIRATION))

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
        utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
        print(f"Stored math challenge for user {user_id} in group {group_id}: {math_challenge}")

    elif authentication_type == 'word':
        challenges = [config.WORD_0, config.WORD_1, config.WORD_2, config.WORD_3, config.WORD_4, config.WORD_5, config.WORD_6, config.WORD_7, config.WORD_8]
        original_challenges = challenges.copy()  # Copy the original list before shuffling
        random.shuffle(challenges)
        word_challenge = challenges[0]  # The word challenge is the first word in the shuffled list
        index = original_challenges.index(word_challenge)  # Get the index of the word challenge in the original list

        blob = firebase.BUCKET.blob(f'sypherbot/private/auth/word_{index}.jpg')
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
        utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates
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

    group_doc = firebase.DATABASE.collection('groups').document(group_id)
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

    group_doc = firebase.DATABASE.collection('groups').document(group_id)
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
    group_doc = firebase.DATABASE.collection('groups').document(group_id)
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
        utils.clear_group_cache(str(group_id)) # Clear the cache on all database updates

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
    group_doc = utils.fetch_group_info(update, context, return_doc=True, group_id=group_id)
    group_data = group_doc.get().to_dict()

    if 'unverified_users' in group_data and user_id in group_data['unverified_users']:
        group_data['unverified_users'][user_id] = None

    print(f"Reset challenge for user {user_id} in group {group_id}")

    group_doc.set(group_data) # Write the updated group data back to Firestore
    utils.clear_group_cache(str(update.effective_chat.id)) # Clear the cache on all database updates

    context.bot.delete_message(
        chat_id=update.effective_chat.id,
        message_id=update.callback_query.message.message_id
    )

    context.bot.send_message( # Send a message to the user instructing them to start the authentication process again
        chat_id=user_id,
        text="Authentication failed. Please start the authentication process again by clicking on the 'Authenticate' button above."
    )

def delete_welcome_message(context: CallbackContext) -> None:
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