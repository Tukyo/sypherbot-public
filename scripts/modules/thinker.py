import re
import sys
import openai
import random
from threading import Timer
from telegram import Update
from telegram.ext import CallbackContext

## Import the needed modules from the config folder
# {config.py} - Environment variables and global variables used in the bot
# {firebase.py} - Firebase configuration and database initialization
# {utils.py} - Utility functions and variables used in the bot
from modules import config, logger, utils

sys.stdout = logger.StdoutWrapper()  # Redirect stdout
sys.stderr = logger.StderrWrapper()  # Redirect stderr

# Configuration variables for easy adjustment
MAX_INTENT_TOKENS = 20  # Maximum tokens for intent classification
MAX_RESPONSE_TOKENS = 100  # Maximum tokens for OpenAI response
TEMPERATURE = 0.7  # AI creativity level
OPENAI_MODEL = "gpt-3.5-turbo"  # OpenAI model to use
PROMPT_PATTERN = r"^(hey sypher(?:bot)?)\s*(.*)$"  # Matches "hey sypher" or "hey sypherbot" at the start

ongoing_conversations = {} # Dictionary to store ongoing conversations
prompt_timeout = 10  # Timeout for conversation prompts in seconds

ERROR_REPLIES = [
    "Sorry, I didn't understand that. Please try rephrasing.",
    "I'm not sure what you're asking. Can you try again?",
    "I'm having trouble understanding. Please try again.",
    "I'm not sure how to respond to that...",
    "I have literally no idea what you are saying lol",
    "I'm not sure what you're asking...",
    "That didn't make sense...",
    "Oops! That went over my head. Can you say it differently?",
    "Hmm, I'm puzzled. Could you clarify?",
    "My circuits are confused. Try asking in another way?",
    "I need a bit more info to help you out. Can you elaborate?",
    "I'm scratching my head here. What do you mean?",
    "That one stumped me. Mind rephrasing?",
    "I'm lost in translation. Can you rephrase that?",
    "I think I missed something. Could you try again?",
    "My AI brain is having a moment. Can you ask differently?",
    "I'm not quite following. Can you explain it another way?",
    "That didn't compute. Can you say it another way?",
    "I'm drawing a blank here. Can you rephrase?",
    "I'm a bit confused. Could you clarify your question?"
]

GENERIC_REPLIES = [
    "What's up?",
    "Hey there!",
    "Hello!",
    "Hi!",
    "Hey!",
    "GM!",
    "Wassup??",
    "Yo!",
    "Howdy!",
    "How can I help?",
    "What's on your mind?",
    "What can I do for you?",
    "What's good?"
]

def initialize_openai():
    openai.api_key = config.OPENAI_API_KEY
    print("OpenAI API initialized.")

#region Prompt & Intention
# The following function is used to handle incoming messages and prompt the AI for a response
# The AI is prompted with the user's query and the group's context to generate a response
##
def prompt_handler(update: Update, context: CallbackContext) -> None:
    message_text = update.message.text.strip()
    user_id = update.message.from_user.id
    group_id = update.message.chat_id

    replied_message = update.message.reply_to_message.text if update.message.reply_to_message else None # Check if the message is a reply to a bot message
    if replied_message is not None:
        last_response = None
        query = message_text.strip()
        print(f"Received a reply to a bot message: '{replied_message}' from user {user_id} in chat {group_id}: '{message_text}'")

    last_response = get_conversation_context(user_id, group_id) # Get the last response for the user in the group
    if last_response is not None and replied_message is None:
        match = re.match(PROMPT_PATTERN, message_text, re.IGNORECASE)
        if not match and not get_conversation(user_id, group_id):  # Skip if no "hey sypher" and no active conversation
            print("No ongoing conversation and no trigger phrase provided...")
            return None
    
    if replied_message is None:
        query = match.group(2).strip() if match else message_text.strip()  # Extract the query (everything after the trigger phrase)
        if not query: # If there is no query just provide a generic response
            generic_greeting = random.choice(GENERIC_REPLIES)
            update.message.reply_text(generic_greeting)
            print(f"Received 'hey sypher' with no query from a user in chat {update.message.chat_id}")
            return generic_greeting
    
    print(f"Processing query from user {user_id} in chat {group_id}: {query}")

    # Admin dictionary MIGHT be too big for processing correctly with 10 tokens...
    # LATER TODO: Implement a way to split the dictionary into smaller chunks for processing
    # if not utils.is_user_admin(update, context): # If admin triggered the bot, get the entire group dictionary
    #     dictionary = utils.fetch_group_dictionary(update, context)
    # else:
    #     dictionary = utils.fetch_group_dictionary(update, context, True) # If regular user triggered the bot, get the general group dictionary
    
    dictionary = utils.fetch_group_dictionary(update, context, True) # If regular user triggered the bot, get the general group dictionary
    if not dictionary: # You'll always find a dictionary with default values, so if not found, error occurred
        print(f"No dictionary found for chat {update.message.chat_id}. Proceeding without group-specific context.")
        return None
    
    if last_response is not None:
        intent = determine_intent(query, dictionary, last_response) # Determine the user's intent based on the query and group context
        print(f"Determined intent: {intent}")
    elif replied_message is not None:
        intent = determine_intent(query, dictionary, None, replied_message)
        print(f"Determined intent: {intent}")
    
    context_info = f"Context: {dictionary}\n"
    if intent == "continue_conversation":
        context_info += f"Previous Response: {last_response}\nQuery: {query}\n"
    elif intent == "reply_to_message":
        context_info += f"Replied Message: {replied_message}\nQuery: {query}\n" 
    else:
        context_info += f"Query: {query}\nIntent: {intent}\n"
        print("No previous response found in conversation context.")

    messages = [
        {"role": "system", "content": (
            "You are SypherBot a smart telegram bot created by Tukyo. "
            "Your users are mostly degens and crypto traders. "
            "Answer accurately using group context and intent. Keep responses concise and under 40 words unless more detail is requested. "
            "Be professional, engaging, and use humor sparingly, especially with memes. "
            "Never cut off responses mid-thought."
        )},
        {"role": "user", "content": context_info}
    ]

    try:  # Call OpenAI API with the new `ChatCompletion.create` syntax
        openai_response = openai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=MAX_RESPONSE_TOKENS,
            temperature=TEMPERATURE,
        )
        response_message = openai_response.choices[0].message.content.strip()  # Extract the response text
    except Exception as e:
        error_reply = update.message.reply_text("Sorry, I couldn't process your request. Try again later.")
        print(f"OpenAI API error: {e}")
        return error_reply

    if response_message:  # Send the response back to the user
        update.message.reply_text(response_message)
        print(f"Response in chat {update.message.chat_id}: {response_message}")
        return response_message
    else:
        error_reply = random.choice(ERROR_REPLIES)
        update.message.reply_text(error_reply)
        print("Error determining response, sending a random error reply")
        return error_reply
