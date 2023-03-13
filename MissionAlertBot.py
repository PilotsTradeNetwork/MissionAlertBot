# MissionAlertBot.py
# Discord bot to help PTN Carrier Owners post trade missions to Discord and Reddit
# By Charles Tosh 17 March 2021
# Additional contributions by Alexander Leidinger
# Discord Developer Portal: https://discord.com/developers/applications/822146046934384640/information
# Git repo: https://github.com/PilotsTradeNetwork/MissionAlertBot
import ast
import copy
from doctest import debug_script
from pydoc import describe
import re
import tempfile
# from turtle import color
from typing import Union
import enum
from functools import wraps
from PIL import Image, ImageFont, ImageDraw
import os
import sys
import discord
import sqlite3
import asyncpraw
import asyncio
import shutil
from discord.errors import HTTPException, Forbidden, NotFound
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Select, View, Button, Modal
from datetime import datetime
from datetime import timezone
from datetime import timedelta
from dotenv import load_dotenv
from dateutil.relativedelta import relativedelta
import constants
import random
import emoji
#
#                       INIT STUFF
#

# Ast will parse a value into a python type, but if you try to give a boolean its going to get into problems. Just use
# a string and be consistent.
from CarrierData import CarrierData
from Commodity import Commodity
from MissionData import MissionData
from CommunityCarrierData import CommunityCarrierData
from NomineesData import NomineesData
from version import version

_production = ast.literal_eval(os.environ.get('PTN_MISSION_ALERT_SERVICE', 'False'))

# We need some locks to we wait on the DB queries
carrier_db_lock = asyncio.Lock()
mission_db_lock = asyncio.Lock()
carrier_channel_lock = asyncio.Lock()

# setting some variables, you can toggle between production and test by setting an env variable flag now,
# PTN-MISSION-ALERT-SERVICE
conf = constants.get_constant(_production)

bot_guild_id = int(conf['BOT_GUILD'])
guild_obj = discord.Object(bot_guild_id)

flair_mission_start = conf['MISSION_START']
flair_mission_stop = conf['MISSION_STOP']

# channel IDs
trade_alerts_id = conf['TRADE_ALERTS_ID']
legacy_alerts_id = conf['LEGACY_ALERTS_ID']
wine_alerts_loading_id = conf['WINE_ALERTS_LOADING_ID']
wine_alerts_unloading_id = conf['WINE_ALERTS_UNLOADING_ID']
bot_spam_id = conf['BOT_SPAM_CHANNEL']
dev_channel_id = conf['BOT_DEV_CHANNEL']

# category IDs
cc_cat_id = conf['CC_CAT']
trade_cat_id = conf['TRADE_CAT']
archive_cat_id = conf['ARCHIVE_CAT']

# reddit IDs
to_subreddit = conf['SUB_REDDIT']

# role IDs
hauler_role_id = conf['HAULER_ROLE']
legacy_hauler_role_id = conf['LEGACY_HAULER_ROLE']
cpillar_role_id = conf['CPILLAR_ROLE']
cc_role_id = conf['CC_ROLE']
cmentor_role_id = conf['CMENTOR_ROLE']
certcarrier_role_id = conf['CERTCARRIER_ROLE']
rescarrier_role_id = conf['RESCARRIER_ROLE']
botadmin_role_id = conf['ADMIN_ROLE']
mod_role_id = conf['MOD_ROLE']
trainee_role_id = conf['TRAINEE_ROLE']
botdev_role_id = conf['DEV_ROLE']
any_elevated_role = [cc_role_id, cmentor_role_id, certcarrier_role_id, rescarrier_role_id, botadmin_role_id, trainee_role_id, botdev_role_id]

# emoji IDs
upvote_emoji = conf['UPVOTE_EMOJI']

# channel removal timers
seconds_short = conf['SECONDS_SHORT']
seconds_long = conf['SECONDS_LONG']

# Get the discord token from the local .env file. Deliberately not hosted in the repo or Discord takes the bot down
# because the keys are exposed. DO NOT HOST IN THE REPO. Seriously do not do it ...
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN_PROD') if _production else os.getenv('DISCORD_TOKEN_TESTING')

########################
# Database Configuration
########################
# Each database should have:
#   1. connection
#   2. row_factory definition
#   3. database object pointing to the cursor
#
# Each Table should have:
#   1. create statement string (update with new columns as added)
#   2. columns list (update with new columns as added)

#  carrier database/table config
carriers_conn = sqlite3.connect('carriers.db')
carriers_conn.row_factory = sqlite3.Row
carrier_db = carriers_conn.cursor()
carriers_table_create = '''
    CREATE TABLE carriers(
        p_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        shortname TEXT NOT NULL UNIQUE,
        longname TEXT NOT NULL,
        cid TEXT NOT NULL,
        discordchannel TEXT NOT NULL,
        channelid INT,
        ownerid INT,
        lasttrade INT NOT NULL DEFAULT (cast(strftime('%s','now') as int))
    )
    '''
carriers_table_columns = ['p_ID', 'shortname', 'longname', 'cid', 'discordchannel', 'channelid', 'ownerid', 'lasttrade']

community_carriers_table_create = '''
    CREATE TABLE community_carriers(
        ownerid INT NOT NULL UNIQUE,
        channelid INT NOT NULL UNIQUE,
        roleid INT NOT NULL UNIQUE
    )
    '''
community_carriers_table_columns = ['ownerid', 'channelid', 'roleid']

nominees_table_create = '''
    CREATE TABLE nominees(
        nominatorid INT NOT NULL,
        pillarid INT NOT NULL,
        note TEXT
    )
    '''
nominess_table_columns = ['nominatorid', 'pillarid', 'note']

#  missions database/table config
missions_conn = sqlite3.connect('missions.db')
missions_conn.row_factory = sqlite3.Row
mission_db = missions_conn.cursor()
missions_table_create = '''
    CREATE TABLE missions(
        "carrier"	TEXT NOT NULL UNIQUE,
        "cid"	TEXT,
        "channelid"	INT,
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
    '''
missions_tables_columns = ['carrier', 'cid', 'channelid', 'commodity', 'missiontype', 'system', 'station',\
    'profit', 'pad', 'demand', 'rp_text', 'reddit_post_id', 'reddit_post_url', 'reddit_comment_id',\
    'reddit_comment_url', 'discord_alert_id', 'is_complete']

channel_cleanup_table_create = '''
    CREATE TABLE channel_cleanup(
        "channelid" INT NOT NULL UNIQUE,
        "is_complete" BOOLEAN DEFAULT 0
    )
'''
channel_cleanup_columns = ['channelid', 'is_complete']

deletion_in_progress = False

# random gifs and images

byebye_gifs = [
    'https://media.tenor.com/gRgywxwuxb0AAAAd/explosion-gi-joe-a-real-american-hero.gif',
    'https://media.tenor.com/a7LMG-8ldlAAAAAC/ice-cube-bye-felicia.gif',
    'https://media.tenor.com/SqrZAbYtcq0AAAAC/madagscar-penguins.gif',
    'https://media.tenor.com/ctCdr1R4ga4AAAAC/boom-explosion.gif',
]

boom_gifs = [
    'https://media.tenor.com/xGJ5PEQ9lLYAAAAC/self-destruction-imminent-please-evacuate.gif'
    'https://media.tenor.com/gRgywxwuxb0AAAAd/explosion-gi-joe-a-real-american-hero.gif',
    'https://media.tenor.com/a7LMG-8ldlAAAAAC/ice-cube-bye-felicia.gif',
    'https://media.tenor.com/v_d_Flu6pY0AAAAC/countdown-lastseconds.gif',
    'https://media.tenor.com/Ijf5y9BUgg8AAAAC/final-countdown-countdown.gif',
    'https://media.tenor.com/apADIQqKnSEAAAAC/self-destruct-mission-impossible.gif',
    'https://media.tenor.com/ctCdr1R4ga4AAAAC/boom-explosion.gif',
]

hello_gifs = [
    'https://media.tenor.com/DSG9ZID25nsAAAAC/hello-there-general-kenobi.gif', # obi wan
    'https://media.tenor.com/uNQvTg9Tk_QAAAAC/hey-tom-hanks.gif', # tom hanks
    'https://media.tenor.com/-z2KfO5zAckAAAAC/hello-there-baby-yoda.gif', # baby yoda
    'https://media.tenor.com/iZPmuJ0KON8AAAAd/hello-there.gif', # toddler
    'https://media.tenor.com/KKvpO702avgAAAAC/hey-hay.gif', # rollerskates
    'https://media.tenor.com/pE2UP8CBBuwAAAAC/jim-carrey-funny.gif', # jim carrey
    'https://media.tenor.com/-UiIDx_KNUUAAAAd/hi-friends-baby-goat.gif', # goat
]

error_gifs = [
    'https://tenor.com/view/beaker-fire-shit-omg-disaster-gif-4767835',
    'https://tenor.com/view/nothingtosee-disperse-casual-explosion-gif-4545906',
    'https://tenor.com/view/spongebob-patrick-panic-run-scream-gif-4656335',
    'https://tenor.com/view/angry-panda-rage-mad-gif-11780191',
]

#
#                       DATABASE ACTION STUFF
#


print('MissionAlertBot starting')
print(f'Configuring to run against: {"Production" if _production else "Testing"} env.')


def check_database_table_exists(table_name, database):
    """
    Checks whether a table exists in the database already.

    :param str table_name:  The database string name to create.
    :param sqlite.Connection.cursor database: The database to connect againt.
    :returns: A boolean state, True if it exists, else False
    :rtype: bool
    """
    print(f'Starting up - checking if {table_name} table exists or not')

    database.execute(f"SELECT count(name) FROM sqlite_master WHERE TYPE = 'table' AND name = '{table_name}'")
    return bool(database.fetchone()[0])


def create_missing_table(table, db_obj, create_stmt):
    print(f'{table} table missing - creating it now')

    if os.path.exists(os.path.join(os.getcwd(), 'db_sql', f'{table}_dump.sql')):

        # recreate from backup file
        print('Recreating database from backup ...')
        with open(os.path.join(os.getcwd(), 'db_sql', f'{table}_dump.sql')) as f:

            sql_script = f.read()
            db_obj.executescript(sql_script)


        # print('Loaded the following data: ')
        # carrier_db.execute('''SELECT * from carriers ''')
        # for e in carrier_db.fetchall():
        #     print(f'\t {CarrierData(e)}')
    else:
        # Create a new version
        print('No backup found - Creating empty database')

        db_obj.execute(create_stmt)


def check_table_column_exists(column_name, table_name, database):
    """
    Checks whether a column exists in a table for a database.


    :param str column_name: The column name to check for.
    :param str table_name: The table to check for the column in.
    :param sqlite.Connection.cursor database: The database to connect against.
    :returns: A boolean state, True if it exists, else False
    :rtype: bool
    """
    print(f'Starting up - checking if {table_name} table has new "{column_name}" column or not')

    database.execute(f"SELECT COUNT(name) FROM pragma_table_info('{table_name}') WHERE name='{column_name}'")
    return bool(database.fetchone()[0])



def create_missing_column(table, column, existing, db_name, db_obj, db_conn, create_stmt):

    """
    In order to create the new column, a new table has to be created because
    SQLite does not allow adding a new column with a non-constant value.
    We then copy data from table to table, and rename them into place.
    We will leave the backup table in case something goes wrong.
    There is not enough try/catch here to be perfect. sorry. (that's OK Durzo, thanks for the code!)


    :param str table: name of the table the new column should be created in
    :param str column: name of the new column
    :param list existing: list of all columns in table
    :param str db_name: name of database
    :param db_obj
    :param sqlite.Connection.cursor db_obj: database cursor
    :param sqlite.Connection db_conn: database connection
    :param string create_stmt: table create command
    :returns: return

    """
    temp_ts = int(datetime.now(tz=timezone.utc).timestamp())
    temp_database_table = f'{table}_newcolumn_{temp_ts}'
    backup_database_table = f'{table}_backup_{temp_ts}'

    print(f'{column} column missing from {db_name} database, creating new temp table: {temp_database_table}')
    db_obj.execute(create_stmt.replace(table, temp_database_table))

    # copy data from community_carriers table to new temp table.
    print(f'Copying {table} data to new table.')
    # new column won't exist, so remove it from the existing list
    existing.remove(column)
    db_obj.execute(f"INSERT INTO {temp_database_table} ({','.join(existing)}) select * from {table}")

    # rename old table and keep as backup just in case.
    print(f'Renaming current {table} table to "{backup_database_table}"')
    db_obj.execute(f'ALTER TABLE {table} RENAME TO {backup_database_table}')


    # rename temp table as original.
    print(f'Renaming "{temp_database_table}" temp table to "{table}"')
    db_obj.execute(f'ALTER TABLE {temp_database_table} RENAME TO {table}')


    print('Operation complete.')
    db_conn.commit()
    return

# Add a mapping when a new table needs to be created
# Requires:
#   table_name (str):
#       obj (sqlite db obj): sqlite connection to db
#       create (str): sql create statement for table
database_table_map = {
    'carriers' : {'obj': carrier_db, 'create': carriers_table_create},
    'community_carriers': {'obj': carrier_db, 'create': community_carriers_table_create},
    'nominees': {'obj': carrier_db, 'create': nominees_table_create},
    'missions': {'obj': mission_db, 'create': missions_table_create},
    'channel_cleanup': {'obj': mission_db, 'create': channel_cleanup_table_create}
}

for table_name in database_table_map:
    t = database_table_map[table_name]
    if not check_database_table_exists(table_name, t['obj']):
        create_missing_table(table_name, t['obj'], t['create'])
    else:
        print(f'{table_name} table exists, do nothing')

# Add a mapping when a new column needs to be added to an existing table
# Requires:
#   column_name (str):
#       db_name (str): name of database the table exist in
#       table (str): table the column needs to be added to
#       obj (sqlite db obj): sqlite connection to db
#       columns (list): list of existing column names
#       conn (sqlite connection): connection to sqlitedb
#       create (str): sql create statement for table
new_column_map = {
    'lasttrade': {
        'db_name': 'carriers',
        'table': 'carriers',
        'obj': carrier_db,
        'columns': carriers_table_columns,
        'conn': carriers_conn,
        'create': carriers_table_create
    },
    'roleid': {
        'db_name': 'carriers',
        'table': 'community_carriers',
        'obj': carrier_db,
        'columns': community_carriers_table_columns,
        'conn': carriers_conn,
        'create': community_carriers_table_create
    },
}

for column_name in new_column_map:
    c = new_column_map[column_name]
    if not check_table_column_exists(column_name, c['table'], c['obj']):
        create_missing_column(c['table'], column_name, c['columns'], c['db_name'], c['obj'], c['conn'], c['create'])
    else:
        print(f'{column_name} exists, do nothing')


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

    os.makedirs('db_sql', exist_ok=True)
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
async def add_carrier_to_database(short_name, long_name, carrier_id, channel, channel_id, owner_id):
    """
    Inserts a carrier's details into the database.

    :param str short_name: The carriers shortname reference
    :param str long_name: The carriers full name description
    :param str carrier_id: The carriers ID value from the game
    :param str discord_channel: The carriers discord channel
    :param int channel_id: The discord channel ID for the carrier
    :returns: None
    """
    await carrier_db_lock.acquire()
    try:
        carrier_db.execute(''' INSERT INTO carriers VALUES(NULL, ?, ?, ?, ?, ?, ?, strftime('%s','now')) ''',
                           (short_name.lower(), long_name.upper(), carrier_id.upper(), channel, channel_id, owner_id))
        carriers_conn.commit()
    finally:
        carrier_db_lock.release()
        # copy the blank bitmap to the new carrier's name to serve until unique image uploaded
        # shutil.copy('bitmap.png', f'images/{short_name.lower()}.png')
        # we don't do this anymore but leaving code here in case users respond poorly




"""
DATABASE SEARCH FUNCTIONS
"""

# class for CCO Carrier database
class CarrierDbFields(enum.Enum):
    longname = 'longname'
    shortname = 'shortname'
    cid = 'cid'
    channelname = 'discordchannel'
    channelid = 'channelid'
    ownerid = 'ownerid'
    lasttrade = 'lasttrade'
    p_id = 'p_ID'

# class for CC database
class CCDbFields(enum.Enum):
    ownerid = 'ownerid'
    channelid = 'channelid'
    roleid = 'roleid'

# function to remove a carrier
async def delete_carrier_from_db(p_id):
    carrier = find_carrier(p_id, CarrierDbFields.p_id.name)
    try:
        await carrier_db_lock.acquire()
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


# function to remove a community carrier
async def delete_community_carrier_from_db(ownerid):
    try:
        await carrier_db_lock.acquire()
        carrier_db.execute(f"DELETE FROM community_carriers WHERE ownerid = {ownerid}")
        carriers_conn.commit()
    finally:
        carrier_db_lock.release()
    return


# remove a nominee from the database
async def delete_nominee_from_db(pillarid):
    try:
        await carrier_db_lock.acquire()
        carrier_db.execute(f"DELETE FROM nominees WHERE pillarid = {pillarid}")
        carriers_conn.commit()
    finally:
        carrier_db_lock.release()
    return


# function to remove a nominee
async def delete_nominee_by_nominator(nomid, pillarid):
    print(f"Attempting to delete {nomid} {pillarid} match.")
    try:
        await carrier_db_lock.acquire()
        carrier_db.execute(f"DELETE FROM nominees WHERE nominatorid = {nomid} AND pillarid = {pillarid}")
        carriers_conn.commit()
    finally:
        carrier_db_lock.release()
    return print("Deleted")


# function to remove all carriers, not currently used by any bot command
def _delete_all_from_database(database):
    """
    Removes all the entries from the database.

    :returns: None
    """
    carrier_db.execute(f"DELETE FROM {database}")
    carriers_conn.commit()


# function to search for a carrier
def find_carrier(searchterm, searchfield):
    """
    Finds any carriers from the specified column matching the given searchterm.

    :param searchterm: Search term to match
    :param searchfield: DB column to match against
    :returns: A single CarrierData object
    :rtype: CarrierData
    """
    # TODO: This needs to check an exact not a `LIKE`
    carrier_db.execute(
        f"SELECT * FROM carriers WHERE {searchfield} LIKE (?)", (f'%{searchterm}%',)
        )
    carrier_data = CarrierData(carrier_db.fetchone())
    print(f"FC {carrier_data.pid} is {carrier_data.carrier_long_name} {carrier_data.carrier_identifier} called by "
          f"shortname {carrier_data.carrier_short_name} with channel #{carrier_data.discord_channel} called "
          f"from find_carrier.")
    return carrier_data


# used to find carriers if we expect multiple results for a search term
# TODO: make every carrier longname search prompt with multiple results and use this function
def find_carriers_mult(searchterm, searchfield):
    """
    Returns all carriers matching the searchterm from the searchfield

    :param searchterm: The searchterm to match
    :param searchfield: The db field to match against
    :returns: A list of carrier data objects
    :rtype: list[CarrierData]
    """
    carrier_db.execute(
        f"SELECT * FROM carriers WHERE {searchfield} LIKE (?)", (f'%{searchterm}%',)
    )
    carrier_data = [CarrierData(carrier) for carrier in carrier_db.fetchall()]
    for carrier in carrier_data:
        print(f"FC {carrier.pid} is {carrier.carrier_long_name} {carrier.carrier_identifier} called by "
              f"shortname {carrier.carrier_short_name} with channel <#{carrier.channel_id}> "
              f"and owner {carrier.ownerid} called from find_carriers_mult.")

    return carrier_data


def find_community_carrier(searchterm, searchfield):
    """
    Returns channel owner and role matching the ownerid

    :param str searchterm: The searchterm to match
    :param str searchfield: The db column to match against
    :returns: A list of community carrier data objects
    :rtype: list[CommunityCarrierData]
    """
    carrier_db.execute(f"SELECT * FROM community_carriers WHERE "
                       f"{searchfield} = {searchterm} ")
    community_carrier_data = [CommunityCarrierData(community_carrier) for community_carrier in carrier_db.fetchall()]
    for community_carrier in community_carrier_data:
        print(f"{community_carrier.owner_id} owns channel {community_carrier.channel_id}"
              f" called from find_community_carrier.")

    return community_carrier_data


def find_nominee_with_id(pillarid):
    """
    Returns nominee, nominator and note matching the nominee's user ID

    :param int pillarid: The user id to match
    :returns: A list of nominees data objects
    :rtype: list[NomineesData]
    """
    carrier_db.execute(f"SELECT * FROM nominees WHERE "
                       f"pillarid = {pillarid} ")
    nominees_data = [NomineesData(nominees) for nominees in carrier_db.fetchall()]
    for nominees in nominees_data:
        print(f"{nominees.pillar_id} nominated by {nominees.nom_id} for reason {nominees.note}"
              f" called from find_nominee_with_id.")

    return nominees_data


def find_nominator_with_id(nomid):
    """
    Returns nominee, nominator and note matching the nominator's user ID

    :param int nomid: The user id to match
    :returns: A list of nominees data objects
    :rtype: list[NomineesData]
    """
    carrier_db.execute(f"SELECT * FROM nominees WHERE "
                       f"nominatorid = {nomid} ")
    nominees_data = [NomineesData(nominees) for nominees in carrier_db.fetchall()]
    for nominees in nominees_data:
        print(f"{nominees.nom_id} nominated {nominees.pillar_id} for reason {nominees.note}"
              f" called from find_nominee_with_id.")

    return nominees_data


# search the mission database
def find_mission(searchterm, searchfield):
    print("called find_mission")
    """
    Searches the mission database for ongoing missions

    :param str searchterm: the searchterm to match
    :param str searchfield: the DB column to match against
    :returns: list[mission data]
    """
    mission_db.execute(f'''SELECT * FROM missions WHERE {searchfield} LIKE (?)''',
                        (f'%{searchterm}%',))
    mission_data = MissionData(mission_db.fetchone())
    print(f'Found mission data: {mission_data}')
    return mission_data


# check if a carrier is for a registered PTN fleet carrier
async def _is_carrier_channel(carrier_data):
    if not carrier_data.discord_channel:
        # if there's no channel match, return an error
        embed = discord.Embed(description="Try again in a **🚛Trade Carriers** channel.", color=constants.EMBED_COLOUR_QU)
        return embed
    else:
        return

