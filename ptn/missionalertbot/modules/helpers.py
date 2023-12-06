"""
A module for helper functions called by other modules.

Depends on: constants, ErrorHandler, database

"""

# import libraries
import asyncio
from datetime import datetime, timezone
import emoji
import random
import re
import sys

# import discord.py
import discord
from discord import Interaction, app_commands
from discord.errors import HTTPException, Forbidden, NotFound
from discord.ext import commands

# import local classes
from ptn.missionalertbot.classes.ChannelDefs import ChannelDefs
from ptn.missionalertbot.classes.CommunityCarrierData import CommunityCarrierData

# import local constants
import ptn.missionalertbot.constants as constants
from ptn.missionalertbot.constants import bot, cc_role, get_overwrite_perms, get_guild, bot_spam_channel, archive_cat, cc_cat, cmentor_role, admin_role, \
    training_cat, training_alerts, training_mission_command_channel, training_upvotes, training_wine_alerts, training_sub_reddit, training_reddit_in_progress, training_reddit_completed, \
    trade_cat, trade_alerts_channel, mission_command_channel, channel_upvotes, wine_alerts_loading_channel, wine_alerts_unloading_channel, sub_reddit, \
    reddit_flair_mission_start, reddit_flair_mission_stop

# import local modules
from ptn.missionalertbot.database.database import find_community_carrier, CCDbFields, carrier_db, carrier_db_lock, carriers_conn, delete_community_carrier_from_db, \
    find_carrier, CarrierDbFields
from ptn.missionalertbot.modules.ErrorHandler import CommandChannelError, CommandRoleError, CustomError, on_generic_error


# trio of helper functions to check a user's permission to run a command based on their roles, and return a helpful error if they don't have the correct role(s)
def getrole(ctx, id): # takes a Discord role ID and returns the role object
    role = discord.utils.get(ctx.guild.roles, id=id)
    return role

async def checkroles_actual(interaction: discord.Interaction, permitted_role_ids):
    try:
        """
        Check if the user has at least one of the permitted roles to run a command
        """
        print(f"checkroles called.")
        author_roles = interaction.user.roles
        permitted_roles = [getrole(interaction, role) for role in permitted_role_ids]
        print(author_roles)
        print(permitted_roles)
        permission = True if any(x in permitted_roles for x in author_roles) else False
        print(permission)
        return permission, permitted_roles
    except Exception as e:
        print(e)
    return permission


def check_roles(permitted_role_ids):
    async def checkroles(interaction: discord.Interaction): # TODO convert messages to custom error handler, make work with text commands
        permission, permitted_roles = await checkroles_actual(interaction, permitted_role_ids)
        print("Inherited permission from checkroles")
        if not permission: # raise our custom error to notify the user gracefully
            role_list = []
            for role in permitted_role_ids:
                role_list.append(f'<@&{role}> ')
                formatted_role_list = " • ".join(role_list)
            try:
                raise CommandRoleError(permitted_roles, formatted_role_list)
            except CommandRoleError as e:
                print(e)
                raise
        return permission
    return app_commands.check(checkroles)


# helper for channel permission check
def getchannel(id):
    channel = bot.get_channel(id)
    return channel


# decorator for interaction channel checks
def check_command_channel(permitted_channel):
    """
    Decorator used on an interaction to limit it to specified channels
    """
    async def check_channel(ctx):
        """
        Check if the channel the command was run from matches any permitted channels for that command
        """
        print("check_command_channel called")
        if isinstance(permitted_channel, list):
            permitted_channels = [getchannel(id) for id in permitted_channel]
        else:
            permitted_channels = [getchannel(permitted_channel)]

        channel_list = []
        for channel in permitted_channels:
            channel_list.append(f'<#{channel.id}>')
        formatted_channel_list = " • ".join(channel_list)

        permission = True if any(channel == ctx.channel for channel in permitted_channels) else False
        if not permission:
            # problem, wrong channel, no progress
            try:
                raise CommandChannelError(permitted_channel, formatted_channel_list)
            except CommandChannelError as e:
                print(e)
                raise
        else:
            return True
    return app_commands.check(check_channel)


