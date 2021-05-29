# MissionAlertBot.py
# Discord bot to help PTN Carrier Owners post trade missions to Discord and Reddit
# By Charles Tosh 17 March 2021
# Additional contributions by Alexander Leidinger
# Discord Developer Portal: https://discord.com/developers/applications/822146046934384640/information
# Git repo: https://github.com/PilotsTradeNetwork/MissionAlertBot
import ast
import copy
from itertools import islice
from math import ceil

from PIL import Image, ImageFont, ImageDraw
import os
import sys
import discord
import sqlite3
import asyncpraw
import asyncio
import shutil
from discord.errors import HTTPException, InvalidArgument, Forbidden, NotFound
from discord.ext import commands
from discord_slash import SlashCommand, SlashContext
from datetime import datetime
from datetime import timezone
from dotenv import load_dotenv
from dateutil.relativedelta import relativedelta
import constants
import threading
#
#                       INIT STUFF
#

# Ast will parse a value into a python type, but if you try to give a boolean its going to get into problems. Just use
# a string and be consistent.
from CarrierData import CarrierData
from Commodity import Commodity
from MissionData import MissionData

_production = ast.literal_eval(os.environ.get('PTN_MISSION_ALERT_SERVICE', 'False'))

# We need some locks to we wait on the DB queries
carrier_db_lock = threading.Lock()
mission_db_lock = threading.Lock()

# setting some variables, you can toggle between production and test by setting an env variable flag now,
# PTN-MISSION-ALERT-SERVICE
conf = constants.get_constant(_production)

bot_guild_id = int(conf['BOT_GUILD'])

flair_mission_start = conf['MISSION_START']
flair_mission_stop = conf['MISSION_STOP']

# channel IDs
trade_alerts_id = conf['TRADE_ALERTS_ID']
bot_spam_id = conf['BOT_SPAM_CHANNEL']
to_subreddit = conf['SUB_REDDIT']

# Get the discord token from the local .env file. Deliberately not hosted in the repo or Discord takes the bot down
# because the keys are exposed. DO NOT HOST IN THE REPO. Seriously do not do it ...
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN_PROD') if _production else os.getenv('DISCORD_TOKEN_TESTING')

# create reddit instance
reddit = asyncpraw.Reddit('bot1')

# connect to sqlite carrier database
carriers_conn = sqlite3.connect('carriers.db')
carriers_conn.row_factory = sqlite3.Row
carrier_db = carriers_conn.cursor()

# connect to sqlite missions database
missions_conn = sqlite3.connect('missions.db')
missions_conn.row_factory = sqlite3.Row
mission_db = missions_conn.cursor()

#
#                       DATABASE STUFF
#

# TEST DEBUG FLAG ONLY
debugging_carrier_edit = False

print('MissionAlertBot starting')
print(f'Configuring to run against: {"Production" if _production else "Testing"} env.')


# create carrier record if necessary (only needed on first run)
def check_database_table_exists(table_name, database):
    """
    Checks whether a carrier exists in the database already.

    :param str table_name:  The database string name to create.
    :param sqlite.Connection.cursor database: The database to connect againt.
    :returns: A boolean state, True if it exists, else False
    :rtype: bool
    """
    database.execute('''SELECT count(name) FROM sqlite_master WHERE TYPE = 'table' AND name = '{}' '''.format(
        table_name))
    return bool(database.fetchone()[0])


print('Starting up - checking carriers database if it exists or not')
if not check_database_table_exists('carriers', carrier_db):
    print('Carriers database missing - creating it now')

    if os.path.exists(os.path.join(os.getcwd(), 'db_sql', 'carriers_dump.sql')):
        # recreate from backup file
        print('Recreating database from backup ...')
        with open(os.path.join(os.getcwd(), 'db_sql', 'carriers_dump.sql')) as f:
            sql_script = f.read()
            carrier_db.executescript(sql_script)

        # print('Loaded the following data: ')
        # carrier_db.execute('''SELECT * from carriers ''')
        # for e in carrier_db.fetchall():
        #     print(f'\t {CarrierData(e)}')
    else:
        # Create a new version
        print('No backup found - Creating empty database')
        carrier_db.execute('''
            CREATE TABLE carriers( 
                p_ID INTEGER PRIMARY KEY AUTOINCREMENT,
                shortname TEXT NOT NULL UNIQUE, 
                longname TEXT NOT NULL, 
                cid TEXT NOT NULL, 
                discordchannel TEXT NOT NULL,
                channelid INT,
                roleid INT,
                ownerid INT
            ) 
        ''')
else:
    print('Carrier database exists, do nothing')

print('Starting up - checking missions database if it exists or not')
# create missions db if necessary
if not check_database_table_exists('missions', mission_db):
    print('Mission database missing - creating it now')

    if os.path.exists(os.path.join(os.getcwd(), 'db_sql', 'missions_dump.sql')):
        # recreate from backup file
        print('Recreating mission db database from backup ...')
        with open(os.path.join(os.getcwd(), 'db_sql', 'missions_dump.sql')) as f:
            sql_script = f.read()
            mission_db.executescript(sql_script)

        # print('Loaded the following data: ')
        # mission_db.execute('''SELECT * from missions ''')
        # for e in mission_db.fetchall():
        #     print(f'\t {MissionData(e)}')

    else:
        # Create a new version
        print('No backup found - Creating empty database')
        mission_db.execute('''
            CREATE TABLE missions(
                "carrier"	TEXT NOT NULL UNIQUE,
                "cid"	TEXT,
                "channelid"	INTEGER,
                "commodity"	TEXT,
                "missiontype"	TEXT,
                "system"	TEXT NOT NULL,
                "station"	TEXT,
                "profit"	INTEGER,
                "pad"	TEXT,
                "demand"    TEXT,
                "rp_text"	TEXT,
                "reddit_post_id"	TEXT,
                "reddit_post_url"	TEXT,
                "reddit_comment_id"	TEXT,
                "reddit_comment_url"	TEXT,
                "discord_alert_id"	INT
            )
        ''')
else:
    print('Mission database exists, do nothing')


def dump_database_test(database_name):
    """
    Dumps the database object to a .sql text file while backing up the database. Used just to get something we can
    recreate the database from.  This will only store the last state and should periodically be committed to the repo
    from the bot.

    :param str database_name: The DB name to connect against.
    :returns: None
    :raises ValueError: if the db name is unknown
    """
    # We only have 2 databases today, carriers and missions, though this could really just be 2 tables in a single
    # database at some stage.

    if database_name == 'missions':
        connection = missions_conn
    elif database_name == 'carriers':
        connection = carriers_conn
    else:
        raise ValueError(f'Unknown DB dump handling for: {database_name}')

    with open(f'db_sql/{database_name}_dump.sql', 'w') as f:
        for line in connection.iterdump():
            f.write(line)


# function to backup carrier database
def backup_database(database_name):
    """
    Creates a backup of the requested database into .backup/db_name.datetimestamp.db

    :param str database_name: The database name to back up
    :rtype: None
    """
    dt_file_string = get_formatted_date_string()[1]
    if not os.path.exists(os.path.join(os.getcwd(), 'backup')):
        # make sure the backup folder exists first
        os.mkdir(os.path.join(os.getcwd(), 'backup'))

    shutil.copy(f'{database_name}.db', f'backup/{database_name}.{dt_file_string}.db')
    print(f'Backed up {database_name}.db at {dt_file_string}')
    dump_database_test(database_name)


# function to add carrier, being sure to correct case
def add_carrier_to_database(short_name, long_name, carrier_id, channel, channel_id, roleid, owner_id):
    """
    Inserts a carrier's details into the database.

    :param str short_name: The carriers shortname reference
    :param str long_name: The carriers full name description
    :param str carrier_id: The carriers ID value from the game
    :param str discord_channel: The carriers discord channel
    :param int channel_id: The discord channel ID for the carrier
    :returns: None
    """
    carrier_db_lock.acquire()
    try:
        carrier_db.execute(''' INSERT INTO carriers VALUES(NULL, ?, ?, ?, ?, ?, ?, ?) ''',
                           (short_name.lower(), long_name.upper(), carrier_id.upper(), channel, channel_id, roleid, owner_id))
        carriers_conn.commit()
    finally:
        carrier_db_lock.release()
        # copy the blank bitmap to the new carrier's name to serve until unique image uploaded
        shutil.copy('bitmap.png', f'images/{short_name.lower()}.png')


# function to remove a carrier
def delete_carrier_from_db(p_id):
    carrier = find_carrier_from_pid(p_id)
    try:
        carrier_db_lock.acquire()
        carrier_db.execute(f"DELETE FROM carriers WHERE p_ID = {p_id}")
        carriers_conn.commit()
    finally:
        carrier_db_lock.release()
    # archive the removed carrier's image by appending date and time of deletion to it
    try:
        shutil.move(f'images/{carrier.carrier_short_name}.png',
                    f'images/old/{carrier.carrier_short_name}.{get_formatted_date_string()[1]}.png')
    except:
        errormsg = 'Unable to backup image file, perhaps it never existed?'
        print(errormsg)
        return errormsg

    return


# function to remove all carriers, not currently used by any bot command
def _delete_all_from_database(database):
    """
    Removes all the entries from the database.

    :returns: None
    """
    carrier_db.execute(f"DELETE FROM {database}")
    carriers_conn.commit()


# function to search for a carrier by longname
def find_carrier_from_long_name(find_long_name):
    """
    Finds any carriers matching a long name

    :param str find_long_name: A short name of the carrier.
    :returns: CarrierData object for the exact match
    :rtype: CarrierData
    """
    # TODO: This needs to check an exact not a `LIKE`
    carrier_db.execute(
        f"SELECT * FROM carriers WHERE longname LIKE (?)",
        (f'%{find_long_name}%',))
    carrier_data = CarrierData(carrier_db.fetchone())
    print(f"FC {carrier_data.pid} is {carrier_data.carrier_long_name} {carrier_data.carrier_identifier} called by "
          f"shortname {carrier_data.carrier_short_name} with channel <#{carrier_data.channel_id}> "
          f"and owner {carrier_data.ownerid} called from find_carrier_from_long_name.")

    return carrier_data


def find_carrier_with_role_id(roleid):
    """
    Returns all carriers matching the roleid

    :param int roleid: The role id  to match
    :returns: A list of carrier data objects
    :rtype: list[CarrierData]
    """
    carrier_db.execute(
        f"SELECT * FROM carriers WHERE roleid LIKE (?)", (f'%{roleid}%',)
    )
    carrier_data = [CarrierData(carrier)  for carrier in carrier_db.fetchall() ]
    for carrier in carrier_data:
        print(f"FC {carrier.pid} is {carrier.carrier_long_name} {carrier.carrier_identifier} called by "
              f"shortname {carrier.carrier_short_name} with channel <#{carrier.channel_id}> "
              f"and owner {carrier.ownerid} and role id: {carrier.roleid} called from find_carrier_with_role_id.")

    return carrier_data


# function to search for a carrier by shortname
def find_carrier_from_short_name(find_short_name):
    """
    Finds any carriers matching a short name

    :param str find_short_name: A short name of the carrier.
    :returns: List of CarrierData
    :rtype: list[CarrierData]
    """
    carrier_db.execute(f"SELECT * FROM carriers WHERE shortname LIKE (?)", (f'%{find_short_name}%',))
    carriers = [CarrierData(carrier) for carrier in carrier_db.fetchall()]
    for carrier_data in carriers:
        print(f"FC {carrier_data.pid} is {carrier_data.carrier_long_name} {carrier_data.carrier_identifier} called by "
              f"shortname {carrier_data.carrier_short_name} with channel <#{carrier_data.channel_id}> called from "
              f"find_carrier_from_short_name.")

    return carriers