# return an embed featuring either the active mission or the not found message
async def _is_mission_active_embed(carrier_data):
    print("Called _is_mission_active_embed")
    # look to see if the carrier is on an active mission
    mission_data = find_mission(carrier_data.carrier_long_name, "carrier")

    if not mission_data:
        # if there's no result, make our embed tell the user this
        embed = discord.Embed(description=f"**{carrier_data.carrier_long_name}** doesn't seem to be on a trade"
                                            f" mission right now.",
                                color=constants.EMBED_COLOUR_OK)
        return embed

    # mission data exists so format it for the user as an embed

    embed_colour = constants.EMBED_COLOUR_LOADING if mission_data.mission_type == 'load' else \
        constants.EMBED_COLOUR_UNLOADING

    mission_description = ''
    if mission_data.rp_text and mission_data.rp_text != 'NULL':
        mission_description = f"> {mission_data.rp_text}"

    embed = discord.Embed(title=f"{mission_data.mission_type.upper()}ING {mission_data.carrier_name} ({mission_data.carrier_identifier})",
                            description=mission_description, color=embed_colour)

    embed = _mission_summary_embed(mission_data, embed)

    embed.set_footer(text="You can use m.complete if the mission is complete.")
    return embed


# function to search for a commodity by name or partial name
async def find_commodity(commodity_search_term, ctx):
    # TODO: Where do we get set up this database? it is searching for things, but what is the source of the data, do
    #  we update it periodically?

    print(f'Searching for commodity against match "{commodity_search_term}" requested by {ctx.author}')

    carrier_db.execute(
        f"SELECT * FROM commodities WHERE commodity LIKE (?)",
        (f'%{commodity_search_term}%',))

    commodities = [Commodity(commodity) for commodity in carrier_db.fetchall()]
    commodity = None
    if not commodities:
        print('No commodities found for request')
        await ctx.send(f"No commodities found for {commodity_search_term}")
        # Did not find anything, short-circuit out of the next block
        return
    elif len(commodities) == 1:
        print('Single commodity found, returning that directly')
        # if only 1 match, just assign it directly
        commodity = commodities[0]
    elif len(commodities) > 3:
        # If we ever get into a scenario where more than 3 commodities can be found with the same search directly, then
        # we need to revisit this limit
        print(f'More than 3 commodities found for: "{commodity_search_term}", {ctx.author} needs to search better.')
        await ctx.send(f'Please narrow down your commodity search, we found {len(commodities)} matches for your '
                       f'input choice: "{commodity_search_term}"')
        return # Just return None here and let the calling method figure out what is needed to happen
    else:
        print(f'Between 1 and 3 commodities found for: "{commodity_search_term}", asking {ctx.author} which they want.')
        # The database runs a partial match, in the case we have more than 1 ask the user which they want.
        # here we have less than 3, but more than 1 match
        embed = discord.Embed(title=f"Multiple commodities found for input: {commodity_search_term}", color=constants.EMBED_COLOUR_OK)

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
            await ctx.send("Commodity selection timed out. Cancelling.")
            print('User failed to respond in time')
            return
        await message_confirm.delete()
        if response:
            await response.delete()
    if commodity: # only if this is successful is returnflag set so mission gen will continue
        gen_mission.returnflag = True
        print(f"Commodity {commodity.name} avgsell {commodity.average_sell} avgbuy {commodity.average_buy} "
              f"maxsell {commodity.max_sell} minbuy {commodity.min_buy} maxprofit {commodity.max_profit}")
    return commodity



"""
IMAGE GEN STUFF
"""



# defining fonts for pillow use
reg_font = ImageFont.truetype('font/Exo/static/Exo-Light.ttf', 16)
name_font = ImageFont.truetype('font/Exo/static/Exo-ExtraBold.ttf', 29)
title_font = ImageFont.truetype('font/Exo/static/Exo-ExtraBold.ttf', 22)
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


# function to overlay carrier image with background template
async def _overlay_mission_image(carrier_data):
    print("Called mission image overlay function")
    """
    template:       the background image with logo, frame elements etc
    carrier_image:  the inset image optionally created by the Carrier Owner
    """
    template = Image.open("template.png")
    carrier_image = Image.open(f"images/{carrier_data.carrier_short_name}.png")
    template.paste(carrier_image, (47,13))
    return template


# function to create image for loading
async def create_carrier_mission_image(carrier_data, commodity, system, station, profit, pads, demand, mission_type):
    print("Called mission image generator")
    """
    Builds the carrier image and returns the relative path.
    """

    template = await _overlay_mission_image(carrier_data)

    image_editable = ImageDraw.Draw(template)

    mission_action = 'LOADING' if mission_type == 'load' else 'UNLOADING'
    image_editable.text((46, 304), "PILOTS TRADE NETWORK", (255, 255, 255), font=title_font)
    image_editable.text((46, 327), f"CARRIER {mission_action} MISSION", (191, 53, 57), font=title_font)
    image_editable.text((46, 366), "FLEET CARRIER " + carrier_data.carrier_identifier, (0, 217, 255), font=reg_font)
    image_editable.text((46, 382), carrier_data.carrier_long_name, (0, 217, 255), font=name_font)
    image_editable.text((46, 439), "COMMODITY:", (255, 255, 255), font=field_font)
    image_editable.text((170, 439), commodity.name.upper(), (255, 255, 255), font=normal_font)
    image_editable.text((46, 477), "SYSTEM:", (255, 255, 255), font=field_font)
    image_editable.text((170, 477), system.upper(), (255, 255, 255), font=normal_font)
    image_editable.text((46, 514), "STATION:", (255, 255, 255), font=field_font)
    image_editable.text((170, 514), f"{station.upper()} ({pads.upper()} pads)", (255, 255, 255), font=normal_font)
    image_editable.text((46, 552), "PROFIT:", (255, 255, 255), font=field_font)
    image_editable.text((170, 552), f"{profit}k per unit, {demand} units", (255, 255, 255), font=normal_font)

    # Check if this will work fine, we might need to delete=False and clean it ourselves
    result_name = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    print(f'Saving temporary mission file for carrier: {carrier_data.carrier_long_name} to: {result_name.name}')
    template.save(result_name.name)
    return result_name.name





"""
TEXT GEN FUNCTIONS
"""




def txt_create_discord(carrier_data, mission_type, commodity, station, system, profit, pads, demand, eta_text, mission_temp_channel_id, edmc_off, legacy):
    discord_channel = f"<#{mission_temp_channel_id}>" if mission_temp_channel_id else f"#{carrier_data.discord_channel}"
    discord_text = (
        f"{'**◄ LEGACY UNIVERSE ►** : ' if legacy else ''}"
        f"{'**★ EDMC-OFF MISSION! ★** : ' if edmc_off else ''}"
        f"{discord_channel} {'load' if mission_type == 'load' else 'unload'}ing "
        f"{commodity.name} "
        f"{'from' if mission_type == 'load' else 'to'} **{station.upper()}** station in system "
        f"**{system.upper()}** : {profit}k per unit profit : "
        f"{demand} {'demand' if mission_type == 'load' else 'supply'} : {pads.upper()}-pads"
        f".{eta_text}"
    )
    return discord_text


def txt_create_reddit_title(carrier_data, legacy):
    reddit_title = (
        f"{'◄ LEGACY UNIVERSE ► : ' if legacy else ''}"
        f"P.T.N. TRADE MISSION: "
        f"P.T.N. News - Trade mission - {carrier_data.carrier_long_name} {carrier_data.carrier_identifier}" \
                   f" - {get_formatted_date_string()[0]}"
    )
    return reddit_title


def txt_create_reddit_body(carrier_data, mission_type, commodity, station, system, profit, pads, demand, eta_text, legacy):

    if mission_type == 'load':
        reddit_body = (
            f"    INCOMING WIDEBAND TRANSMISSION: P.T.N. CARRIER LOADING MISSION IN PROGRESS\n"
            f"{'**◄ LEGACY UNIVERSE ►**' if legacy else ''}"
            f"\n\n"
            f"**BUY FROM**: station **{station.upper()}** ({pads.upper()}-pads) in system **{system.upper()}**\n\n**COMMODITY**: "
            f"{commodity.name}\n\n&#x200B;\n\n**SELL TO**: Fleet Carrier **{carrier_data.carrier_long_name} "
            f"{carrier_data.carrier_identifier}{eta_text}**\n\n**PROFIT**: {profit}k/unit : {demand} "
            f"demand\n\n\n\n[Join us on Discord]({constants.REDDIT_DISCORD_LINK_URL}) for "
            f"mission updates and discussion, channel **#{carrier_data.discord_channel}**.")
    else:
        reddit_body = (
            f"    INCOMING WIDEBAND TRANSMISSION: P.T.N. CARRIER UNLOADING MISSION IN PROGRESS\n"
            f"{'**◄ LEGACY UNIVERSE ►** : ' if legacy else ''}"
            f"\n\n"
            f"**BUY FROM**: Fleet Carrier **{carrier_data.carrier_long_name} {carrier_data.carrier_identifier}{eta_text}**"
            f"\n\n**COMMODITY**: {commodity.name}\n\n&#x200B;\n\n**SELL TO**: station "
            f"**{station.upper()}** ({pads.upper()}-pads) in system **{system.upper()}**\n\n**PROFIT**: {profit}k/unit "
            f": {demand} supply\n\n\n\n[Join us on Discord]({constants.REDDIT_DISCORD_LINK_URL}) for mission updates"
            f" and discussion, channel **#{carrier_data.discord_channel}**.")
    return reddit_body




"""
OTHER
"""

# trio of helper functions to check a user's permission to run a command based on their roles, and return a helpful error if they don't have the correct role(s)
def getrole(ctx, id): # takes a Discord role ID and returns the role object
    role = discord.utils.get(ctx.guild.roles, id=id)
    return role

async def checkroles(ctx, permitted_role_ids):
    """
    Check if the user has at least one of the permitted roles to run a command
    """
    try: # hacky way to make this work with both slash and normal commands
        author_roles = ctx.author.roles
    except: # slash commands use interaction instead of ctx and user instead of author
        author_roles = ctx.user.roles
    permitted_roles = [getrole(ctx, role) for role in permitted_role_ids]
    print(author_roles)
    print(permitted_roles)
    permission = True if any(x in permitted_roles for x in author_roles) else False
    print(permission)
    if not permission:
        role_list = []
        for role in permitted_role_ids:
            role_list.append(f'<@&{role}> ')
            formatted_role_list = " • ".join(role_list)
        if len(permitted_roles)>1:
            embed=discord.Embed(description=f"**Permission denied**: You need one of the following roles to use this command:\n{formatted_role_list}", color=constants.EMBED_COLOUR_ERROR)
        else:
            embed=discord.Embed(description=f"**Permission denied**: You need the following role to use this command:\n{formatted_role_list}", color=constants.EMBED_COLOUR_ERROR)
        # hacky way to check whether we were sent an interaction object or a ctx object is to check attributes.
        # ctx has the author attribute, interaction does not, so we may as well use that since we already used it earlier
        await ctx.channel.send(embed=embed) if hasattr(ctx, 'author') else await ctx.response.send_message(embed=embed, ephemeral=True)
    return permission

def check_roles(permitted_role_ids):
    """
    Decorator used on a normal or slash command to enforce the command
    can only be users with a specific role(s)
    """
    def decorator(function):
        @wraps(function)
        async def wrapper(*args, **kwargs):
            permission = await checkroles(args[0], permitted_role_ids)
            if permission:
                return await function(*args, **kwargs)
            else:
                return
        return wrapper
    return decorator


async def check_channel(ctx, permitted_channel):
    """
    Check if the channel the command was run in, matches the channel it can only be run from
    """
    permitted = bot.get_channel(permitted_channel)
    if ctx.channel != permitted:
        # problem, wrong channel, no progress
        embed=discord.Embed(description=f"Sorry, you can only run this command out of: {permitted}.", color=constants.EMBED_COLOUR_ERROR)
        await ctx.channel.send(embed=embed) if hasattr(ctx, 'author') else await ctx.response.send_message(embed=embed, ephemeral=True)
        return False
    else:
        return True


def check_command_channel(permitted_channel):
    """
    Decorator used on a normal or slash command to enforce the command
    can only be run in specific channels
    """
    def decorator(function):
        @wraps(function)
        async def wrapper(*args, **kwargs):
            correct_channel = await check_channel(args[0], permitted_channel)
            if correct_channel:
                return await function(*args, **kwargs)
            else:
                return
        return wrapper
    return decorator


# function to stop and quit
def user_exit():
    sys.exit("User requested exit.")


async def lock_mission_channel():
    print("Attempting channel lock...")
    await carrier_channel_lock.acquire()
    print("Channel lock acquired.")

async def get_reddit():
    """
    Return reddit instance
    discord.py complains if an async resource is not initialized
    inside async
    """
    return asyncpraw.Reddit('bot1')

async def get_overwrite_perms():
    """
    Default permission set for set_permissions()
    """
    overwrite = discord.PermissionOverwrite()
    overwrite.read_messages = True
    overwrite.manage_channels = True
    overwrite.manage_roles = True
    overwrite.manage_webhooks = True
    overwrite.create_instant_invite = True
    overwrite.send_messages = True
    overwrite.embed_links = True
    overwrite.attach_files = True
    overwrite.add_reactions = True
    overwrite.external_emojis = True
    overwrite.manage_messages = True
    overwrite.read_message_history = True
    overwrite.use_application_commands = True
    return overwrite


async def get_guild():
    """
    Return bot guild instance for use in get_member()
    """
    return bot.get_guild(bot_guild_id)


"""
BOT COMMANDS
"""



bot = commands.Bot(command_prefix='m.', intents=discord.Intents.all())


@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    devchannel = bot.get_channel(dev_channel_id)
    embed = discord.Embed(title="MISSION ALERT BOT ONLINE", description=f"<@{bot.user.id}> connected, version **{version}**.", color=constants.EMBED_COLOUR_OK)
    embed.set_image(url=random.choice(hello_gifs))
    await devchannel.send(embed=embed)
    # sync slash commands
    try:
        bot.tree.copy_global_to(guild=guild_obj)
        await bot.tree.sync(guild=guild_obj)
        print("Synchronised bot tree.")
    except Exception as e:
        print(f"Tree sync failed: {e}.")

    # define our background tasks
    reddit_task = asyncio.create_task(_monitor_reddit_comments())
    # Check if any trade channels were not deleted before bot restart/stop
    cleanup_channels = await get_trade_channels_on_startup()
    for channel in cleanup_channels:
        asyncio.create_task(cleanup_trade_channel(channel))
    # start the lasttrade_cron loop.
    await lasttrade_cron.start()
    # start monitoring reddit comments
    await reddit_task


@bot.event
async def on_guild_channel_pins_update(channel, last_pin):
    """
    Delete the system message informing you a message was pinned in this channel
    Watches every public channel in the guild (discord)
    """
    async for msg in channel.history(limit=200):
        if msg.type is discord.MessageType.pins_add and msg.author == bot.user:
            await msg.delete()


# monitor reddit comments
async def _monitor_reddit_comments():
    print("Reddit monitor started")
    while True:
        try:
            # TODO: what happens if there's an error in this process, e.g. reddit is down?

            comment_channel = bot.get_channel(conf['REDDIT_CHANNEL'])
            # establish a comment stream to the subreddit using async praw
            reddit = await get_reddit()
            subreddit = await reddit.subreddit(to_subreddit)
            async for comment in subreddit.stream.comments(skip_existing=True):
                print(f"New reddit comment: {comment}. Is_submitter is {comment.is_submitter}")
                # ignore comments from the bot / post author
                if not comment.is_submitter:
                    # log some data
                    print(f"{comment.author} wrote:\n {comment.body}\nAt: {comment.permalink}\nIn: {comment.submission}")

                    # get a submission object so we can interrogate it for the parent post title
                    submission = await reddit.submission(comment.submission)

                    # lookup the parent post ID with the mission database
                    mission_db.execute(f"SELECT * FROM missions WHERE "
                                    f"reddit_post_id = '{comment.submission}' ")

                    print('DB command ran, go fetch the result')
                    mission_data = MissionData(mission_db.fetchone())

                    if not mission_data:
                        print("No match in mission DB, mission must be complete.")

                        embed = discord.Embed(title=f"{submission.title}",
                                            description=f"This mission is **COMPLETED**.\n\nComment by **{comment.author}**\n{comment.body}"
                                                        f"\n\nTo view this comment click here:\nhttps://www.reddit.com{comment.permalink}",
                                                        color=constants.EMBED_COLOUR_QU)

                    elif mission_data:
                        # mission is active, we'll get info from the db and ping the CCO
                        print(f'Found mission data: {mission_data}')

                        # now we need to lookup the carrier data in the db
                        carrier_data = find_carrier(mission_data.carrier_name, CarrierDbFields.longname.name)

                        # We can't easily moderate Reddit comments so we'll post it to a CCO-only channel

                        await comment_channel.send(f"<@{carrier_data.ownerid}>, your Reddit trade post has received a new comment:")
                        embed = discord.Embed(title=f"{submission.title}",
                                            description=f"This mission is **IN PROGRESS**.\n\nComment by **{comment.author}**\n{comment.body}"
                                                        f"\n\nTo view this comment click here:\nhttps://www.reddit.com{comment.permalink}",
                                                        color=constants.EMBED_COLOUR_REDDIT)

                    await comment_channel.send(embed=embed)
                    print("Sent comment to channel")
        except Exception as e:
            print(f"Error while monitoring {to_subreddit} for comments: {e}")
            spamchannel = bot.get_channel(bot_spam_id)
            await spamchannel.send(f"<@211891698551226368> error with Reddit monitoring: {e}") # this is a mention for Sihmm




#
#                       LOAD/UNLOAD COMMANDS
#

# load commands
@bot.command(name='load', help='Generate details for a loading mission and optionally broadcast.\n'
                               '\n'
                               'carrier_name_search_term should be a unique part of your carrier\'s name. (Use quotes if spaces are required)\n'
                               'commodity_name_partial should be a unique part of any commodity\'s name.\n'
                               'System and Station names should be enclosed in quotes if they contain spaces.\n'
                               'Profit should be expressed as a simple number e.g. enter 10 for 10k/unit profit.\n'
                               'Pad size should be expressed as L or M.\n'
                               'Demand should be expressed as an absolute number e.g. 20k, 20,000, etc.\n'
                               'ETA is optional and should be expressed as a number of minutes e.g. 15.\n'
                               'Case is automatically corrected for all inputs.')
@check_roles([certcarrier_role_id, trainee_role_id])
@check_command_channel(conf['MISSION_CHANNEL'])
async def load(ctx, carrier_name_search_term: str, commodity_search_term: str, system: str, station: str,
               profit: Union[int, float], pads: str, demand: str, eta: str = None):
    rp = False
    mission_type = 'load'
    legacy = False
    await gen_mission(ctx, carrier_name_search_term, commodity_search_term, system, station, profit, pads, demand,
                      rp, mission_type, eta, legacy)


@bot.command(name="loadrp", help='Same as load command but prompts user to enter roleplay text\n'
                                 'This is added to the Reddit comment as as a quote above the mission details\n'
                                 'and sent to the carrier\'s Discord channel in quote format if those options are '
                                 'chosen')
@check_roles([certcarrier_role_id, trainee_role_id])
@check_command_channel(conf['MISSION_CHANNEL'])
async def loadrp(ctx, carrier_name_search_term: str, commodity_search_term: str, system: str, station: str,
                 profit: Union[int, float], pads: str, demand: str, eta: str = None):
    rp = True
    mission_type = 'load'
    legacy = False
    await gen_mission(ctx, carrier_name_search_term, commodity_search_term, system, station, profit, pads, demand,
                      rp, mission_type, eta, legacy)


# legacy load commands
@bot.command(name='loadlegacy', help='Generate details for a LEGACY loading mission and optionally broadcast.\n'
                               '\n'
                               'carrier_name_search_term should be a unique part of your carrier\'s name. (Use quotes if spaces are required)\n'
                               'commodity_name_partial should be a unique part of any commodity\'s name.\n'
                               'System and Station names should be enclosed in quotes if they contain spaces.\n'
                               'Profit should be expressed as a simple number e.g. enter 10 for 10k/unit profit.\n'
                               'Pad size should be expressed as L or M.\n'
                               'Demand should be expressed as an absolute number e.g. 20k, 20,000, etc.\n'
                               'ETA is optional and should be expressed as a number of minutes e.g. 15.\n'
                               'Case is automatically corrected for all inputs.')
@check_roles([certcarrier_role_id, trainee_role_id])
@check_command_channel(conf['MISSION_CHANNEL'])
async def loadlegacy(ctx, carrier_name_search_term: str, commodity_search_term: str, system: str, station: str,
               profit: Union[int, float], pads: str, demand: str, eta: str = None):
    rp = False
    mission_type = 'load'
    legacy = True
    await gen_mission(ctx, carrier_name_search_term, commodity_search_term, system, station, profit, pads, demand,
                      rp, mission_type, eta, legacy)


@bot.command(name="loadrplegacy", help='Same as load command but prompts user to enter roleplay text\n'
                                 'This is added to the Reddit comment as as a quote above the mission details\n'
                                 'and sent to the carrier\'s Discord channel in quote format if those options are '
                                 'chosen')
@check_roles([certcarrier_role_id, trainee_role_id])
@check_command_channel(conf['MISSION_CHANNEL'])
async def loadrplegacy(ctx, carrier_name_search_term: str, commodity_search_term: str, system: str, station: str,
                 profit: Union[int, float], pads: str, demand: str, eta: str = None):
    rp = True
    mission_type = 'load'
    legacy = True
    await gen_mission(ctx, carrier_name_search_term, commodity_search_term, system, station, profit, pads, demand,
                      rp, mission_type, eta, legacy)

# unload commands
@bot.command(name='unload', help='Generate details for an unloading mission.\n'
                                 '\n'
                                 'carrier_name_search_term should be a unique part of your carrier\'s name. (Use quotes if spaces are required)\n'
                                 'commodity_name_partial should be a unique part of any commodity\'s name.\n'
                                 'System and Station names should be enclosed in quotes if they contain spaces.\n'
                                 'Profit should be expressed as a simple number e.g. enter 10 for 10k/unit profit.\n'
                                 'Pad size should be expressed as L or M.\n'
                                 'Supply should be expressed as an absolute number e.g. 20k, 20,000, etc.\n'
                                 'ETA is optional and should be expressed as a number of minutes e.g. 15.\n'
                                 'Case is automatically corrected for all inputs.')
@check_roles([certcarrier_role_id, trainee_role_id])
@check_command_channel(conf['MISSION_CHANNEL'])
async def unload(ctx, carrier_name_search_term: str, commodity_search_term: str, system: str, station: str,
                 profit: Union[int, float], pads: str, supply: str, eta: str = None):
    rp = False
    mission_type = 'unload'
    legacy = False
    await gen_mission(ctx, carrier_name_search_term, commodity_search_term, system, station, profit, pads, supply, rp,
                      mission_type, eta, legacy)


@bot.command(name="unloadrp", help='Same as unload command but prompts user to enter roleplay text\n'
                                   'This is added to the Reddit comment as as a quote above the mission details\n'
                                   'and sent to the carrier\'s Discord channel in quote format if those options are '
                                   'chosen')
