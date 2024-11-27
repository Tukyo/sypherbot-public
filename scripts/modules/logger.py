import sys
import pytz
from telegram import Bot
from threading import Timer
from datetime import datetime

from modules import config

#region LOGGING
bot = Bot(token=config.TELEGRAM_TOKEN)
LOG_CHAT = "-1002087245760"
LOGGING_TIMEZONE = "America/Los_Angeles"
MAX_TELEGRAM_MESSAGE_LENGTH = 4096
LOG_INTERVAL = 30
class TelegramLogger: # Batch all logs and send to the logging channel for debugging in telegram
    def __init__(self):
        self.original_stdout = sys.stdout  # Keep a reference to the original stdout
        self.original_stderr = sys.stderr # Keep a reference to the original stderr
        self.log_buffer = []  # Buffer to store logs
        self.flush_interval = LOG_INTERVAL  # Send logs every interval
        self.timer = Timer(self.flush_interval, self.flush_logs)  # Timer for batching
        self.timer.start()

    def write(self, message, from_stderr=False):
        if "RuntimeError: cannot schedule new futures after shutdown" in message: # Later TODO: Fix this error
            return
        if message.strip():  # Avoid sending empty lines
            pst_timezone = pytz.timezone(LOGGING_TIMEZONE)
            timestamp = datetime.now(pst_timezone).strftime("%Y-%m-%d %I:%M:%S %p PST")
            formatted_message = f"{timestamp} - {message.strip()}"
            if from_stderr: # Only append @Tukyowave for stderr messages
                formatted_message += " @Tukyowave"
            self.log_buffer.append(formatted_message)
        
        if from_stderr: # Write to the original stream
            self.original_stderr.write(message)
        else:
            self.original_stdout.write(message)

    def flush(self):
        if self.original_stdout:
            self.original_stdout.flush()
        if self.original_stderr:
            self.original_stderr.flush()

    def flush_logs(self):
        if self.log_buffer:
            combined_message = "\n\n".join(self.log_buffer)
            while combined_message:
                chunk = combined_message[:MAX_TELEGRAM_MESSAGE_LENGTH]
                bot.send_message(chat_id=LOG_CHAT, text=chunk)
                combined_message = combined_message[MAX_TELEGRAM_MESSAGE_LENGTH:]
            self.log_buffer = []

        self.timer = Timer(self.flush_interval, self.flush_logs) # Restart the timer
        self.timer.start()

    def stop(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None

logger = TelegramLogger()

class StdoutWrapper:
    def write(self, message):
        logger.write(message, from_stderr=False)

    def flush(self):
        logger.flush()

class StderrWrapper:
    def write(self, message):
        logger.write(message, from_stderr=True)

    def flush(self):
        logger.flush()
#endregion LOGGING