# function to search for a carrier by p_ID
def find_carrier_from_pid(db_id):
    carrier_db.execute(f"SELECT * FROM carriers WHERE p_ID = {db_id}")
    carrier_data = CarrierData(carrier_db.fetchone())
    print(f"FC {carrier_data.pid} is {carrier_data.carrier_long_name} {carrier_data.carrier_identifier} called by "
          f"shortname {carrier_data.carrier_short_name} with channel <#{carrier_data.channel_id}> called "
          f"from find_carrier_from_pid.")
    return carrier_data


# function to search for a commodity by name or partial name
async def find_commodity(lookfor, ctx):
    # TODO: Where do we get set up this database? it is searching for things, but what is the source of the data, do
    #  we update it periodically?

    print(f'Searching for commodity against match "{lookfor}" requested by {ctx.author}')

    carrier_db.execute(
        f"SELECT * FROM commodities WHERE commodity LIKE (?)",
        (f'%{lookfor}%',))

    commodities = [Commodity(commodity) for commodity in carrier_db.fetchall()]
    commodity = None
    if not commodities:
        print('No commodities found for request')
        # Did not find anything, short-circuit out of the next block
        return None
    elif len(commodities) == 1:
        print('Single commodity found, returning that directly')
        # if only 1 match, just assign it directly
        commodity = commodities[0]
    elif len(commodities) > 3:
        # If we ever get into a scenario where more than 3 commodities can be found with the same search directly, then
        # we need to revisit this limit
        print(f'More than 3 commodities found for: "{lookfor}", {ctx.author} needs to search better.')
        await ctx.send(f'Please narrow down your commodity search, we found {len(commodities)} matches for your '
                       f'input choice: "{lookfor}"')
        return None  # Just return None here and let the calling method figure out what is needed to happen
    else:
        print(f'Between 1 and 3 commodities found for: "{lookfor}", asking {ctx.author} which they want.')
        # The database runs a partial match, in the case we have more than 1 ask the user which they want.
        # here we have less than 3, but more than 1 match
        embed = discord.Embed(title=f"Multiple commodities found for input: {lookfor}", color=constants.EMBED_COLOUR_OK)

        count = 0
        response = None  # just in case we try to do something before it is assigned, give it a value of None
        for commodity in commodities:
            count += 1
            embed.add_field(name=f'{count}', value=f"{commodity.name}", inline=True)

        embed.set_footer(text='Please select the commodity with 1, 2 or 3')

        def check(message):
            return message.author == ctx.author and message.channel == ctx.channel and \
                   len(message.content) == 1 and message.content.lower() in ["1", "2", "3"]

        message_confirm = await ctx.send(embed=embed)
        try:
            # Wait on the user input, this might be better by using a reaction?
            response = await bot.wait_for("message", check=check, timeout=15)
            print(f'{ctx.author} responded with: "{response.content}", type: {type(response.content)}.')
            index = int(response.content) - 1  # Users count from 1, computers count from 0
            commodity = commodities[index]
        except asyncio.TimeoutError:
            print('User failed to respond in time')
            pass
        await message_confirm.delete()
        if response:
            await response.delete()
    if commodity:
        print(f"Commodity {commodity.name} avgsell {commodity.average_sell} avgbuy {commodity.average_buy} "
              f"maxsell {commodity.max_sell} minbuy {commodity.min_buy} maxprofit {commodity.max_profit}")
    return commodity

#
#                       IMAGE GEN STUFF
#


# defining fonts for pillow use
reg_font = ImageFont.truetype('font/Exo/static/Exo-Light.ttf', 16)
name_font = ImageFont.truetype('font/Exo/static/Exo-ExtraBold.ttf', 34)
title_font = ImageFont.truetype('font/Exo/static/Exo-ExtraBold.ttf', 26)
normal_font = ImageFont.truetype('font/Exo/static/Exo-Medium.ttf', 18)
field_font = ImageFont.truetype('font/Exo/static/Exo-Light.ttf', 18)


# get date and time
def get_formatted_date_string():
    """
    Returns a tuple of the Elite Dangerous Time and the current real world time.

    :rtype: tuple
    """
    dt_now = datetime.now(tz=timezone.utc)
    # elite_time_string is the Elite Dangerous time this is running in, today plus 1286 years
    elite_time_string = (dt_now + relativedelta(years=1286)).strftime("%d %B %Y %H:%M %Z")
    current_time_string = dt_now.strftime("%Y%m%d %H%M%S")
    return elite_time_string, current_time_string


# function to create image for loading
def create_carrier_mission_image(carrier_data, commodity, system, station, profit, pads, demand, mission_type):
    my_image = Image.open(f"images/{carrier_data.carrier_short_name}.png")
    image_editable = ImageDraw.Draw(my_image)
    mission_action = 'LOADING' if mission_type == 'load' else 'UNLOADING'
    image_editable.text((27, 150), "PILOTS TRADE NETWORK", (255, 255, 255), font=title_font)
    image_editable.text((27, 180), f"CARRIER {mission_action} MISSION", (191, 53, 57), font=title_font)
    image_editable.text((27, 235), "FLEET CARRIER " + carrier_data.carrier_identifier, (0, 217, 255), font=reg_font)
    image_editable.text((27, 250), carrier_data.carrier_long_name, (0, 217, 255), font=name_font)
    image_editable.text((27, 320), "COMMODITY:", (255, 255, 255), font=field_font)
    image_editable.text((150, 320), commodity.name.upper(), (255, 255, 255), font=normal_font)
    image_editable.text((27, 360), "SYSTEM:", (255, 255, 255), font=field_font)
    image_editable.text((150, 360), system.upper(), (255, 255, 255), font=normal_font)
    image_editable.text((27, 400), "STATION:", (255, 255, 255), font=field_font)
    image_editable.text((150, 400), f"{station.upper()} ({pads.upper()} pads)", (255, 255, 255), font=normal_font)
    image_editable.text((27, 440), "PROFIT:", (255, 255, 255), font=field_font)
    image_editable.text((150, 440), f"{profit}k per unit, {demand} units", (255, 255, 255), font=normal_font)
    my_image.save("result.png")


#
#                       TEXT GEN FUNCTIONS
#

def txt_create_discord(carrier_data, mission_type, commodity, station, system, profit, pads, demand, eta_text):
    discord_text = f"<#{carrier_data.channel_id}> {'load' if mission_type == 'load' else 'unload'}ing " \
                   f"{commodity.name} " \
                   f"{'from' if mission_type == 'load' else 'to'} **{station.upper()}** station in system " \
                   f"**{system.upper()}** : {profit}k per unit profit : "\
                   f"{demand} {'demand' if mission_type == 'load' else 'supply'} : {pads.upper()}-pads" \
                   f".{eta_text}"
    return discord_text


def txt_create_reddit_title(carrier_data):
    reddit_title = f"P.T.N. News - Trade mission - {carrier_data.carrier_long_name} {carrier_data.carrier_identifier}" \
                   f" - {get_formatted_date_string()[0]}"
    return reddit_title


def txt_create_reddit_body(carrier_data, mission_type, commodity, station, system, profit, pads, demand, eta_text):

    if mission_type == 'load':
        reddit_body = (
            f"    INCOMING WIDEBAND TRANSMISSION: P.T.N. CARRIER LOADING MISSION IN PROGRESS\n\n**BUY FROM**: station "
            f"**{station.upper()}** ({pads.upper()}-pads) in system **{system.upper()}**\n\n**COMMODITY**: "
            f"{commodity.name}\n\n&#x200B;\n\n**SELL TO**: Fleet Carrier **{carrier_data.carrier_long_name} "
            f"{carrier_data.carrier_identifier}{eta_text}**\n\n**PROFIT**: {profit}k/unit : {demand} "
            f"demand\n\n\n\n[Join us on Discord]({constants.REDDIT_DISCORD_LINK_URL}) for "
            f"mission updates and discussion, channel **#{carrier_data.discord_channel}**.")
    else:
        reddit_body = (
            f"    INCOMING WIDEBAND TRANSMISSION: P.T.N. CARRIER UNLOADING MISSION IN PROGRESS\n\n**BUY FROM**: Fleet "
            f"Carrier **{carrier_data.carrier_long_name} {carrier_data.carrier_identifier}{eta_text}**"
            f"\n\n**COMMODITY**: {commodity.name}\n\n&#x200B;\n\n**SELL TO**: station "
            f"**{station.upper()}** ({pads.upper()}-pads) in system **{system.upper()}**\n\n**PROFIT**: {profit}k/unit "
            f": {demand} supply\n\n\n\n[Join us on Discord]({constants.REDDIT_DISCORD_LINK_URL}) for mission updates"
            f" and discussion, channel **#{carrier_data.discord_channel}**.")
    return reddit_body

#
#                       OTHER
#


# function to stop and quit
def user_exit():
    sys.exit("User requested exit.")


#
#                       BOT STUFF STARTS HERE
#

bot = commands.Bot(command_prefix='m.', intents=discord.Intents.all())
slash = SlashCommand(bot, sync_commands=True)

@bot.event
async def on_message(message):
    # do some extra stuff here
    global debugging_carrier_edit
    if debugging_carrier_edit:
        print(f'Carrier Edit on going. this message is: {message} from {message.author} in channel: {message.channel} repr:{repr(message)}')

    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')


#
#                       LOAD/UNLOAD COMMANDS
#

# load commands
@bot.command(name='load', help='Generate details for a loading mission and optionally broadcast to Discord.\n'
                               '\n'
                               '<lookname> is the carrier\'s shortname.\n'
                               '<commshort> is the commodity shortened to anything that will still successfully search,'
                               ' e.g. agro\n'
                               '<system> should be in quotes\n'
                               '<station> should also be in quotes\n'
                               '<profit> is a number of thousands without the k\n'
                               '<pads> is the largest pad size available (M for outposts, L for everything else)\n'
                               '<demand> is how much your carrier is buying\n'
                               'Optional: a number in minds for the carrier\'s ETA\n'
                               '\n'
                               'Case is automatically corrected for all inputs.')
@commands.has_role('Carrier Owner')
async def load(ctx, carrier_name, commodity_short_name, system, station, profit, pads, demand, eta=None):
    rp = False
    mission_type = 'load'
    await gen_mission(ctx, carrier_name, commodity_short_name, system, station, profit, pads, demand, rp, mission_type,
                      eta)


@bot.command(name="loadrp", help='Same as load command but prompts user to enter roleplay text\n'
                                 'This is added to the Reddit comment as as a quote above the mission details\n'
                                 'and sent to the carrier\'s Discord channel in quote format if those options are '
                                 'chosen')
@commands.has_role('Carrier Owner')
async def loadrp(ctx, carrier_name, commodity_short_name, system, station, profit, pads, demand, eta=None):
    rp = True
    mission_type = 'load'
    await gen_mission(ctx, carrier_name, commodity_short_name, system, station, profit, pads, demand, rp, mission_type,
                      eta)


# unload commands
@bot.command(name='unload', help='Generate details for an unloading mission.\n'
                                 '\n'
                                 '<lookname> is the carrier\'s shortname.\n'
                                 '<commshort> is the commodity shortened to anything that will still successfully '
                                 'search, e.g. agro\n'
                                 '<system> should be in quotes\n'
                                 '<station> should also be in quotes\n'
                                 '<profit> is a number of thousands without the k\n'
                                 '<pads> is the largest pad size available (M for outposts, L for everything else)\n'
                                 '<demand> is how much your carrier is buying\n'
                                 'Optional: a number in minds for the carrier\'s <ETA>\n'
                                 '\n'
                                 'Case is automatically corrected for all inputs.')