@check_roles([certcarrier_role_id, trainee_role_id])
@check_command_channel(conf['MISSION_CHANNEL'])
async def unloadrp(ctx, carrier_name_search_term: str, commodity_search_term: str, system: str, station: str,
                   profit: Union[int, float], pads: str, demand: str, eta: str = None):

    rp = True
    mission_type = 'unload'
    legacy = False
    await gen_mission(ctx, carrier_name_search_term, commodity_search_term, system, station, profit, pads, demand,
                      rp, mission_type, eta, legacy)

# legacy unload commands
@bot.command(name='unloadlegacy', help='Generate details for a LEGACY unloading mission.\n'
                                 '\n'
                                 'carrier_name_search_term should be a unique part of your carrier\'s name. (Use quotes if spaces are required)\n'
                                 'commodity_name_partial should be a unique part of any commodity\'s name.\n'
                                 'System and Station names should be enclosed in quotes if they contain spaces.\n'
                                 'Profit should be expressed as a simple number e.g. enter 10 for 10k/unit profit.\n'
                                 'Pad size should be expressed as L or M.\n'
                                 'Supply should be expressed as an absolute number e.g. 20k, 20,000, etc.\n'
                                 'ETA is optional and should be expressed as a number of minutes e.g. 15.\n'
                                 'Case is automatically corrected for all inputs.')
@check_roles([certcarrier_role_id, trainee_role_id])
@check_command_channel(conf['MISSION_CHANNEL'])
async def unload(ctx, carrier_name_search_term: str, commodity_search_term: str, system: str, station: str,
                 profit: Union[int, float], pads: str, supply: str, eta: str = None):
    rp = False
    mission_type = 'unload'
    legacy = True
    await gen_mission(ctx, carrier_name_search_term, commodity_search_term, system, station, profit, pads, supply, rp,
                      mission_type, eta, legacy)


@bot.command(name="unloadrplegacy", help='Same as unload command but prompts user to enter roleplay text\n'
                                   'This is added to the Reddit comment as as a quote above the mission details\n'
                                   'and sent to the carrier\'s Discord channel in quote format if those options are '
                                   'chosen')
@check_roles([certcarrier_role_id, trainee_role_id])
@check_command_channel(conf['MISSION_CHANNEL'])
async def unloadrp(ctx, carrier_name_search_term: str, commodity_search_term: str, system: str, station: str,
                   profit: Union[int, float], pads: str, demand: str, eta: str = None):
    rp = True
    mission_type = 'unload'
    legacy = True
    await gen_mission(ctx, carrier_name_search_term, commodity_search_term, system, station, profit, pads, demand,
                      rp, mission_type, eta, legacy)


