import re
import sys
import openai
import random
from telegram import Update
from telegram.ext import CallbackContext

## Import the needed modules from the config folder
# {config.py} - Environment variables and global variables used in the bot
# {firebase.py} - Firebase configuration and database initialization
# {utils.py} - Utility functions and variables used in the bot
from scripts import config, logger, utils

sys.stdout = logger.StdoutWrapper()  # Redirect stdout
sys.stderr = logger.StderrWrapper()  # Redirect stderr

# Configuration variables for easy adjustment
MAX_INTENT_TOKENS = 10  # Maximum tokens for intent classification
MAX_RESPONSE_TOKENS = 50  # Maximum tokens for OpenAI response
TEMPERATURE = 0.7  # AI creativity level
TRIGGER_PHRASES = ["hey sypher", "hey sypherbot"]  # Trigger phrases
OPENAI_MODEL = "gpt-3.5-turbo"  # OpenAI model to use
PROMPT_PATTERN = r"^(hey sypher(?:bot)?)\s*(.*)$"  # Matches "hey sypher" or "hey sypherbot" at the start

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

INTENT_MAP = {
    "group_name": {
        "classification": "group_name",
        "response_template": "This group's name is '{group_username}'."
    },
    "website": {
        "classification": "website",
        "response_template": "This group's website is: {group_website_url}."
    },
    "group_link": {
        "classification": "group_link",
        "response_template": "You can join this group using the link: {group_link}."
    },
    "owner": {
        "classification": "owner",
        "response_template": "The owner of this group is {owner_username}."
    },
    "group_token": {
        "classification": "group_token",
        "response_template": "This group's token is '{token_symbol}' on the '{token_chain}' blockchain."
    },
    "contract_address": {
        "classification": "contract_address",
        "response_template": "The contract address for '{token_name}' is {token_contract_address}."
    },
    "total_supply": {
        "classification": "total_supply",
        "response_template": "The total supply of '{token_name}' is {token_total_supply}."
    },
    "buy": {
        "classification": "buy",
        "response_template": "You can buy '{token_name}' here: https://app.uniswap.org/swap?outputCurrency={contract_address}"
    }
}

def initialize_openai():
    openai.api_key = config.OPENAI_API_KEY
    print("OpenAI API initialized.")

def prompt_handler(update: Update, context: CallbackContext) -> None:
    message_text = update.message.text.strip()
    match = re.match(PROMPT_PATTERN, message_text, re.IGNORECASE)

    if not match:
        return
    
    dictionary = utils.fetch_group_dictionary(update, context)

    if not dictionary: # You'll always find a dictionary with default values, so if not found, error occurred
        print(f"No dictionary found for chat {update.message.chat_id}. Proceeding without group-specific context.")
        return
    
    query = match.group(2).strip()  # Extract the query (everything after the trigger phrase)
    if not query:
        update.message.reply_text("What's up?")
        return
    
    print(f"Received 'hey sypher' with a query from a user in chat {update.message.chat_id}")

    generic_intent = determine_generic_intent(query) # Use the LLM to classify the intent
    if generic_intent:  # If intent is classified, fetch the corresponding generic response
        response = fetch_generic_response(generic_intent, dictionary)
        if response:
            update.message.reply_text(response)
            print(f"Generic response sent for intent '{generic_intent}' in chat {update.message.chat_id}: {response}")
            return
    
    # No generic response found, proceed with AI response

    messages = [
        {"role": "system", "content": (
            "You are SypherBot, an intelligent and friendly assistant. "
            "Answer questions clearly and concisely. Ensure responses are complete but never exceed the token limit. "
            "Avoid unnecessary detail unless specifically requested. Be engaging and professional, and use humor sparingly when discussing memes."
            "Ensure your response is never cut off mid-thought."
        )},
        {"role": "user", "content": query}
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
        update.message.reply_text("Sorry, I couldn't process your request. Try again later.")
        print(f"OpenAI API error: {e}")
        return

    if response_message:  # Send the response back to the user
        update.message.reply_text(response_message)
        print(f"Response in chat {update.message.chat_id}: {response_message}")
    else:
        error_reply = random.choice(ERROR_REPLIES)
        update.message.reply_text(error_reply)

def determine_generic_intent(query: str) -> str | None:
    classifications = ", ".join(f"'{intent}'" for intent in INTENT_MAP.keys())
    classification_prompt = (
        f"Classify the following query into one of these intents: {classifications}, or 'unknown'. "
        "Return only the intent name. Here is the query:\n\n"
        f"{query}"
    )
    
    try:
        intent_response = openai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": "You are a classifier for intents based on user queries."},
                      {"role": "user", "content": classification_prompt}],
            max_tokens=MAX_INTENT_TOKENS,  # Very low token usage, since the response is short
            temperature=0.0  # Deterministic response
        )
        intent = intent_response.choices[0].message.content.strip().lower()
        return intent if intent in [
            "group_token", "contract_address", "group_name", 
            "website", "group_link", "total_supply", "owner"
        ] else None
    except Exception as e:
        print(f"Error classifying intent: {e}")
        return None

def fetch_generic_response(intent: str, dictionary: dict) -> str | None:
    if intent in INTENT_MAP:
        template = INTENT_MAP[intent]["response_template"]
        try:
            return template.format(**dictionary)
        except KeyError as e:
            print(f"Missing key in dictionary for intent '{intent}': {e}")
            return None
    return None

def main():
    initialize_openai()

if __name__ == "__main__":
    main()