@commands.has_role('Carrier Owner')
async def unload(ctx, carrier_name, commodity_short_name, system, station, profit, pads, demand, eta=None):
    rp = False
    mission_type = 'unload'
    await gen_mission(ctx, carrier_name, commodity_short_name, system, station, profit, pads, demand, rp, mission_type,
                      eta)


@bot.command(name="unloadrp", help='Same as unload command but prompts user to enter roleplay text\n'
                                   'This is added to the Reddit comment as as a quote above the mission details\n'
                                   'and sent to the carrier\'s Discord channel in quote format if those options are '
                                   'chosen')
@commands.has_role('Carrier Owner')
async def unloadrp(ctx, carrier_name, commodity_short_name, system, station, profit, pads, demand, eta=None):
    rp = True
    mission_type = 'unload'
    await gen_mission(ctx, carrier_name, commodity_short_name, system, station, profit, pads, demand, rp, mission_type,
                      eta)


# mission generator called by loading/unloading commands
async def gen_mission(ctx, carrier_name, commodity_short_name, system, station, profit, pads, demand, rp, mission_type,
                      eta):
    # Check we are in the designated mission channel, if not go no farther.
    mission_gen_channel = bot.get_channel(conf['MISSION_CHANNEL'])
    current_channel = ctx.channel

    print(f'Mission generation type: {mission_type} with RP: {rp}, requested by {ctx.author}. Request triggered from '
          f'channel {current_channel}.')

    if current_channel != mission_gen_channel:
        # problem, wrong channel, no progress
        return await ctx.send(f'Sorry, you can only run this command out of: {mission_gen_channel}.')

    # TODO: This method is way too long, break it up into logical steps.

    # None-strings, should hopefully not break the database. If it does revert these to 'NULL'
    rp_text = None
    reddit_post_id = None
    reddit_post_url = None
    reddit_comment_id = None
    reddit_comment_url = None
    discord_alert_id = None

    eta_text = f" (ETA {eta} minutes)" if eta else ""

    embed = discord.Embed(title="Generating and fetching mission alerts...", color=constants.EMBED_COLOUR_QU)
    message_gen = await ctx.send(embed=embed)

    mission_db.execute(f'''SELECT * FROM missions WHERE carrier LIKE (?)''', ('%' + carrier_name + '%',))
    mission_data = MissionData(mission_db.fetchone())
    if mission_data:
        embed = discord.Embed(title="Error",
                              description=f"{mission_data.carrier_name} is already on a mission, please "
                                          f"use **m.done** to mark it complete before starting a new mission.",
                              color=constants.EMBED_COLOUR_ERROR)
        await ctx.send(embed=embed)
        return  # We want to stop here, so go exit out

    def check_confirm(message):
        # use all to verify that all the characters in the message content are present in the allowed list (dtrx).
        # Anything outwith this grouping will cause all to fail. Use set to throw away any duplicate objects.
        # not sure if the msg.content can ever be None, but lets gate it anyway
        return message.content and message.author == ctx.author and message.channel == ctx.channel and \
               all(character in 'drtnx' for character in set(message.content.lower()))

    def check_rp(message):
        return message.author == ctx.author and message.channel == ctx.channel

    if rp:
        embed = discord.Embed(title="Input roleplay text",
                              description="Roleplay text is sent in quote style like this:\n\n> This is a quote!"
                                          "\n\nYou can use all regular Markdown formatting. If the 'send to Discord' "
                                          "option is chosen, your quote will be broadcast to your carrier's channel "
                                          "following its mission image. If the 'send to Reddit' option is chosen, "
                                          "the quote is inserted above the mission details in the top-level comment.",
                              color=constants.EMBED_COLOUR_RP)
        message_rp = await ctx.send(embed=embed)

        try:

            message_rp_text = await bot.wait_for("message", check=check_rp, timeout=120)
            rp_text = message_rp_text.content

        except asyncio.TimeoutError:
            await ctx.send("**Mission generation cancelled (waiting too long for user input)**")
            await message_rp.delete()
            return

    # generate the mission elements
    commodity_data = await find_commodity(commodity_short_name, ctx)
    if not commodity_data:
        raise ValueError('Missing commodity data')
    carrier_data = find_carrier_from_long_name(carrier_name)

    create_carrier_mission_image(carrier_data, commodity_data, system, station, profit, pads, demand, mission_type)
    discord_text = txt_create_discord(carrier_data, mission_type, commodity_data, station, system, profit, pads,
                                      demand, eta_text)
    reddit_title = txt_create_reddit_title(carrier_data)
    reddit_body = txt_create_reddit_body(carrier_data, mission_type, commodity_data, station, system, profit, pads,
                                         demand, eta_text)

    # check they're happy with output and offer to send
    embed = discord.Embed(title=f"Mission pending for {carrier_data.carrier_long_name}{eta_text}",
                          color=constants.EMBED_COLOUR_OK)
    embed.add_field(name="Mission type", value=f"{mission_type.title()}ing", inline=True)
    embed.add_field(name="Commodity", value=f"{demand} of {commodity_data.name.title()} at {profit}k/unit", inline=True)
    embed.add_field(name="Location",
                    value=f"{station.upper()} station ({pads.upper()}-pads) in system {system.upper()}", inline=True)
    if rp:
        await message_rp.delete()
        await message_rp_text.delete()
        embed.add_field(name="Roleplay text", value=rp_text, inline=False)
    message_pending = await ctx.send(embed=embed)
    await message_gen.delete()

    embed = discord.Embed(title="Where would you like to send the alert?",
                          description="(**d**)iscord, (**r**)eddit, (**t**)ext for copy/pasting or (**x**) to cancel\n"
                          "Use (**n**) to also notify your crew.",
                          color=constants.EMBED_COLOUR_QU)
    embed.set_footer(text="Enter all that apply, e.g. **drn** will send alerts to Discord and Reddit and notify your crew.")
    message_confirm = await ctx.send(embed=embed)

    try:
        msg = await bot.wait_for("message", check=check_confirm, timeout=30)

        if "x" in msg.content.lower():
            # immediately stop if there's an x anywhere in the message, even if there are other proper inputs
            message_cancelled = await ctx.send("**Mission creation cancelled.**")
            await msg.delete()
            await message_confirm.delete()
            return

        if "t" in msg.content.lower():

            embed = discord.Embed(title="Trade Alert (Discord)", description=f"`{discord_text}`",
                                  color=constants.EMBED_COLOUR_DISCORD)
            await ctx.send(embed=embed)
            if rp:
                embed = discord.Embed(title="Roleplay Text (Discord)", description=f"`> {rp_text}`",
                                      color=constants.EMBED_COLOUR_DISCORD)
                await ctx.send(embed=embed)

            embed = discord.Embed(title="Reddit Post Title", description=f"`{reddit_title}`",
                                  color=constants.EMBED_COLOUR_REDDIT)
            await ctx.send(embed=embed)
            if rp:
                embed = discord.Embed(title="Reddit Post Body - PASTE INTO MARKDOWN MODE",
                                      description=f"```> {rp_text}\n\n{reddit_body}```",
                                      color=constants.EMBED_COLOUR_REDDIT)
            else:
                embed = discord.Embed(title="Reddit Post Body - PASTE INTO MARKDOWN MODE",
                                      description=f"```{reddit_body}```", color=constants.EMBED_COLOUR_REDDIT)
            embed.set_footer(text="**REMEMBER TO USE MARKDOWN MODE WHEN PASTING TEXT TO REDDIT.**")
            await ctx.send(embed=embed)
            await ctx.send(file=discord.File('result.png'))
            embed = discord.Embed(title=f"Alert Generation Complete for {carrier_data.carrier_long_name}",
                                  description="Paste Reddit content into **MARKDOWN MODE** in the editor. You can swap "
                                              "back to Fancy Pants afterwards and make any changes/additions or embed "
                                              "the image.\n\nBest practice for Reddit is an image post with a top level"
                                              " comment that contains the text version of the advert. This ensures the "
                                              "image displays with highest possible compatibility across platforms and "
                                              "apps. When mission complete, flag the post as *Spoiler* to prevent "
                                              "image showing and add a comment to inform.",
                                  color=constants.EMBED_COLOUR_OK)
            await ctx.send(embed=embed)

        if "d" in msg.content.lower():
            message_send = await ctx.send("**Sending to Discord...**")

            # send trade alert to trade alerts channel
            channel = bot.get_channel(trade_alerts_id)

            if mission_type == 'load':
                embed = discord.Embed(description=discord_text, color=constants.EMBED_COLOUR_LOADING)
            else:
                embed = discord.Embed(description=discord_text, color=constants.EMBED_COLOUR_UNLOADING)

            trade_alert_msg = await channel.send(embed=embed)
            discord_alert_id = trade_alert_msg.id

            channel = bot.get_channel(carrier_data.channel_id)

            file = discord.File("result.png", filename="image.png")

            embed_colour = constants.EMBED_COLOUR_LOADING if mission_type == 'load' \
                else constants.EMBED_COLOUR_UNLOADING
            embed = discord.Embed(title="P.T.N TRADE MISSION STARTING",
                                  description=f"> {rp_text}" if rp else "", color=embed_colour)

            embed.add_field(name="Destination", value=f"Station: {station.upper()}\nSystem: {system.upper()}", inline=True)
            if eta: embed.add_field(name="ETA", value=f"{eta} minutes", inline=True)
        
            embed.set_image(url="attachment://image.png")
            embed.set_footer(
                text="m.complete will mark this mission complete\nm.ission will display info to channel\nm.issions "
                     "will list trade missions for all carriers\nUse /crew to join or leave this carrier's crew")
            await channel.send(file=file, embed=embed)

            embed = discord.Embed(title=f"Discord trade alerts sent for {carrier_data.carrier_long_name}",
                                  description=f"Check <#{trade_alerts_id}> for trade alert and "
                                              f"<#{carrier_data.channel_id}> for image.",
                                  color=constants.EMBED_COLOUR_DISCORD)
            await ctx.send(embed=embed)
            await message_send.delete()

        if "r" in msg.content.lower():
            message_send = await ctx.send("**Sending to Reddit...**")

            # post to reddit
            subreddit = await reddit.subreddit(to_subreddit)
            submission = await subreddit.submit_image(reddit_title, image_path="result.png",
                                                      flair_id=flair_mission_start)
            reddit_post_url = submission.permalink
            reddit_post_id = submission.id
            if rp:
                comment = await submission.reply(f"> {rp_text}\n\n&#x200B;\n\n{reddit_body}")
            else:
                comment = await submission.reply(reddit_body)
            reddit_comment_url = comment.permalink
            reddit_comment_id = comment.id
            embed = discord.Embed(title=f"Reddit trade alert sent for {carrier_data.carrier_long_name}",
                                  description=f"https://www.reddit.com{reddit_post_url}",
                                  color=constants.EMBED_COLOUR_REDDIT)
            await ctx.send(embed=embed)
            await message_send.delete()
            embed = discord.Embed(title=f"{carrier_data.carrier_long_name} REQUIRES YOUR UPDOOTS",
                                  description=f"https://www.reddit.com{reddit_post_url}",
                                  color=constants.EMBED_COLOUR_REDDIT)
            channel = bot.get_channel(conf['CHANNEL_UPVOTES'])
            await channel.send(embed=embed)

        if "n" in msg.content.lower():

            # get carrier's channel object

            channel = bot.get_channel(carrier_data.channel_id)

            await channel.send(f"<@&{carrier_data.roleid}>: {discord_text}")

            embed = discord.Embed(title=f"Crew notification sent for {carrier_data.carrier_long_name}",
                        description=f"Pinged <@&{carrier_data.roleid}> in <#{carrier_data.channel_id}>",
                        color=constants.EMBED_COLOUR_DISCORD)
            await ctx.send(embed=embed)

    except asyncio.TimeoutError:
        await ctx.send("**Mission not generated or broadcast (no valid response from user).**")
        return

    # now clear up by deleting the prompt message and user response
    await msg.delete()
    await message_confirm.delete()
    await mission_add(ctx, carrier_data, commodity_data, mission_type, system, station, profit, pads, demand,
                      rp_text, reddit_post_id, reddit_post_url, reddit_comment_id, reddit_comment_url, discord_alert_id)
    await mission_generation_complete(ctx, carrier_data, message_pending, eta_text)