# mission generator called by loading/unloading commands
async def gen_mission(ctx, carrier_name_search_term: str, commodity_search_term: str, system: str, station: str,
                      profit: Union[int, float], pads: str, demand: str, rp: str, mission_type: str,
                      eta: str, legacy):
    current_channel = ctx.channel

    print(f'Mission generation type: {mission_type} with RP: {rp}, requested by {ctx.author}. Request triggered from '
          f'channel {current_channel}.')

    if pads.upper() not in ['M', 'L']:
        # In case a user provides some junk for pads size, gate it
        print(f'Exiting mission generation requested by {ctx.author} as pad size is invalid, provided: {pads}')
        return await ctx.send(f'Sorry, your pad size is not L or M. Provided: {pads}. Mission generation cancelled.')

    # check if commodity can be found, exit gracefully if not
    gen_mission.returnflag = False
    commodity_data = await find_commodity(commodity_search_term, ctx)
    if not gen_mission.returnflag:
        return # we've already given the user feedback on why there's a problem, we just want to quit gracefully now
    if not commodity_data:
        raise ValueError('Missing commodity data')

    # check if the carrier can be found, exit gracefully if not
    carrier_data = find_carrier(carrier_name_search_term, CarrierDbFields.longname.name)
    if not carrier_data:
        return await ctx.send(f"No carrier found for {carrier_name_search_term}. You can use `/find` or `/owner` to search for carrier names.")

    # check carrier isn't already on a mission
    mission_data = find_mission(carrier_data.carrier_long_name, "carrier")
    if mission_data:
        embed = discord.Embed(title="Error",
                            description=f"{mission_data.carrier_name} is already on a mission, please "
                                        f"use **m.done** to mark it complete before starting a new mission.",
                            color=constants.EMBED_COLOUR_ERROR)
        await ctx.send(embed=embed)
        return  # We want to stop here, so go exit out

    # check if the carrier has an associated image
    if os.path.isfile(f"images/{carrier_data.carrier_short_name}.png"):
        print("Carrier mission image found, checking size...")
        image = Image.open(f"images/{carrier_data.carrier_short_name}.png")
        image_is_good = image.size == (506, 285)
    else:
        image_is_good = False
    if not image_is_good:
        print(f"No valid carrier image found for {carrier_data.carrier_long_name}")
        # send the user to upload an image
        embed = discord.Embed(description="**YOUR FLEET CARRIER MUST HAVE A VALID MISSION IMAGE TO CONTINUE**.", color=constants.EMBED_COLOUR_QU)
        await ctx.send(embed=embed)
        await carrier_image(ctx, carrier_data.carrier_long_name)
        # OK, let's see if they fixed the problem. Once again we check the image exists and is the right size
        if os.path.isfile(f"images/{carrier_data.carrier_short_name}.png"):
            print("Found an image file, checking size")
            image = Image.open(f"images/{carrier_data.carrier_short_name}.png")
            image_is_good = image.size == (506, 285)
        else:
            image_is_good = False
        if not image_is_good:
            print("Still no good image, aborting")
            embed = discord.Embed(description="**ERROR**: You must have a valid mission image to continue.", color=constants.EMBED_COLOUR_ERROR)
            await ctx.send(embed=embed)
            return

    # TODO: This method is way too long, break it up into logical steps.

    try: # this try/except pair is to try and ensure the channel lock is released if something breaks during mission gen
         # otherwise the bot freezes next time the lock is attempted

        # None-strings, should hopefully not break the database. If it does revert these to 'NULL'
        rp_text = None
        reddit_post_id = None
        reddit_post_url = None
        reddit_comment_id = None
        reddit_comment_url = None
        discord_alert_id = None
        mission_temp_channel_id = None
        check_characters = None
        edmc_off = False


        eta_text = f" (ETA {eta} minutes)" if eta else ""

        embed = discord.Embed(title="Generating and fetching mission alerts...", color=constants.EMBED_COLOUR_QU)
        message_gen = await ctx.send(embed=embed)

        def check_confirm(message):
            # use all to verify that all the characters in the message content are present in the allowed list (dtrx).
            # Anything outwith this grouping will cause all to fail. Use set to throw away any duplicate objects.
            # not sure if the msg.content can ever be None, but lets gate it anyway
            return message.content and message.author == ctx.author and message.channel == ctx.channel and \
                all(character in check_characters for character in set(message.content.lower()))

        def check_rp(message):
            return message.author == ctx.author and message.channel == ctx.channel

        async def default_timeout_message(location):
            await ctx.send(f"**Mission generation cancelled (waiting too long for user input)** ({location})")


        # gen_mission.returnflag = False
        # mission_temp_channel_id = await create_mission_temp_channel(ctx, carrier_data.discord_channel, carrier_data.ownerid)
        # mission_temp_channel = bot.get_channel(mission_temp_channel_id)
        # # flag is set to True if mission channel creation is successful
        # if not gen_mission.returnflag:
        #     return # we've already notified the user

        # beyond this point any exits need to release the channel lock

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
                await default_timeout_message('rp')
                return

        # Options that should create a mission db entry will change this to True
        submit_mission = False

        # generate the mission elements

        file_name = await create_carrier_mission_image(carrier_data, commodity_data, system, station, profit, pads, demand,
                                                mission_type)
        discord_text = txt_create_discord(carrier_data, mission_type, commodity_data, station, system, profit, pads,
                        demand, eta_text, mission_temp_channel_id, edmc_off, legacy)
        print("Generated discord elements")
        reddit_title = txt_create_reddit_title(carrier_data, legacy)
        reddit_body = txt_create_reddit_body(carrier_data, mission_type, commodity_data, station, system, profit, pads,
                                            demand, eta_text, legacy)
        print("Generated Reddit elements")

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
        print("Output check displayed")

        embed = discord.Embed(title="Where would you like to send the alert?",
                            description="(**d**)iscord, (**r**)eddit, (**t**)ext for copy/pasting or (**x**) to cancel\n"
                            "You can also use (**n**) to also notify PTN Haulers, and (**e**) to flag your mission as EDMC-OFF.",
                            color=constants.EMBED_COLOUR_QU)
        embed.set_footer(text="Enter all that apply, e.g. **drn** will send alerts to Discord and Reddit and notify PTN Haulers.")
        message_confirm = await ctx.send(embed=embed)
        print("Prompted user for alert destination")

        try:
            check_characters = 'dertnx'
            msg = await bot.wait_for("message", check=check_confirm, timeout=30)
            edmc_off = True if "e" in msg.content.lower() else False

            if "x" in msg.content.lower():
                # immediately stop if there's an x anywhere in the message, even if there are other proper inputs
                message_cancelled = await ctx.send("**Mission creation cancelled.**")
                await msg.delete()
                await message_confirm.delete()
                print("User cancelled mission generation")
                return

            if "t" in msg.content.lower():
                print("User used option t")
                embed = discord.Embed(title="Trade Alert (Discord)", description=f"`{discord_text}`",
                                    color=constants.EMBED_COLOUR_DISCORD)
                await ctx.send(embed=embed)
                if rp:
                    embed = discord.Embed(title="Roleplay Text (Discord)", description=f"`>>> {rp_text}`",
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
                await ctx.send(file=discord.File(file_name))

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
                print("User used option d, creating mission channel")

                mission_temp_channel_id = await create_mission_temp_channel(ctx, carrier_data.discord_channel, carrier_data.ownerid, carrier_data.carrier_short_name)
                mission_temp_channel = bot.get_channel(mission_temp_channel_id)

                # Recreate this text since we know the channel id
                discord_text = txt_create_discord(carrier_data, mission_type, commodity_data, station, system, profit, pads,
                                demand, eta_text, mission_temp_channel_id, edmc_off, legacy)
                message_send = await ctx.send("**Sending to Discord...**")
                try:
                    # send trade alert to trade alerts channel, or to wine alerts channel if loading wine
                    if commodity_data.name.title() == "Wine":
                        if mission_type == 'load':
                            channel = bot.get_channel(wine_alerts_loading_id)
                            channelId = wine_alerts_loading_id
                        else:   # unloading block
                            channel = bot.get_channel(wine_alerts_unloading_id)
                            channelId = wine_alerts_unloading_id
                    else:
                        if legacy:
                            channel = bot.get_channel(legacy_alerts_id)
                            channelId = legacy_alerts_id
                        else:
                            channel = bot.get_channel(trade_alerts_id)
                            channelId = trade_alerts_id

                    if mission_type == 'load':
                        embed = discord.Embed(description=discord_text, color=constants.EMBED_COLOUR_LOADING)
                    else:
                        embed = discord.Embed(description=discord_text, color=constants.EMBED_COLOUR_UNLOADING)
                    embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar)

                    trade_alert_msg = await channel.send(embed=embed)
                    discord_alert_id = trade_alert_msg.id

                    discord_file = discord.File(file_name, filename="image.png")

                    embed_colour = constants.EMBED_COLOUR_LOADING if mission_type == 'load' \
                        else constants.EMBED_COLOUR_UNLOADING
                    embed = discord.Embed(title="P.T.N TRADE MISSION STARTING",
                                        description=f">>> {rp_text}" if rp else "", color=embed_colour)

                    embed.add_field(name="Destination", value=f"Station: {station.upper()}\nSystem: {system.upper()}", inline=True)
                    embed.add_field(name="Carrier Owner", value=f"<@{carrier_data.ownerid}>")
                    if eta:
                        embed.add_field(name="ETA", value=f"{eta} minutes", inline=False)

                    embed.set_image(url="attachment://image.png")
                    stock_field = f'\n;stock {carrier_data.carrier_short_name} will show carrier market data'
                    embed.set_footer(
                        text=
                             f"m.complete will mark this mission complete"
                             f"{stock_field if not legacy else ''}"
                             f"\n/info will show this carrier's details")
                    # pin the carrier trade msg sent by the bot
                    pin_msg = await mission_temp_channel.send(file=discord_file, embed=embed)
                    await pin_msg.pin()
                    embed = discord.Embed(title=f"Discord trade alerts sent for {carrier_data.carrier_long_name}",
                                        description=f"Check <#{channelId}> for trade alert and "
                                                    f"<#{mission_temp_channel_id}> for image.",
                                        color=constants.EMBED_COLOUR_DISCORD)
                    await ctx.send(embed=embed)
                    await message_send.delete()
                    submit_mission = True
                except Exception as e:
                    print(f"Error sending to Discord: {e}")
                    await ctx.send(f"Error sending to Discord: {e}\nAttempting to continue with mission gen...")

            if "r" in msg.content.lower() and not edmc_off:
                print("User used option r")
                # profit is a float, not an int.
                if float(profit) < 10:
                    print(f'Not posting the mission from {ctx.author} to reddit due to low profit margin <10k/t.')
                    await ctx.send(f'Skipped Reddit posting due to profit margin of {profit}k/t being below the PTN 10k/t '
                                f'minimum. (Did you try to post a Wine load?)')
                else:
                    message_send = await ctx.send("**Sending to Reddit...**")

                    try:

                        # post to reddit
                        reddit = await get_reddit()
                        subreddit = await reddit.subreddit(to_subreddit)
                        submission = await subreddit.submit_image(reddit_title, image_path=file_name,
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
                        upvote_message = await channel.send(embed=embed)
                        emoji = bot.get_emoji(upvote_emoji)
                        await upvote_message.add_reaction(emoji)
                        submit_mission = True
                    except Exception as e:
                        print(f"Error posting to Reddit: {e}")
                        await ctx.send(f"Error posting to Reddit: {e}\nAttempting to continue with rest of mission gen...")

            if "n" in msg.content.lower() and "d" in msg.content.lower():
                print("User used option n")

                ping_role_id = legacy_hauler_role_id if legacy else hauler_role_id
                await mission_temp_channel.send(f"<@&{ping_role_id}>: {discord_text}")

                embed = discord.Embed(title=f"Mission notification sent for {carrier_data.carrier_long_name}",
                            description=f"Pinged <@&{ping_role_id}> in <#{mission_temp_channel_id}>",
                            color=constants.EMBED_COLOUR_DISCORD)
                await ctx.send(embed=embed)

            if "e" in msg.content.lower() and "d" in msg.content.lower():
                print('Sending EDMC OFF messages to haulers')
                embed = discord.Embed(title='PLEASE STOP ALL 3RD PARTY SOFTWARE: EDMC, EDDISCOVERY, ETC',
                        description=("Maximising our haulers' profits for this mission means keeping market data at this station"
                                 " **a secret**! For this reason **please disable/exit all journal reporting plugins/programs**"
                                 " and leave them off until all missions at this location are complete. Thanks CMDRs!"),
                        color=constants.EMBED_COLOUR_REDDIT)
                edmc_file = discord.File(f"images/system/edmc_off_{random.randint(1,2)}.png", filename="image.png")

                embed.set_image(url="attachment://image.png")
                pin_edmc = await mission_temp_channel.send(file=edmc_file, embed=embed)
                await pin_edmc.pin()

                embed = discord.Embed(title=f"EDMC OFF messages sent", description='Reddit posts will be skipped',
                            color=constants.EMBED_COLOUR_DISCORD)
                await ctx.send(embed=embed)

                print('Reacting to #official-trade-alerts message with EDMC OFF')
                for r in ["🇪","🇩","🇲","🇨","📴"]:
                    await trade_alert_msg.add_reaction(r)

        except asyncio.TimeoutError:
            await default_timeout_message('notification_type_decision')
            try:
                if mission_temp_channel_id:
                    carrier_channel_lock.release()
                    print("Channel lock released")
            finally:
                if mission_temp_channel_id:
                    await remove_carrier_channel(mission_temp_channel_id, seconds_short)
            return

        print("All options worked through, now clean up")

        # now clear up by deleting the prompt message and user response
        try:
            await msg.delete()
            await message_confirm.delete()
        except Exception as e:
            print(f"Error during clearup: {e}")
            await ctx.send(f"Oops, error detected: {e}\nAttempting to continue with mission gen.")

        if submit_mission:
            await mission_add(ctx, carrier_data, commodity_data, mission_type, system, station, profit, pads, demand,
                        rp_text, reddit_post_id, reddit_post_url, reddit_comment_id, reddit_comment_url, discord_alert_id, mission_temp_channel_id)
            await mission_generation_complete(ctx, carrier_data, message_pending, eta_text)
        cleanup_temp_image_file(file_name)
        if mission_temp_channel_id:
            await mark_cleanup_channel(mission_temp_channel_id, 0)

        print("Reached end of mission generator")
        return
    except Exception as e:
        await ctx.send("Oh no! Something went wrong :( Mission generation aborted.")
        await ctx.send(e)
        print("Something went wrong with mission generation :(")
        print(e)
        carrier_channel_lock.release()
        if mission_temp_channel_id:
            await remove_carrier_channel(mission_temp_channel_id, seconds_short)




async def create_mission_temp_channel(ctx, discord_channel, owner_id, shortname):
    # create the carrier's channel for the mission

    # first check whether channel already exists

    mission_temp_channel = discord.utils.get(ctx.guild.channels, name=discord_channel)

    # we need to lock the channel to stop it being deleted mid process
    print("Waiting for Mission Generator channel lock...")
    lockwait_msg = await ctx.send("Waiting for channel lock to become available...")
    try:
        await asyncio.wait_for(lock_mission_channel(), timeout=10)
    except asyncio.TimeoutError:
        print("We couldn't get a channel lock after 10 seconds, let's abort rather than wait around.")
        return await ctx.send("Error: Channel lock could not be acquired, please try again. If the problem persists please contact an Admin.")

    await lockwait_msg.delete()

    if mission_temp_channel:
        # channel exists, so reuse it
        mission_temp_channel_id = mission_temp_channel.id
        await ctx.send(f"Found existing mission channel <#{mission_temp_channel_id}>.")
        print(f"Found existing {mission_temp_channel}")
    else:
        # channel does not exist, create it

        topic = f"Use \";stock {shortname}\" to retrieve stock levels for this carrier."

        category = discord.utils.get(ctx.guild.categories, id=trade_cat_id)
        mission_temp_channel = await ctx.guild.create_text_channel(discord_channel, category=category, topic=topic)
        mission_temp_channel_id = mission_temp_channel.id
        print(f"Created {mission_temp_channel}")

    print(f'Channels: {ctx.guild.channels}')

    if not mission_temp_channel:
        raise EnvironmentError(f'Could not create carrier channel {discord_channel}')

    # we made it this far, we can change the returnflag
    gen_mission.returnflag = True

    # find carrier owner as a user object
    guild = await get_guild()
    try:
        member = await guild.fetch_member(owner_id)
        print(f"Owner identified as {member.display_name}")
    except:
        raise EnvironmentError(f'Could not find Discord user matching ID {owner_id}')

    # add owner to channel permissions
    overwrite = await get_overwrite_perms()
    try:
        await mission_temp_channel.set_permissions(member, overwrite=overwrite)
        print(f"Set permissions for {member} in {mission_temp_channel}")
    except Forbidden:
        raise EnvironmentError(f"Could not set channel permissions in {mission_temp_channel}, reason: Bot does not have permissions to edit channel specific permissions.")
    except NotFound:
        raise EnvironmentError(f"Could not set channel permissions in {mission_temp_channel}, reason: The role or member being edited is not part of the guild.")
    except HTTPException:
        raise EnvironmentError(f"Could not set channel permissions in {mission_temp_channel}, reason: Editing channel specific permissions failed.")
    except (TypeError, ValueError):
        raise EnvironmentError(f"Could not set channel permissions in {mission_temp_channel}, reason: The overwrite parameter invalid or the target type was not Role or Member.")
    except:
        raise EnvironmentError(f'Could not set channel permissions in {mission_temp_channel}')

    # send the channel back to the mission generator as a channel id

    return mission_temp_channel_id


def cleanup_temp_image_file(file_name):
    """
    Takes an input file path and removes it.

    :param str file_name: The file path
    :returns: None
    """
    # Now we delete the temp file, clean up after ourselves!
    try:
        print(f'Deleting the temp file at: {file_name}')
        os.remove(file_name)
    except Exception as e:
        print(f'There was a problem removing the temp image file located {file_name}')
        print(e)


#
#                       MISSION DB
#
# add mission to DB, called from mission generator
async def mission_add(ctx, carrier_data, commodity_data, mission_type, system, station, profit, pads, demand,
                      rp_text, reddit_post_id, reddit_post_url, reddit_comment_id, reddit_comment_url, discord_alert_id, mission_temp_channel_id):
    backup_database('missions')  # backup the missions database before going any further

    print("Called mission_add to write to database")
    mission_db.execute(''' INSERT INTO missions VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ''', (
        carrier_data.carrier_long_name, carrier_data.carrier_identifier, mission_temp_channel_id,
        commodity_data.name.title(), mission_type.lower(), system.title(), station.title(), profit, pads.upper(),
        demand, rp_text, reddit_post_id, reddit_post_url, reddit_comment_id, reddit_comment_url, discord_alert_id
    ))
    missions_conn.commit()
    print("Mission added to db")

    print("Updating last trade timestamp for carrier")
    carrier_db.execute(''' UPDATE carriers SET lasttrade=strftime('%s','now') WHERE p_ID=? ''', ( [ carrier_data.pid ] ))
    carriers_conn.commit()

    # now we can release the channel lock
    if mission_temp_channel_id:
        carrier_channel_lock.release()
        print("Channel lock released")
    return

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
    print("Mission generation complete")
    return


# list active carrier trade mission from DB
@bot.command(name='ission', help="Show carrier's active trade mission.")
async def ission(ctx):

    # this is the spammy version of the command, prints details to open channel

    # take a note of the channel name
    msg_ctx_name = ctx.channel.name

    carrier_data = find_carrier(msg_ctx_name, "discordchannel")
    embed = await _is_carrier_channel(carrier_data)

    if not embed:
        embed = await _is_mission_active_embed(carrier_data)

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


# find what fleet carriers are owned by a user - private slash command
@bot.tree.command(name="owner",
    description="Private command: Use with @User to find out what fleet carriers that user owns.", guild=guild_obj)
async def _owner(interaction: discord.Interaction, owner: discord.Member):

    try:
        # look for matches for the owner ID in the carrier DB
        carrier_list = find_carriers_mult(owner.id, CarrierDbFields.ownerid.name)

        if not carrier_list:
            await interaction.response.send_message(f"No carriers found owned by <@{owner.id}>", ephemeral=True)
            return print(f"No carriers found for owner {owner.id}")

        embed = discord.Embed(description=f"Showing registered Fleet Carriers owned by <@{owner.id}>:",
                                color=constants.EMBED_COLOUR_OK)

        for carrier_data in carrier_list:
            embed.add_field(name=f"{carrier_data.carrier_long_name} ({carrier_data.carrier_identifier})",
                            value=f"Last Trade: <t:{carrier_data.lasttrade}> (<t:{carrier_data.lasttrade}:R>)",
                            inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except TypeError as e:
        print('Error: {}'.format(e))


# mission slash command - private, non spammy
@bot.tree.command(name="mission",
    description="Private command: Use in a Fleet Carrier's channel to display its current mission.", guild=guild_obj)
async def _mission(interaction: discord.Interaction):

    print(f"{interaction.user} asked for active mission in <#{interaction.channel}> (used /mission)")

    # take a note of the channel name
    msg_channel_name = interaction.channel.name

    carrier_data = find_carrier(msg_channel_name, "discordchannel")
    embed = await _is_carrier_channel(carrier_data)

    if not embed:
        embed = await _is_mission_active_embed(carrier_data)

    await interaction.response.send_message(embed=embed, ephemeral=True)
    return






# list all active carrier trade missions from DB
@bot.command(name='issions', help='List all active trade missions.')
async def issions(ctx):

    print(f'User {ctx.author} asked for all active missions.')

    co_role = discord.utils.get(ctx.guild.roles, id=certcarrier_role_id)
    print(f'Check if user has role: "{co_role}"')
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

# missions slash command - private, non-spammy
@bot.tree.command(name="missions",
    description="Private command: Display all missions in progress.", guild=guild_obj)
async def _missions(interaction: discord.Interaction):

    print(f'User {interaction.user} asked for all active missions via /missions in {interaction.channel}.')

    print(f'Generating full unloading mission list requested by: {interaction.user}')
    mission_db.execute('''SELECT * FROM missions WHERE missiontype="unload";''')
    unload_records = [MissionData(mission_data) for mission_data in mission_db.fetchall()]

    mission_db.execute('''SELECT * FROM missions WHERE missiontype="load";''')
    print(f'Generating full loading mission list requested by: {interaction.user}')
    load_records = [MissionData(mission_data) for mission_data in mission_db.fetchall()]

    trade_channel = bot.get_channel(trade_alerts_id)
    number_of_missions = len(load_records) + len(unload_records)

    description_text = f'For full details of all current trade missions follow the link to <#{trade_channel.id}>'
    if not number_of_missions:
        description_text = f'Currently no active missions listed in <#{trade_channel.id}>'

    embed = discord.Embed(
        title=f"{number_of_missions} P.T.N Fleet Carrier missions in progress:",
        description=description_text,
        color=constants.EMBED_COLOUR_LOADING
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

    if not number_of_missions:
        return
    else:

        embed = discord.Embed(title=f"{len(load_records)} P.T.N Fleet Carrier LOADING missions in progress:",
                            color=constants.EMBED_COLOUR_LOADING)
        embed = _format_missions_embedd(load_records, embed)
        await interaction.followup.send(embed=embed, ephemeral=True)

        embed = discord.Embed(title=f"{len(unload_records)} P.T.N Fleet Carrier UNLOADING missions in progress:",
                            color=constants.EMBED_COLOUR_UNLOADING)
        embed = _format_missions_embedd(unload_records, embed)
        await interaction.followup.send(embed=embed, ephemeral=True)


# CO command to quickly mark mission as complete, optionally send some RP text
@bot.command(name='done', help='Marks a mission as complete for specified carrier.\n\n'
                               'Deletes trade alert in Discord and sends messages to carrier channel, reddit and owner if '
                               'appropriate.\n\nAnything after the carrier name will be treated as a '
                               'quote to be sent along with the completion notice. This can be used for RP if desired.')
@check_roles([certcarrier_role_id, trainee_role_id, rescarrier_role_id])
@check_command_channel(conf['MISSION_CHANNEL'])
async def done(ctx, carrier_name_search_term: str, *, rp: str = None):

    current_channel = ctx.channel

    print(f'Request received from {ctx.author} to mark the mission of {carrier_name_search_term} as done from channel: '
          f'{current_channel}')

    mission_data = find_mission(carrier_name_search_term, "carrier")
    if not mission_data:
        embed = discord.Embed(
            description=f"**ERROR**: no trade missions found for carriers matching \"**{carrier_name_search_term}\"**.",
            color=constants.EMBED_COLOUR_ERROR)
        await ctx.send(embed=embed)

    else:
        # fill in some info for messages
        desc_msg = f"> {rp}\n" if rp else ""
        reddit_complete_text = f"    INCOMING WIDEBAND TRANSMISSION: P.T.N. CARRIER MISSION UPDATE\n\n**{mission_data.carrier_name}** mission complete. o7 CMDRs!\n\n{desc_msg}"
        discord_complete_embed = discord.Embed(title=f"{mission_data.carrier_name} MISSION COMPLETE", description=f"{desc_msg}",
                                  color=constants.EMBED_COLOUR_OK)
        discord_complete_embed.set_footer(text=f"This mission channel will be removed in {seconds_long//60} minutes.")

        await _cleanup_completed_mission(ctx, mission_data, reddit_complete_text, discord_complete_embed, desc_msg)



# clean up a completed mission
async def _cleanup_completed_mission(ctx, mission_data, reddit_complete_text, discord_complete_embed, desc_msg):

        mission_channel = bot.get_channel(mission_data.channel_id)
        mission_gen_channel = bot.get_channel(conf['MISSION_CHANNEL'])
        if ctx.channel.id == mission_gen_channel.id: # tells us whether m.done was used or m.complete
            m_done = True
            print("Processing mission complete by m.done")
        else:
            m_done = False
            print("Processing mission complete by m.complete")

        backup_database('missions')  # backup the missions database before going any further

        # delete Discord trade alert
        print("Delete Discord trade alert...")
        if mission_data.discord_alert_id and mission_data.discord_alert_id != 'NULL':
            try:  # try in case it's already been deleted, which doesn't matter to us in the slightest but we don't
                # want it messing up the rest of the function

                # first check if it's Wine, in which case it went to the booze cruise channel
                if mission_data.commodity.title() == "Wine":
                    if mission_data.mission_type == 'load':
                        alert_channel = bot.get_channel(wine_alerts_loading_id)
                    else:
                        alert_channel = bot.get_channel(wine_alerts_unloading_id)
                else:
                    alert_channel = bot.get_channel(trade_alerts_id)

                discord_alert_id = mission_data.discord_alert_id

                try: # shitty hacky message of incorporating legacy trades without extra DB fields
                    msg = await alert_channel.fetch_message(discord_alert_id)
                    await msg.delete()
                except: # if it can't find a message in the normal channel it'll look in legacy instead
                    alert_channel = bot.get_channel(legacy_alerts_id)
                    msg = await alert_channel.fetch_message(discord_alert_id)
                    await msg.delete()

            except:
                print(f"Looks like this mission alert for {mission_data.carrier_name} was already deleted"
                      f" by someone else. We'll keep going anyway.")

            # send Discord carrier channel updates
            # try in case channel already deleted
            try:
                await mission_channel.send(embed=discord_complete_embed)
            except:
                print(f"Unable to send completion message for {mission_data.carrier_name}, maybe channel deleted?")

        # add comment to Reddit post
        print("Add comment to Reddit post...")
        if mission_data.reddit_post_id and mission_data.reddit_post_id != 'NULL':
            try:  # try in case Reddit is down
                reddit_post_id = mission_data.reddit_post_id
                reddit = await get_reddit()
                await reddit.subreddit(to_subreddit)
                submission = await reddit.submission(reddit_post_id)
                await submission.reply(reddit_complete_text)
                # mark original post as spoiler, change its flair
                await submission.flair.select(flair_mission_stop)
                await submission.mod.spoiler()
            except:
                await ctx.send("Failed updating Reddit :(")

        # delete mission entry from db
        print("Remove from mission database...")
        mission_db.execute(f'''DELETE FROM missions WHERE carrier LIKE (?)''', ('%' + mission_data.carrier_name + '%',))
        missions_conn.commit()

        await clean_up_pins(mission_channel)

        # command feedback
        print("Send command feedback to user")
        spamchannel = bot.get_channel(bot_spam_id)
        embed = discord.Embed(title=f"Mission complete for {mission_data.carrier_name}",
                              description=f"{ctx.author} marked the mission complete in #{ctx.channel.name}",
                              color=constants.EMBED_COLOUR_OK)
        await spamchannel.send(embed=embed)
        if m_done:
            # notify user in mission gen channel
            embed = discord.Embed(title=f"Mission complete for {mission_data.carrier_name}",
                                  description=f"{desc_msg}",
                                  color=constants.EMBED_COLOUR_OK)
            embed.set_footer(text="Updated any sent alerts and removed from mission list.")
            await ctx.send(embed=embed)

        # notify owner if not command author
        carrier_data = find_carrier(mission_data.carrier_name, CarrierDbFields.longname.name)
        if not ctx.author.id == carrier_data.ownerid:
            print("Notify carrier owner")
            # notify in channel - not sure this is needed anymore, leaving out for now
            # await ctx.send(f"Notifying carrier owner: <@{carrier_data.ownerid}>")

            # notify by DM
            owner = await bot.fetch_user(carrier_data.ownerid)
            #chnaged to if there is rp text not if it was m.done
            if desc_msg != "":
                """
                desc_msg converts rp text received by m.done into a format that can be inserted directly into messages
                without having to change the message's format depending on whether it exists or not. This was primarily
                intended for CCOs to be able to send a message to their channel via the bot on mission completion.

                Now it's pulling double-duty as a way for other CCOs to notify the owner why they used m.done on a
                mission that wasn't theirs. In this case it's still useful for that information to be sent to the channel
                (e.g. "Supply exhausted", "tick changed prices", etc)

                desc_msg is "" if received from empty rp argument, so reason converts it to None if empty and adds a line break.
                This can probably be reworked to be neater and use fewer than 3 separate variables for one short message in the future.
                """
                reason = f"\n{desc_msg}" if desc_msg else None
                await owner.send(f"Ahoy CMDR! {ctx.author.display_name} has concluded the trade mission for your Fleet Carrier **{carrier_data.carrier_long_name}**. **Reason given**: {reason}\nIts mission channel will be removed in {seconds_long//60} minutes unless a new mission is started.")
            else:
                await owner.send(f"Ahoy CMDR! The trade mission for your Fleet Carrier **{carrier_data.carrier_long_name}** has been marked as complete by {ctx.author.display_name}. Its mission channel will be removed in {seconds_long//60} minutes unless a new mission is started.")

        # remove channel
        await mark_cleanup_channel(mission_data.channel_id, 1)
        await remove_carrier_channel(mission_data.channel_id, seconds_long)

        return


async def mark_cleanup_channel(mission_channel_id, status):
    """
    Create or update entry in the channel_cleanup table
    """
    insert_stmt = f"""
        INSERT INTO channel_cleanup
        (channelid, is_complete)
        VALUES({mission_channel_id}, {status})
        ON CONFLICT(channelid)
        DO UPDATE SET is_complete = {status};
        """
    mission_db.execute(insert_stmt)
    missions_conn.commit()
    return


async def remove_channel_cleanup_entry(mission_channel_id):
    """
    Remove entry from channel_cleanup after successful channel deletion
    """
    mission_db.execute(f"DELETE FROM channel_cleanup WHERE channelid = {mission_channel_id}")
    missions_conn.commit()
    return


async def get_trade_channels_on_startup():
    """
    This function is called on bot.on_ready() to clean up any channels
    that had their timer lost during bot stop/restart
    """
    print('Checking for trade channels that were not cleaned up before bot restart')
    mission_db.execute('SELECT * FROM channel_cleanup WHERE is_complete = 1')
    return mission_db.fetchall()


async def cleanup_trade_channel(channel):
    """
    This function is called on bot.on_ready() to clean up any channels
    that had their timer lost during bot stop/restart
    """
    print(f"Sending channel {channel['channelid']} for removal")
    await remove_carrier_channel(channel['channelid'], seconds_long)
    return


async def clean_up_pins(channel):
    """
    Currently used in _cleanup_completed_mission to clear pins
    in case a new mission is started in an existing channel before cleanup
    Only cleans up pinned messages that were sent by the bot
    """
    print(f'Cleaning up pins in #{channel}')
    all_pins = await channel.pins()
    for pin in all_pins:
        if pin.author.bot:
            await pin.unpin()


async def remove_carrier_channel(mission_channel_id, seconds):
    # get channel ID to remove
    delchannel = bot.get_channel(mission_channel_id)
    spamchannel = bot.get_channel(bot_spam_id)

    # start a timer
    print(f"Starting {seconds} second countdown for deletion of {delchannel}")
    await asyncio.sleep(seconds)
    print("Channel removal timer complete")

    try:
        # try to acquire a channel lock, if unsuccessful after a period of time, abort and throw up an error
        try:
            await asyncio.wait_for(lock_mission_channel(), timeout=120)
        except asyncio.TimeoutError:
            print(f"No channel lock available for {delchannel}")
            return await spamchannel.send(f"<@211891698551226368> WARNING: No channel lock available on {delchannel} after 120 seconds. Deletion aborted.")

        # this is clunky but we want to know if a channel lock is because it's about to be deleted
        global deletion_in_progress
        deletion_in_progress = True

        # check whether channel is in-use for a new mission
        mission_db.execute(f"SELECT * FROM missions WHERE "
                        f"channelid = {mission_channel_id}")
        mission_data = MissionData(mission_db.fetchone())
        print(f'Mission data from remove_carrier_channel: {mission_data}')

        if mission_data:
            # abort abort abort
            print(f'New mission underway in this channel, aborting removal')
        else:
            # delete channel after a parting gift
            gif = random.choice(boom_gifs)
            try:
                await delchannel.send(gif)
                await asyncio.sleep(5)
                await delchannel.delete()
                print(f'Deleted {delchannel}')
                await remove_channel_cleanup_entry(mission_channel_id)

            except Forbidden:
                raise EnvironmentError(f"Could not delete {delchannel}, reason: Bot does not have permission.")
            except NotFound:
                print("Channel appears to have been deleted by someone else, we'll just continue on.")
                await spamchannel.send(f"Channel {delchannel} could not be deleted because it doesn't exist.")
    finally:
        # now release the channel lock
        carrier_channel_lock.release()
        deletion_in_progress = False
        print("Channel lock released")
        return


# a command for users to mark a carrier mission complete from within the carrier channel
@bot.command(name='complete', help="Use in a carrier's channel to mark the current trade mission complete.")
async def complete(ctx, *, comment: str = None):

    print(f"m.complete called in {ctx.channel} by {ctx.author}")

    # look for a match for the channel name in the carrier DB
    print("Looking for carrier by channel name match")
    carrier_data = find_carrier(ctx.channel.name, "discordchannel")
    if not carrier_data:
        # if there's no channel match, return an error
        embed = discord.Embed(description="**You need to be in a carrier's channel to mark its mission as complete.**",
                              color=constants.EMBED_COLOUR_ERROR)
        await ctx.send(embed=embed)
        return

    # now look to see if the carrier is on an active mission
    print("Looking for mission by channel ID match")
    mission_data = find_mission(ctx.channel.id, "channelid")
    if not mission_data:
        # if there's no result, return an error
        embed = discord.Embed(description=f"**{carrier_data.carrier_long_name} doesn't seem to be on a trade "
                                            f"mission right now.**",
                                color=constants.EMBED_COLOUR_ERROR)
        return await ctx.send(embed=embed)


    # user is in correct channel and carrier is on a mission, so check whether user is sure they want to proceed
    print("Send user confirm prompt")
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
            # whoops lol actually no
            print("User responded no")
            embed = discord.Embed(description="OK, mission will remain listed as in-progress.",
                                    color=constants.EMBED_COLOUR_OK)
            await ctx.send(embed=embed)
            return
        elif msg.content.lower() == "y":
            # they said yes!
            print("User responded yes")
            reddit_complete_text = f"    INCOMING WIDEBAND TRANSMISSION: P.T.N. CARRIER MISSION UPDATE\n\n**" \
                                   f"{mission_data.carrier_name}** mission complete. o7 CMDRs!\n\n\n\n*Reported on " \
                                   f"PTN Discord by {ctx.author.display_name}*"
            discord_complete_embed = discord.Embed(title=f"{mission_data.carrier_name} MISSION COMPLETE",
                                                   description=f"<@{ctx.author.id}> reports mission complete! **This mission channel will be removed in {seconds_long//60} minutes.**",
                                                   color=constants.EMBED_COLOUR_OK)
            print("Sending to _cleanup_completed_mission")
            desc_msg = f"> {comment}\n" if comment else ""
            await _cleanup_completed_mission(ctx, mission_data, reddit_complete_text, discord_complete_embed, desc_msg)

    except asyncio.TimeoutError:
        embed = discord.Embed(description="No response, mission will remain listed as in-progress.")
        await ctx.send(embed=embed)



#
#                       UTILITY COMMANDS
#

# backup databases
@bot.command(name='backup', help='Backs up the carrier and mission databases.')
@check_roles([botadmin_role_id])
@check_command_channel(conf['BOT_COMMAND_CHANNEL'])
async def backup(ctx):
    print(f"{ctx.author} requested a manual DB backup")
    backup_database('missions')
    backup_database('carriers')
    await ctx.send("Database backup complete.")


@bot.tree.command(name="info",
    description="Private command: Use in a Fleet Carrier's channel to show information about it.", guild=guild_obj)
async def _info(interaction: discord.Interaction):

    print(f'/info command carrier_data called by {interaction.user} in {interaction.channel}')

    # take a note of channel name and ID
    msg_channel_name = interaction.channel.name
    msg_channel_id = interaction.channel.id

    # look for a match for the ID in the community carrier database
    carrier_db.execute(f"SELECT * FROM community_carriers WHERE "
                       f"channelid = {msg_channel_id}")
    community_carrier_data = CommunityCarrierData(carrier_db.fetchone())

    if community_carrier_data:
        embed = discord.Embed(title="COMMUNITY CHANNEL",
                              description=f"<#{interaction.channel.id}> is a P.T.N. Community channel "
                                          f"registered to <@{community_carrier_data.owner_id}>.\n\n"
                                          f"Community channels are for events and community building and "
                                          f"are administered by the <@&{cc_role_id}> and <@&{cmentor_role_id}>s. See channel pins and description "
                                          f"more information about this channel's purpose and associated event(s).", color=constants.EMBED_COLOUR_OK)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return # if it was a Community Carrier, we're done and gone. Otherwise we keep looking.

    # now look for a match for the channel name in the carrier DB
    carrier_db.execute(f"SELECT * FROM carriers WHERE "
                       f"discordchannel = '{msg_channel_name}' ;")
    carrier_data = CarrierData(carrier_db.fetchone())

    if not carrier_data.discord_channel:
        print(f"/info failed, {interaction.channel} doesn't seem to be a carrier channel")
        # if there's no channel match, return an error
        embed = discord.Embed(description="Try again in a **🚛Trade Carriers** channel.", color=constants.EMBED_COLOUR_QU)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    else:
        print(f'Found data: {carrier_data}')
        embed = discord.Embed(title=f"Welcome to {carrier_data.carrier_long_name} ({carrier_data.carrier_identifier})", color=constants.EMBED_COLOUR_OK)
        embed = _add_common_embed_fields(embed, carrier_data, interaction)
        carrier_owner_obj = bot.get_user(carrier_data.ownerid)
        thumbnail_file = discord.File(f"images/{carrier_data.carrier_short_name}.png", filename="image.png")
        embed.set_thumbnail(url="attachment://image.png")
        embed.set_author(name=carrier_owner_obj.name, icon_url=carrier_owner_obj.display_avatar)
        interaction.user = carrier_owner_obj
        return await interaction.response.send_message(file=thumbnail_file, embed=embed, ephemeral=True)


@bot.tree.command(name="find",
    description="Private command: Search for a fleet carrier by partial match for its name.", guild=guild_obj)
async def _find(interaction: discord.Interaction, carrier_name_search_term: str):
    print(f"{interaction.user} used /find for '{carrier_name_search_term}' in {interaction.channel}")

    try:
        carrier_data = find_carrier(carrier_name_search_term, CarrierDbFields.longname.name)
        if carrier_data:
            print(f"Found {carrier_data}")
            embed = discord.Embed(title="Fleet Carrier Search Result",
                                  description=f"Displaying first match for {carrier_name_search_term}", color=constants.EMBED_COLOUR_OK)
            embed = _add_common_embed_fields(embed, carrier_data, interaction)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

    except TypeError as e:
        print('Error in carrier long search: {}'.format(e))
    await interaction.response.send_message(f'No result for {carrier_name_search_term}.', ephemeral=True)


# list FCs
@bot.command(name='carrier_list', help='List all Fleet Carriers in the database. This times out after 60 seconds')
@check_roles(any_elevated_role)
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
                        value=f"<@{carrier.ownerid}>, <t:{carrier.lasttrade}:R>", inline=False)
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
                                        value=f"<@{carrier.ownerid}>, <t:{carrier.lasttrade}:R>", inline=False)

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
                                        value=f"<@{carrier.ownerid}>, <t:{carrier.lasttrade}:R>", inline=False)

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
            embed = discord.Embed(description=f'Closed the active carrier list request from {ctx.author} due to no input in 60 seconds.', color=constants.EMBED_COLOUR_QU)
            await ctx.send(embed=embed)
            await message.delete()
            await ctx.message.delete()
            break


# add FC to database
@bot.command(name='carrier_add', help='Add a Fleet Carrier to the database:\n'
                                      '\n'
                                      '<short_name> is used as a filename and should be a short one-word string with no special characters\n'
                                      '<long_name> is the carrier\'s full name including P.T.N. etc - surround this '
                                      'with quotes.\n'
                                      '<carrier_id> is the carrier\'s unique identifier in the format ABC-XYZ\n'
                                      '<owner_id> is the owner\'s Discord ID')