# decorator for text command channel checks
def check_text_command_channel(permitted_channel):
    """
    Decorator used on a text command to limit it to a specified channel
    """
    async def check_text_channel(ctx):
        """
        Check if the channel the command was run in, matches the channel it can only be run from
        """
        permitted = bot.get_channel(permitted_channel)
        if ctx.channel != permitted:
            # problem, wrong channel, no progress
            embed=discord.Embed(description=f"Sorry, you can only run this command out of: <#{permitted_channel}>.", color=constants.EMBED_COLOUR_ERROR)
            await ctx.channel.send(embed=embed)
            return False
        else:
            return True
    return commands.check(check_text_channel)

channel_locks = {} # define dictionary for channel lock/unlock names

async def lock_mission_channel(channel):
    print(f"Attempting channel lock for {channel}...")
    # Create a lock if it doesn't exist for the given fruit
    if channel not in channel_locks:
        channel_locks[channel] = asyncio.Lock()

    lock = channel_locks[channel]
    await lock.acquire()
    print(f"Channel lock acquired for {channel}.")


async def unlock_mission_channel(channel):
    print(f"Attempting to release channel lock for {channel}...")
    if channel in channel_locks:
        lock = channel_locks[channel]
        lock.release()
        del channel_locks[channel]
    print(f"Channel lock released for {channel}.")


def check_mission_channel_lock(channel):
    print(f"Checking status of channel lock for {channel}...")
    if channel in channel_locks:
        print(f"{channel} is locked.")
        return True
    else:
        print(f"{channel} is not locked.")
        return False


# function to stop and quit
def bot_exit():
    sys.exit("User requested exit.")


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

def _regex_alphanumeric_only(regex_string):
    # remove spaces and make lowercase
    regex_string_no_spaces = regex_string.lower().replace(' ', '')
    # take only the alphanumeric characters and hyphens, leave behind everything else
    re_compile = re.compile('([\w-]+)')
    compiled_name = re_compile.findall(regex_string_no_spaces)
    # join together all the extracted bits into one string
    processed_string = ''.join(compiled_name)
    print(f"Processed {regex_string} into {processed_string}")
    return processed_string


"""
Community Team command helpers

Include some database-related functions which have too many dependencies to go into  database module
"""

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
        embed = discord.Embed(description=f"❌ The role <@&{new_role.id}> already exists. Please choose a different name for your Community channel or delete the existing role and try again.", color=constants.EMBED_COLOUR_ERROR)
        await interaction.response.send_message(embed=embed)
        return False
    return True

# helper function to create a CC channel, returns a channel object
async def _cc_create_channel(interaction, new_channel_name, cc_category):
    try:
        new_channel = await interaction.guild.create_text_channel(f"{new_channel_name}", category=cc_category)
        print(f"Created {new_channel}")

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
    role = discord.utils.get(interaction.guild.roles, id=cc_role())
    print(cc_role())
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
    embed = discord.Embed(description=f"<@{owner.id}> is now a <@&{cc_role()}> and owns <#{new_channel.id}> with notification role <@&{new_role.id}>."
                                      f" **This channel will remain closed** (private) until `/open_community_channel` is used in it."
                                      f"\n\nNote channels and roles can be freely renamed.", color=constants.EMBED_COLOUR_OK)
    await interaction.followup.send(embed=embed)

    return


"""
Helpers for /remove_community_channel
"""

