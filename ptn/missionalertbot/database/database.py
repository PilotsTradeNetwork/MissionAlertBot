"""
Functions relating to the databases used by MAB.

Depends on: constants, ErrorHandler

"""

# libraries
import os
import sqlite3
import asyncio
import shutil
import enum
import discord
import pickle
from datetime import datetime
from datetime import timezone

# local classes
from ptn.missionalertbot.classes.CarrierData import CarrierData
from ptn.missionalertbot.classes.Commodity import Commodity
from ptn.missionalertbot.classes.MissionData import MissionData
from ptn.missionalertbot.classes.CommunityCarrierData import CommunityCarrierData
from ptn.missionalertbot.classes.NomineesData import NomineesData
from ptn.missionalertbot.classes.WebhookData import WebhookData

# local constants
import ptn.missionalertbot.constants as constants
from ptn.missionalertbot.constants import bot
from ptn.missionalertbot.database.Commodities import commodities_all

# local modules
from ptn.missionalertbot.modules.DateString import get_formatted_date_string
from ptn.missionalertbot.modules.ErrorHandler import CustomError, on_generic_error


# connect to sqlite carrier database
carriers_conn = sqlite3.connect(constants.CARRIERS_DB_PATH)
carriers_conn.row_factory = sqlite3.Row
carrier_db = carriers_conn.cursor()

# carrier database creation
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

# commodities table creation
commodities_table_create = '''
    CREATE TABLE commodities(
        entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
        commodity TEXT NOT NULL
    )
    '''
commodities_table_columns = ['entry_id', 'commodity']

webhooks_table_create = '''
    CREATE TABLE webhooks(
        webhook_owner_id INT NOT NULL,
        webhook_url TEXT NOT NULL,
        webhook_name TEXT NOT NULL
    )
    '''
webhooks_table_columns = ['webhook_owner_id', 'webhook_url', 'webhook_name']

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


# connect to sqlite missions database
missions_conn = sqlite3.connect(constants.MISSIONS_DB_PATH)
missions_conn.row_factory = sqlite3.Row
mission_db = missions_conn.cursor()