@check_roles([botadmin_role_id])
@check_command_channel(conf['BOT_COMMAND_CHANNEL'])
async def carrier_add(ctx, short_name: str, long_name: str, carrier_id: str, owner_id: int):

    # check the ID code is correct format (thanks boozebot code!)
    if not re.match(r"\w{3}-\w{3}", carrier_id):
        print(f'{ctx.author}, the carrier ID was invalid, XXX-XXX expected received, {carrier_id}.')
        return await ctx.channel.send(f'ERROR: Invalid carrier ID. Expected: XXX-XXX, received {carrier_id}.')

    # Only add to the carrier DB if it does not exist, if it does exist then the user should not be adding it.
    carrier_data = find_carrier(long_name, CarrierDbFields.longname.name)
    if carrier_data:
        # Carrier exists already, go skip it.
        print(f'Request recieved from {ctx.author} to add a carrier that already exists in the database ({long_name}).')

        embed = discord.Embed(title="Fleet carrier already exists, use /carrier_edit to change its details.",
                              description=f"Carrier data matched for {long_name}", color=constants.EMBED_COLOUR_OK)
        embed = _add_common_embed_fields(embed, carrier_data, ctx)
        return await ctx.send(embed=embed)

    backup_database('carriers')  # backup the carriers database before going any further

    # now generate a string to use for the carrier's channel name based on its long name
    stripped_name = _regex_alphanumeric_with_hyphens(long_name)

    # find carrier owner as a user object

    try:
        owner = await bot.fetch_user(owner_id)
        print(f"Owner identified as {owner.display_name}")
    except:
        raise EnvironmentError(f'Could not find Discord user matching ID {owner_id}')

    # finally, send all the info to the db
    await add_carrier_to_database(short_name, long_name, carrier_id, stripped_name.lower(), 0, owner_id)

    carrier_data = find_carrier(long_name, CarrierDbFields.longname.name)
    embed = discord.Embed(title="Fleet Carrier successfully added to database",
                          color=constants.EMBED_COLOUR_OK)
    embed = _add_common_embed_fields(embed, carrier_data, ctx)
    return await ctx.send(embed=embed)


# remove FC from database
@bot.command(name='carrier_del', help='Delete a Fleet Carrier from the database using its database entry ID#.')
@check_roles([botadmin_role_id])
@check_command_channel(conf['BOT_COMMAND_CHANNEL'])
async def carrier_del(ctx, db_id: int):
    try:
        carrier_data = find_carrier(db_id, CarrierDbFields.p_id.name)
        if carrier_data:
            embed = discord.Embed(title="Delete Fleet Carrier", description=f"Result for {db_id}",
                                  color=constants.EMBED_COLOUR_OK)
            embed = _add_common_embed_fields(embed, carrier_data, ctx)
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
                        error_msg = await delete_carrier_from_db(db_id)
                        if error_msg:
                            await ctx.send(error_msg)

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
                                        'Use with carrier\'s name as argument to check the '
                                        'carrier\'s image or begin upload of a new image.')
@check_roles([certcarrier_role_id, trainee_role_id])
async def carrier_image(ctx, lookname):

    print(f"{ctx.author} called m.carrier_image for {lookname}")
    carrier_data = find_carrier(lookname, CarrierDbFields.longname.name)

    # check carrier exists
    if not carrier_data:
        await ctx.send(f"Sorry, no carrier found matching \"{lookname}\". Try using `/find` or `/owner`.")
        return print(f"No carrier found for {lookname}")

    # define image requiremenets
    true_size = (506, 285)
    true_width, true_height = true_size
    true_aspect = true_width / true_height
    legacy_message, noimage_message = False, False

    newimage_description = ("The mission image helps give your Fleet Carrier trade missions a distinct visual identity. "
                            " You only need to upload an image once. This will be inserted into the slot in the "
                            "mission image template.\n\n"
                            "• It is recommended to use in-game screenshots showing **scenery** and/or "
                            "**your Fleet Carrier**. You may also wish to add a **logo** or **emblem** for your Fleet "
                            "Carrier if you have one.\n"
                            "• Images will be cropped to 16:9 and resized to 506x285 if not already.\n"
                            "• You can use `m.carrier_image <yourcarrier>` at any time to change your image.\n\n"
                            "**You can upload your image now to change it**.\n"
                            "Alternatively, input \"**x**\" to cancel, or \"**p**\" to use a random placeholder with PTN logo.\n\n"
                            "**You must have a valid image to generate a mission**.")

    # see if there's an image for this carrier already
    # newly added carriers have no image (by intention - we want CCOs to engage with this aspect of the job!)
    try:
        print("Looking for existing image")
        file = discord.File(f"images/{carrier_data.carrier_short_name}.png", filename="image.png")
    except:
        file = None

    if file:
        # we found an existing image, so show it to the user
        print("Found image")
        embed = discord.Embed(title=f"{carrier_data.carrier_long_name} MISSION IMAGE",
                                color=constants.EMBED_COLOUR_QU)
        embed.set_image(url="attachment://image.png")
        await ctx.send(file=file, embed=embed)
        image_exists = True

        # check if it's a legacy image - if it is, we want them to replace it
        image = Image.open(f"images/{carrier_data.carrier_short_name}.png")
        valid_image = image.size == true_size

    else:
        # no image found
        print("No existing image found")
        image_exists, valid_image = False, False

    if valid_image:
        # an image exists and is the right size, user is not nagged to change it
        embed = discord.Embed(title="Change carrier's mission image?",
                                    description="If you want to replace this image you can upload the new image now. "
                                                "Images will be automatically cropped to 16:9 and resized to 506x285.\n\n"
                                                "**To continue without changing**:         Input \"**x**\" or wait 60 seconds\n"
                                                "**To switch to a random PTN logo image**: Input \"**p**\"",
                                    color=constants.EMBED_COLOUR_QU)

    elif not valid_image and not image_exists:
        # there's no mission image, prompt the user to upload one or use a PTN placeholder
        file = discord.File("template.png", filename="image.png")
        embed = discord.Embed(title=f"NO MISSION IMAGE FOUND",
                                color=constants.EMBED_COLOUR_QU)
        embed.set_image(url="attachment://image.png")
        noimage_message = await ctx.send(file=file, embed=embed)
        embed = discord.Embed(title="Upload a mission image",
                              description=newimage_description, color=constants.EMBED_COLOUR_QU)

    elif not valid_image and image_exists:
        # there's an image but it's outdated, prompt them to change it
        embed = discord.Embed(title="WARNING: LEGACY MISSION IMAGE DETECTED",
                              description="The mission image format has changed. You must upload a new image to continue"
                                                " to use the Mission Generator.",
                                          color=constants.EMBED_COLOUR_ERROR)
        legacy_message = await ctx.send(embed=embed)
        embed = discord.Embed(title="Upload a mission image",
                              description=newimage_description, color=constants.EMBED_COLOUR_QU)

    # send the embed we created
    message_upload_now = await ctx.send(embed=embed)

    # function to check user's response
    def check(message_to_check):
        return message_to_check.author == ctx.author and message_to_check.channel == ctx.channel

    try:
        # now we process the user's response
        message = await bot.wait_for("message", check=check, timeout=60)
        if message.content.lower() == "x": # user backed out without making changes
            embed = discord.Embed(description="No changes made.",
                                    color=constants.EMBED_COLOUR_OK)
            await ctx.send(embed=embed)
            await message.delete()
            await message_upload_now.delete()
            if noimage_message:
                await noimage_message.delete()
            return

        elif message.content.lower() == "p": # user wants to use a placeholder image
            print("User wants default image")
            try:
                # first backup the existing image, if any
                shutil.move(f'images/{carrier_data.carrier_short_name}.png',
                            f'images/old/{carrier_data.carrier_short_name}.{get_formatted_date_string()[1]}.png')
            except:
                pass
            try:
                # select a random image from our default image library so not every carrier is the same
                default_img = random.choice(os.listdir("images/default"))
                shutil.copy(f'images/default/{default_img}',
                            f'images/{carrier_data.carrier_short_name}.png')
            except Exception as e:
                print(e)

        elif message.attachments: # user has uploaded something, let's hope it's an image :))
            # first backup the existing image, if any
            try:
                shutil.move(f'images/{carrier_data.carrier_short_name}.png',
                            f'images/old/{carrier_data.carrier_short_name}.{get_formatted_date_string()[1]}.png')
            except:
                pass
            # now process our attachment
            for attachment in message.attachments:
                # there can only be one attachment per message
                await attachment.save(attachment.filename)

                """
                Now we need to check the image's size and aspect ratio so we can trim it down without the user
                requiring any image editing skills. This is a bit involved. We need to compare both aspect
                ratio and size to our desired values and fix them in that order. Aspect correction requires
                figuring out whether the image is too tall or too wide, then centering the crop correctly.
                Size correction takes place after aspect correction and is super simple.
                """

                print("Checking image size")
                try:
                    image = Image.open(attachment.filename)
                except Exception as e: # they uploaded something daft
                    print(e)
                    await ctx.send("Sorry, I don't recognise that as an image file. Upload aborted.")
                    return await message_upload_now.delete()

                # now we check the image dimensions and aspect ratio
                upload_width, upload_height = image.size
                print(f"{upload_width}, {upload_height}")
                upload_size = (upload_width, upload_height)
                upload_aspect = upload_width / upload_height

                if not upload_aspect == true_aspect:
                    print(f"Image aspect ratio of {upload_aspect} requires adjustment")
                    # check largest dimension
                    if upload_aspect > true_aspect:
                        print("Image is too wide")
                        # image is too wide, we'll crop width to maintain height
                        new_width = upload_height * true_aspect
                        new_height = upload_height
                    else:
                        print("Image is too high")
                        # image is too high, we'll crop height to maintain width
                        new_height = upload_width / true_aspect
                        new_width = upload_width
                    # now perform the incision. Nurse: scalpel!
                    crop_width = upload_width - new_width
                    crop_height = upload_height - new_height
                    left = 0.5 * crop_width
                    top = 0.5 * crop_height
                    right = 0.5 * crop_width + new_width
                    bottom = 0.5 * crop_height + new_height
                    print(left, top, right, bottom)
                    image = image.crop((left, top, right, bottom))
                    print(f"Cropped image to {new_width} x {new_height}")
                    upload_size = (new_width, new_height)
                # now check its size
                if not upload_size == true_size:
                    print("Image requires resizing")
                    image = image.resize((true_size))

            # now we can save the image
            image.save(f"images/{carrier_data.carrier_short_name}.png")

            # remove the downloaded attachment
            try:
                image.close()
                os.remove(attachment.filename)
            except Exception as e:
                print(f"Error deleting file {attachment.filename}: {e}")

        # now we can show the user the result in situ
        in_image = await _overlay_mission_image(carrier_data)
        result_name = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        print(f'Saving temporary mission image preview file for carrier: {carrier_data.carrier_long_name} to: {result_name.name}')
        in_image.save(result_name.name)

        file = discord.File(result_name.name, filename="image.png")
        embed = discord.Embed(title=f"{carrier_data.carrier_long_name}",
                                description="Mission image updated.", color=constants.EMBED_COLOUR_OK)
        embed.set_image(url="attachment://image.png")
        await ctx.send(file=file, embed=embed)
        print("Sent result to user")
        await message.delete()
        await message_upload_now.delete()
        if noimage_message:
            await noimage_message.delete()
        # only delete legacy warning if user uploaded valid new file
        if legacy_message:
            await legacy_message.delete()
        print("Tidied up our prompt messages")

        # cleanup the tempfile
        result_name.close()
        os.unlink(result_name.name)
        print("Removed the tempfile")

        print(f"{ctx.author} updated carrier image for {carrier_data.carrier_long_name}")

    except asyncio.TimeoutError:
        embed = discord.Embed(description="No changes made (no response from user).",
                                color=constants.EMBED_COLOUR_OK)
        await ctx.send(embed=embed)
        await message_upload_now.delete()
        return


# find FC based on shortname
@bot.command(name='findshort', help='DEPRECATED. Use to find a carrier by searching for its image file name (shortname).\n'
                                    '\n'
                                    'Syntax: m.findshort <search_term>\n'
                                    '\n'
                                    'Partial matches will work but only if they incorporate part of the shortname.\n'
                                    'To find a carrier based on a match with part of its full name, use the /find '
                                    'command.')
async def findshort(ctx, shortname_search_term: str):
    try:
        carriers = find_carriers_mult(shortname_search_term, CarrierDbFields.shortname.name)
        if carriers:
            carrier_data = None

            if len(carriers) == 1:
                print('Single carrier found, returning that directly')
                # if only 1 match, just assign it directly
                carrier_data = carriers[0]
            elif len(carriers) > 3:
                # If we ever get into a scenario where more than 3 can be found with the same search
                # directly, then we need to revisit this limit
                print(f'More than 3 carriers found for: "{shortname_search_term}", {ctx.author} needs to search better.')
                await ctx.send(f'Please narrow down your search, we found {len(carriers)} matches for your '
                               f'input choice: "{shortname_search_term}"')
                return None  # Just return None here and let the calling method figure out what is needed to happen
            else:
                print(f'Between 1 and 3 carriers found for: "{shortname_search_term}", asking {ctx.author} which they want.')
                # The database runs a partial match, in the case we have more than 1 ask the user which they want.
                # here we have less than 3, but more than 1 match
                embed = discord.Embed(title=f"Multiple carriers ({len(carriers)}) found for input: {shortname_search_term}",
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
                                      description=f"Displaying first match for {shortname_search_term}",
                                      color=constants.EMBED_COLOUR_OK)
                embed = _add_common_embed_fields(embed, carrier_data, ctx)
                return await ctx.send(embed=embed)
    except TypeError as e:
        print('Error in carrier search: {}'.format(e))
    await ctx.send(f'No result for {shortname_search_term}.')


def _add_common_embed_fields(embed, carrier_data, ctx_interaction):
    embed.add_field(name="Carrier Name", value=f"{carrier_data.carrier_long_name}", inline=True)
    embed.add_field(name="Carrier ID", value=f"{carrier_data.carrier_identifier}", inline=True)
    embed.add_field(name="Database Entry", value=f"{carrier_data.pid}", inline=True)

    # make the channel field a clickable link if there's an active channel by that name
    channel = discord.utils.get(ctx_interaction.guild.channels, name=carrier_data.discord_channel)
    discord_channel = f"<#{channel.id}>" if channel else f"#{carrier_data.discord_channel}"
    embed.add_field(name="Discord Channel", value=f"{discord_channel}", inline=True)

    embed.add_field(name="Owner", value=f"<@{carrier_data.ownerid}>", inline=True)
    embed.add_field(name="Market Data", value=f"`;stock {carrier_data.carrier_short_name}`", inline=True)
    embed.add_field(name="Last Trade", value=f"<t:{carrier_data.lasttrade}> (<t:{carrier_data.lasttrade}:R>)", inline=True)
    # shortname is not relevant to users and will be auto-generated in future
    return embed


def _regex_alphanumeric_with_hyphens(regex_string):
    # replace any spaces with hyphens
    regex_string_hyphenated = regex_string.replace(' ', '-')
    # take only the alphanumeric characters and hyphens, leave behind everything else
    re_compile = re.compile('([\w-]+)')
    compiled_name = re_compile.findall(regex_string_hyphenated)
    # join together all the extracted bits into one string
    processed_string = ''.join(compiled_name)
    print(f"Processed {regex_string} into {processed_string}")
    return processed_string


def _get_id_from_mention(mention):
    # use re to return the devmode Discord ID from a string that we're not sure whether it's a mention/channel link or an ID
    # mentions are in a format like <@0982340982304>
    re_compile = re.compile('([\d-]+)')
    mention_id = re_compile.findall(mention)
    return mention_id

# find FC based on longname
@bot.command(name='find', help='Find a carrier based on a partial match with any part of its full name\n'
                               '\n'
                               'Syntax: m.find <search_term>')