#
#                       MISSION DB
#
# add mission to DB, called from mission generator
async def mission_add(ctx, carrier_data, commodity_data, mission_type, system, station, profit, pads, demand,
                      rp_text, reddit_post_id, reddit_post_url, reddit_comment_id, reddit_comment_url, discord_alert_id):
    backup_database('missions')  # backup the missions database before going any further

    mission_db.execute(''' INSERT INTO missions VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ''', (
        carrier_data.carrier_long_name, carrier_data.carrier_identifier, carrier_data.channel_id,
        commodity_data.name.title(), mission_type.lower(), system.title(), station.title(), profit, pads.upper(),
        demand, rp_text, reddit_post_id, reddit_post_url, reddit_comment_id, reddit_comment_url, discord_alert_id
    ))
    missions_conn.commit()

async def mission_generation_complete(ctx, carrier_data, message_pending, eta_text):

    # fetch data we just committed back

    mission_db.execute('''SELECT * FROM missions WHERE carrier LIKE (?)''',
                        ('%' + carrier_data.carrier_long_name + '%',))
    print('DB command ran, go fetch the result')
    mission_data = MissionData(mission_db.fetchone())
    print(f'Found mission data: {mission_data}')

    # return result to user

    embed_colour = constants.EMBED_COLOUR_LOADING if mission_data.mission_type == 'load' else \
        constants.EMBED_COLOUR_UNLOADING

    mission_description = ''
    if mission_data.rp_text and mission_data.rp_text != 'NULL':
        mission_description = f"> {mission_data.rp_text}"

    embed = discord.Embed(title=f"{mission_data.mission_type.upper()}ING {mission_data.carrier_name} ({mission_data.carrier_identifier}) {eta_text}",
                            description=mission_description, color=embed_colour)

    embed = _mission_summary_embed(mission_data, embed)

    embed.set_footer(text="You can use m.done <carrier> to mark the mission complete.")

    await ctx.send(embed=embed)
    await message_pending.delete()


# list active carrier trade mission from DB
@bot.command(name='ission', help="Show carrier's active trade mission.")
async def ission(ctx):
    # take a note channel ID
    msg_ctx_id = ctx.channel.id
    # look for a match for the channel ID in the carrier DB
    carrier_db.execute(f"SELECT * FROM carriers WHERE "
                       f"channelid = {msg_ctx_id}")
    carrier_data = CarrierData(carrier_db.fetchone())
    print(f'Mission command carrier_data: {carrier_data}')
    if not carrier_data.channel_id:
        # if there's no channel match, return an error
        embed = discord.Embed(description="Try again in the carrier's channel.", color=constants.EMBED_COLOUR_QU)
        await ctx.send(embed=embed)
        return
    else:
        print(f'Searching if carrier ({carrier_data.carrier_long_name}) has active mission.')
        # now look to see if the carrier is on an active mission
        mission_db.execute('''SELECT * FROM missions WHERE carrier LIKE (?)''',
                           ('%' + carrier_data.carrier_long_name + '%',))
        print('DB command ran, go fetch the result')
        mission_data = MissionData(mission_db.fetchone())
        print(f'Found mission data: {mission_data}')

        if not mission_data:
            # if there's no result, return an error
            embed = discord.Embed(description=f"**{carrier_data.carrier_long_name}** doesn't seem to be on a trade"
                                              f" mission right now.",
                                  color=constants.EMBED_COLOUR_OK)
            await ctx.send(embed=embed)
        else:
            # user is in correct channel and carrier is on a mission, so show the current trade mission for selected
            # carrier
            embed_colour = constants.EMBED_COLOUR_LOADING if mission_data.mission_type == 'load' else \
                constants.EMBED_COLOUR_UNLOADING

            mission_description = ''
            if mission_data.rp_text and mission_data.rp_text != 'NULL':
                mission_description = f"> {mission_data.rp_text}"

            embed = discord.Embed(title=f"{mission_data.mission_type.upper()}ING {mission_data.carrier_name} ({mission_data.carrier_identifier})",
                                  description=mission_description, color=embed_colour)

            embed = _mission_summary_embed(mission_data, embed)

            embed.set_footer(text="You can use m.complete if the mission is complete.")

            await ctx.send(embed=embed)
            return

def _mission_summary_embed(mission_data, embed):
    embed.add_field(name="System", value=f"{mission_data.system.upper()}", inline=True)
    embed.add_field(name="Station", value=f"{mission_data.station.upper()} ({mission_data.pad_size}-pads)",
                    inline=True)
    embed.add_field(name="Commodity", value=f"{mission_data.commodity.upper()}", inline=True)
    embed.add_field(name="Quantity and profit",
                    value=f"{mission_data.demand} units at {mission_data.profit}k profit per unit", inline=True)
    return embed

# list all active carrier trade missions from DB
@bot.command(name='issions', help='List all active trade missions.')
async def issions(ctx):

    print(f'User {ctx.author} asked for all active missions.')

    co_role = discord.utils.get(ctx.guild.roles, name='Carrier Owner')
    print(f'Check is user has role: "{co_role}"')
    print(f'User has roles: {ctx.author.roles}')

    print(f'Generating full unloading mission list requested by: {ctx.author}')
    mission_db.execute('''SELECT * FROM missions WHERE missiontype="unload";''')
    unload_records = [MissionData(mission_data) for mission_data in mission_db.fetchall()]

    mission_db.execute('''SELECT * FROM missions WHERE missiontype="load";''')
    print(f'Generating full loading mission list requested by: {ctx.author}')
    load_records = [MissionData(mission_data) for mission_data in mission_db.fetchall()]

    # If used by a non-carrier owner, link the total mission count and point to trade alerts.
    if co_role not in ctx.author.roles:
        print(f'User {ctx.author} does not have the required CO role, sending them to trade alerts.')
        # Sorry user, you need to go to trade alerts.
        trade_channel = bot.get_channel(trade_alerts_id)
        number_of_missions = len(load_records) + len(unload_records)

        description_text = f'For full details of all current trade missions follow the link to <#{trade_channel.id}>'
        if not number_of_missions:
            description_text = f'Currently no active missions listed in: <#{trade_channel.id}>'

        embed = discord.Embed(
            title=f"{number_of_missions} P.T.N Fleet Carrier missions in progress:",
            description=description_text,
            color=constants.EMBED_COLOUR_LOADING
        )

        return await ctx.send(embed=embed)

    print(f'User {ctx.author} has the required CO role, dumping all the missions here.')
    embed = discord.Embed(title=f"{len(load_records)} P.T.N Fleet Carrier LOADING missions in progress:",
                          color=constants.EMBED_COLOUR_LOADING)
    embed = _format_missions_embedd(load_records, embed)
    await ctx.send(embed=embed)

    embed = discord.Embed(title=f"{len(unload_records)} P.T.N Fleet Carrier UNLOADING missions in progress:",
                          color=constants.EMBED_COLOUR_UNLOADING)
    embed = _format_missions_embedd(unload_records, embed)
    await ctx.send(embed=embed)


def _format_missions_embedd(mission_data_list, embed):
    """
    Loop over a set of records and add certain fields to the message.
    """
    for mission_data in mission_data_list:
        embed.add_field(name=f"{mission_data.carrier_name}", value=f"<#{mission_data.channel_id}>", inline=True)
        embed.add_field(name=f"{mission_data.commodity}",
                        value=f"{mission_data.demand} at {mission_data.profit}k/unit", inline=True)
        embed.add_field(name=f"{mission_data.system.upper()} system",
                        value=f"{mission_data.station} ({mission_data.pad_size}-pads)", inline=True)
    return embed


# CO command to quickly mark mission as complete, optionally send some RP text
@bot.command(name='done', help='Marks a mission as complete for specified carrier.\n'
                               'Deletes trade alert in Discord and sends messages to carrier channel and reddit if '
                               'appropriate.\n\nAnything put in quotes after the carrier name will be treated as a '
                               'quote to be sent along with the completion notice. This can be used for RP if desired.')
@commands.has_role('Carrier Owner')
async def done(ctx, carrier_name, rp=None):

    # Check we are in the designated mission channel, if not go no farther.
    mission_gen_channel = bot.get_channel(conf['MISSION_CHANNEL'])
    current_channel = ctx.channel

    print(f'Request received from {ctx.author} to mark the mission of {carrier_name} as done from channel: '
          f'{current_channel}')

    if current_channel != mission_gen_channel:
        # problem, wrong channel, no progress
        return await ctx.send(f'Sorry, you can only run this command out of: <#{mission_gen_channel.id}>.')

    mission_db.execute(f'''SELECT * FROM missions WHERE carrier LIKE (?)''', ('%' + carrier_name + '%',))
    mission_data = MissionData(mission_db.fetchone())
    if not mission_data:
        embed = discord.Embed(
            description=f"**ERROR**: no trade missions found for carriers matching \"**{carrier_name}\"**.",
            color=constants.EMBED_COLOUR_ERROR)
        await ctx.send(embed=embed)

    else:
        backup_database('missions')  # backup the missions database before going any further

        # fill in some info for messages
        desc_msg = f"> {rp}\n\n" if rp else ""

        # delete Discord trade alert
        if mission_data.discord_alert_id and mission_data.discord_alert_id != 'NULL':
            try:  # try in case it's already been deleted, which doesn't matter to us in the slightest but we don't
                # want it messing up the rest of the function
                discord_alert_id = mission_data.discord_alert_id
                channel = bot.get_channel(trade_alerts_id)
                msg = await channel.fetch_message(discord_alert_id)
                await msg.delete()
            except:
                await ctx.send("Looks like this mission alert was already deleted. Not to worry.")

            # send Discord carrier channel updates
            channel = bot.get_channel(mission_data.channel_id)
            embed = discord.Embed(title=f"{mission_data.carrier_name} MISSION COMPLETE", description=f"{desc_msg}",
                                  color=constants.EMBED_COLOUR_OK)
            await channel.send(embed=embed)

        # add comment to Reddit post
        if mission_data.reddit_post_id and mission_data.reddit_post_id != 'NULL':
            try:  # try in case Reddit is down
                reddit_post_id = mission_data.reddit_post_id
                await reddit.subreddit(to_subreddit)
                submission = await reddit.submission(reddit_post_id)
                await submission.reply(
                    f"    INCOMING WIDEBAND TRANSMISSION: P.T.N. CARRIER MISSION UPDATE\n\n**"
                    f"{mission_data.carrier_name}** mission complete. o7 CMDRs!\n\n{desc_msg}")

                # mark original post as spoiler, change its flair
                await submission.flair.select(flair_mission_stop)
                await submission.mod.spoiler()
            except:
                await ctx.send("Failed updating Reddit :(")

        # delete mission entry from db
        mission_db.execute(f'''DELETE FROM missions WHERE carrier LIKE (?)''', ('%' + carrier_name + '%',))
        missions_conn.commit()

        embed = discord.Embed(title=f"Mission complete for {mission_data.carrier_name}",
                              description=f"{desc_msg}Updated any sent alerts and removed from mission list.",
                              color=constants.EMBED_COLOUR_OK)
        await ctx.send(embed=embed)
        return


