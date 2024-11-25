from telethon.sync import TelegramClient
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch
from scripts import config

def log_deleted(chat_id):
    client = TelegramClient("bot", config.API_ID, config.API_HASH)  # Create the client instance
    deleted_users = []

    try:
        client.start(bot_token=config.TELEGRAM_TOKEN)  # Start the client explicitly with the bot token
        group_entity = client.get_entity(int(chat_id))
        offset = 0
        limit = 100

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
                    deleted_users.append(user.id)  # Append only the user ID

            offset += len(participants.users)

    finally:
        client.disconnect()  # Ensure the client disconnects after use

    for user_id in deleted_users:
        print(user_id)