async def find(ctx, carrier_name_search_term: str):
    try:
        carriers = find_carriers_mult(carrier_name_search_term, CarrierDbFields.longname.name)
        if carriers:
            carrier_data = None

            if len(carriers) == 1:
                print('Single carrier found, returning that directly')
                # if only 1 match, just assign it directly
                carrier_data = carriers[0]
            elif len(carriers) > 3:
                # If we ever get into a scenario where more than 3 commodities can be found with the same search
                # directly, then we need to revisit this limit
                print(f'More than 3 carriers found for: "{carrier_name_search_term}", {ctx.author} needs to search better.')
                await ctx.send(f'Please narrow down your search, we found {len(carriers)} matches for your '
                               f'input choice: "{carrier_name_search_term}"')
                return None  # Just return None here and let the calling method figure out what is needed to happen
            else:
                print(f'Between 1 and 3 carriers found for: "{carrier_name_search_term}", asking {ctx.author} which they want.')
                # The database runs a partial match, in the case we have more than 1 ask the user which they want.
                # here we have less than 3, but more than 1 match
                embed = discord.Embed(title=f"Multiple carriers ({len(carriers)}) found for input: {carrier_name_search_term}",
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
                embed = discord.Embed(title="Fleet Carrier Search Result",
                                      description=f"Displaying match for {carrier_name_search_term}",
                                      color=constants.EMBED_COLOUR_OK)
                embed = _add_common_embed_fields(embed, carrier_data, ctx)
                return await ctx.send(embed=embed)
    except TypeError as e:
        print('Error in carrier search: {}'.format(e))
    await ctx.send(f'No result for {carrier_name_search_term}.')


# find FC based on ID
@bot.command(name='findid', help='Find a carrier based on its database ID\n'
                                 'Syntax: findid <integer>')
async def findid(ctx, db_id: int):
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
        carrier_data = find_carrier(db_id, CarrierDbFields.p_id.name)
        if carrier_data:
            embed = discord.Embed(title="Fleet Carrier DB# Search Result",
                                  description=f"Displaying carrier with DB# {carrier_data.pid}",
                                  color=constants.EMBED_COLOUR_OK)
            embed = _add_common_embed_fields(embed, carrier_data, ctx)
            await ctx.send(embed=embed)
            return  # We exit here

    except TypeError as e:
        print('Error in carrier findid search: {}'.format(e))
    await ctx.send(f'No result for {db_id}.')


# find commodity
@bot.command(name='findcomm', help='Find a commodity based on a search term\n'
                                   'If a term has too many possible matches try a longer search term.\n')
async def search_for_commodity(ctx, commodity_search_term: str):
    print(f'search_for_commodity called by {ctx.author} to search for {commodity_search_term}')
    try:
        commodity = await find_commodity(commodity_search_term, ctx)
        if commodity:
            return await ctx.send(commodity)
    except:
        # Catch any exception
        pass
    await ctx.send(f'No such commodity found for: "{commodity_search_term}".')


@bot.tree.command(name="carrier_edit",
    description="Edit a specific carrier in the database", guild=guild_obj)
@check_roles([botadmin_role_id])
@check_command_channel(conf['BOT_COMMAND_CHANNEL'])
async def _carrier_edit(interaction: discord.Interaction, carrier_name_search_term: str):
    """
    Edits a carriers information in the database. Provide a carrier name that can be partially matched and follow the
    steps.

    :param discord.interaction interaction: The discord interaction
    :param str carrier_name_search_term: The carrier name to find
    :returns: None
    """
    print(f'/carrier_edit called by {interaction.user} to update the carrier: {carrier_name_search_term} from channel: {interaction.channel}')

    # Go fetch the carrier details by searching for the name

    carrier_data = copy.copy(find_carrier(carrier_name_search_term, CarrierDbFields.longname.name))
    orig_carrier_data = copy.copy(carrier_data)
    print(carrier_data)
    if carrier_data:
        embed = discord.Embed(title="Original Carrier Data", color=discord.Color.green())
        embed = await _configure_all_carrier_detail_embed(embed, carrier_data)
        return await interaction.response.send_message(
            embed=embed,
            view=CarrierEditView(carrier_data=carrier_data,orig_carrier_data=orig_carrier_data), ephemeral=True)
    else:
        embed = discord.Embed(title=f'No result found for the carrier: "{carrier_name_search_term}"', color=constants.EMBED_COLOUR_ERROR)
        return await interaction.response.send_message(embed=embed)


class CarrierEditView(discord.ui.View):
    """
    Main trade view containing the:
        select menu, station|system modal, trade data modal
    If self.data is not set, create a dict with default keys set to ''
    """
    def __init__(self, carrier_data, orig_carrier_data):
        self.carrier_data = carrier_data
        self.orig_carrier_data = orig_carrier_data
        super().__init__()

    @discord.ui.button(label="Name|ID|ShortName", row=1, custom_id='name_id')
    async def name_callback(self, interaction, button):
        await interaction.response.send_modal(CarrierNameIDModal(title='Carrier Name | ID | ShortName', view=self))

    @discord.ui.button(label="Channel|Owner|LastTrade", row=1, custom_id='discord_data')
    async def discord_callback(self, interaction, button):
        await interaction.response.send_modal(CarrierDiscordDataModal(title='Channel | Owner | LastTrade', view=self))

    @discord.ui.button(label="Update Carrier", row=2, custom_id='update', style=discord.ButtonStyle.green)
    async def update_callback(self, interaction, button):
        if self.carrier_data == self.orig_carrier_data:
            embed = discord.Embed(title="No Edits made", color=constants.EMBED_COLOUR_ERROR)
            self.stop()
            return await interaction.response.edit_message(content=None, embed=embed, view=None)
        else:
            embed = discord.Embed(title="Review Carrier Changes", color=discord.Color.orange())
            embed = await _configure_all_carrier_detail_embed(embed, self.carrier_data)
            await interaction.response.edit_message(
                content=None,
                embed=embed,
                view=CarrierEditConfirmationView(self.carrier_data, self.orig_carrier_data)
            )

    @discord.ui.button(label="Cancel", row=2, custom_id='cancel', style=discord.ButtonStyle.red)
    async def quit_button_callback(self, interaction, button):
        embed = discord.Embed(title="Carrier Edit Cancelled", color=constants.EMBED_COLOUR_ERROR)
        await interaction.response.edit_message(content=None, embed=embed, view=None)
        print('Carrier Edit cancelled')
        self.stop()


class CarrierEditConfirmationView(discord.ui.View):
    """
    """
    def __init__(self, carrier_data, orig_carrier_data):
        self.carrier_data = carrier_data
        self.orig_carrier_data = orig_carrier_data
        super().__init__()

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def save_button_callback(self, interaction, button):
        await _update_carrier_details_in_database(self.carrier_data, self.orig_carrier_data.carrier_long_name)
        print(f'Carrier data now looks like:')
        print(f'\t Original: {self.orig_carrier_data}')
        print(f'\t Updated: {self.carrier_data}')
        if self.carrier_data.carrier_short_name != self.orig_carrier_data.carrier_short_name:
            print('Renaming the carriers image')
            os.rename(
                f'images/{self.orig_carrier_data.carrier_short_name}.png',
                f'images/{self.carrier_data.carrier_short_name}.png'
            )
            print(f'Carrier image renamed from: images/{self.orig_carrier_data.carrier_short_name}.png to '
                  f'images/{self.carrier_data.carrier_short_name}.png')

        updated_carrier_data = find_carrier(self.carrier_data.carrier_long_name, CarrierDbFields.longname.name)
        if updated_carrier_data:
            embed = discord.Embed(title=f"Reading the settings from DB:",
                                  description=f"Double check and re-run if incorrect the settings for old name: "
                                              f"{self.orig_carrier_data.carrier_long_name}",
                                  color=constants.EMBED_COLOUR_OK)
            embed = await _configure_all_carrier_detail_embed(embed, updated_carrier_data)
            self.stop()
            return await interaction.response.edit_message(content=None, view=None, embed=embed)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def quit_button_callback(self, interaction, button):
        embed = discord.Embed(title="Carrier Edit Cancelled", color=constants.EMBED_COLOUR_ERROR)
        await interaction.response.edit_message(content=None, embed=embed, view=None)
        print('Carrier Edit cancelled')
        self.stop()


class CarrierNameIDModal(discord.ui.Modal):
    """
    """
    def __init__(self, title, view, timeout=None):
        self.view = view
        self.longname = discord.ui.TextInput(
            label = 'Long Name',
            custom_id = 'long_name',
            default = self.view.carrier_data.carrier_long_name
            )

        self.shortname = discord.ui.TextInput(
            label = 'Short Name',
            custom_id = 'short_name',
            default = self.view.carrier_data.carrier_short_name
            )

        self.cid = discord.ui.TextInput(
            label = 'Carrier Identifier',
            custom_id = 'c_id',
            default = self.view.carrier_data.carrier_identifier
            )
        super().__init__(title=title, timeout=timeout)
        self.add_item(self.longname)
        self.add_item(self.shortname)
        self.add_item(self.cid)

    async def on_submit(self, interaction):
        self.view.carrier_data.carrier_long_name = self.children[0].value.strip().upper()
        self.view.carrier_data.carrier_short_name = self.children[1].value.strip().lower()
        self.view.carrier_data.carrier_identifier = self.children[2].value.strip().upper()
        await interaction.response.edit_message(view=self.view)


class CarrierDiscordDataModal(discord.ui.Modal):
    """
    """
    def __init__(self, title, view, timeout=None):
        self.view = view

        self.discord_channel = discord.ui.TextInput(
            label = 'Discord Channel',
            custom_id = 'discord_channel',
            default = self.view.carrier_data.discord_channel
            )
        self.ownerid = discord.ui.TextInput(
            label = 'Owner ID',
            custom_id = 'owner_id',
            default = self.view.carrier_data.ownerid
            )
        self.lasttrade = discord.ui.TextInput(
            label = 'Last Trade',
            custom_id = 'last_trade',
            default = self.view.carrier_data.lasttrade
            )
        super().__init__(title=title, timeout=timeout)
        self.add_item(self.discord_channel)
        self.add_item(self.ownerid)
        self.add_item(self.lasttrade)

    async def on_submit(self, interaction):
        self.view.carrier_data.discord_channel = self.children[0].value.strip().lower()
        self.view.carrier_data.ownerid = self.children[1].value.strip()
        self.view.carrier_data.lasttrade = self.children[2].value.strip()

        await interaction.response.edit_message(view=self.view)


async def _update_carrier_details_in_database(carrier_data, original_name):
    """
    Updates the carrier details into the database.

    :param CarrierData carrier_data: The carrier data to write
    :param str original_name: The original carrier name, needed so we can find it in the database
    """
    backup_database('carriers')  # backup the carriers database before going any further

    # TODO: Write to the database
    await carrier_db_lock.acquire()
    try:

        data = (
            carrier_data.carrier_short_name,
            carrier_data.carrier_long_name,
            carrier_data.carrier_identifier,
            carrier_data.discord_channel,
            carrier_data.channel_id,
            carrier_data.ownerid,
            f'%{original_name}%'
        )
        # Handy number to print out what the database connection is actually doing
        carriers_conn.set_trace_callback(print)
        carrier_db.execute(
            ''' UPDATE carriers
            SET shortname=?, longname=?, cid=?, discordchannel=?, channelid=?, ownerid=?
            WHERE longname LIKE (?) ''', data
        )

        carriers_conn.commit()
    finally:
        carrier_db_lock.release()


async def _configure_all_carrier_detail_embed(embed, carrier_data: CarrierData):
    """
    Adds all the common fields to a message embed and returns the embed.

    :param discord.Embed embed: The original embed to edit.
    :param CarrierData carrier_data: The carrier data to use for populating the embed
    :returns: The embeded message
    """
    embed.add_field(name='Carrier Name', value=f'{carrier_data.carrier_long_name}', inline=True)
    embed.add_field(name='Carrier Identifier', value=f'{carrier_data.carrier_identifier}', inline=True)
    embed.add_field(name='Short Name', value=f'{carrier_data.carrier_short_name}', inline=True)
    embed.add_field(name='Discord Channel', value=f'#{carrier_data.discord_channel}', inline=True)
    embed.add_field(name='Carrier Owner', value=f'<@{carrier_data.ownerid}>', inline=True)
    embed.add_field(name='DB ID', value=f'{carrier_data.pid}', inline=True)
    embed.set_footer(text="Note: DB ID is not an editable field.")
    return embed


#
#                       COMMUNITY CARRIER COMMANDS
#

# app command to upload cc thumbnail
@bot.tree.context_menu(name='Upload CC Thumb')
@check_roles([cmentor_role_id, botadmin_role_id, cc_role_id])
async def upload_cc_thumb(interaction: discord.Interaction, message: discord.Message):
    # check we're in the CC channel
    if not await _send_notice_channel_check(interaction): return

    if message.attachments:
        for attachment in message.attachments: # there can only be one attachment per message
            await attachment.save(f'images/cc/{interaction.channel.id}.png')
        await interaction.response.send_message(embed = discord.Embed(description="Image saved as Channel notice thumbnail. It should appear when you use `/send_notice`.", color=constants.EMBED_COLOUR_OK), ephemeral=True)
    else:
        # we'll be super lazy and use this as the offially mandated way to delete thumbnails 🤷‍♀️
        await interaction.response.send_message(embed = discord.Embed(description="No image found in this message. If you had an existing thumbnail, it has been removed.", color=constants.EMBED_COLOUR_ERROR), ephemeral=True)

        # see if there's already a thumbnail file
        if os.path.isfile(f"images/cc/{interaction.channel.id}.png"):
            print(f"Found image file images/cc/{interaction.channel.id}.png")
            try: # try to delete it
                os.remove(f"images/cc/{interaction.channel.id}.png")
            except Exception as e:
                await interaction.followup.send(embed = discord.Embed(description=f"**ERROR**: {e}", color=constants.EMBED_COLOUR_ERROR), ephemeral=True)
    return

# helper function to validate CC owner, returns False if owner already in db or True if check passes
async def _cc_owner_check(interaction, owner):
    community_carrier_data = find_community_carrier(owner.id, CCDbFields.ownerid.name)
    if community_carrier_data:
        # TODO: this should be fetchone() not fetchall but I can't make it work otherwise
        for community_carrier in community_carrier_data:
            print(f"Found data: {community_carrier.owner_id} owner of {community_carrier.channel_id}")
            await interaction.response.send_message(f"User {owner.display_name} is already registered as a Community channel owner with channel <#{community_carrier.channel_id}>")
            return False
    return True

# helper function to validate CC new role, returns False if role exists or True if check passes
async def _cc_role_create_check(interaction, new_channel_name):
    # CHECK: existing role
    new_role = discord.utils.get(interaction.guild.roles, name=new_channel_name)
    if new_role:
        # if the role exists we won't use it because it could lead to security concerns :(
        print(f"Role {new_role} already exists.")
        embed = discord.Embed(description=f"**Error**: The role <@&{new_role.id}> already exists. Please choose a different name for your Community channel or delete the existing role and try again.", color=constants.EMBED_COLOUR_ERROR)
        await interaction.response.send_message(embed=embed)
        return False
    return True

# helper function to create a CC channel, returns a channel object
async def _cc_create_channel(interaction, new_channel_name, cc_category):
    try:
        new_channel = await interaction.guild.create_text_channel(f"{new_channel_name}", category=cc_category)
        print(f"Created {new_channel}")

        print(f'Channels: {interaction.guild.channels}')

        embed = discord.Embed(description=f"Created channel <#{new_channel.id}>.", color=constants.EMBED_COLOUR_OK)
        await interaction.response.send_message(embed=embed)
    except:
        raise EnvironmentError(f'Could not create carrier channel {new_channel_name}')
    return new_channel

# helper function to create a CC role, returns a role object
async def _cc_role_create(interaction, new_channel_name):
    # create pingable role to go with channel
    new_role = await interaction.guild.create_role(name=new_channel_name)
    print(f"Created {new_role}")
    print(f'Roles: {interaction.guild.roles}')
    if not new_role:
        raise EnvironmentError(f'Could not create role {new_channel_name}')
    embed = discord.Embed(description=f"Created role <@&{new_role.id}>.", color=constants.EMBED_COLOUR_OK)
    await interaction.followup.send(embed=embed)
    return new_role

# helper function to assign CC channel permissions
async def _cc_assign_permissions(interaction, owner, new_channel):
    role = discord.utils.get(interaction.guild.roles, id=cc_role_id)
    print(cc_role_id)
    print(role)

    try:
        await owner.add_roles(role)
        print(f"Added Community Carrier role to {owner}")
    except Exception as e:
        print(e)
        raise EnvironmentError(f"Failed adding role to {owner}: {e}")

    # add owner to channel permissions
    guild = await get_guild()
    overwrite = await get_overwrite_perms()
    try:
        member = await guild.fetch_member(owner.id)
        print(f"Owner identified as {member.display_name}")
    except:
        raise EnvironmentError(f'Could not find Discord user matching ID {owner.id}')
    try:
        # first make sure it has the default permissions for the CC category
        await new_channel.edit(sync_permissions=True)
        print("Synced permissions with parent category")
        # now add the owner with superpermissions
        await new_channel.set_permissions(member, overwrite=overwrite)
        print(f"Set permissions for {member} in {new_channel}")
        # now set the channel to private for other users
        await new_channel.set_permissions(interaction.guild.default_role, read_messages=False)
    except Forbidden:
        raise EnvironmentError(f"Could not set channel permissions in {new_channel}, reason: Bot does not have permissions to edit channel specific permissions.")
    except NotFound:
        raise EnvironmentError(f"Could not set channel permissions in {new_channel}, reason: The role or member being edited is not part of the guild.")
    except HTTPException:
        raise EnvironmentError(f"Could not set channel permissions in {new_channel}, reason: Editing channel specific permissions failed.")
    except (ValueError, TypeError):
        raise EnvironmentError(f"Could not set channel permissions in {new_channel}, reason: The overwrite parameter invalid or the target type was not Role or Member.")
    except:
        raise EnvironmentError(f'Could not set channel permissions in {new_channel}')

async def _cc_db_enter(interaction, owner, new_channel, new_role):
    # now we enter everything into the community carriers table
    print("Locking carrier db...")
    await carrier_db_lock.acquire()
    print("Carrier DB locked.")
    try:
        carrier_db.execute(''' INSERT INTO community_carriers VALUES(?, ?, ?) ''',
                           (owner.id, new_channel.id, new_role.id))
        carriers_conn.commit()
        print("Added new community carrier to database")
    except:
        raise EnvironmentError("Error: failed to update community channels database.")
    finally:
        print("Unlocking carrier db...")
        carrier_db_lock.release()
        print("Carrier DB unlocked.")

    # tell the user what's going on
    embed = discord.Embed(description=f"<@{owner.id}> is now a <@&{cc_role_id}> and owns <#{new_channel.id}> with notification role <@&{new_role.id}>."
                                      f" **This channel will remain closed** (private) until `/open_community_channel` is used in it."
                                      f"\n\nNote channels and roles can be freely renamed.", color=constants.EMBED_COLOUR_OK)
    await interaction.followup.send(embed=embed)

    return


@bot.tree.command(name="create_community_channel",
                  description="Create a Community Channel linked to a specific user.",
                  guild=guild_obj)
@check_roles([cmentor_role_id, botadmin_role_id])
async def _create_community_channel(interaction: discord.Interaction, owner: discord.Member, channel_name: str, channel_emoji: str = None):
    print(f"{interaction.user.name} used /create_community_channel")
    print(f"Params: {owner} {channel_name} {channel_emoji}")
    # trim emojis to 1 character
    emoji_string = channel_emoji[:1] if not channel_emoji == None else None

    # PROCESS: check for valid emoji
    print(emoji.is_emoji(emoji_string))
    if not emoji.is_emoji(emoji_string) and not emoji_string == None:
        embed = discord.Embed(description="**Error**: Invalid emoji supplied. Use a valid Unicode emoji from your emoji keyboard,"
                                        f"or leave the field blank. **Discord custom emojis will not work**.", color=constants.EMBED_COLOUR_ERROR)
        bu_link = Button(label="Full Emoji List", url="https://unicode.org/emoji/charts/full-emoji-list.html")
        view = View()
        view.add_item(bu_link)
        return await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # PROCESS: remove unusable characters and render to lowercase
    stripped_channel_name = _regex_alphanumeric_with_hyphens(channel_name.lower())

    # check the channel name isn't too long
    if len(stripped_channel_name) > 30:
        embed = discord.Embed(description="**Error**: Channel name should be fewer than 30 characters. (Preferably a *lot* fewer.)", color=constants.EMBED_COLOUR_ERROR)
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    # join with the emoji
    new_channel_name = emoji_string + stripped_channel_name if not emoji_string == None else stripped_channel_name
    print(f"Candidate channel name: {new_channel_name}")

    # CHECK: user already owns a channel
    if not await _cc_owner_check(interaction, owner): return

    # get the CC category as a discord channel category object
    cc_category = discord.utils.get(interaction.guild.categories, id=cc_cat_id)
    archive_category = discord.utils.get(interaction.guild.categories, id=archive_cat_id)

    # check the role validity here so we can stop if needed
    if not await _cc_role_create_check(interaction, new_channel_name): return

    # CHECK: existing channels
    new_channel = discord.utils.get(interaction.guild.channels, name=new_channel_name)

    if new_channel:
        # check whether it's an existing CC channel
        if new_channel.category == cc_category:
            embed = discord.Embed(description=f"**Error**: A Community channel <#{new_channel.id}> already exists."
                                f" Please choose a different name for your Community channel.", color=constants.EMBED_COLOUR_ERROR)
            await interaction.response.send_message(embed=embed)

        # check whether it's an archived CC channel
        elif new_channel.category == archive_category:
            embed = discord.Embed(description=f"**Error**: A Community channel <#{new_channel.id}> already exists in the archives."
                                f" Use `/restore_community_channel` in the channel to restore it.", color=constants.EMBED_COLOUR_ERROR)
            await interaction.response.send_message(embed=embed)

        # the channel must exist with that name elsewhere on the server and so can't be used
        else:
            embed = discord.Embed(description=f"**Error**: A channel <#{new_channel.id}> already exists on the server"
                                f" and does not appear to be a Community channel."
                                f" Please choose a different name for your Community channel.", color=constants.EMBED_COLOUR_ERROR)
            await interaction.response.send_message(embed=embed)
            return

    else:
        # channel does not exist, create it
        new_channel = await _cc_create_channel(interaction, new_channel_name, cc_category)

    # create the role
    new_role = await _cc_role_create(interaction, new_channel_name)

    # assign channel permissions
    await _cc_assign_permissions(interaction, owner, new_channel)

    # enter into the db
    await _cc_db_enter(interaction, owner, new_channel, new_role)

    # add a note in bot_spam
    spamchannel = bot.get_channel(bot_spam_id)
    await spamchannel.send(f"{interaction.user} used `/create_community_channel` in <#{interaction.channel.id}> to add {owner.display_name} as a Community channel owner with channel <#{new_channel.id}>")

    return


@bot.tree.command(name="restore_community_channel",
    description="Restore an archived Community Channel.",
                guild=guild_obj)
@check_roles([cmentor_role_id, botadmin_role_id])
async def _restore_community_channel(interaction: discord.Interaction, owner: discord.Member):

    # get the CC categories as discord channel category objects
    cc_category = discord.utils.get(interaction.guild.categories, id=cc_cat_id)
    archive_category = discord.utils.get(interaction.guild.categories, id=archive_cat_id)

    # check we're in an archived community channel
    if not interaction.channel.category == archive_category:
        embed = discord.Embed(description=f"**Error**: This command can only be used in an archived Community channel in the <#{archive_cat_id}> category.", color=constants.EMBED_COLOUR_QU)
        return await interaction.response.send_message(embed=embed)

    # now prep the channel
    # CHECK: user already owns a channel
    if not await _cc_owner_check(interaction, owner): return

    # check the role validity here so we can stop if needed
    if not await _cc_role_create_check(interaction, interaction.channel.name): return

    # move the channel from the archive to the CC category
    try:
        await interaction.channel.edit(category=cc_category)
        embed = discord.Embed(description=f"<#{interaction.channel.id}> moved to <#{cc_cat_id}>.", color=constants.EMBED_COLOUR_OK)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = discord.Embed(description=f"**Error**: {e}", color=constants.EMBED_COLOUR_ERROR)
        await interaction.response.send_message(embed=embed)
        raise EnvironmentError(f"Error moving channel: {e}")

    # create the role
    new_role = await _cc_role_create(interaction, interaction.channel.name)

    # assign channel permissions
    await _cc_assign_permissions(interaction, owner, interaction.channel)

    # enter into the db
    await _cc_db_enter(interaction, owner, interaction.channel, new_role)

    # add a note in bot_spam
    spamchannel = bot.get_channel(bot_spam_id)
    await spamchannel.send(f"{interaction.user} used `/restore_community_channel` in <#{interaction.channel.id}> and granted ownership to {owner.display_name}.")

    return


# list all community carriers
@bot.command(name='cc_list', help='List all Community Carriers.')
@check_roles([cmentor_role_id, botadmin_role_id])
async def cc_list(ctx):

    carrier_db.execute(f"SELECT * FROM community_carriers")
    community_carriers = [CommunityCarrierData(carrier) for carrier in carrier_db.fetchall()]

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
    pages = [page for page in chunk(community_carriers)]

    max_pages = len(pages)
    current_page = 1

    embed = discord.Embed(title=f"{len(community_carriers)} Registered Community Carriers Page:#{current_page} of {max_pages}")
    count = 0   # Track the overall count for all carriers
    # Go populate page 0 by default
    for community_carriers in pages[0]:
        count += 1
        embed.add_field(name="\u200b",
                        value=f"{count}: <@{community_carriers.owner_id}> owns <#{community_carriers.channel_id}>, <@&{community_carriers.role_id}>", inline=False)
    # Now go send it and wait on a reaction
    message = await ctx.send(embed=embed)

    # From page 0 we can only go forwards
    if not current_page == max_pages: await message.add_reaction("▶️")

    # 60 seconds time out gets raised by Asyncio
    while True:
        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=60, check=validate_response)
            if str(reaction.emoji) == "▶️" and current_page != max_pages:

                print(f'{ctx.author} requested to go forward a page.')
                current_page += 1   # Forward a page
                new_embed = discord.Embed(title=f"{len(community_carriers)} Registered Community Carriers Page:{current_page}")
                for community_carriers in pages[current_page-1]:
                    # Page -1 as humans think page 1, 2, but python thinks 0, 1, 2
                    count += 1
                    new_embed.add_field(name="\u200b",
                                        value=f"{count}: <@{community_carriers.owner_id}> owns <#{community_carriers.channel_id}>, <@&{community_carriers.role_id}>", inline=False)

                await message.edit(embed=new_embed)

                # Ok now we can go back, check if we can also go forwards still
                if current_page == max_pages:
                    await message.clear_reaction("▶️")

                await message.remove_reaction(reaction, user)
                await message.add_reaction("◀️")

            elif str(reaction.emoji) == "◀️" and current_page > 1:
                print(f'{ctx.author} requested to go back a page.')
                current_page -= 1   # Go back a page

                new_embed = discord.Embed(title=f"{len(community_carriers)} Registered Community Carriers Page:{current_page}")
                # Start by counting back however many carriers are in the current page, minus the new page, that way
                # when we start a 3rd page we don't end up in problems
                count -= len(pages[current_page - 1])
                count -= len(pages[current_page])

                for community_carriers in pages[current_page - 1]:
                    # Page -1 as humans think page 1, 2, but python thinks 0, 1, 2
                    count += 1
                    new_embed.add_field(name="\u200b",
                                        value=f"{count}: <@{community_carriers.owner_id}> owns <#{community_carriers.channel_id}>, <@&{community_carriers.role_id}>", inline=False)

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
            print(f'Timeout hit during community carrier request by: {ctx.author}')
            embed = discord.Embed(description=f'Closed the active carrier list request from {ctx.author} due to no input in 60 seconds.', color=constants.EMBED_COLOUR_QU)
            await ctx.send(embed=embed)
            await message.delete()
            await ctx.message.delete()
            break


# find a community carrier channel by owner
@bot.command(name='cc_owner', help='Search for an owner by @ mention in the Community Carrier database.\n'
                             'Format: m.cc_owner @owner\n')
@check_roles([cmentor_role_id, botadmin_role_id])
async def cc_owner(ctx, owner: discord.Member):

    community_carrier_data = find_community_carrier(owner.id, CCDbFields.ownerid.name)
    if community_carrier_data:
        # TODO: this should be fetchone() not fetchall but I can't make it work otherwise
        for community_carrier in community_carrier_data:
            print(f"Found data: {community_carrier.owner_id} owner of {community_carrier.channel_id}")
            await ctx.send(f"User {owner.display_name} is registered as a Community Carrier with channel <#{community_carrier.channel_id}>")
            return
    else:
        await ctx.send(f"No Community Carrier registered to {owner.display_name}")


# button interaction class for /remove_community_channel
class RemoveCCView(View):
    def __init__(self, author): # call init to pass through the author variable
        self.author = author
        super().__init__()

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.author.id

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="💥", custom_id="delete")
    async def delete_button_callback(self, interaction, button):
        delete_channel = 1
        print("User wants to delete channel.")
        await _remove_cc_manager(interaction, delete_channel, self)

    @discord.ui.button(label="Archive", style=discord.ButtonStyle.primary, emoji="📂", custom_id="archive")
    async def archive_button_callback(self, interaction, button):
        delete_channel = 0
        print("User chose to archive channel.")
        await _remove_cc_manager(interaction, delete_channel, self)


    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray, emoji="✖", custom_id="cancel")
    async def cancel_button_callback(self, interaction, button):
        embed = discord.Embed(title="Remove Community Channel",
                          description=f"Operation cancelled by user.",
                          color=constants.EMBED_COLOUR_OK)
        self.clear_items()
        await interaction.response.edit_message(view=self, embed=embed)
        print("User cancelled cc_del command.")


# delete a Community Carrier
@bot.tree.command(name="remove_community_channel",
                  description="Retires a community channel.",
                  guild=guild_obj)