##
# The following function is used to classify the user's intent based on the query and group context
# The AI is prompted with the query and group context to determine the user's intent
##
def determine_intent(query: str, group_dictionary: dict, last_response: str = None, replied_msg: str = None) -> str:
    if last_response:  # Prioritize conversation continuation
        print("Intent Classification: continue_conversation")
        return "continue_conversation"

    if replied_msg:
        print("Intent Classification: reply_to_message")
        return "reply_to_message"
    
    classification_prompt = (
        "Analyze the following query and classify it based on the context provided below. "
        "Use the context to understand the user's intent and generate a response if necessary. "
        "If the query does not align with the context or is unclear, return 'unknown'. "
        f"\n\nContext:\n{group_dictionary}\n\nQuery:\n{query}"
    )

    try:
        intent_response = openai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": "You are an intelligent assistant that classifies and responds to user queries."},
                      {"role": "user", "content": classification_prompt}],
            max_tokens=MAX_INTENT_TOKENS,
            temperature=0.0  # Deterministic response
        )
        intent = intent_response.choices[0].message.content.strip().lower()
        print(f"Intent classification: {intent}")
        return intent
    except Exception as e:
        print(f"Error determining intent: {e}")
        return "unknown"
##
#endregion Prompt & Intention
##   
#
##
#region Conversation Management
# The following functions are used to manage ongoing conversations with users in groups
# The conversation state is stored in the ongoing_conversations dictionary
# Each conversation is associated with a user_id and group_id
# The conversation state includes the last response from the bot and a timer to clear the conversation
##
def start_conversation(user_id, group_id, last_response): # Start or reset a conversation for a user in a group
    key = (user_id, group_id)

    if key in ongoing_conversations: # If the user is already in a conversation, cancel the existing timer
        ongoing_conversations[key]['timer'].cancel()

    timer = Timer(prompt_timeout, clear_conversation, [user_id, group_id]) # Clear the conversation after prompt_timeout
    timer.start()

    ongoing_conversations[key] = { # Store the conversation state
        'timer': timer,
        'last_response': last_response,
    }
    print(f"Started conversation for user {user_id} in group {group_id}.")

def clear_conversation(user_id, group_id): # Clear the conversation state for a user in a group
    key = (user_id, group_id)
    if key in ongoing_conversations:
        del ongoing_conversations[key]
        print(f"Cleared conversation for user {user_id} in group {group_id}.")

def get_conversation_context(user_id, group_id): # Get the conversation context for a user in a group, or None if not active
    conversation = get_conversation(user_id, group_id)
    if conversation:
        return conversation['last_response']
    return None

def get_conversation(user_id, group_id): # Get the conversation state for a user in a group, or None if not active
    return ongoing_conversations.get((user_id, group_id))
##
#endregion Conversation Management