# missions database creation
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
        "discord_alert_id"	INT,
        "mission_params"    BLOB
    )
    '''
missions_tables_columns = ['carrier', 'cid', 'channelid', 'commodity', 'missiontype', 'system', 'station',\
    'profit', 'pad', 'demand', 'rp_text', 'reddit_post_id', 'reddit_post_url', 'reddit_comment_id',\
    'reddit_comment_url', 'discord_alert_id', 'mission_params']

channel_cleanup_table_delete = "DROP TABLE IF EXISTS channel_cleanup"


# We need some locks while we wait on the DB queries
carrier_db_lock = asyncio.Lock()
mission_db_lock = asyncio.Lock()


# dump db to .sql file
def dump_database_test(database_name):
    print("Called dump_database_test")
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

    os.makedirs(constants.SQL_PATH, exist_ok=True)
    with open(f'{constants.SQL_PATH}/{database_name}_dump.sql', 'w') as f:
        for line in connection.iterdump():
            f.write(line)


# function to backup database
def backup_database(database_name):
    print("Called backup_database")
    """
    Creates a backup of the requested database into .backup/db_name.datetimestamp.db

    :param str database_name: The database name to back up
    :rtype: None
    """
    dt_file_string = get_formatted_date_string()[1]
    print(dt_file_string)

    db_path = (os.path.join(constants.DB_PATH, f'{database_name}.db'))
    print(f"DB Path: {db_path}")
    backup_path = (os.path.join(constants.BACKUP_DB_PATH, f'{database_name}.{dt_file_string}.db'))
    print(f"Backup Path: {backup_path}")

    shutil.copy(db_path, backup_path)
    print(f'Backed up {database_name}.db at {dt_file_string}')
    try:
      dump_database_test(database_name)
    except Exception as e:
        print(e)


# function to check if a given table exists in a given database
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


# function to check if a given column exists in a given table in a given database
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


# function to create a missing table / database
def create_missing_table(table, db_obj, create_stmt):
    print(f'{table} table missing - creating it now')

    if os.path.exists(os.path.join(os.getcwd(), 'db_sql', f'{table}_dump.sql')):

        # recreate from backup file
        print('Recreating database from backup ...')
        with open(os.path.join(os.getcwd(), 'db_sql', f'{table}_dump.sql')) as f:

            sql_script = f.read()
            db_obj.executescript(sql_script)

    else:
        # Create a new version
        print('No backup found - Creating empty database')

        db_obj.execute(create_stmt)


# function to create a missing column
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


# ensure all paths function for a clean install
def build_directory_structure_on_startup():
    print("Building directory structure...")
    os.makedirs(constants.DB_PATH, exist_ok=True) # /database - the main database files
    os.makedirs(constants.IMAGE_PATH, exist_ok=True) # /images - carrier images
    os.makedirs(f"{constants.IMAGE_PATH}/old", exist_ok=True) # /images/old - backed up carrier images
    os.makedirs(constants.SQL_PATH, exist_ok=True) # /database/db_sql - DB SQL dumps
    os.makedirs(constants.BACKUP_DB_PATH, exist_ok=True) # /database/backups - db backups
    os.makedirs(constants.CC_IMAGE_PATH, exist_ok=True) # /images/cc - CC thumbnail images


# build the databases, from scratch if needed
def build_database_on_startup():
    print("Building databases...")

    # Add a mapping when a new table needs to be created
    # Requires:
    #   table_name (str):
    #       obj (sqlite db obj): sqlite connection to db
    #       create (str): sql create statement for table
    database_table_map = {
        'carriers' : {'obj': carrier_db, 'create': carriers_table_create},
        'commodities': {'obj': carrier_db, 'create': commodities_table_create},
        'webhooks' : {'obj': carrier_db, 'create': webhooks_table_create},
        'community_carriers': {'obj': carrier_db, 'create': community_carriers_table_create},
        'nominees': {'obj': carrier_db, 'create': nominees_table_create},
        'missions': {'obj': mission_db, 'create': missions_table_create}
    }

    # check database exists, create from scratch if needed
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
        'mission_params': {
            'db_name': 'missions',
            'table': 'missions',
            'obj': mission_db,
            'columns': missions_tables_columns,
            'conn': missions_conn,
            'create': missions_table_create
        }
    }

    for column_name in new_column_map:
        c = new_column_map[column_name]
        if not check_table_column_exists(column_name, c['table'], c['obj']):
            create_missing_column(c['table'], column_name, c['columns'], c['db_name'], c['obj'], c['conn'], c['create'])
        else:
            print(f'{column_name} exists, do nothing')

    # remove channel cleanup table
    try:
        print("Removing cleanup table if it exists")
        mission_db.execute(channel_cleanup_table_delete)
        missions_conn.commit()
    except Exception as e:
        print(e)

# populate commodities database on fresh install
def populate_commodities_table_on_startup():
    for commodity in commodities_all:
        # Check if the commodity already exists in the table
        carrier_db.execute("SELECT commodity FROM commodities WHERE commodity=?", (commodity,))
        existing_entry = carrier_db.fetchone()

        # If the commodity does not exist, insert it
        if existing_entry is None:
            carrier_db.execute("INSERT INTO commodities (commodity) VALUES (?)", (commodity,))

    # Commit the changes to the database
    carriers_conn.commit()



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


# add a webhook to the database
async def add_webhook_to_database(owner_id, webhook_url, webhook_name):
    print("Called add_webhook_to_database")
    await carrier_db_lock.acquire()
    print("Carrier DB locked.")
    try:
        carrier_db.execute(''' INSERT INTO webhooks VALUES(?, ?, ?) ''',
                        (owner_id, webhook_url, webhook_name))
        carriers_conn.commit()
        print(f"Successfully added webhook {webhook_url} to database for {owner_id} with name {webhook_name}")
    except Exception as e:
        print(e)
    finally:
        carrier_db_lock.release()
        print("Carrier DB unlocked.")


# carrier edit function
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
        print('Unable to backup image file, perhaps it never existed?')

    return


# function to remove a webhook
async def delete_webhook_by_name(userid, webhook_name):
    print(f"Attempting to delete {userid} {webhook_name} match.")
    try:
        await carrier_db_lock.acquire()
        query = f"DELETE FROM webhooks WHERE webhook_owner_id = ? AND webhook_name = ?"
        carrier_db.execute(query, (userid, webhook_name))
        carriers_conn.commit()
        return print("Deleted")
    finally:
        carrier_db_lock.release()


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


def find_webhook_from_owner(ownerid):
    """
    Returns owner ID, webhook URL and webhook name matching the nominee's user ID

    :param int ownerid: The user id to match
    :returns: A list of webhook data objects
    :rtype: list[WebhookData]
    """
    carrier_db.execute(f"SELECT * FROM webhooks WHERE "
                       f"webhook_owner_id = {ownerid} ")
    webhook_data = [WebhookData(webhooks) for webhooks in carrier_db.fetchall()]
    for webhooks in webhook_data:
        print(f"{webhooks.webhook_owner_id} owns {webhooks.webhook_url} called {webhooks.webhook_name}"
              f" called from find_webhook_from_owner.")

    return webhook_data


def find_webhook_by_name(ownerid, name): # TODO: why doesn't this work?
    print("Called find_webhook_by_name")
    """
    Returns owner ID, webhook URL and webhook name matching the nominee's user ID

    :param int ownerid: The user id to match
    :param str name: The webhook name to match
    :returns: A webhook data object
    """
    try:
        query = f"SELECT * FROM webhooks WHERE webhook_owner_id = ? AND webhook_name = ?"
        carrier_db.execute(query, (ownerid, name))
        webhook_data = WebhookData(carrier_db.fetchone())
        print(f"Found {webhook_data}")
        return webhook_data
    except Exception as e:
        print(e)
        return


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

    # unpickle the mission_params object if it exists
    if mission_data.mission_params:
        print("Found mission_params, enumerating...")
        mission_data.mission_params = pickle.loads(mission_data.mission_params)
        mission_data.mission_params.print_values()
    else:
        print("No mission_params found")
        return mission_data

    return mission_data


# carrier edit function
async def _update_mission_in_database(mission_params):
    print("Called _update_mission_in_database")
    """
    Updates the mission details in the database.

    :param mission_params The new mission data to write
    """
    backup_database('missions')  # backup the carriers database before going any further

    # TODO: Write to the database
    print("Getting mission db lock...")
    await mission_db_lock.acquire()

    print("Pickling mission_params...")
    pickled_mission_params = pickle.dumps(mission_params)

    try:
        data = (
            mission_params.carrier_data.carrier_long_name,
            mission_params.carrier_data.carrier_identifier,
            mission_params.mission_temp_channel_id,
            mission_params.commodity_name,
            mission_params.mission_type,
            mission_params.system,
            mission_params.station,
            mission_params.profit,
            mission_params.pads,
            mission_params.demand,
            mission_params.cco_message_text,
            mission_params.reddit_post_id,
            mission_params.reddit_post_url,
            mission_params.reddit_comment_id,
            mission_params.reddit_comment_url,
            mission_params.discord_alert_id,
            pickled_mission_params,
            mission_params.carrier_data.carrier_long_name
        )
        # Handy number to print out what the database connection is actually doing
        missions_conn.set_trace_callback(print)

        # define our SQL update statement
        statement = """
        UPDATE missions
        SET carrier = ?,
            cid = ?,
            channelid = ?,
            commodity = ?,
            missiontype = ?,
            system = ?,
            station = ?,
            profit = ?,
            pad = ?,
            demand = ?,
            rp_text = ?,
            reddit_post_id = ?,
            reddit_post_url = ?,
            reddit_comment_id = ?,
            reddit_comment_url = ?,
            discord_alert_id = ?,
            mission_params = ?
        WHERE carrier LIKE ?
        """

        print("Executing update...")
        mission_db.execute(statement, data)
        print("Committing...")
        missions_conn.commit()
    except Exception as e:
        print(e)
    finally:
        print("Releasing mission_db lock")
        mission_db_lock.release()
        print("Completed _update_mission_in_database")
        return


# check if a carrier is for a registered PTN fleet carrier
async def _is_carrier_channel(carrier_data):
    if not carrier_data.discord_channel:
        # if there's no channel match, return an error
        embed = discord.Embed(description="Try again in a **🚛Trade Carriers** channel.", color=constants.EMBED_COLOUR_QU)
        return embed
    else:
        return


# function to search for a commodity by name or partial name
async def find_commodity(mission_params, interaction):
    # TODO: Where do we get set up this database? it is searching for things, but what is the source of the data, do
    #  we update it periodically?

    print(f'Searching for commodity against match "{mission_params.commodity_search_term}" requested by {interaction.user.display_name}')

    carrier_db.execute(
        f"SELECT * FROM commodities WHERE commodity LIKE (?)",
        (f'%{mission_params.commodity_search_term}%',))

    commodities = [Commodity(commodity) for commodity in carrier_db.fetchall()]
    commodity = None
    if not commodities:
        mission_params.returnflag = False 
        embed = discord.Embed(
            description=f"❌ No commodities found for {mission_params.commodity_search_term}.",
            color=constants.EMBED_COLOUR_ERROR
        )
        print('No commodities found for request')
        return await interaction.channel.send(embed=embed) # error condition, return
    elif len(commodities) == 1:
        print('Single commodity found, returning that directly')
        # if only 1 match, just assign it directly
        commodity = commodities[0]
    elif len(commodities) > 3:
        # If we ever get into a scenario where more than 3 commodities can be found with the same search directly, then
        # we need to revisit this limit
        mission_params.returnflag = False 
        print(f'More than 3 commodities found for: "{mission_params.commodity_search_term}", {interaction.user.display_name} needs to search better.')
        error_message = f'Please narrow down your commodity search, we found {len(commodities)} matches for your input choice: "{mission_params.commodity_search_term}"'
        try:
            raise CustomError(error_message, isprivate=False)
        except CustomError as e:
            print(e)
            await on_generic_error(interaction, e)

        return # Just return None here and let the calling method figure out what is needed to happen

    else:
        print(f'Between 1 and 3 commodities found for: "{mission_params.commodity_search_term}", asking {interaction.user.display_name} which they want.')
        # The database runs a partial match, in the case we have more than 1 ask the user which they want.
        # here we have less than 3, but more than 1 match
        embed = discord.Embed(title=f"Multiple commodities found for input: {mission_params.commodity_search_term}", color=constants.EMBED_COLOUR_OK)

        count = 0
        response = None  # just in case we try to do something before it is assigned, give it a value of None
        for commodity in commodities:
            count += 1
            embed.add_field(name=f'{count}', value=f"{commodity.name}", inline=True)

        embed.set_footer(text='Please select the commodity with 1, 2 or 3')

        def check(message):
            return message.author == interaction.user and message.channel == interaction.channel and \
                   len(message.content) == 1 and message.content.lower() in ["1", "2", "3"]

        message_confirm = await interaction.channel.send(embed=embed)
        try:
            # Wait on the user input, this might be better by using a reaction?
            response = await bot.wait_for("message", check=check, timeout=15)
            print(f'{interaction.user.display_name} responded with: "{response.content}", type: {type(response.content)}.')
            index = int(response.content) - 1  # Users count from 1, computers count from 0
            commodity = commodities[index]
        except asyncio.TimeoutError:
            mission_params.returnflag = False 
            await interaction.channel.send("Commodity selection timed out. Cancelling.")
            print('User failed to respond in time')
            return # error condition, return
        await message_confirm.delete()
        if response:
            await response.delete()
    if commodity: # only if this is successful is returnflag set so mission gen will continue
        print(f"Found commodity {commodity.name}")
        mission_params.commodity_name = commodity.name
    return commodity
