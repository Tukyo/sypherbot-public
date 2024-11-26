import sys
import openai
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

## Import the needed modules from the config folder
# {config.py} - Environment variables and global variables used in the bot
# {firebase.py} - Firebase configuration and database initialization
# {utils.py} - Utility functions and variables used in the bot
from scripts import config
from scripts import utils
from scripts import firebase
from scripts import logger

sys.stdout = logger.StdoutWrapper()  # Redirect stdout
sys.stderr = logger.StderrWrapper()  # Redirect stderr

def main():
    openai_api_key = config.OPENAI_API_KEY

    if openai_api_key:
        print("OpenAI API key loaded!")
    else:
        print("OpenAI API key not found...")

if __name__ == "__main__":
    main()