@check_roles([cmentor_role_id, botadmin_role_id])
async def _remove_community_channel(interaction: discord.Interaction):

    print(f"{interaction.user.name} called `/remove_community_channel` command in {interaction.channel.name}")
    author = interaction.user # define author here so we can use it to check the interaction later
    print(f"{interaction.user} is {author.name} as {author.display_name}")


    # check if we're in a community channel
    carrier_db.execute(f"SELECT * FROM community_carriers WHERE "
                    f"channelid = {interaction.channel.id}")
    community_carrier = CommunityCarrierData(carrier_db.fetchone())
    # if not, we return a notice and then try the db purge action
    if not community_carrier:
        embed = discord.Embed(description=f"This does not appear to be a community channel. Running purge task instead.", color=constants.EMBED_COLOUR_ERROR)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        # this purges database entries with invalid channel ids so users aren't stuck with ghost channels if e.g. it was manually deleted
        carrier_db.execute(f"SELECT * FROM community_carriers")
        community_carriers = [CommunityCarrierData(carrier) for carrier in carrier_db.fetchall()]
        for carrier in community_carriers:
            if not bot.get_channel(carrier.channel_id):
                print(f"Could not find channel for owner {carrier.owner_id}, deleting from db")
                embed = discord.Embed(description=f"Found invalid channel for <@{carrier.owner_id}>, removing from database."
                                                   f"\nRemoving <@&{cc_role_id}> from <@{carrier.owner_id}>."
                                                   f"\nDeleting associated channel role.", color=constants.EMBED_COLOUR_QU)
                await interaction.followup.send(embed=embed, ephemeral=True)
                try:
                    carrier_db.execute(f"DELETE FROM community_carriers WHERE channelid = {carrier.channel_id}")
                    owner = interaction.guild.get_member(carrier.owner_id)
                    embed = await _remove_cc_role_from_owner(interaction, owner) # this returns an embed but we'll only use it to pass into the next function
                    await _cc_role_delete(interaction, carrier.role_id, embed) # this returns an embed but we won't use it

                except Exception as e:
                    await interaction.followup.send(e, ephemeral=True)
        return

    elif community_carrier:
        print(f"Found data: {community_carrier.owner_id} owner of {community_carrier.channel_id}")
        owner_id = community_carrier.owner_id
        owner = await bot.fetch_user(owner_id)
        channel_id = community_carrier.channel_id
        role_id = community_carrier.role_id

    embed = discord.Embed(title="Remove Community Channel",
                          description=f"This will:\n\n• Remove the <@&{cc_role_id}> role from <@{owner_id}>\n"
                                      f"• Delete the associated role <@&{role_id}>\n"
                                      f"• Delete or Archive the channel <#{channel_id}>\n\n"
                                      f"• **Archived** channels are moved to the archive and remain accessible to Community Team members. "
                                      f"They can be re-activated at any time using `/restore_community_channel` in-channel.\n\n"
                                      f"• **WARNING**: *Deleted* channels are gone forever and can NOT be recovered.",
                          color=constants.EMBED_COLOUR_QU)

    view = RemoveCCView(author)

    await interaction.response.send_message(embed=embed, view=view)

    return

# function called by button responses to process channel deletion
async def _remove_cc_manager(interaction, delete_channel, button_self):
    # get the carrier data again because I can't figure out how to penetrate callbacks with additional variables or vice versa
    carrier_db.execute(f"SELECT * FROM community_carriers WHERE "
                    f"channelid = {interaction.channel.id}")
    community_carrier = CommunityCarrierData(carrier_db.fetchone())
    # error if not
    if not community_carrier:
        embed = discord.Embed(description=f"Error: This somehow does not appear to be a community channel anymore(?).", color=constants.EMBED_COLOUR_ERROR, ephemeral=True)
        await interaction.response.send_message(embed=embed)
        return

    elif community_carrier:
        print(f"Found data: {community_carrier.owner_id} owner of {community_carrier.channel_id}")
        guild = await get_guild()
        owner_id = community_carrier.owner_id
        owner = guild.get_member(owner_id)
        print(f"Owner is {owner}")
        role_id = community_carrier.role_id

    # now we do the thing

    # remove db entry
    print("Removing db entry...")
    if not await _remove_cc_owner_from_db(interaction, owner): return

    # remove role from owner
    print("Removing role from owner...")
    embed = await _remove_cc_role_from_owner(interaction, owner)

    # archive channel if relevant - we save deleting for later so user can read bot status messages in channel
    print("Processing archive flag...")

    if not delete_channel: embed = await _archive_cc_channel(interaction, embed, button_self, 0) # the 0 sets the number of attempts to archive the channel

    # delete role
    print("Deleting role...")
    embed = await _cc_role_delete(interaction, role_id, embed)

    # inform user of everything that happened
    print("Returning finished embed...")
    if delete_channel: embed.add_field(name="Channel", value=f"<#{interaction.channel.id}> **will be deleted** in **10 seconds**.", inline=False)
    embed.set_image(url=random.choice(byebye_gifs))
    await interaction.channel.send(embed=embed)

    # delete channel if relevant
    print("Processing delete flag...")
    if delete_channel: await _delete_cc_channel(interaction, button_self)

    # notify bot-spam
    print("Notifying bot-spam...")
    spamchannel = bot.get_channel(bot_spam_id)
    await spamchannel.send(f"{interaction.user} used `/remove_community_channel` in <#{interaction.channel.id}>, removing {owner.name} as a Community channel owner.")

    # all done
    print("_remove_cc_manager done.")
    return

# helper function for /remove_community_channel
async def _remove_cc_owner_from_db(interaction, owner):
    # remove the database entry
    try:
        error_msg = await delete_community_carrier_from_db(owner.id)
        if error_msg:
            return await interaction.channel.send(error_msg)

        print("User DB entry removed.")
    except Exception as e:
        return await interaction.channel.send(f'Something went wrong, go tell the bot team "computer said: {e}"')

    return True

# helper function for /remove_community_channel
async def _remove_cc_role_from_owner(interaction, owner):

    role = discord.utils.get(interaction.guild.roles, id=cc_role_id)

    embed = discord.Embed(title="Community Channel Removed", description=f"", color=constants.EMBED_COLOUR_OK)
    try:
        await owner.remove_roles(role)
        print(f"Removed Community Carrier role from {owner}")
        embed.add_field(name="Owner", value=f"<@{owner.id}> is no longer registered as the <@&{cc_role_id}>.", inline=False)
    except Exception as e:
        print(e)
        embed.add_field(name="Owner", value=f"**Failed removing role from <@{owner.id}>**: {e}", inline=False)

    return embed

# helper function for /remove_community_channel
async def _delete_cc_channel(interaction, button_self):
    # start a timer so the user has time to read the status embed
    channel_name = interaction.channel.name
    button_self.clear_items()
    await interaction.response.edit_message(view=button_self)
    print(f"Starting countdown for deletion of {channel_name}")
    await asyncio.sleep(10)
    try:
        await interaction.channel.delete()
        print(f'Deleted {channel_name}')

    except Exception as e:
        print(e)
        await interaction.channel.send(f"**Failed to delete <#{interaction.channel.id}>**: {e}")

    return

# helper function for /remove_community_channel
async def _archive_cc_channel(interaction, embed, button_self, attempt):
    archive_category = discord.utils.get(interaction.guild.categories, id=archive_cat_id)

    try: # there's probably a better way to do this using an if statement
        button_self.clear_items()
        await interaction.response.edit_message(view=button_self)
        await interaction.delete_original_response()
    except:
        pass

    try:
        await interaction.channel.edit(category=archive_category)
        # this interaction seems to take some time on the live server.
        # let's try adding a check that it's completed before proceeding
        if not interaction.channel.category == archive_category:
            attempt = attempt + 1
            await _archive_cc_channel_delay(interaction, embed, button_self, attempt)
        print("moved channel to archive")
        # now make sure it has the default permissions for the archive category
        await interaction.channel.edit(sync_permissions=True)
        print("Synced permissions")

        print(embed.fields)

        if len(embed.fields)==1: embed.add_field(name="Channel", value=f"<#{interaction.channel.id}> moved to Archives.", inline=False)

    except Exception as e:
        print(e)
        embed.add_field(name="Channel", value=f"**Failed archiving <#{interaction.channel.id}>**: {e}", inline=False)

    return embed

# helper function for archive function
async def _archive_cc_channel_delay(interaction, embed, button_self, attempt):
    print(f"Channel not moved yet. Number of attempts so far: {attempt}")
    attempt = attempt + 1
    print(f"Beginning attempt {attempt}")
    if attempt <= 5:
        await asyncio.sleep(2)
        await _archive_cc_channel(interaction, embed, button_self, attempt) # we probably don't need to attempt the channel edit again but is there a disadvantage to doing so?
    else: # still nothing after 10 seconds, give up I guess
        embed.add_field(name="Channel", value=f"**Failed archiving <#{interaction.channel.id}>**: channel does not appear to be moved after {attempt} attempts.", inline=False)

    return embed

# helper function for /remove_community_channel
async def _cc_role_delete(interaction, role_id, embed):
    # get the role
    role = discord.utils.get(interaction.guild.roles, id=role_id)
    # delete the role
    try:
        await role.delete()
        print(f'Deleted {role}')

        embed.add_field(name="Role", value=f"{role} deleted.", inline=False)

    except Exception as e:
        print(e)
        embed.add_field(name="Role", value=f"**Failed to delete <@&{role_id}>**: {e}", inline=False)

    return embed


# open a community channel (i.e. set non private)
@bot.tree.command(name="open_community_channel",
    description="Use in a Community Channel to open it to visitors (set it non-private).", guild=guild_obj)
@check_roles([cmentor_role_id, botadmin_role_id, cc_role_id]) # allow owners to open/close their own channels
async def _open_community_channel(interaction: discord.Interaction):
    print(f"{interaction.user.name} used /open_community_channel in {interaction.channel.name}")
    open = True
    await _openclose_community_channel(interaction, open)

# close a community channel (i.e. set private)
@bot.tree.command(name="close_community_channel",
    description="Use in a Community Channel to close it to visitors (set it private).", guild=guild_obj)
@check_roles([cmentor_role_id, botadmin_role_id, cc_role_id]) # allow owners to open/close their own channels
async def _close_community_channel(interaction: discord.Interaction):
    print(f"{interaction.user.name} used /close_community_channel in {interaction.channel.name}")
    open = False
    await _openclose_community_channel(interaction, open)

# helper function for open and closing community channel commands
async def _openclose_community_channel(interaction, open):

    status_text_verb = "open" if open else "close"
    status_text_adj = "open" if open else "closed"

    #check we're in the right category
    cc_category = discord.utils.get(interaction.guild.categories, id=cc_cat_id)
    if not interaction.channel.category == cc_category:
        embed = discord.Embed(description=f"**Error**: This command can only be used in an active Community channel in the <#{cc_cat_id}> category.", color=constants.EMBED_COLOUR_ERROR)
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    # now set permissions
    try:
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=None) if open else await interaction.channel.set_permissions(interaction.guild.default_role, read_messages=False)
    except Exception as e:
        embed = discord.Embed(description=f"**ERROR**: Could not {status_text_verb} channel: {e}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # notify user
    embed = discord.Embed(description=f"**<#{interaction.channel.id}> is {status_text_adj}!**"
                                      f"{' This channel is now visble to the server community 😊' if open else f' This channel is now hidden from the server community 😳'}",
                                       color=constants.EMBED_COLOUR_OK)
    await interaction.response.send_message(embed=embed, ephemeral=True)

    # notify channel
    des_text = "Welcome everybody, it's good to see you here!" if open else "So long, farewell, auf Wiedersehen, goodbye."
    embed = discord.Embed(title=f"★ COMMUNITY CHANNEL {status_text_adj.upper()} ★", description=f"**<#{interaction.channel.id}> is now {status_text_adj}!** *🎶 {des_text}*", color=constants.EMBED_COLOUR_OK)
    embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)
    embed.set_thumbnail(url=interaction.guild.icon.url)
    embed.timestamp= datetime.now(tz=timezone.utc)
    if open: # we don't need the notify_me footer on close and nobody's going to see any close gifs except community team members
        embed.set_image(url=random.choice(hello_gifs))
        embed.set_footer(text="You can use \"/notify_me\" in this channel to sign up for notifications of announcements by the channel owner or Community Mentors."
                    "\nYou can opt out at any time by using \"/notify_me\" again.")
    await interaction.channel.send(embed=embed)

    return


# sign up for a Community Carrier's notification role
@bot.tree.command(name="notify_me",
    description="Private command: Use in a COMMUNITY CHANNEL to opt in/out to receive its notifications.", guild=guild_obj)
async def _notify_me(interaction: discord.Interaction):
    print(f"{interaction.user.name} used /notify_me in {interaction.channel.name}")

    # note channel ID
    msg_channel_id = interaction.channel.id

    # define spamchannel
    spamchannel = bot.get_channel(bot_spam_id)

    # look for a match for the channel ID in the community carrier DB
    community_carrier_data = find_community_carrier(msg_channel_id, CCDbFields.channelid.name)

    if not community_carrier_data:
        # if there's no channel match, return an error
        embed = discord.Embed(description="Please try again in a Community Channel.", color=constants.EMBED_COLOUR_ERROR)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    elif community_carrier_data:
        # TODO: this should be fetchone() not fetchall but I can't make it work otherwise
        for community_carrier in community_carrier_data:
            print(f"Found data: {community_carrier.owner_id} owner of {community_carrier.channel_id}")
            channel_id = community_carrier.channel_id
            role_id = community_carrier.role_id
            owner_id = community_carrier.owner_id

    # we're in a carrier's channel so try to match its role ID with a server role
    print(f"/notify used in channel for {channel_id}")
    notify_role = discord.utils.get(interaction.guild.roles, id=role_id)

    # check if role actually exists
    if not notify_role:
        await interaction.response.send_message("Sorry, I couldn't find a notification role for this channel. Please report this to an Admin.", ephemeral=True)
        await spamchannel.send(f"**ERROR**: {interaction.user} tried to use `/notify_me` in <#{interaction.channel.id}> but received an error (role does not exist).")
        print(f"No role found matching {interaction.channel}")
        return

    # check if user has this role
    print(f'Check whether user has role: "{notify_role}"')
    print(f'User has roles: {interaction.user.roles}')
    if notify_role not in interaction.user.roles:
        # they don't so give it to them
        await interaction.user.add_roles(notify_role)
        embed = discord.Embed(title=f"You've signed up for notifications for {interaction.channel.name}!",
                                description=f"You'll receive notifications from <@{owner_id}> or "
                                            f"<@&{cmentor_role_id}>s about this event or channel's activity. You can cancel at any"
                                            f" time by using `/notify_me` again in this channel.", color=constants.EMBED_COLOUR_OK)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        # they do so take it from them
        await interaction.user.remove_roles(notify_role)
        embed = discord.Embed(title=f"You've cancelled notifications for {interaction.channel.name}.",
                                description="You'll no longer receive notifications about this event or channel's activity."
                                            " You can sign up again at any time by using `/notify_me` in this channel.",
                                            color=constants.EMBED_COLOUR_QU)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# send a notice from a Community Carrier owner to their 'crew' - this is the long form command using a modal
@bot.tree.command(name="send_notice",
    description="Private command: Used by Community Channel owners to send notices to their participants.", guild=guild_obj)
@check_roles([cmentor_role_id, botadmin_role_id, cc_role_id]) # allow all owners for now then restrict during command
async def _send_notice(interaction: discord.Interaction):
    print(f"{interaction.user.name} used /send_notice in {interaction.channel.name}")

    community_carrier = await _send_notice_channel_check(interaction)
    if not community_carrier: return

    # create a modal to take the message
    await interaction.response.send_modal(SendNoticeModal(community_carrier.role_id, None)) # the None parameter tells the modal we are sending, not editing

    print("Back from modal interaction")

    try: # this to avoid annoying thinking response remaining bug if user cancels on mobile
        await interaction.response.defer()
    finally:
        return

# modal for send_notice
class SendNoticeModal(Modal):
    def __init__(self, role_id, orginal_message, title = 'Send to Community Channel', timeout = None) -> None:
        self.role_id = role_id # we need to use the role_id in the response
        self.original_message = orginal_message # if used via edit, this will be a discord.Message object
        super().__init__(title=title, timeout=timeout)

    embedtitle = discord.ui.TextInput(
        label='Optional: give your message a title',
        placeholder='Leave blank for none.',
        required=False,
        max_length=256,
    )
    message = discord.ui.TextInput(
        label='Enter your message below.',
        style=discord.TextStyle.long,
        placeholder='Normal Discord markdown works, but mentions and custom emojis require full code.',
        required=True,
        max_length=4000,
    )
    image = discord.ui.TextInput(
        label='Optional: include an image',
        placeholder='Enter the image\'s URL or leave blank for none.',
        required=False,
        max_length=512,
    )

    async def on_submit(self, interaction: discord.Interaction):
        print(self.role_id)

        embed, file = await _generate_cc_notice_embed(interaction.channel.id, interaction.user.display_name, interaction.user.display_avatar.url, self.embedtitle, self.message, self.image)

        header_text = f":bell: <@&{self.role_id}> New message from <@{interaction.user.id}> for <#{interaction.channel.id}> :bell:"

        if self.original_message: # if the modal was called by the edit command, we'll edit instead of sending a new message
            print("Editing existing message")
            await self.original_message.edit(content=f"{header_text}\n*(edited {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')})*", embed=embed)
            await interaction.response.send_message(embed=discord.Embed(description=f"Message edited: {self.original_message.jump_url}", color=constants.EMBED_COLOUR_OK), ephemeral=True)

        else:
            await interaction.response.defer() # this gives us time to upload the file, but also responses and followups do not ping
            print("Sending new message")
            # send the message to the CC channel
            if file: # "file" is the thumbnail image
                await interaction.channel.send(header_text, file=file, embed=embed)
            else:
                await interaction.channel.send(header_text, embed=embed)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message(f'Oops! Something went wrong: {error}', ephemeral=True)


# embed generator for send_notice commands
async def _generate_cc_notice_embed(channel_id, user, avatar, title, message, image_url):
    print(f"generating embed for CC notice in channel {channel_id}")

    thumb_file = None

    if os.path.isfile(f"images/cc/{channel_id}.png"):
        thumb_file = discord.File(f'images/cc/{channel_id}.png', filename='image.png')
        print(thumb_file)

    embed = discord.Embed(title=title, description=message, color=constants.EMBED_COLOUR_QU)
    embed.set_author(name=user, icon_url=avatar)
    embed.set_image(url=image_url)
    if thumb_file: embed.set_thumbnail(url='attachment://image.png')
    embed.timestamp= datetime.now(tz=timezone.utc)
    embed.set_footer(text="Use \"/notify_me\" in this channel to sign up for future notifications."
                    "\nYou can opt out at any time by using \"/notify_me\" again.")

    return embed, thumb_file

# send_notice app command - alternative to above, just noms a message like adroomba but via right click
@bot.tree.context_menu(name='Send CC Notice')
@check_roles([cmentor_role_id, botadmin_role_id, cc_role_id])
async def send_cc_notice(interaction: discord.Interaction, message: discord.Message):
    print(f"{interaction.user.name} used send context menu in {interaction.channel.name}")

    community_carrier = await _send_notice_channel_check(interaction)
    if not community_carrier: return

    try:
        embed, file = await _generate_cc_notice_embed(message.channel.id, message.author.display_name, message.author.display_avatar.url, None, message.content, None) # get the embed
        if message.author.id == interaction.user.id:
            heading = f"<@&{community_carrier.role_id}> New message from <@{interaction.user.id}>"
        else:
            heading = f"<@&{community_carrier.role_id}>: <@{interaction.user.id}> has forwarded a message from <@{message.author.id}>"

        # send the embed
        if file: # this "file" is the message thumbnail, if any
            await interaction.channel.send(f":bell: {heading} for <#{interaction.channel.id}> :bell:", file=file, embed=embed)
        else:
            await interaction.channel.send(f":bell: {heading} for <#{interaction.channel.id}> :bell:", embed=embed)

        if message.author.id == interaction.user.id: await message.delete() # you can send anyone's message using this interaction
                                                                            # this check protects the messages of random users from being deleted if sent
        embed = discord.Embed(description="Your notice has been sent.", color=constants.EMBED_COLOUR_OK)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"Sorry, I couldn't send your message. Reason: {e}", ephemeral=True)

# helper function shared by the send_notice commands
async def _send_notice_channel_check(interaction):
    # check if we're in a community channel
    carrier_db.execute(f"SELECT * FROM community_carriers WHERE "
                    f"channelid = {interaction.channel.id}")
    community_carrier = CommunityCarrierData(carrier_db.fetchone())
    # error if not
    if not community_carrier:
        embed = discord.Embed(description=f"Error: This does not appear to be a community channel.", color=constants.EMBED_COLOUR_ERROR)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    elif community_carrier:
        print(f"Found data: {community_carrier.owner_id} owner of {community_carrier.channel_id}")
        owner = await bot.fetch_user(community_carrier.owner_id)

    # check that the command user is the channel owner, or a Community Mentor/Admin
    if not interaction.user.id == owner.id:
        print("Channel user is not command user")
        if not await checkroles(interaction, [cmentor_role_id, botadmin_role_id]): return
    return community_carrier

# edit notice app command - edits an existing sent notice
@bot.tree.context_menu(name='Edit CC Notice')
@check_roles([cmentor_role_id, botadmin_role_id, cc_role_id])
async def edit_cc_notice(interaction: discord.Interaction, message: discord.Message):
    print(f"{interaction.user.name} used edit CC notice context menu in {interaction.channel.name}")

    # check we're in a CC channel and get the CC data
    community_carrier = await _send_notice_channel_check(interaction)
    if not community_carrier: return

    """
    Now we check the message that we've been given. It must:
    1. be by MAB
    2. have been originally authored by the interaction.user
    3. have characteristics of a send_notice message
    We can check 2 & 3 with the same string
    """
    if not message.author.id == bot.user.id or not f"New message from <@{interaction.user.id}>" in message.content:
        await interaction.response.send_message(embed=discord.Embed(description=f"Error: This does not appear to be a CC Notice message, or a CC Notice message authored by you.", color=constants.EMBED_COLOUR_ERROR), ephemeral=True)

    # Zhu'li, do the thing
    # call the sendnotice modal to take the message
    await interaction.response.send_modal(SendNoticeModal(community_carrier.role_id, message))

    print("Back from modal interaction")

    try: # this to avoid annoying thinking response remaining bug if user cancels on mobile
        await interaction.response.defer()
    finally:
        return


# help for Community Channel users. when we refactor we'll work on having proper custom help available in more depth
@bot.tree.command(name="community_channel_help",
    description="Private command: get help with Community Channel commands and functions.", guild=guild_obj)