# function called by button responses to process channel deletion
async def _remove_cc_manager(interaction: discord.Interaction, delete_channel, button_self):
    # get the carrier data again because I can't figure out how to penetrate callbacks with additional variables or vice versa
    carrier_db.execute(f"SELECT * FROM community_carriers WHERE "
                    f"channelid = {interaction.channel.id}")
    community_carrier = CommunityCarrierData(carrier_db.fetchone())
    # error if not
    if not community_carrier:
        embed = discord.Embed(description=f"❌ This somehow does not appear to be a community channel anymore(?).", color=constants.EMBED_COLOUR_ERROR, ephemeral=True)
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
    embed.set_image(url=random.choice(constants.byebye_gifs))
    await interaction.channel.send(embed=embed)

    # delete channel if relevant
    print("Processing delete flag...")
    if delete_channel: await _delete_cc_channel(interaction, button_self)

    # notify bot-spam
    print("Notifying bot-spam...")
    spamchannel = bot.get_channel(bot_spam_channel())

    embed = discord.Embed(
        description=f"{interaction.user} used `/remove_community_channel` in <#{interaction.channel.id}>, removing {owner.name} as a Community channel owner.",
        color=constants.EMBED_COLOUR_OK
    )

    await spamchannel.send(embed=embed)

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

    role = discord.utils.get(interaction.guild.roles, id=cc_role())

    embed = discord.Embed(title="Community Channel Removed", description=f"", color=constants.EMBED_COLOUR_OK)
    try:
        await owner.remove_roles(role)
        print(f"Removed Community Carrier role from {owner}")
        embed.add_field(name="Owner", value=f"<@{owner.id}> is no longer registered as the <@&{cc_role()}>.", inline=False)
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
async def _archive_cc_channel(interaction: discord.Interaction, embed: discord.Embed, button_self, attempt):
    async with interaction.channel.typing():
        archive_category = discord.utils.get(interaction.guild.categories, id=archive_cat())

        try: # there's probably a better way to do this using an if statement
            button_self.clear_items()
            await interaction.response.edit_message(view=button_self)
            await interaction.delete_original_response()
        except:
            pass

        if not interaction.channel.category == archive_category:
            print("⏳ Attempting to move channel to archive category...")

            try:
                await interaction.channel.edit(category=archive_category)
                # this interaction seems to take some time on the live server.
                # let's try adding a check that it's completed before proceeding
                if not interaction.channel.category == archive_category:
                    attempt = attempt + 1
                    await _archive_cc_channel_delay(interaction, embed, button_self, attempt)
                else: # reset attempts if we're successful
                    attempt = 0
                    print("✅ Moved channel to archive.")

            except Exception as e:
                print(e)
                embed.add_field(name="Channel", value=f"**Failed archiving <#{interaction.channel.id}>**: {e}", inline=False)

        else:
            attempt = 0
            print("✅ Moved channel to archive")

        try:
            print("⏳ Attemping permissions sync with archive category...")
            # now make sure it has the default permissions for the archive category
            await asyncio.sleep(1) # wait a moment for the channel move to be processed
            await interaction.channel.edit(sync_permissions=True)
            await asyncio.sleep(1)
            if not interaction.channel.permissions_synced: # permission sync hasn't worked, try again
                await _archive_cc_channel_perms_delay(interaction, embed, button_self, attempt)
            else:
                print("✅ Synced permissions")

        except Exception as e:
            print(e)
            embed.add_field(name="Channel", value=f"**Failed setting permissions for <#{interaction.channel.id}>**: {e}", inline=False)

        print(embed.fields)

        if len(embed.fields)==1: embed.add_field(name="Channel", value=f"<#{interaction.channel.id}> moved to Archives.", inline=False)

        return embed

# helper function for archive function
async def _archive_cc_channel_delay(interaction, embed, button_self, attempt):
    print(f"⚠ Channel not moved yet. Number of attempts so far: {attempt}")
    attempt = attempt + 1
    print(f"⏳ Beginning attempt {attempt}")
    if attempt <= 10:
        await asyncio.sleep(2)
        await _archive_cc_channel(interaction, embed, button_self, attempt)
    else: # still nothing after 10 seconds, give up I guess
        embed.add_field(name="Channel", value=f"**Failed archiving <#{interaction.channel.id}>**: channel does not appear to be moved after {attempt} attempts.", inline=False)

    return embed

# helper function for archive function
async def _archive_cc_channel_perms_delay(interaction, embed, button_self, attempt):
    print(f"⚠ Permissions not synced yet. Number of attempts so far: {attempt}")
    attempt = attempt + 1
    print(f"⏳ Beginning attempt {attempt}")
    if attempt <= 10:
        await asyncio.sleep(2)
        await _archive_cc_channel(interaction, embed, button_self, attempt) # we probably don't need to attempt the channel edit again but is there a disadvantage to doing so?
    else: # still nothing after 10 seconds, give up I guess
        embed.add_field(name="Channel", value=f"**Failed setting permissions for <#{interaction.channel.id}>**: permissions do not appear to be synced after {attempt} attempts.", inline=False)

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