# a command for users to mark a carrier mission complete from within the carrier channel
@bot.command(name='complete', help="Use in a carrier's channel to mark the current trade mission complete.")
async def complete(ctx):

    # take a note of user and channel ID
    msg_ctx_id = ctx.channel.id
    msg_usr_id = ctx.author.id
    # look for a match for the channel ID in the carrier DB
    carrier_db.execute(f"SELECT * FROM carriers WHERE channelid = {msg_ctx_id}")
    carrier_data = CarrierData(carrier_db.fetchone())
    if not carrier_data:
        # if there's no channel match, return an error
        embed = discord.Embed(description="**You need to be in a carrier's channel to mark its mission as complete.**",
                              color=constants.EMBED_COLOUR_ERROR)
        await ctx.send(embed=embed)
        return
    else:
        backup_database('missions')  # backup the missions database before going any further

        # now look to see if the carrier is on an active mission
        mission_db.execute('''SELECT * FROM missions WHERE carrier LIKE (?)''', ('%' + carrier_data.carrier_long_name + '%',))
        mission_data = MissionData(mission_db.fetchone())
        if not mission_data:
            # if there's no result, return an error
            embed = discord.Embed(description=f"**{carrier_data.carrier_long_name} doesn't seem to be on a trade "
                                              f"mission right now.**",
                                  color=constants.EMBED_COLOUR_ERROR)
            await ctx.send(embed=embed)

        else:
            # user is in correct channel and carrier is on a mission, so check whether user is sure they want to proceed
            embed = discord.Embed(
                description=f"Please confirm that **{mission_data.carrier_name}** has been fully "
                            f"{mission_data.mission_type}ed : **y** / **n**",
                color=constants.EMBED_COLOUR_QU)
            # embed.set_footer(text="For other issues (e.g. station price changes) please @ the Carrier Owner
            # directly.")
            await ctx.send(embed=embed)

            def check(message):
                return message.author == ctx.author and message.channel == ctx.channel and \
                       message.content.lower() in ["y", "n"]

            try:
                msg = await bot.wait_for("message", check=check, timeout=30)
                if msg.content.lower() == "n":
                    embed = discord.Embed(description="OK, mission will remain listed as in-progress.",
                                          color=constants.EMBED_COLOUR_OK)
                    await ctx.send(embed=embed)
                    return
                elif msg.content.lower() == "y":
                    embed = discord.Embed(title=f"{mission_data.carrier_name} MISSION COMPLETE",
                                          description=f"<@{msg_usr_id}> reports mission complete!",
                                          color=constants.EMBED_COLOUR_OK)
                    await ctx.send(embed=embed)
                    await ctx.send(f"Notifying carrier owner: <@{carrier_data.ownerid}>")
                    # now we need to go do all the mission cleanup stuff

                    # delete Discord trade alert
                    if mission_data.discord_alert_id and mission_data.discord_alert_id != 'NULL':
                        try:
                            channel = bot.get_channel(trade_alerts_id)
                            msg = await channel.fetch_message(mission_data.discord_alert_id)
                            await msg.delete()
                        except:
                            print(f"Looks like this mission alert for {mission_data.carrier_name} was already deleted"
                                  f" by someone else")

                    # add comment to Reddit post
                    if mission_data.reddit_post_id and mission_data.reddit_post_id != 'NULL':
                        try:
                            await reddit.subreddit(to_subreddit)
                            submission = await reddit.submission(mission_data.reddit_post_id)
                            await submission.reply(
                                f"    INCOMING WIDEBAND TRANSMISSION: P.T.N. CARRIER MISSION UPDATE\n\n"
                                f"**{mission_data.carrier_name}** mission complete. o7 CMDRs!\n\n\n\n*"
                                f"Reported on PTN Discord by {ctx.author.display_name}*")

                            # mark original post as spoiler, change its flair
                            await submission.flair.select(flair_mission_stop)
                            await submission.mod.spoiler()
                        except:
                            print(f"Reddit post failed to update for {mission_data.carrier_name}")

                    # delete mission entry from db
                    mission_db.execute(f'''DELETE FROM missions WHERE carrier LIKE (?)''',
                                       ('%' + mission_data.carrier_name + '%',))
                    missions_conn.commit()

            except asyncio.TimeoutError:
                embed = discord.Embed(description="No response, mission will remain listed as in-progress.")
                await ctx.send(embed=embed)


#
#                       UTILITY COMMANDS
#

# backup databases
@bot.command(name='backup', help='Backs up the carrier and mission databases.')
@commands.has_role('Admin')
async def backup(ctx):

    # make sure we are in the right channel
    bot_command_channel = bot.get_channel(conf['BOT_COMMAND_CHANNEL'])
    current_channel = ctx.channel
    if current_channel != bot_command_channel:
        # problem, wrong channel, no progress
        return await ctx.send(f'Sorry, you can only run this command out of: {bot_command_channel}.')

    print(f"{ctx.author} requested a manual DB backup")
    backup_database('missions') 
    backup_database('carriers') 
    await ctx.send("Database backup complete.")


# join a carrier's crew
@slash.slash(name="crew", guild_ids=[bot_guild_id],
             description="Use in a carrier's channel to join or leave that carrier's crew.")
async def _crew(ctx: SlashContext):
    print(f"{ctx.author} used /crew in {ctx.channel}")

    # note channel ID
    msg_ctx_id = ctx.channel.id

    # define bot spam channel so we can notify
    channel = bot.get_channel(bot_spam_id)

    # look for a match for the channel ID in the carrier DB
    carrier_db.execute(f"SELECT * FROM carriers WHERE "
                       f"channelid = {msg_ctx_id}")
    carrier_data = CarrierData(carrier_db.fetchone())
    print(f'Crew command carrier_data: {carrier_data}')
    if not carrier_data.channel_id:
        # if there's no channel match, return an error
        embed = discord.Embed(description="Try again in a carrier's channel.", color=constants.EMBED_COLOUR_ERROR)
        await ctx.send(embed=embed, hidden=True)
        return
    else:
        # we're in a carrier's channel, now we define its crew role from db
        print(f"/crew used in channel for {carrier_data.carrier_long_name}")
        crew_role = discord.utils.get(ctx.guild.roles, id=carrier_data.roleid)

        # check if role exists
        if not crew_role: 
            await ctx.send("Sorry, I couldn't find a crew for this carrier. Please alert an Admin.", hidden=True)
            await channel.send(f"**ERROR**: {ctx.author} tried to use **/crew** in <#{ctx.channel.id}> but received an error (role does not exist).")
            print(f"No crew role found matching {ctx.channel}")
            return

        # check if user has this role
        print(f'Check whether user has role: "{crew_role}"')
        print(f'User has roles: {ctx.author.roles}')
        if crew_role not in ctx.author.roles:
            # they don't so give it to them
            await ctx.author.add_roles(crew_role)
            embed = discord.Embed(title=f"You've joined the crew for {carrier_data.carrier_long_name}!", description="You'll receive notifications about this carrier's activity. You can leave the crew at any time by using **/crew** again in this channel.", color=constants.EMBED_COLOUR_QU)
            await ctx.send(embed=embed, hidden=True)
            await channel.send(f"{ctx.author} joined the crew in <#{ctx.channel.id}>")
        else:
            # they do so take it from them
            await ctx.author.remove_roles(crew_role)
            embed = discord.Embed(title=f"You've left the crew for {carrier_data.carrier_long_name}.", description="You'll no longer receive notifications about this carrier's activity. You can rejoin the crew at any time by using **/crew** again in this channel.", color=constants.EMBED_COLOUR_OK)
            await ctx.send(embed=embed, hidden=True)
            await channel.send(f"{ctx.author} left the crew in <#{ctx.channel.id}>")


@slash.slash(name="crews", guild_ids=[bot_guild_id],
             description="Use to find out which carrier crews you're signed up to.")
async def _crews(ctx: SlashContext):
    print(f'{ctx.author} wants to find all of the crews they are part of.')
    # Find all the crews the user is a part of
    author = ctx.author
    crew_roles = [role for role in author.roles if role.name.lower().startswith('crew')]
    print(f'{ctx.author} has the following crew roles: {crew_roles}')

    if crew_roles:
        embed = discord.Embed(description=f"You are signed up for {len(crew_roles)} crews.",
                              color=constants.EMBED_COLOUR_ERROR)
        for crew in crew_roles:
            carrier_list = find_carrier_with_role_id(crew.id)
            if len(carrier_list) > 1:
                carrier_channels = ''
                for carrier in carrier_list:
                    carrier_channels += f'<#{carrier.carrier_long_name}>, '

                if carrier_channels.endswith(', '):
                    carrier_channels = carrier_channels[:-2:]

            else:
                carrier_channels = f'<#{carrier_list[0].channel_id}>'

            embed.add_field(name=f'{crew.name}', value=f'Channels: {carrier_channels}', inline=True)
    else:
        embed = discord.Embed(description=f"You aren't signed up for any crews! Use **/crew** in a carrier channel to "
                                          f"sign up.", color=constants.EMBED_COLOUR_ERROR)
    await ctx.send(embed=embed, hidden=True)
    pass


