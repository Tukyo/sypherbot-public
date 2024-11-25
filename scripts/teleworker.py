from telethon.sync import TelegramClient
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch

from scripts import config

def log_deleted(chat_id):
    client = TelegramClient("bot", config.API_ID, config.API_HASH) # Create the client instance
    print(f"Checking group {chat_id} for deleted accounts...")

    try:
        client.start(bot_token=config.TELEGRAM_TOKEN) # Start the client explicitly with the bot token
        group_entity = client.get_entity(int(chat_id))
        offset = 0
        limit = 100
        deleted_users = []

        while True:
            participants = client(GetParticipantsRequest(
                group_entity,
                ChannelParticipantsSearch(""),
                offset,
                limit,
                hash=0
            ))
            if not participants.users:
                break

            for user in participants.users:
                if user.deleted:
                    deleted_users.append(f"Deleted account found: {user.id}")

            offset += len(participants.users)

        print(f"Found {len(deleted_users)} deleted accounts in group {chat_id}") # Output results for subprocess
        for user in deleted_users:
            print(user)

    finally:
        client.disconnect() # Ensure the client disconnects after use