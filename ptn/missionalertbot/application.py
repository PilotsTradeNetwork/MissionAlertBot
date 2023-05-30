"""
The Python script that starts the bot.

"""

# import libraries
import asyncio
import os

# import bot Cogs
from ptn.missionalertbot.botcommands.GeneralCommands import GeneralCommands
from ptn.missionalertbot.botcommands.CCOCommands import CCOCommands
from ptn.missionalertbot.botcommands.CTeamCommands import CTeamCommands
from ptn.missionalertbot.botcommands.DatabaseInteraction import DatabaseInteraction

# import database build function
from ptn.missionalertbot.database.database import build_database_on_startup, build_directory_structure_on_startup

# import bot object, token, production status
from ptn.missionalertbot.constants import bot, TOKEN, _production, DATA_DIR

print(f"Data dir is {DATA_DIR} from {os.path.join(os.getcwd(), 'ptn', 'missionalertbot', DATA_DIR, '.env')}")
print(f"Token is {TOKEN}")

print(f'MissionAlertBot is connecting against production: {_production}.')


def run():
    asyncio.run(missionalertbot())


async def missionalertbot():
    async with bot:
        build_directory_structure_on_startup()
        build_database_on_startup()
        await bot.add_cog(GeneralCommands(bot))
        await bot.add_cog(CCOCommands(bot))
        await bot.add_cog(CTeamCommands(bot))
        await bot.add_cog(DatabaseInteraction(bot))
        await bot.start(TOKEN)


if __name__ == '__main__':
    """
    If running via `python ptn/missionalertbot/appliction.py
    """
    run()