# list FCs
@bot.command(name='carrier_list', help='List all Fleet Carriers in the database. This times out after 60 seconds')
async def carrier_list(ctx):

    print(f'Carrier List requested by user: {ctx.author}')

    carrier_db.execute(f"SELECT * FROM carriers")
    carriers = [CarrierData(carrier) for carrier in carrier_db.fetchall()]

    def chunk(chunk_list, max_size=10):
        """
        Take an input list, and an expected max_size.

        :returns: A chunked list that is yielded back to the caller
        :rtype: iterator
        """
        for i in range(0, len(chunk_list), max_size):
            yield chunk_list[i:i + max_size]

    def validate_response(react, user):
        return user == ctx.author and str(react.emoji) in ["◀️", "▶️"]
        # This makes sure nobody except the command sender can interact with the "menu"

    # TODO: should pages just be a list of embed_fields we want to add?
    pages = [page for page in chunk(carriers)]

    max_pages = len(pages)
    current_page = 1

    embed = discord.Embed(title=f"{len(carriers)} Registered Fleet Carriers Page:#{current_page} of {max_pages}")
    count = 0   # Track the overall count for all carriers
    # Go populate page 0 by default
    for carrier in pages[0]:
        count += 1
        embed.add_field(name=f"{count}: {carrier.carrier_long_name} ({carrier.carrier_identifier})",
                        value=f"<#{carrier.channel_id}>", inline=False)
    # Now go send it and wait on a reaction
    message = await ctx.send(embed=embed)

    # From page 0 we can only go forwards
    await message.add_reaction("▶️")

    # 60 seconds time out gets raised by Asyncio
    while True:
        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=60, check=validate_response)
            if str(reaction.emoji) == "▶️" and current_page != max_pages:

                print(f'{ctx.author} requested to go forward a page.')
                current_page += 1   # Forward a page
                new_embed = discord.Embed(title=f"{len(carriers)} Registered Fleet Carriers Page:{current_page}")
                for carrier in pages[current_page-1]:
                    # Page -1 as humans think page 1, 2, but python thinks 0, 1, 2
                    count += 1
                    new_embed.add_field(name=f"{count}: {carrier.carrier_long_name} ({carrier.carrier_identifier})",
                                        value=f"<#{carrier.channel_id}>", inline=False)

                await message.edit(embed=new_embed)

                # Ok now we can go back, check if we can also go forwards still
                if current_page == max_pages:
                    await message.clear_reaction("▶️")

                await message.remove_reaction(reaction, user)
                await message.add_reaction("◀️")

            elif str(reaction.emoji) == "◀️" and current_page > 1:
                print(f'{ctx.author} requested to go back a page.')
                current_page -= 1   # Go back a page

                new_embed = discord.Embed(title=f"{len(carriers)} Registered Fleet Carriers Page:{current_page}")
                # Start by counting back however many carriers are in the current page, minus the new page, that way
                # when we start a 3rd page we don't end up in problems
                count -= len(pages[current_page - 1])
                count -= len(pages[current_page])

                for carrier in pages[current_page - 1]:
                    # Page -1 as humans think page 1, 2, but python thinks 0, 1, 2
                    count += 1
                    new_embed.add_field(name=f"{count}: {carrier.carrier_long_name} ({carrier.carrier_identifier})",
                                        value=f"<#{carrier.channel_id}>", inline=False)

                await message.edit(embed=new_embed)
                # Ok now we can go forwards, check if we can also go backwards still
                if current_page == 1:
                    await message.clear_reaction("◀️")

                await message.remove_reaction(reaction, user)
                await message.add_reaction("▶️")
            else:
                # It should be impossible to hit this part, but lets gate it just in case.
                print(f'HAL9000 error: {ctx.author} ended in a random state while trying to handle: {reaction.emoji} '
                      f'and on page: {current_page}.')
                # HAl-9000 error response.
                error_embed = discord.Embed(title=f"I'm sorry {ctx.author}, I'm afraid I can't do that.")
                await message.edit(embed=error_embed)
                await message.remove_reaction(reaction, user)

        except asyncio.TimeoutError:
            print(f'Timeout hit during carrier request by: {ctx.author}')
            await ctx.send(f'Closed the active carrier list request from: {ctx.author} due to no input in 60 seconds.')
            await message.delete()
            break


# add FC to database
@bot.command(name='carrier_add', help='Add a Fleet Carrier to the database:\n'
                                      '\n'
                                      '<shortname> should be a short one-word string with no special characters\n'
                                      '<longname> is the carrier\'s full name including P.T.N. etc - surround this '
                                      'with quotes.\n'
                                      '<carrier_id> is the carrier\'s unique identifier in the format ABC-XYZ\n'
                                      '<owner_id> is the owner\'s Discord ID')
@commands.has_role('Admin')
async def carrier_add(ctx, short_name, long_name, carrier_id, owner_id):

    # make sure we are in the right channel
    bot_command_channel = bot.get_channel(conf['BOT_COMMAND_CHANNEL'])
    current_channel = ctx.channel
    if current_channel != bot_command_channel:
        # problem, wrong channel, no progress
        return await ctx.send(f'Sorry, you can only run this command out of: {bot_command_channel}.')

    # Only add to the carrier DB if it does not exist, if it does exist then the user should not be adding it.
    carrier_data = find_carrier_from_long_name(long_name)
    if carrier_data:
        # Carrier exists already, go skip it.
        print(f'Request recieved from {ctx.author} to add a carrier that already exists in the database ({long_name}).')

        embed = discord.Embed(title="Fleet carrier already exists, use m.carrier_edit to change its details.",
                              description=f"Carrier data matched for {long_name}", color=constants.EMBED_COLOUR_OK)
        embed = _add_common_embed_fields(embed, carrier_data)
        return await ctx.send(embed=embed)

    backup_database('carriers')  # backup the carriers database before going any further

    # TODO: If command fails at any stage, reset roles and channels to previous state before exiting

    # first create the new carrier's channel
    # check whether channel already exists by sanitising the carrier's name input to match discord channel format,
    # otherwise create one

    stripped_name = long_name.replace(' ', '-').replace('.', '')
    channel = discord.utils.get(ctx.guild.channels, name=stripped_name.lower())

    if channel:
        await ctx.send("Channel creation skipped: a channel already exists with this carrier's name")
        print(f"Found existing {channel}")
    else:
        category = discord.utils.get(ctx.guild.categories, name="Drydock")
        channel = await ctx.guild.create_text_channel(stripped_name.lower(), category=category)
        print(f"Created {channel}")

    print(f'Channels: {ctx.guild.channels}')

    if not channel:
        raise EnvironmentError(f'Could not create carrier channel {stripped_name.lower()}')

    # find carrier owner as a user object

    try:
        owner = await bot.fetch_user(owner_id)
        print(f"Owner identified as {owner.display_name}")
    except:
        raise EnvironmentError(f'Could not find Discord user matching ID {owner_id}')

    # add owner to channel permissions

    try:
        await channel.set_permissions(owner, read_messages=True,
                                            manage_channels=True,
                                            manage_roles=True,
                                            manage_webhooks=True,
                                            create_instant_invite=True,
                                            send_messages=True,
                                            embed_links=True,
                                            attach_files=True,
                                            add_reactions=True,
                                            external_emojis=True,
                                            manage_messages=True,
                                            read_message_history=True,
                                            use_slash_commands=True)
        print(f"Set permissions for {owner} in {channel}")
    except Forbidden:
        raise EnvironmentError(f"Could not set channel permissions for {owner.display_name} in {channel}, reason: Bot does not have permissions to edit channel specific permissions.")
    except NotFound:
        raise EnvironmentError(f"Could not set channel permissions for {owner.display_name} in {channel}, reason: The role or member being edited is not part of the guild.")
    except HTTPException:
        raise EnvironmentError(f"Could not set channel permissions for {owner.display_name} in {channel}, reason: Editing channel specific permissions failed.")
    except InvalidArgument:
        raise EnvironmentError(f"Could not set channel permissions for {owner.display_name} in {channel}, reason: The overwrite parameter invalid or the target type was not Role or Member.")
    except:
        raise EnvironmentError(f'Could not set channel permissions for {owner.display_name} in {channel}')

    # create crew role

    # check whether one already exists, otherwise create one

    role = discord.utils.get(ctx.guild.roles, name=f"CREW: {long_name}")

    if role:
        await ctx.send('Crew role creation skipped: a role by that name already exists')
        print(f'Found existing {role}')

    else:
        role = await ctx.guild.create_role(name=f"CREW: {long_name}")
        print(f'Created {role}')
  
    # finally, send all the info to the db
    add_carrier_to_database(short_name, long_name, carrier_id, str(channel), channel.id, role.id, owner_id)

    carrier_data = find_carrier_from_long_name(long_name)
    await ctx.send(
        f"Added **{carrier_data.carrier_long_name.upper()}** **{carrier_data.carrier_identifier.upper()}** "
        f"with shortname **{carrier_data.carrier_short_name.lower()}**, channel "
        f"**<#{carrier_data.channel_id}>** and Crew Role <@&{carrier_data.roleid}> "
        f"owned by <@{owner_id}> at ID **{carrier_data.pid}**")


# remove FC from database
@bot.command(name='carrier_del', help='Delete a Fleet Carrier from the database using its database entry ID#.')
@commands.has_role('Admin')
async def carrier_del(ctx, db_id):

    # make sure we are in the right channel
    bot_command_channel = bot.get_channel(conf['BOT_COMMAND_CHANNEL'])
    current_channel = ctx.channel
    if current_channel != bot_command_channel:
        # problem, wrong channel, no progress
        return await ctx.send(f'Sorry, you can only run this command out of: {bot_command_channel}.')

    try:
        carrier_data = find_carrier_from_pid(db_id)
        if carrier_data:
            embed = discord.Embed(title="Delete Fleet Carrier", description=f"Result for {db_id}",
                                  color=constants.EMBED_COLOUR_OK)
            embed = _add_common_embed_fields(embed, carrier_data)
            await ctx.send(embed=embed)

            embed = discord.Embed(title="Proceed with deletion?", description="y/n", color=constants.EMBED_COLOUR_OK)
            await ctx.send(embed=embed)

            def check(message):
                return message.author == ctx.author and message.channel == ctx.channel and \
                       message.content.lower() in ["y", "n"]

            # TODO: Prompt user whether to also delete the carrier's channel and crew role

            try:
                msg = await bot.wait_for("message", check=check, timeout=30)
                if msg.content.lower() == "n":
                    embed=discord.Embed(description="Deletion cancelled.", color=constants.EMBED_COLOUR_OK)
                    await ctx.send(embed=embed)
                    return
                elif msg.content.lower() == "y":
                    try:
                        error_msg = delete_carrier_from_db(db_id)
                        if error_msg:
                            return await ctx.send(error_msg)

                        embed = discord.Embed(description=f"Fleet carrier #{carrier_data.pid} deleted.",
                                              color=constants.EMBED_COLOUR_OK)
                        return await ctx.send(embed=embed)
                    except Exception as e:
                        return ctx.send(f'Something went wrong, go tell the bot team "computer said: {e}"')

            except asyncio.TimeoutError:
                return await ctx.send("**Cancelled - timed out**")

    except TypeError as e:
        print(f'Error while finding carrier to delete: {e}.')
    await ctx.send(f"Couldn't find a carrier with ID #{db_id}.")


# change FC background image
@bot.command(name='carrier_image', help='Change the background image for the specified carrier:\n\n'
                                        'Type without argument to receive a blank PNG suitable for overlaying on top of'
                                        ' your carrier\'s image.\nType with carrier as argument to check the '
                                        'carrier\'s image or begin upload of a new image.')
@commands.has_role('Carrier Owner')
async def carrier_image(ctx, lookname=None):
    if not lookname:
        file = discord.File(f"blank.png", filename="image.png")
        embed = discord.Embed(title=f"Blank foreground image",
                              description="Overlay atop your carrier's image then use m.carrier_image <carrier> "
                                          "to upload.",
                              color=constants.EMBED_COLOUR_OK)
        embed.set_image(url="attachment://image.png")
        await ctx.send(file=file, embed=embed)
    else:
        carrier_data = find_carrier_from_long_name(lookname)
        file = discord.File(f"images/{carrier_data.carrier_short_name}.png", filename="image.png")
        embed = discord.Embed(title=f"View or change background image for {carrier_data.carrier_long_name}",
                              description="You can upload a replacement image now. Images should be 500x500, in .png "
                                          "format, and based on the standard PTN image template. Or input **x** to "
                                          "cancel upload and just view.",
                              color=constants.EMBED_COLOUR_QU)
        embed.set_image(url="attachment://image.png")
        message_upload_now = await ctx.send(file=file, embed=embed)

        def check(message_to_check):
            return message_to_check.author == ctx.author and message_to_check.channel == ctx.channel

        try:
            message = await bot.wait_for("message", check=check, timeout=30)
            if message.attachments:
                shutil.move(f'images/{carrier_data.carrier_short_name}.png',
                            f'images/old/{carrier_data.carrier_short_name}.{get_formatted_date_string()[1]}.png')
                for attachment in message.attachments:
                    await attachment.save(f"images/{carrier_data.carrier_short_name}.png")
                file = discord.File(f"images/{carrier_data.carrier_short_name}.png", filename="image.png")
                embed = discord.Embed(title=f"{carrier_data.carrier_long_name}",
                                      description="Background image updated.", color=constants.EMBED_COLOUR_OK)
                embed.set_image(url="attachment://image.png")
                await ctx.send(file=file, embed=embed)
                await message.delete()
                await message_upload_now.delete()
            elif message.content.lower() == "x":
                await ctx.send("**Upload cancelled**")
                await message.delete()
                # await message_upload_now.delete()
                return
        except asyncio.TimeoutError:
            await ctx.send("**Cancelled - timed out**")
            await message_upload_now.delete()
            return


