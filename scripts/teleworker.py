import sys
from telethon.sync import TelegramClient
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch

from scripts import config

if len(sys.argv) != 2:
    print("Usage: python telethon_worker.py <chat_id>")
    sys.exit(1)

chat_id = sys.argv[1]

async def log_deleted(chat_id):
    async with TelegramClient("bot", config.API_ID, config.API_HASH).start(bot_token=config.TELEGRAM_TOKEN) as client:
        group_entity = await client.get_entity(int(chat_id))
        offset = 0
        limit = 100
        deleted_users = []

        while True:
            participants = await client(GetParticipantsRequest(
                group_entity,
                ChannelParticipantsSearch(""),
                offset,
                limit,
            ))
            if not participants.users:
                break

            for user in participants.users:
                if user.deleted:
                    deleted_users.append(f"Deleted account found: {user.id}")

            offset += len(participants.users)

        # Output results for subprocess
        print(f"Found {len(deleted_users)} deleted accounts.")
        for user in deleted_users:
            print(user)

# Run the async function
import asyncio
asyncio.run(log_deleted(chat_id))