@check_roles([cmentor_role_id, botadmin_role_id, cc_role_id, cpillar_role_id])
async def _community_channel_help(interaction: discord.Interaction):
    print(f"{interaction.user.name} used /community_channel_help")
    embed = discord.Embed(title="Community Channel Help",
                          # sorry Kutu I'm not wrapping this too eagerly
                          description=f"**Community Channel commands:**\n\nAll commands require the <@&{cmentor_role_id}> role unless specified."
                          "\n\n:arrow_forward: `/create_community_channel`:\n"
                          "**USE IN**: anywhere (but please use it in the back rooms only!)\n"
                          "**REQUIRES:** a **user**, a **channel name**, and optionally an **emoji** to go at the beginning of the channel name.\n"
                          "**FUNCTION**: creates a new Community Channel.\n"
                          "Best practice for channel name is a single word or short phrase of no more than 30 characters. Disallowed characters "
                          "are automatically stripped and spaces are converted to hyphens. The emoji, if supplied, is put at the beginning of the channel's name. "
                          "Each CC is registered to one user, known as the channel 'owner', and each user can only have one CC registered to them. "
                          "CC owners get full permissions on their channel and can rename them, pin messages, delete any message, etc. "
                          "Creating a Community Channel also creates an associated role which users can sign up to for notices. "
                          f"CC owners, as well as <@&{cmentor_role_id}>s, can use a special command to send notices to this role. "
                          "Note: **new Community Channels are set to private** when created."
                          "\n\n:arrow_forward: `/open_community channel`:\n"
                          "**USE IN**: the target Community Channel\n"
                          f"**USED BY**: channel owner or any <@&{cmentor_role_id}>\n"
                          "**FUNCTION**: Makes the channel no longer private, i.e. open for any P.T.N. Pilot to view."
                          "\n\n:arrow_forward: `/close_community channel`:\n"
                          "**USE IN**: the target Community Channel\n"
                          f"**USED BY**: channel owner or any <@&{cmentor_role_id}>\n"
                          "**FUNCTION**: Makes the channel private again, i.e. hidden from normal users' view. Community roles and the channel's owner can still see private Community Channels."
                          "\n\n:arrow_forward: `/remove_community_channel`:\n"
                          "**USE IN**: the target Community Channel\n"
                          "**FUNCTION**: Deletes or Archives the Community Channel.\n"
                          "Archived CCs remain visible to Community team roles. If the channel's erstwhile owner has one of these roles, they will also be able to see it, but will no longer be considered "
                          "its 'owner'. **This command also has a secondary purpose**: if used *outside a Community Channel*, it will scan the database and check for "
                          "any orphaned owners (owners with a channel which is no longer valid) and purge them from the database. Useful if a community channel has "
                          "been accidentally deleted or the database update failed upon the bot removing it."
                          "\n\n:arrow_forward: `/restore_community_channel`:\n"
                          "**USE IN**: target archived Community Channel\n"
                          "**REQUIRES:** a **user** to be the channel's new owner\n"
                          "**FUNCTION**: moves the archived Community Channel back to the Community Channel category and assigns it an owner. "
                          "As with newly created  Community Channels, restored channels are also set to private until 'opened'.",
                          color=constants.EMBED_COLOUR_QU)
    await interaction.response.send_message(embed=embed, ephemeral=True)
    embed = discord.Embed(title="Community Channel Help",
                            # sorry Kutu I'm not wrapping this too eagerly
                            description="\n\n**Broadcast message commands:**"
                            f"\n\n:arrow_forward: `/send_notice`:\n"
                            "**USE IN**: the target Community Channel\n"
                            f"**USED BY**: channel owner or any <@&{cmentor_role_id}>\n"
                            "**FUNCTION**: This command gives its user a pop-out form in which to type a message which will be sent to the channel as an embed, pinging the channel's "
                            "associated role in the process. The embed can be up to 4000 characters and can optionally include a title and an image: images have to be linked, not uploaded,"
                            " but you can upload them to Discord (anywhere, even in a DM or another server) and use the link from that. It will also "
                            "feature the name and avatar of the sending user, and, if set up (see below), a thumbnail image."
                            "\n\n:arrow_forward: **\"Send CC Notice\"** context menu command:\n"
                            "**USE ON**: any message in the target Community Channel\n"
                            f"**USED BY**: channel owner or any <@&{cmentor_role_id}>\n"
                            "**FUNCTION**: Similar to the above, this sends a notice to the channel's associated role, but it can be "
                            "used *on a message* in the channel. To access it:\n> :mouse_three_button: **Right click** or :point_up_2: **long press** on any message in the channel\n"
                            "> :arrow_right: **Apps**\n> :arrow_right: **Send CC Notice**\n"
                            "If the message was sent by the command's user, it will be consumed by the bot and spat out with a role ping and helpful information appended. "
                            "If the message was sent by anyone else, it will not be deleted, but the bot will instead copy it."
                            "\n\n:arrow_forward: **\"Upload CC Thumb\"** context menu command:\n"
                            "**USE ON**: any message in the target Community Channel\n"
                            f"**USED BY**: channel owner or any <@&{cmentor_role_id}>\n"
                            "**FUNCTION**: if the message contains an attached image, that image will be uploaded for use as a thumbnail on `/send_notice` embeds. "
                            "If not, any existing thumbnail will be deleted. To use it:\n> :mouse_three_button: **Right click** or :point_up_2: **long press** on any message in the channel\n"
                            "> :arrow_right: **Apps**\n> :arrow_right: **Upload CC Thumb**\n"
                            "\n:arrow_forward: **\"Edit CC Notice\"** context menu command:\n"
                            "**USED BY**: author of a CC notice message\n"
                            "**FUNCTION**: Edits (recreates from scratch) any CC Notice message sent by MAB *of which the user is the original author*."
                            "You may not edit messages you forward from another user, or CC Notices sent by another user. To use it:\n"
                            "> :mouse_three_button: **Right click** or :point_up_2: **long press** on a CC Notice message in the channel\n"
                            "> :arrow_right: **Apps**\n> :arrow_right: **Edit CC Notice**\n",
                            color=constants.EMBED_COLOUR_QU)
    await interaction.followup.send(embed=embed, ephemeral=True)

#
#                       COMMUNITY NOMINATION COMMANDS
#

# prints information about /nominate to current channel
@bot.tree.command(name="thanks",
    description="COMMUNITY TEAM ONLY: Display information about the /nominate command.", guild=guild_obj)
@check_roles([cpillar_role_id, cmentor_role_id, botadmin_role_id, mod_role_id])
async def _thanks(interaction: discord.Interaction):
    print(f"/thanks called by {interaction.user} in {interaction.channel.name}")
    embed = discord.Embed(title=":heart: NOMINATE TO APPRECIATE :heart:",
                          description="Did someone **go out of their way to be helpful**? Use the </nominate:878304221118742578> "
                                      "command to help them be considered "
                                      f"for <@&{cpillar_role_id}> and show your appreciation!", color=constants.EMBED_COLOUR_QU)
    embed.set_thumbnail(url='https://pilotstradenetwork.com/wp-content/uploads/2021/08/PTN_Discord_Icon.png')
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="nominate",
    description="Private command: Nominate an @member to become a Community Pillar.", guild=guild_obj)
async def _nominate(interaction: discord.Interaction, user: discord.Member, *, reason: str):

    # TODO: command to list nominations for a nominator

    # first check the user is not nominating themselves because seriously dude

    if interaction.user.id == user.id:
        print(f"{interaction.user} tried to nominate themselves for Community Pillar :]")
        return await interaction.response.send_message("You can't nominate yourself! But congrats on the positive self-esteem :)", ephemeral=True)

    #Skip nominating Cpillar|Cmentor|Council|Mod
    for avoid_role in [cpillar_role_id, cmentor_role_id, botadmin_role_id, mod_role_id]:
        if user.get_role(avoid_role):
            print(f"{interaction.user} tried to nominate a Cpillar|Cmentor|Council|Mod : {user.name}")
            return await interaction.response.send_message(
                ("You can't nominate an existing Community Pillar,"
                " Community Mentor, Council or Mod."
                " But we appreciate your nomination attempt!"),
                ephemeral=True)

    print(f"{interaction.user} wants to nominate {user}")
    spamchannel = bot.get_channel(bot_spam_id)

    # first check this user has not already nominated the same person
    nominees_data = find_nominator_with_id(interaction.user.id)
    if nominees_data:
        for nominees in nominees_data:
            if nominees.pillar_id == user.id:
                print("This user already nommed this dude")
                embed = discord.Embed(title="Nomination Failed", description=f"You've already nominated <@{user.id}> for reason **{nominees.note}**.\n\n"
                                                                             f"You can nominate any number of users, but only once for each user.", color=constants.EMBED_COLOUR_ERROR)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

    print("No matching nomination, proceeding")

    # enter nomination into nominees db
    try:
        print("Locking carrier db...")
        await carrier_db_lock.acquire()
        print("Carrier DB locked.")
        try:
            carrier_db.execute(''' INSERT INTO nominees VALUES(?, ?, ?) ''',
                            (interaction.user.id, user.id, reason))
            carriers_conn.commit()
            print("Registered nomination to database")
        finally:
            print("Unlocking carrier db...")
            carrier_db_lock.release()
            print("Carrier DB unlocked.")
    except Exception as e:
        await interaction.response.send_message("Sorry, something went wrong and developers have been notified.", ephemeral=True)
        # notify in bot_spam
        await spamchannel.send(f"Error on /nominate by {interaction.user}: {e}")
        return print(f"Error on /nominate by {interaction.user}: {e}")

    # notify user of success
    embed = discord.Embed(title="Nomination Successful", description=f"Thank you! You've nominated <@{user.id}> "
                                f"to become a Community Pillar.\n\nReason: **{reason}**", color=constants.EMBED_COLOUR_OK)
    await interaction.response.send_message(embed=embed, ephemeral=True)

    # also tell bot-spam
    await spamchannel.send(f"<@{user.id}> was nominated for Community Pillar.")
    return print("Nomination successful")


@bot.tree.command(name="nominate_remove",
    description="Private command: Remove your Pillar nomination for a user.", guild=guild_obj)
async def _nominate_remove(interaction: discord.Interaction, user: discord.Member):

    print(f"{interaction.user} wants to un-nominate {user}")

    # find the nomination
    nominees_data = find_nominator_with_id(interaction.user.id)
    if nominees_data:
        for nominees in nominees_data:
            if nominees.pillar_id == user.id:
                await delete_nominee_by_nominator(interaction.user.id, user.id)
                embed = discord.Embed(title="Nomination Removed", description=f"Your nomination for <@{user.id}> "
                                           f"has been removed. If they're being a jerk, consider reporting privately "
                                           f"to a Mod or Council member.", color=constants.EMBED_COLOUR_OK)
                await interaction.response.send_message(embed=embed, ephemeral=True)

                # notify bot-spam
                spamchannel = bot.get_channel(bot_spam_id)
                await spamchannel.send(f"A nomination for <@{user.id}> was withdrawn.")
                return

    # otherwise return an error
    print("No such nomination")
    return await interaction.response.send_message("No nomination found by you for that user.", ephemeral=True)

def nom_count_user(pillarid):
    """
    Counts how many active nominations a nominee has.
    """
    nominees_data = find_nominee_with_id(pillarid)

    count = len(nominees_data)
    print(f"{count} for {pillarid}")

    return count

@bot.command(name='nom_count', help='Shows all users with more than X nominations')
@check_roles([cmentor_role_id, botadmin_role_id])
@check_command_channel(conf['ADMIN_BOT_CHANNEL'])
async def nom_count(ctx, number: int):

    numberint = int(number)

    print(f"nom_list called by {ctx.author}")
    embed=discord.Embed(title="Community Pillar nominees", description=f"Showing all with {number} nominations or more.", color=constants.EMBED_COLOUR_OK)

    print("reading database")

    # we need to 1: get a list of unique pillars then 2: send only one instance of each unique pillar to nom_count_user

    # 1: get a list of unique pillars
    carrier_db.execute(f"SELECT DISTINCT pillarid FROM nominees")
    nominees_data = [NomineesData(nominees) for nominees in carrier_db.fetchall()]
    for nominees in nominees_data:
        print(nominees.pillar_id)

        # 2: pass each unique pillar through to the counting function to retrieve the number of times they appear in the table
        count = nom_count_user(nominees.pillar_id)
        print(f"{nominees.pillar_id} has {count}")

        # only show those with a count >= the number the user specified
        if count >= numberint:
            embed.add_field(name=f'{count} nominations', value=f"<@{nominees.pillar_id}>", inline=False)

    await ctx.send(embed=embed)
    return print("nom_count complete")


@bot.command(name='nom_details', help='Shows nomination details for given user by ID or @ mention')
@check_roles([cmentor_role_id, botadmin_role_id])
@check_command_channel(conf['ADMIN_BOT_CHANNEL'])
async def nom_details(ctx, userid: Union[discord.Member, int]):
    # userID should really be a discord.Member object, but that lacks a sensible way to cast back to a userid,
    # so just use a string and ignore the problem.


    if not isinstance(userid, discord.Member):
        # sanitise userid in case they used an @ mention
        userid = int(re.search(r'\d+', userid).group())
        member = await bot.fetch_user(userid)
        print(f"looked for member with {userid} and found {member}")

    else:
        # if we have a member object, then the member is the userid, and the id is the userid.id ... confused?
        member = userid
        userid = userid.id  # Actually the ID

    print(f"nom_details called by {ctx.author} for member: {member}")

    embed=discord.Embed(title=f"Nomination details", description=f"Discord user <@{member.id}>", color=constants.EMBED_COLOUR_OK)

    # look up specified user and return every entry for them as embed fields. TODO: This will break after too many nominations, would need to be paged.
    # if an empty list is returned, update the embed description and color
    nominees_data = find_nominee_with_id(userid)
    if nominees_data:
        for nominees in nominees_data:
            nominator = await bot.fetch_user(nominees.nom_id)
            embed.add_field(name=f'Nominator: {nominator.display_name}',
                            value=f"{nominees.note}", inline=False)
    else:
        embed.description = f'No nominations found for <@{member.id}>'
        embed.color = constants.EMBED_COLOUR_REDDIT

    await ctx.send(embed=embed)


@bot.command(name='nom_delete', help='Completely removes all nominations for a user by user ID or @ mention. NOT RECOVERABLE.')
@check_roles([cmentor_role_id, botadmin_role_id])
@check_command_channel(conf['ADMIN_BOT_CHANNEL'])
async def nom_delete(ctx, userid: Union[str, int]):

    print(f"nom_delete called by {ctx.author}")

    # userID should really be a discord.Member object, but that lacks a sensible way to cast back to a userid,
    # so just use a string and ignore the problem.

    # sanitise userid in case they used an @ mention
    if not isinstance(userid, discord.Member):
        # sanitise userid in case they used an @ mention
        userid = int(re.search(r'\d+', userid).group())
        member = await bot.fetch_user(userid)
        print(f"looked for member with {userid} and found {member}")

    else:
        # if we have a member object, then the member is the userid, and the id is the userid.id ... confused?
        member = userid
        userid = userid.id  # Actually the ID

    # check whether user has any nominations
    nominees_data = find_nominee_with_id(userid)
    if not nominees_data:
        return await ctx.send(f'No results (user ID {userid})')

    # now check they're sure they want to delete

    def check(message):
        return message.author == ctx.author and message.channel == ctx.channel and \
                                 message.content.lower() in ["y", "n"]

    await ctx.send(f"Are you **sure** you want to completely remove {member} from the nominees database? **The data is gone forever**.\n**y**/**n**")

    try:
        msg = await bot.wait_for("message", check=check, timeout=30)
        if msg.content.lower() == "n":
            await ctx.send("OK, cancelling.")
            print("User cancelled nom_del command.")
            return
        elif msg.content.lower() == "y":
            print("User wants to proceed with removal.")
            await ctx.send("You're the boss, boss.")

    except asyncio.TimeoutError:
        await ctx.send("**Cancelled**: no response.")
        return

    # remove the database entry
    try:
        error_msg = await delete_nominee_from_db(userid)
        if error_msg:
            return await ctx.send(error_msg)

        print("User removed from nominees database.")
    except Exception as e:
        return await ctx.send(f'Something went wrong, go tell the bot team "computer said: {e}"')

    await ctx.send(f"User {member} removed from nominees database.")



# ping the bot
@bot.command(name='ping', help='Ping the bot')
@check_roles(any_elevated_role)
async def ping(ctx):
    print(f"{ctx.author} used PING in {ctx.channel.name}")
    gif = random.choice(hello_gifs)
    await ctx.send(gif)
    # await ctx.send("**PING? PONG!**")


@bot.command(name='unlock_override', help='Unlock the channel lock manually after Sheriff Benguin breaks it.')
@check_roles([botadmin_role_id, botdev_role_id])
async def unlock_override(ctx):

    print(f"{ctx.author} called manual channel_lock release in {ctx.channel}")
    if not carrier_channel_lock.locked():
        return await ctx.send("Channel lock is not set.")

    await ctx.send("Make sure nobody is using the Mission Generator before proceeding.")
    global deletion_in_progress

    # this global variable is set when the channel deletion function acquires its lock
    if deletion_in_progress:
        await ctx.send("Lock appears to be set from a channel deletion task underway. This usually takes ~10 seconds per channel."
                       " Please make sure no mission channels are about to be deleted. Deletion occurs 15 minutes after `m.complete`"
                       " or `m.done` or 2 minutes following using a mission generator command without generating a mission "
                       "(i.e. by error or user abort).")

    await ctx.send("Do you still want to proceed? **y**/**n**")

    def check(message):
        return message.author == ctx.author and message.channel == ctx.channel and \
                                    message.content.lower() in ["y", "n"]

    try:
        msg = await bot.wait_for("message", check=check, timeout=30)
        if msg.content.lower() == "n":
            await ctx.send("Manual lock release aborted.")
            print("User cancelled manual unlock command.")
            return
        elif msg.content.lower() == "y":
            print("User wants to manually release channel lock.")

    except asyncio.TimeoutError:
        await ctx.send("**Cancelled**: no response.")
        return

    await ctx.send("OK. Releasing channel lock.")
    carrier_channel_lock.release()

    deletion_in_progress = False
    print("Channel lock manually released.")


@bot.command(name='cron_status', help='Check the status of the lasttrade cron task')
@check_roles([botadmin_role_id, botdev_role_id])
async def cron_status(ctx):

    if not lasttrade_cron.is_running() or lasttrade_cron.failed():
        print("lasttrade cron task has failed, restarting.")
        await ctx.send('lasttrade cron task has failed, restarting...')
        lasttrade_cron.restart()
    else:
        nextrun = lasttrade_cron.next_iteration - datetime.now(tz=timezone.utc)
        await ctx.send(f'lasttrade cron task is running. Next run in {str(nextrun)}')


# quit the bot
@bot.command(name='stopquit', help="Stops the bots process on the VM, ending all functions.")
@check_roles([botadmin_role_id])
async def stopquit(ctx):
    await ctx.send(f"k thx bye")
    await user_exit()


# lasttrade task loop:
# Every 24 hours, check the timestamp of the last trade for all carriers and remove
# 'Certified Carrier' role from owner if there has been no trade for 28 days.
# If not already present, add 'Fleet Reserve' role to the owner.
@tasks.loop(hours=24)
async def lasttrade_cron():
    print(f"last trade cron running.")
    try:
        # get roles
        guild = await get_guild()
        cc_role = discord.utils.get(guild.roles, id=certcarrier_role_id)
        fr_role = discord.utils.get(guild.roles, id=rescarrier_role_id)
        # get spam channel
        spamchannel = bot.get_channel(bot_spam_id)
        # calculate epoch for 28 days ago
        now = datetime.now(tz=timezone.utc)
        lasttrade_max = now - timedelta(days=28)
        # get carriers who last traded >28 days ago
        # for owners with multiple carriers look at only the most recently used
        carrier_db.execute(f'''
                            SELECT p_ID, shortname, ownerid, lasttrade
                            FROM carriers c1
                            WHERE lasttrade = (SELECT MAX(lasttrade) FROM carriers c2 WHERE c1.ownerid = c2.ownerid)
                            and lasttrade < {int(lasttrade_max.timestamp())}
                            ''')
        carriers = [CarrierData(carrier) for carrier in carrier_db.fetchall()]
        for carrier_data in carriers:
            # check roles on owners, remove/add as needed.
            last_traded = datetime.fromtimestamp(carrier_data.lasttrade).strftime('%Y-%m-%d %H:%M:%S')
            print(f"Processing carrier '{carrier_data.carrier_short_name}'. Last traded: {last_traded}")
            owner = guild.get_member(carrier_data.ownerid)
            if owner:
                if cc_role in owner.roles:
                    print(f"{owner.name} has the Certified Carrier role, removing.")
                    await owner.remove_roles(cc_role)
                    await spamchannel.send(f"{owner.name} has been removed from the Certified Carrier role due to inactivity.")
                    # notify by DM
                    owner_dm = await bot.fetch_user(carrier_data.ownerid)
                    await owner_dm.send(f"Ahoy CMDR! Your last PTN Fleet Carrier trade was more than 28 days ago at {last_traded} so you have been automatically marked as inactive and placed in the PTN Fleet Reserve. **You can visit <#939919613209223270> at any time to mark yourself as active and return to trading**. o7 CMDR!")
                    print(f"Notified {owner.name} by DM.")
                if fr_role not in owner.roles:
                    print(f"{owner.name} does not have the Fleet Reserve role, adding.")
                    await owner.add_roles(fr_role)
                    await spamchannel.send(f"{owner.name} has been added to the Fleet Reserve role.")
            else:
                print(f"Carrier owner id {carrier_data.ownerid} is invalid, skipping.")
                await spamchannel.send(f"Owner of {carrier_data.carrier_short_name} with ID {carrier_data.ownerid} is invalid. "
                                        "Cannot process lasttrade_cron for this carrier.")
        print("All carriers have been processed.")
    except Exception as e:
        print(f"last trade cron failed: {e}")
        pass


#
# error handling
#
@bot.event
async def on_command_error(ctx, error):
    gif = random.choice(error_gifs)
    if isinstance(error, commands.BadArgument):
        await ctx.send(f'**Bad argument!** {error}')
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("**Invalid command.**")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("**Sorry, that didn't work**.\n• Check you've included all required arguments. Use `m.help <command>` for details."
                       "\n• If using quotation marks, check they're opened *and* closed, and are in the proper place.\n• Check quotation"
                       " marks are of the same type, i.e. all straight or matching open/close smartquotes.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send('**You must be a Carrier Owner to use this command.**')
    else:
        await ctx.send(gif)
        await ctx.send(f"Sorry, that didn't work. Check your syntax and permissions, error: {error}")

bot.run(TOKEN)