# find FC based on shortname
@bot.command(name='findshort', help='Find a carrier based on its shortname.\n'
                                    '\n'
                                    'Syntax: findshort <string>\n'
                                    '\n'
                                    'Partial matches will work but only if they incorporate part of the shortname.\n'
                                    'To find a carrier based on a match with part of its full name, use the findlong '
                                    'command.')
async def findshort(ctx, lookshort):
    try:
        carriers = find_carrier_from_short_name(lookshort)
        if carriers:
            carrier_data = None

            if len(carriers) == 1:
                print('Single carrier found, returning that directly')
                # if only 1 match, just assign it directly
                carrier_data = carriers[0]
            elif len(carriers) > 3:
                # If we ever get into a scenario where more than 3 commodities can be found with the same search
                # directly, then we need to revisit this limit
                print(f'More than 3 carriers found for: "{lookshort}", {ctx.author} needs to search better.')
                await ctx.send(f'Please narrow down your commodity search, we found {len(carriers)} matches for your '
                               f'input choice: "{lookshort}"')
                return None  # Just return None here and let the calling method figure out what is needed to happen
            else:
                print(f'Between 1 and 3 carriers found for: "{lookshort}", asking {ctx.author} which they want.')
                # The database runs a partial match, in the case we have more than 1 ask the user which they want.
                # here we have less than 3, but more than 1 match
                embed = discord.Embed(title=f"Multiple carriers ({len(carriers)}) found for input: {lookshort}",
                                      color=constants.EMBED_COLOUR_OK)

                count = 0
                response = None  # just in case we try to do something before it is assigned, give it a value of None
                for carrier in carriers:
                    count += 1
                    embed.add_field(name='Carrier Name', value=f'{carrier.carrier_long_name}', inline=True)

                embed.set_footer(text='Please select the carrier with 1, 2 or 3')

                def check(message):
                    return message.author == ctx.author and message.channel == ctx.channel and \
                           len(message.content) == 1 and message.content.lower() in ["1", "2", "3"]

                message_confirm = await ctx.send(embed=embed)
                try:
                    # Wait on the user input, this might be better by using a reaction?
                    response = await bot.wait_for("message", check=check, timeout=15)
                    print(f'{ctx.author} responded with: "{response.content}", type: {type(response.content)}.')
                    index = int(response.content) - 1  # Users count from 1, computers count from 0
                    carrier_data = carriers[index]
                except asyncio.TimeoutError:
                    print('User failed to respond in time')
                    pass
                await message_confirm.delete()
                if response:
                    await response.delete()

            if carrier_data:
                embed = discord.Embed(title="Fleet Carrier Shortname Search Result",
                                      description=f"Displaying first match for {lookshort}",
                                      color=constants.EMBED_COLOUR_OK)
                embed = _add_common_embed_fields(embed, carrier_data)
                return await ctx.send(embed=embed)
    except TypeError as e:
        print('Error in carrier search: {}'.format(e))
    await ctx.send(f'No result for {lookshort}.')


def _add_common_embed_fields(embed, carrier_data):
    embed.add_field(name="Carrier Name", value=f"{carrier_data.carrier_long_name}", inline=True)
    embed.add_field(name="Carrier ID", value=f"{carrier_data.carrier_identifier}", inline=True)
    embed.add_field(name="Database Entry", value=f"{carrier_data.pid}", inline=True)
    embed.add_field(name="Discord Channel", value=f"<#{carrier_data.channel_id}>", inline=True)
    embed.add_field(name="Crew Role", value=f"<@&{carrier_data.roleid}>", inline=True)
    embed.add_field(name="Owner", value=f"<@{carrier_data.ownerid}>", inline=True)
    embed.add_field(name="Shortname", value=f"{carrier_data.carrier_short_name}", inline=True)
    # shortname is not relevant to users and will be auto-generated in future
    return embed


# find FC based on longname
@bot.command(name='find', help='Find a carrier based on a partial match with any part of its full name\n'
                               '\n'
                               'Syntax: find <string>\n'
                               '\n'
                               'If there are multiple carriers with similar names, only the first on the list will '
                               'return.')
async def find(ctx, looklong):
    try:
        carrier_data = find_carrier_from_long_name(looklong)
        if carrier_data:
            embed = discord.Embed(title="Fleet Carrier Search Result",
                                  description=f"Displaying first match for {looklong}", color=constants.EMBED_COLOUR_OK)
            embed = _add_common_embed_fields(embed, carrier_data)
            return await ctx.send(embed=embed)
    except TypeError as e:
        print('Error in carrier long search: {}'.format(e))
    await ctx.send(f'No result for {looklong}.')


# find FC based on ID
@bot.command(name='findid', help='Find a carrier based on its database ID\n'
                                 'Syntax: findid <integer>')
async def findid(ctx, db_id):
    try:
        if not isinstance(db_id, int):
            try:
                db_id = int(db_id)
                # Someone passed in a non integer, because this gets passed in with the wrapped quotation marks, it is
                # probably impossible to convert. Just go return an error and call the user an fool of a took
            except ValueError:
                return await ctx.send(
                    f'Computer says "The input must be a valid integer, you gave us a {type(db_id)} with value: '
                    f'{db_id}"')
        carrier_data = find_carrier_from_pid(db_id)
        if carrier_data:
            embed = discord.Embed(title="Fleet Carrier DB# Search Result",
                                  description=f"Displaying carrier with DB# {carrier_data.pid}",
                                  color=constants.EMBED_COLOUR_OK)
            embed = _add_common_embed_fields(embed, carrier_data)
            await ctx.send(embed=embed)
            return  # We exit here

    except TypeError as e:
        print('Error in carrier findid search: {}'.format(e))
    await ctx.send(f'No result for {db_id}.')


# find commodity
@bot.command(name='findcomm', help='Find a commodity based on a search term\n'
                                   'Any term which has multiple partial matches will return the first result.\n'
                                   'In this case make your term more specific.\n'
                                   'e.g. searching for "plat" will return Reinforced Mounting Plate as it\'s higher '
                                   'up the list.\n'
                                   'To find Platinum, you\'d have to type at least "plati".')
async def search_for_commodity(ctx, lookfor):
    print(f'search_for_commodity called by {ctx.author} to search for {lookfor}')
    try:
        commodity = await find_commodity(lookfor, ctx)
        if commodity:
            return await ctx.send(commodity)
    except:
        # Catch any exception
        pass
    await ctx.send(f'No such commodity found for: "{lookfor}".')


@bot.command(name='carrier_edit', help='Edit a specific carrier in the database by providing specific inputs')
@commands.has_role('Admin')
async def edit_carrier(ctx, carrier_name):
    """
    Edits a carriers information in the database. Provide a carrier name that can be partially matched and follow the
    steps.

    :param discord.ext.commands.Context ctx: The discord context
    :param str carrier_name: The carrier name to find
    :returns: None
    """
    global debugging_carrier_edit
    debugging_carrier_edit = True
    print(f'edit_carrier called by {ctx.author} to update the carrier: {carrier_name} from channel: {ctx.channel} - '
          f'{ctx}')

    # make sure we are in the right channel
    bot_command_channel = bot.get_channel(conf['BOT_COMMAND_CHANNEL'])
    current_channel = ctx.channel
    if current_channel != bot_command_channel:
        # problem, wrong channel, no progress
        debugging_carrier_edit = False
        return await ctx.send(f'Sorry, you can only run this command out of: {bot_command_channel}.')

    # Go fetch the carrier details by searching for the name

    carrier_data = copy.copy(find_carrier_from_long_name(carrier_name))
    print(carrier_data)
    if carrier_data:
        embed = discord.Embed(title=f"Edit DB request received.",
                              description=f"Editing starting for {carrier_data.carrier_long_name} requested by "
                                          f"{ctx.author}",
                              color=constants.EMBED_COLOUR_OK)
        embed = _configure_all_carrier_detail_embed(embed, carrier_data)

        # Store this, we might want to update it later
        initial_message = await ctx.send(embed=embed)
        edit_carrier_data = await _determine_db_fields_to_edit(ctx, carrier_data)
        if not edit_carrier_data:
            # The determination told the user there was an error. Wipe the original message and move on
            await initial_message.delete()
            debugging_carrier_edit = False
            return

        # Now we know what fields to edit, go do something with them, first display them to the user
        edited_embed = discord.Embed(title=f"Please validate the inputs are correct",
                                     description=f"Validate the new settings for {carrier_data.carrier_long_name}",
                                     color=constants.EMBED_COLOUR_OK)
        edited_embed = _configure_all_carrier_detail_embed(edited_embed, edit_carrier_data)
        edit_send = await ctx.send(embed=edited_embed)

        # Get the user to agree before we write
        confirm_embed = discord.Embed(title="Confirm you want to write these values to the database please",
                                      description="Yes or No.", color=constants.EMBED_COLOUR_QU)
        confirm_embed.set_footer(text='y/n - yes, no.')
        message_confirm = await ctx.send(embed=confirm_embed)

        async def check_confirm(message):
            return await message.content and message.author == ctx.author and message.channel == ctx.channel and \
                   all(character in 'yn' for character in set(message.content.lower())) and len(message.content) == 1

        try:

            msg = await bot.wait_for("message", check=check_confirm, timeout=30)
            if "n" in msg.content.lower():
                print(f'User {ctx.author} requested to cancel the edit operation. {ctx}')
                # immediately stop if there's an x anywhere in the message, even if there are other proper inputs
                await ctx.send("**Edit operation cancelled by the user.**")
                await msg.delete()
                await message_confirm.delete()
                await edit_send.delete()
                await initial_message.delete()
                debugging_carrier_edit = False
                return None  # Exit the check logic

            elif 'y' in msg.content.lower():
                await ctx.send("**Writing the values now ...**")
                await message_confirm.delete()
                await msg.delete()
                await edit_send.delete()
        except asyncio.TimeoutError:
            await ctx.send("**Write operation from {ctx.author} timed out.**")
            await edit_send.delete()
            await message_confirm.delete()
            await initial_message.delete()
            debugging_carrier_edit = False
            return None  # Exit the check logic

        # Go update the details to the database
        _update_carrier_details_in_database(ctx, edit_carrier_data, carrier_data.carrier_long_name)

        # Double check if we need to edit the carrier shortname, if so then we also need to edit the backup image
        if edit_carrier_data.carrier_short_name != carrier_data.carrier_short_name:
            print('Renaming the carriers image')
            os.rename(
                f'images/{carrier_data.carrier_short_name}.png',
                f'images/{edit_carrier_data.carrier_short_name}.png'
            )
            print(f'Carrier image renamed from: images/{carrier_data.carrier_short_name}.png to '
                  f'images/{edit_carrier_data.carrier_short_name}.png')

        # Go grab the details again, make sure it is correct and display to the user
        updated_carrier_data = find_carrier_from_long_name(edit_carrier_data.carrier_long_name)
        if updated_carrier_data:
            embed = discord.Embed(title=f"Reading the settings from DB:",
                                  description=f"Double check and re-run if incorrect the settings for old name: "
                                              f"{carrier_data.carrier_long_name}",
                                  color=constants.EMBED_COLOUR_OK)
            embed = _configure_all_carrier_detail_embed(embed, updated_carrier_data)
            await initial_message.delete()
            debugging_carrier_edit = False
            return await ctx.send(embed=embed)
        else:
            await ctx.send('We did not find the new database entry - that is not good.')
            debugging_carrier_edit = False
    else:

        debugging_carrier_edit = False
        return await ctx.send(f'No result found for the carrier: "{carrier_name}".')


