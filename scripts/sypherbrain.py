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

    intent = determine_intent(query, dictionary)
    print(f"Determined intent: {intent}")

    messages = [
        {"role": "system", "content": (
            "You are SypherBot, an intelligent assistant for Telegram groups."
            "Use the provided group context and intent to understand and respond accurately to user queries."
            "Your users mostly consist of degen crypto traders"
            "Provide concise, contextually relevant responses. Keep responses under 40 words unless more detail is explicitly requested."
            "Avoid unnecessary detail unless specifically requested. Be engaging and professional, and use humor sparingly when discussing memes."
            "Ensure your response is never cut off mid-thought."
        )},
        {"role": "user", "content": f"Context: {dictionary}\n\nQuery: {query}\n\nIntent: {intent}"}
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

def determine_intent(query: str, group_dictionary: dict) -> str | None:
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
        return intent
    except Exception as e:
        print(f"Error determining intent: {e}")
        return "unknown"

def main():
    initialize_openai()

if __name__ == "__main__":
    main()