import re
import openai
import random
from threading import Timer
from telegram import Update
from telegram.ext import CallbackContext

## Import the needed modules from the config folder
# {config.py} - Environment variables and global variables used in the bot
# {firebase.py} - Firebase configuration and database initialization
# {utils.py} - Utility functions and variables used in the bot
from modules import config, utils

# Configuration variables for easy adjustment
MAX_INTENT_TOKENS = 50  # Maximum tokens for intent classification
MAX_RESPONSE_TOKENS = 100  # Maximum tokens for OpenAI response
TEMPERATURE = 0.3  # AI creativity level
FREQUENCY = 1  # AI repetition penalty
PRESENCE = 0.25  # AI context awareness
OPENAI_MODEL = "gpt-4o-mini"  # OpenAI model to use
PROMPT_PATTERN = r"^(hey sypher(?:bot)?)\s*(.*)$"  # Matches "hey sypher" or "hey sypherbot" at the start

ongoing_conversations = {} # Dictionary to store ongoing conversations
RESPONSE_CACHE_SIZE = 10  # Number of responses to cache
response_cache = {} # Cached response mapping per user for the AI to use (clears daily)
PROMPT_TIMEOUT = 10  # Timeout for conversation prompts in seconds

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

#region Prompt Handling
##
# The following function is used to handle incoming messages and prompt the AI for a response
# The AI is prompted with the user's query and the group's context to generate a response
def prompt_handler(update: Update, context: CallbackContext) -> None:
    message_text = update.message.text.strip()
    user_id = update.message.from_user.id
    group_id = update.message.chat_id
    username = utils.get_username(update)

    match = re.match(PROMPT_PATTERN, message_text, re.IGNORECASE)  # Check if the message starts with the trigger phrase

    replied_message = update.message.reply_to_message.text if update.message.reply_to_message else None # Check if the message is a reply to a bot message
    if replied_message is not None:
        last_response = None
        query = message_text.strip()
        print(f"Received a reply to a bot message: '{replied_message}' from user {user_id} in chat {group_id}: '{message_text}'")

    last_response = get_conversation_context(user_id, group_id) # Get the last response for the user in the group
    if last_response is not None and replied_message is None:
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
    
    group_dictionary = utils.fetch_group_dictionary(update, context, True) # If regular user triggered the bot, get the general group dictionary
    if not group_dictionary: # You'll always find a dictionary with default values, so if not found, error occurred
        print(f"No dictionary found for chat {update.message.chat_id}. Proceeding without group-specific context.")
        return None
    
    intent = determine_intent(query, group_dictionary) # Determine the user's intent
    
    if last_response is not None and replied_message is None: # Last response is found
        context_info = determine_context(update, context, intent, query, group_dictionary, user_id, username, last_response, None)
    elif replied_message is not None: # Replied message is found
        context_info = determine_context(update, context, intent, query, group_dictionary, user_id, username, None, replied_message)
    else: # Neither last response nor replied message is found, most likely a new "hey sypher" message
        context_info = determine_context(update, context, intent, query, group_dictionary, user_id, username, None, None)

    messages = [
        {"role": "system", "content": (
            "You are Sypherbot a telegram bot created by Tukyo. "
            "Your users are mostly degens and crypto traders. "
            "Answer using group context and intent. Keep responses concise and under 40 words unless more detail is requested. "
            "Do not add unnecessary generic offers for assistance, polite endings, greetings, or commentary. "
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
            frequency_penalty=FREQUENCY,
            presence_penalty=PRESENCE
        )
        response_message = openai_response.choices[0].message.content.strip()  # Extract the response text
    except Exception as e:
        error_reply = update.message.reply_text("Sorry, I couldn't process your request. Try again later.")
        print(f"OpenAI API error: {e}")
        return error_reply

    if response_message:  # Send the response back to the user
        update.message.reply_text(response_message)
        print(f"Response in chat {update.message.chat_id}: {response_message}")
        cache_interaction(user_id, query, response_message)
        return response_message
    else:
        error_reply = random.choice(ERROR_REPLIES)
        update.message.reply_text(error_reply)
        print("Error determining response, sending a random error reply")
        return error_reply
#endregion Prompt Handling
##
#
##
#region Intention & Context
##
# The following function is used to classify the user's intent based on the query and group context
# The AI is prompted with the query and group context to determine the user's intent
def determine_intent(query: str, group_dictionary: dict) -> str:
    classification_prompt = (
        "Analyze the following query and classify it based on the context provided below. "
        "Describe the user's intent as clearly and specifically as possible using the provided query and context. "
        "If the query is ambiguous or the context is insufficient, determine the intent with reasoning and explain your conclusion."
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
    
def determine_context(update: Update, context: CallbackContext, intent: str, query: str, group_dictionary: dict, user_id: str, username: str, last_response: str = None, replied_message: str = None) -> str:
    context_info = f"Context: {group_dictionary}\n"
    context_info += f"Username: @{username}\n"

    if last_response is not None: # If a previous response is found in the conversation context
        context_info += f"Previous Response: {last_response}\nQuery: {query}\n"
        print(f"Last response found in conversation context: {last_response}")
    elif replied_message is not None: # If a replied message is found in the conversation context
        context_info += f"Replied Message: {replied_message}\nQuery: {query}\n" 
        print(f"Replied message found in conversation context: {replied_message}")
    elif replied_message is None and last_response is None: # No reply or last response found
        context_info += f"Query: {query} || Intent: {intent}\n"
        print("No previous response found in conversation context.")

    matched_function = ( # After determining the intent, check if a function should be called
        FUNCTION_REGISTRY.get(intent, {}).get("function")  # Match by intent first
        or match_function_by_keywords(query)  # Fallback to keyword-based matching
    )

    matched_function = None
    for func_name, details in FUNCTION_REGISTRY.items():
        if details.get("intent") == intent:
            matched_function = details["function"]
            print(f"Matched function by intent: {func_name}")
            break

    if matched_function:  # Execute the matched function if found
        try:
            result = matched_function(update, context)
            if result:
                if isinstance(result, list):
                    formatted_result = "Function Result:\n" + "\n".join(f"- {item}" for item in result)
                elif isinstance(result, dict):
                    formatted_result = "Function Result:\n" + "\n".join(f"{key}: {value}" for key, value in result.items())
                else:
                    formatted_result = f"Function Result:\n{result}"

                context_info += f"\n{formatted_result}\n"
        except Exception as e:
            print(f"Error executing function: {e}")
            error_reply = random.choice(ERROR_REPLIES)
            update.message.reply_text(error_reply)
            return error_reply
        
    cached_interactions = get_interaction_cache(user_id)  # Get the recent responses for the user
    if cached_interactions is not "No recent responses in cache for this user.":  # If there are cached responses, include them in the context
        context_info += f"\n{cached_interactions}"
    
    print(f"Context for prompt: {context_info}")
    return context_info
#endregion Intention & Context
##   
#
##
#region Conversation Management
##
# The following functions are used to manage ongoing conversations with users in groups
# The conversation state is stored in the ongoing_conversations dictionary
# Each conversation is associated with a user_id and group_id
# The conversation state includes the last response from the bot and a timer to clear the conversation
def start_conversation(user_id, group_id, last_response): # Start or reset a conversation for a user in a group
    key = (user_id, group_id)

    if key in ongoing_conversations: # If the user is already in a conversation, cancel the existing timer
        ongoing_conversations[key]['timer'].cancel()

    timer = Timer(PROMPT_TIMEOUT, clear_conversation, [user_id, group_id]) # Clear the conversation after prompt_timeout
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
##
#
##
#region Caching
def cache_interaction(user_id, query, response_message):
    if user_id not in response_cache:
        response_cache[user_id] = []

    if len(response_cache[user_id]) >= RESPONSE_CACHE_SIZE:
        response_cache[user_id].pop(0)  # Remove the oldest interaction for this user

    response_cache[user_id].append({"query": query, "response": response_message})

def get_interaction_cache(user_id):
    if user_id not in response_cache or not response_cache[user_id]:
        return "No recent interactions found for this user."

    cache_summary = "\n".join(  # Format the cache as a readable summary
        f"{i+1}: Q: {interaction['query']} | A: {interaction['response']}"
        for i, interaction in enumerate(response_cache[user_id])
    )
    return f"Recent Interactions for User {user_id}:\n{cache_summary}"
#endregion Caching
##
#
##
#region Function Handling & Registry
# The following functions are used to handle specific commands or queries from users
# Each function is associated with a specific context and keywords for matching
# The function registry stores the available functions and their metadata
FUNCTION_REGISTRY = {
    "fetch_trending_coins": {
        "function": utils.fetch_trending_coins,
        "description": "Fetch trending cryptocurrency coins from CoinGecko.",
        "context": "crypto",
        "keywords": [
            "trending", "trending coins", "crypto trends", "popular coins", "hot coins",
            "top coins", "trending crypto", "top cryptocurrencies", "what's trending",
            "crypto trending"
        ]
    },
    "fetch_token_price": {
        "function": utils.fetch_token_price,
        "description": "Fetch the current price of a specific token from CoinGecko.",
        "context": "crypto",
        "keywords": [
            "price", "token price", "crypto price", "current price", "how much is",
            "usd value", "crypto value", "price of", "cost of", "price check",
            "token value", "value in usd", "check price"
        ]
    },
    "fetch_fear_greed_index": {
        "function": utils.fetch_fear_greed_index,
        "description": "Fetch the current Fear & Greed Index for cryptocurrency sentiment.",
        "context": "sentiment",
        "keywords": [
            "fear", "greed", "fear and greed", "market sentiment", "crypto sentiment",
            "sentiment index", "fng index", "market fear", "market greed", "market emotions",
            "crypto fear", "crypto greed", "current sentiment"
        ]
    }
}
def match_function_by_keywords(query: str):
    query = query.lower()
    for func_name, details in FUNCTION_REGISTRY.items():  # Unpack key-value pairs from FUNCTION_REGISTRY
        if details.get("intent") is None:  # Only consider functions without a clear intent
            for keyword in details.get("keywords", []):
                if keyword.lower() in query:
                    print(f"Matched keyword: {keyword}, Function: {details['function'].__name__}")
                    return details["function"]
    print("No matching keyword found.")
    return None
#endregion Function Handling & Registry