def _update_carrier_details_in_database(ctx, carrier_data, original_name):
    """
    Updates the carrier details into the database. It first ensures that the discord channel actually exists, if it
    does not then you are getting an error back.

    :param discord.ext.commands.Context ctx: The discord context
    :param CarrierData carrier_data: The carrier data to write
    :param str original_name: The original carrier name, needed so we can find it in the database
    """
    backup_database('carriers')  # backup the carriers database before going any further

    print(f'Ensuring the discord channel {carrier_data.channel_id} exists for the carrier: '
          f'{carrier_data.carrier_long_name}')
    print(f'Channels: {ctx.guild.channels}')
    channel = discord.utils.get(ctx.guild.channels, name=carrier_data.discord_channel)
    if not channel:
        raise EnvironmentError('The discord channel does not exist; are you trying to update it? Go make it first and'
                               ' try again')
    # TODO: Write to the database
    carrier_db_lock.acquire()
    try:

        data = (
            carrier_data.carrier_short_name,
            carrier_data.carrier_long_name,
            carrier_data.carrier_identifier,
            carrier_data.discord_channel,
            carrier_data.channel_id,
            f'%{original_name}%'
        )
        # Handy number to print out what the database connection is actually doing
        carriers_conn.set_trace_callback(print)
        carrier_db.execute(
            ''' UPDATE carriers 
            SET shortname=?, longname=?, cid=?, discordchannel=?, channelid=?
            WHERE longname LIKE (?) ''', data
        )

        carriers_conn.commit()
    finally:
        carrier_db_lock.release()


async def _determine_db_fields_to_edit(ctx, carrier_data):
    """
    Loop through a dummy CarrierData object and see if the user wants to update any of the fields.

    :param discord.ext.commands.Context ctx: The discord context object
    :param CarrierData carrier_data: The carriers data you want to edit.
    :returns: A carrier data object to edit into the database
    :rtype: CarrierData
    """
    # We operate and return from this a copy of the object, not the object itself. Else things outside this also get
    # affected. Because python uses pass by reference, and this is a mutable object, things can go wrong.
    new_carrier_data = copy.copy(carrier_data)

    embed = discord.Embed(title=f"Edit DB request in progress ...",
                          description=f"Editing in progress for {carrier_data.carrier_long_name}",
                          color=constants.EMBED_COLOUR_OK)

    async def check_confirm(message, user):
        return message.content and user == ctx.author and message.channel == ctx.channel and \
            all(character in 'ynx' for character in set(message.content.lower())) and len(message.content) == 1

    async def check_user(message):
        return message.content and message.author == ctx.author and message.channel == ctx.channel

    # These two are used below, initial value so we can wipe the message out if needed
    message_confirm = None  # type: discord.Message
    msg = None  # type: discord.Message

    for field in vars(carrier_data):

        # Remove any pre-existing messages/responses if they were present.
        if message_confirm:
            await message_confirm.delete()
        if msg:
            await msg.delete()

        if field == 'pid':
            # We cant edit the DB ID here, so skip over it.
            # TODO: DB ID uses autoincrement, we probably want our own index if we want to use this.
            continue

        print(f'Looking to see if the user wants to edit the field {field} for carrier: '
              f'{carrier_data.carrier_long_name} from {ctx}')

        # Go ask the user for each one if they want to update, and if yes then to what.
        embed.add_field(name=f'Do you want to update the carriers: "{field}" value?',
                        value=f'Current Value: "{getattr(carrier_data, field)}"', inline=True)
        embed.set_footer(text='y/n/x - yes, no or cancel the operation')
        message_confirm = await ctx.send(embed=embed)
        init_channel = ctx.channel
        try:
            msg = await bot.wait_for("message", check=check_confirm, timeout=30)
            curr_channel = msg.channel
            if "x" in msg.content.lower():
                print(f'User {ctx.author} requested to cancel the edit operation.')
                # immediately stop if there's an x anywhere in the message, even if there are other proper inputs
                await ctx.send("**Edit operation cancelled by the user.**")
                await msg.delete()
                await message_confirm.delete()
                return None  # Exit the check logic

            elif 'n' in msg.content.lower():
                # Log a message and skip over
                print(f'User {ctx.author} does not want to edit the field: {field}')
                # We do not care, just move on
            elif 'y' in msg.content.lower():
                # Remove this, we re-assign it now.
                await msg.delete()
                await message_confirm.delete()

                # Log a message and skip over
                print(f'User {ctx.author} wants to edit the field: {field}')
                embed.remove_field(0)   # Remove the current field, add a new one and resend

                embed.add_field(name=f'What is the new value for: {field}?', value='Type your response now.')
                embed.set_footer()   # Clear the foot as well
                message_confirm = await ctx.send(embed=embed)

                msg = await bot.wait_for("message", check=check_user, timeout=30)
                print(f'Setting the value for {new_carrier_data.carrier_long_name} filed {field} to '
                      f'"{msg.content.strip()}"')

                # Use setattr to change the value of the variable field object to the user input
                setattr(new_carrier_data, field, msg.content.strip())
            else:
                print(f'{ctx.author} provided the invalid input: {msg.content} from object: {ctx}.')
                print(f'Expected channel: {init_channel} - received channel: {curr_channel}')
                # Should never be hitting this as we gate the message
                await ctx.send(f"**I cannot do anything with that entry '{msg.content}', please stick to y, n or x.**")
                return None  # Break condition just in case
        except asyncio.TimeoutError:
            print(f'Carrier edit requested by {ctx.author} timed out. Context: {ctx}')
            await ctx.send("**Edit operation timed out (no valid response from user).**")
            await message_confirm.delete()
            return None

        # Remove the previous field so we have things in a nice view
        embed.remove_field(0)

    print(f'Current tracking of carrier data: {carrier_data}')
    # If the current thing is the same as the old thing, why did we bother?
    if new_carrier_data == carrier_data:
        print(f'User {ctx.author} went through the whole process and does not want to edit anything.')
        await ctx.send("**After all those button clicks you did not want to edit anything, fun.**")
        return None

    print(f'Carrier data now looks like:')
    print(f'\t Initial: {carrier_data}')
    print(f'\t Initial: {new_carrier_data}')

    return new_carrier_data


def _configure_all_carrier_detail_embed(embed, carrier_data):
    """
    Adds all the common fields to a message embed and returns the embed.

    :param discord.Embed embed: The original embed to edit.
    :param CarrierData carrier_data: The carrier data to use for populating the embed
    :returns: The embeded message
    """
    embed.add_field(name='Carrier Name', value=f'{carrier_data.carrier_long_name}', inline=True)
    embed.add_field(name='Carrier Identifier', value=f'{carrier_data.carrier_identifier}', inline=True)
    embed.add_field(name='Short Name', value=f'{carrier_data.carrier_short_name}', inline=True)
    embed.add_field(name='Discord Channel', value=f'<#{carrier_data.channel_id}>', inline=True)
    embed.add_field(name='Channel ID', value=f'{carrier_data.channel_id}', inline=True)
    embed.add_field(name='DB ID', value=f'{carrier_data.pid}', inline=True)
    embed.set_footer(text="Note: DB ID is not an editable field.")
    return embed


@commands.has_role('Carrier Owner')
@slash.slash(name="crewcount", guild_ids=[bot_guild_id],
             description="Use /crewcount find the number of people with each crew role. Requires CarrierOwner role.")
async def _crews(ctx: SlashContext):
    """
    Returns a list of every @Crew:xyz role and the number of current users assigned to the role.

    We might want this only to be returned to the requesting user, for now just print it out wherever it was called
    from. This command currently is not channel locked in any way.
    """
    print(f'{ctx.author} requested to run crewcount from channel: {ctx.channel}.')

    # Check we are in the designated mission channel, if not go no farther.
    allowed_channels = [bot.get_channel(conf['MISSION_CHANNEL']), bot.get_channel(conf['BOT_COMMAND_CHANNEL'])]
    current_channel = ctx.channel

    if current_channel not in allowed_channels:
        # urroh, not in the correct channel.
        allowed_channel_names = [f'#{allowed.name}' for allowed in allowed_channels]
        print(f'Request for crewcount was not from the correct channel {ctx.channel}, expected {allowed_channels}.')
        return await ctx.send(f'Sorry, you can only run this command out of: {allowed_channel_names}.')

    all_crew_roles = [role for role in ctx.guild.roles if role.name.lower().startswith('crew')]
    result = {}
    for role in all_crew_roles:
        role_count = 0
        print(f'Searching for crew role: {role.name}')
        for user in ctx.guild.members:
            if role in user.roles:
                # The user have the role we are checking for.
                role_count += 1
        result[role.name] = role_count
    print(dict(reversed(sorted(result.items(), key=lambda item: item[1]))))

    sorted_dict = dict(reversed(sorted(result.items(), key=lambda item: item[1])))
    print(f'Sorted dict is: {sorted_dict}')

    def chunk(data, max_size):
        """
        Take an input dictionary, and an expected max_size.

        :param dict data: The dictionary you wish to chunk.
        :param int max_size: How many elements in your chunk?
        :returns: A chunked list that is yielded back to the caller
        :rtype: iterator
        """
        it = iter(data)
        for i in range(0, len(data), max_size):
            yield {k: data[k] for k in islice(it, max_size)}

    current_page = 0
    max_page_size = 10
    max_pages = int(ceil(len(sorted_dict) / max_page_size))

    embed_list = []
    for page in chunk(sorted_dict, max_page_size):
        print(f'Current working page: {page}')

        current_page += 1
        nextembed = discord.Embed(title=f"{len(sorted_dict)} Roles Found Page: {current_page} of {max_pages}.")
        for key, value in page.items():
            # We might prefer just the long list, for now set inline as True to reduce the length of the display
            # somewhat
            nextembed.add_field(name=f"{key}", value=f"{value} members.", inline=True)

        embed_list.append(nextembed)
        print(nextembed)
        print(embed_list)

    await ctx.send(embeds=embed_list)


# ping the bot
@bot.command(name='ping', help='Ping the bot')
@commands.has_role('Carrier Owner')
async def ping(ctx):
    await ctx.send("**PING? PONG!**")


# quit the bot
@bot.command(name='stopquit', help="Stops the bots process on the VM, ending all functions.")
@commands.has_role('Admin')
async def stopquit(ctx):
    await ctx.send(f"k thx bye")
    await user_exit()


#
# error handling
#
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send('**Bad argument!**')
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("**Invalid command.**")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send('**Please include all required parameters.** Use m.help <command> for details.')
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send('**You must be a Carrier Owner to use this command.**')
    else:
        await ctx.send(f"Sorry, that didn't work. Check your syntax and permissions, error: {error}")


bot.run(TOKEN)