"""
Helper to assemble a community channel name from user input
"""
async def _cc_name_string_check(interaction: discord.Interaction, channel_emoji, channel_name):
    # trim emojis to 1 character
    emoji_string = channel_emoji[:1] if not channel_emoji == None else None

    # PROCESS: check for valid emoji
    print(emoji.is_emoji(emoji_string))
    if not emoji.is_emoji(emoji_string) and not emoji_string == None:
        error = "Invalid emoji supplied. Use a valid Unicode emoji from your emoji keyboard, " \
                "or leave the field blank. **Discord custom emojis will not work**"
        print('Invalid emoji')
        try:
            raise CustomError(error)
        except Exception as e:
            return await on_generic_error(interaction, e)

    # PROCESS: remove unusable characters and render to lowercase
    stripped_channel_name = _regex_alphanumeric_with_hyphens(channel_name.lower())

    # check the channel name isn't too long
    if len(stripped_channel_name) > 30:
        error = "Channel name should be fewer than 30 characters. (Preferably a *lot* fewer.)"
        print('Channel name too long')
        try:
            raise CustomError(error)
        except Exception as e:
            return await on_generic_error(interaction, e)

    # join with the emoji
    new_channel_name = emoji_string + stripped_channel_name if not emoji_string == None else stripped_channel_name
    print(f"Candidate channel name: {new_channel_name}")

    return new_channel_name


"""
Open/close community channels helper
"""


# helper function for open and closing community channel commands
async def _openclose_community_channel(interaction: discord.Interaction, open):

    status_text_verb = "open" if open else "close"
    status_text_adj = "open" if open else "closed"

    #check we're in the right category
    cc_category = discord.utils.get(interaction.guild.categories, id=cc_cat())
    if not interaction.channel.category == cc_category:
        embed = discord.Embed(description=f"❌ This command can only be used in an active Community channel in the <#{cc_cat()}> category.", color=constants.EMBED_COLOUR_ERROR)
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    # now set permissions
    try:
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=None) if open else await interaction.channel.set_permissions(interaction.guild.default_role, read_messages=False)
    except Exception as e:
        embed = discord.Embed(description=f"❌ Could not {status_text_verb} channel: {e}")
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
        embed.set_image(url=random.choice(constants.hello_gifs))
        embed.set_footer(text="You can use \"/notify_me\" in this channel to sign up for notifications of announcements by the channel owner or Community Mentors."
                    "\nYou can opt out at any time by using \"/notify_me\" again.")
    await interaction.channel.send(embed=embed)

    return


"""
CC authority checker
"""

# helper function shared by the various CC commands
async def _community_channel_owner_check(interaction):
    # check if we're in a community channel
    carrier_db.execute(f"SELECT * FROM community_carriers WHERE "
                    f"channelid = {interaction.channel.id}")
    community_carrier = CommunityCarrierData(carrier_db.fetchone())
    # error if not
    if not community_carrier:
        error = "This does not appear to be a community channel."
        print(f'❌ {error}')
        try:
            raise CustomError(error)
        except Exception as e:
            return await on_generic_error(interaction, e)

    elif community_carrier:
        print(f"Found data: {community_carrier.owner_id} owner of {community_carrier.channel_id}")
        owner = await bot.fetch_user(community_carrier.owner_id)

    # check that the command user is the channel owner, or a Community Mentor/Admin
    if not interaction.user.id == owner.id:
        print("Channel user is not command user")
        if not await checkroles_actual(interaction, [cmentor_role(), admin_role()]): return
    return community_carrier


# helper function to convert a STR into an INT or FLOAT
def convert_str_to_float_or_int(element: any) -> bool: # this code turns a STR into a FLOAT or INT based on value
    if element is None: 
        return False
    try:
        value = float(element)
        print(f"We can float {value}")
        if value.is_integer():
            value = int(value)
            print(f"{value} is an integer")
            return value
        else:
            print(f"{value} is not an integer")
            return value
    except ValueError:
        print(f"We can't float {element}")
        return False


