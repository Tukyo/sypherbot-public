import re
import sys
import openai
import random
from telegram import Update
from telegram.ext import CallbackContext, Updater, MessageHandler, Filters, BaseFilter

## Import the needed modules from the config folder
# {config.py} - Environment variables and global variables used in the bot
# {firebase.py} - Firebase configuration and database initialization
# {utils.py} - Utility functions and variables used in the bot
from scripts import config, logger

sys.stdout = logger.StdoutWrapper()  # Redirect stdout
sys.stderr = logger.StderrWrapper()  # Redirect stderr

# Configuration variables for easy adjustment
MAX_TOKENS = 100  # Maximum tokens for OpenAI response
TEMPERATURE = 0.5  # AI creativity level
TRIGGER_PHRASES = ["hey sypher", "hey sypherbot"]  # Trigger phrases
OPENAI_MODEL = "gpt-3.5-turbo-instruct"  # OpenAI model to use
PROMPT_PATTERN = r"^(hey sypher(?:bot)?)\s*(.*)$"  # Matches "hey sypher" or "hey sypherbot" at the start
class RegexFilter(BaseFilter):
    def __init__(self, pattern):
        self.pattern = pattern

    def __call__(self, message): # Check if the message text matches the regex pattern
        return bool(re.match(self.pattern, message.text.strip(), re.IGNORECASE))

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
    
    query = match.group(2).strip() # Extract the query (everything after the trigger phrase)
    if not query:
        update.message.reply_text("Please provide a query after 'hey sypher' or 'hey sypherbot'.")
        return
    
    print(f"Received 'hey sypher' from a user in chat {update.message.chat_id}")

    try: # Call OpenAI API
        openai_response = openai.Completion.create(
            model=OPENAI_MODEL,
            prompt=query,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )
        response_text = openai_response.choices[0].text.strip()
    except Exception as e:
        update.message.reply_text("Sorry, I couldn't process your request. Try again later.")
        print(f"OpenAI API error: {e}")
        return

    if response_text: # Send the response back to the user
        update.message.reply_text(response_text)
    else:
        error_reply = random.choice(ERROR_REPLIES)
        update.message.reply_text(error_reply)

PROMPT_REGEX_FILTER = RegexFilter(PROMPT_PATTERN)
SYPHERBRAIN_PROMPT_HANDLER = MessageHandler(PROMPT_REGEX_FILTER, prompt_handler)

def main():
    initialize_openai()

if __name__ == "__main__":
    main()