# check whether CCO command is being used in training or live categories
def check_training_mode(interaction: discord.Interaction):
    if interaction.channel.category.id == training_cat():
        training = True
        print(f"Training mode detected for {interaction.command.name} in {interaction.channel.name} called by {interaction.user.display_name}")
        channel_defs = ChannelDefs(training_cat(), training_alerts(), training_mission_command_channel(), training_upvotes(), training_wine_alerts(), training_wine_alerts(), training_sub_reddit(), training_reddit_in_progress(), training_reddit_completed())
    else:
        training = False
        channel_defs = ChannelDefs(trade_cat(), trade_alerts_channel(), mission_command_channel(), channel_upvotes(), wine_alerts_loading_channel(), wine_alerts_unloading_channel(), sub_reddit(), reddit_flair_mission_start(), reddit_flair_mission_stop())

    attrs = vars(channel_defs)
    print(attrs)

    return training, channel_defs

# identify PTN carrier details from a string
def extract_carrier_ident_strings(message: discord.Message):
    """
    Searches for matches to the format "PTN Carrier Name (IDX-NUM)

    param message_content: the content of the message to search
    returns: a list of matched pairs of name/ID
    """
    # regex to match the strings
    pattern = r'(P\.?T\.?N\.?\s+[^)]+?)\s+\((\w{3}-\w{3})\)'
    shortname_pattern = r'(P\.?T\.?N\.?)'

    # find all matching occurrences in the message content
    matches = re.findall(pattern, message.content)

    # extract the matched strings into separate variables
    extracted_strings = []

    index = 0

    # make sure each match is a pair
    for match in matches:
        if len(match) == 2:
            ptn_string = str(match[0])
            bracket_string = str(match[1])
            print(f'Found matching pair in message: {ptn_string} ({bracket_string})')
            # extract a shortname
            shortname_string = re.sub(shortname_pattern, '', ptn_string)
            shortname_string = _regex_alphanumeric_only(shortname_string)

            # create a channel name
            stripped_name = _regex_alphanumeric_with_hyphens(ptn_string).lower()

            # attach to list as a dict
            extracted_strings.append({
                'index': index,
                'long_name': ptn_string.upper(),
                'carrier_id': bracket_string.upper(),
                'short_name': shortname_string.lower(),
                'channel_name': stripped_name.lower(),
                'owner_id': message.author.id
            })
            index += 1
        else:
            print(f'Ignoring {match}: no pair found')

    return extracted_strings


# find a carrier by successively searching ID, long name, and short name
def flexible_carrier_search_term(search_term):
    # check if the carrier can be found, exit gracefully if not
    int_search_term = None
    carrier_data = None

    if re.match(r"\w{3}-\w{3}", search_term):
        print("⏳ Carrier Registration format matched, searching by cid...")
        carrier_data = find_carrier(search_term, CarrierDbFields.cid.name)

    else:
        try:
            # check if its an int that can represent a database entry ID
            int_search_term = int(search_term)
        except ValueError:
            print("❕ Searchterm is not a db ID")
            pass

        if int_search_term:
            print("⏳ Searching for carrier by database entry ID")
            carrier_data = find_carrier(search_term, CarrierDbFields.p_id.name)

        else:
            print("⏳ Searching for carrier by full name fragment")
            carrier_data = find_carrier(search_term, CarrierDbFields.longname.name)
            if not carrier_data:
                print("⏳ Not found. Searching again by shortname...")
                carrier_data = find_carrier(search_term, CarrierDbFields.shortname.name)

    return carrier_data

# presently unused
# TODO: remove or incorporate
def _get_id_from_mention(mention):
    # use re to return the devmode Discord ID from a string that we're not sure whether it's a mention/channel link or an ID
    # mentions are in a format like <@0982340982304>
    re_compile = re.compile('([\d-]+)')
    mention_id = re_compile.findall(mention)
    return mention_id