"""
A module containing embeds that are required by multiple functions.

STATUS: This file is complete, but needs to be imported into modules that use it
"""

# import libraries
import os
from datetime import timezone, datetime
from time import strftime

# import discord.py
import discord

# import local classes
from ptn.missionalertbot.classes.CarrierData import CarrierData
from ptn.missionalertbot.classes.CommunityCarrierData import CommunityCarrierData
from ptn.missionalertbot.classes.MissionParams import MissionParams

# import local constants
import ptn.missionalertbot.constants as constants
from ptn.missionalertbot.constants import ptn_logo_discord

#import local modules
from ptn.missionalertbot.database.database import find_mission


# confirm edit mission embed
def _confirm_edit_mission_embed(mission_params: MissionParams):
    """
    Used by mission editor to confirm details with user before committing.

    Param mission_params: ClassInstance of MissionParams
    """
    confirm_embed = discord.Embed(
        title=f"{mission_params.mission_type.upper()}ING: {mission_params.carrier_data.carrier_long_name}",
        description=f"Please confirm updated mission details for {mission_params.carrier_data.carrier_long_name}:\n\n" \
                    f"{mission_params.discord_text}",
        color=constants.EMBED_COLOUR_QU
    )
    thumb_url = constants.ICON_LOADING if mission_params.mission_type == 'load' else constants.ICON_UNLOADING
    confirm_embed.set_thumbnail(url=thumb_url)

    return confirm_embed


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

    mission_description = mission_data.rp_text if not mission_data.rp_text == None else ''

    embed = discord.Embed(title=f"{mission_data.mission_type.upper()}ING {mission_data.carrier_name} ({mission_data.carrier_identifier})",
                            description=mission_description, color=embed_colour)

    embed = _mission_summary_embed(mission_data.mission_params, embed)

    embed.set_footer(text="You can use /mission complete if the mission is complete.")
    return embed


# return an embed summarising a mission database entry
def _mission_summary_embed(mission_params, embed):
    embed.add_field(
        name="Commodity", value=f"**{mission_params.commodity_name.upper()}**", inline=True
    )
    embed.add_field(
        name="Profit", value=f"**{mission_params.profit}K/TON** x **{mission_params.demand}K**", inline=False
    )
    embed.add_field(
        name="System", value=f"**{mission_params.system}**", inline=True
    )
    embed.add_field(
        name="Station", value=f"**{mission_params.station}** (**{mission_params.pads}**-PADS)", inline=True
    )
    return embed


# return an embed summarising all missions of the defined type (for /missions)
def _format_missions_embed(mission_data_list, embed):
    """
    Loop over a set of records and add certain fields to the message.
    """
    for mission_data in mission_data_list:
        embed.add_field(name=f"{mission_data.carrier_name}", value=f"<#{mission_data.channel_id}>", inline=True)
        embed.add_field(name=f"{mission_data.commodity}",
                        value=f"{mission_data.demand}k at {mission_data.profit}k/unit", inline=True)
        embed.add_field(name=f"{mission_data.system.upper()} system",
                        value=f"{mission_data.station} ({mission_data.pad_size}-pads)", inline=True)
    return embed


# returns an embed showing all fields from an entry in the carrier database
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


# embed generator for send_notice commands
async def _generate_cc_notice_embed(channel_id, user, avatar, title, message, image_url):
    print(f"generating embed for CC notice in channel {channel_id}")

    thumb_file = None

    print(f"Looking for CC image in {constants.CC_IMAGE_PATH}...")

    if os.path.isfile(f"{constants.CC_IMAGE_PATH}/{channel_id}.png"):
        print(f"Found CC image file {constants.CC_IMAGE_PATH}/{channel_id}.png")
        thumb_file = discord.File(f'{constants.CC_IMAGE_PATH}/{channel_id}.png', filename='image.png')
        print(thumb_file)

    embed = discord.Embed(title=title, description=message, color=constants.EMBED_COLOUR_QU)
    embed.set_author(name=user, icon_url=avatar)
    embed.set_image(url=image_url)
    if thumb_file: embed.set_thumbnail(url='attachment://image.png')
    embed.timestamp= datetime.now(tz=timezone.utc)
    embed.set_footer(text="Use \"/notify_me\" in this channel to sign up for future notifications."
                    "\nYou can opt out at any time by using \"/notify_me\" again.")

    return embed, thumb_file

# add common embed fields for carrier info
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

# embed to notify someone they've been made a Verified Member
def verified_member_embed(message):
    print("Called verified_member_embed")
    desc = f"""
    Your screenshot featuring you at an official PTN Fleet Carrier {message.jump_url} has been accepted and you are now a **Verified Member** on the PTN Discord. o7 CMDR!
    """
    embed = discord.Embed (
        title="Pilots Trade Network - Verified Member Granted",
        description=desc,
        color=constants.EMBED_COLOUR_OK
    )
    embed.set_thumbnail(url=ptn_logo_discord(strftime('%B')))

    return embed

# embed to notify someone they've been made an Event Organiser
def event_organiser_embed():
    print("Called event_organiser_embed")
    desc = f"""
    You've been given the **Event Organiser** role on the PTN Discord. This is a temporary role that allows access to the <#1023295746692350012> channel where our Community Team can help you plan, organise, and put on an event on the PTN Discord. o7 CMDR!
    """
    embed = discord.Embed (
        title="Pilots Trade Network - Event Organiser Role",
        description=desc,
        color=constants.EMBED_COLOUR_OK
    )
    embed.set_thumbnail(url=ptn_logo_discord(strftime('%B')))

    return embed

# embed to feedback that a user was granted a role
def role_granted_embed(interaction: discord.Interaction, user: discord.Member, message: discord.Message, role):
    print("Called role_granted_embed")
    desc = f"""
    ✅ Gave <@{user.id}> the <@&{role.id}> role.
    """
    embed = discord.Embed (
        description=desc,
        color=constants.EMBED_COLOUR_OK
    )

    try:
        print("Checking for command name...")
        command_name = f" using `{interaction.command.name}`"
    except:
        print("Command name not accessible")
        command_name = ""

    if message:
        message_phrase = f" for {message.jump_url}"
    else:
        message_phrase = ""

    desc = f"<@{interaction.user.id}> gave the <@&{role.id}> role to <@{user.id}>" + message_phrase + command_name
    bot_spam_embed = discord.Embed (
        description=desc,
        color=constants.EMBED_COLOUR_OK
    )

    print("Returning embed")
    return embed, bot_spam_embed

# embed to feedback that a user already has the target role
def role_already_embed(user, role):
    print("Called role_already_embed")
    desc = f"""
    ✅ <@{user.id}> already has the <@&{role.id}> role.
    """
    embed = discord.Embed (
        description=desc,
        color=constants.EMBED_COLOUR_OK
    )

    return embed

# embed to ask a command user whether they want to remove the role from a target user
def confirm_remove_role_embed(user, role):
    print("Called confirm_remove_role_embed")
    embed = discord.Embed(
        description=f":warning: <@{user.id}> already has the <@&{role.id}> role. Do you want to remove it?",
        color=constants.EMBED_COLOUR_QU
    )

    return embed

# embed to ask a command user whether they want to remove the role from a target user
def confirm_grant_role_embed(user, role):
    print("Called confirm_grant_role_embed")
    embed = discord.Embed(
        description=f":warning: Are you sure you want to give <@{user.id}> the <@&{role.id}> role?",
        color=constants.EMBED_COLOUR_QU
    )

    return embed

# embed to feedback that a user had a role removed
def role_removed_embed(interaction: discord.Interaction, user, role):
    print("Called role_removed_embed")
    desc = f"""
    ✅ Removed the <@&{role.id}> role from <@{user.id}>.
    """
    embed = discord.Embed (
        description=desc,
        color=constants.EMBED_COLOUR_OK
    )

    try:
        print("Checking for command name...")
        command_name = f" using `{interaction.command.name}`"
    except:
        print("Command name not accessible")
        command_name = ""

    desc = f"<@{interaction.user.id}> removed the <@&{role.id}> role from <@{user.id}>" + command_name

    bot_spam_embed = discord.Embed (
        description=desc,
        color=constants.EMBED_COLOUR_OK
    )

    print("Returning embed")
    return embed, bot_spam_embed

# embeds to feed back CC channel rename
def cc_renamed_embed(interaction, old_channel_name, community_carrier: CommunityCarrierData):
    print("Called cc_renamed_embed")
    desc = f"""
    ✅ Updated names: <#{community_carrier.channel_id}> • <@&{community_carrier.role_id}>.
    """
    embed = discord.Embed (
        description=desc,
        color=constants.EMBED_COLOUR_OK
    )

    try:
        print("Checking for command name...")
        command_name = f" using `{interaction.command.name}`"
    except:
        print("Command name not accessible")
        command_name = ""

    desc = f"<@{interaction.user.id}> renamed <#{community_carrier.channel_id}> • <@&{community_carrier.role_id}> (was `{old_channel_name}`)" + command_name

    bot_spam_embed = discord.Embed (
        description=desc,
        color=constants.EMBED_COLOUR_OK
    )

    print("Returning embed")
    return embed, bot_spam_embed

def dm_forbidden_embed(user: discord.Member):
    print("Called dm_forbidden embed")
    embed = discord.Embed(
        description=f"↩ Skipped sending notification Direct Message to <@{user.id}>: user is not accepting DMs from this source.",
        color=constants.EMBED_COLOUR_QU
    )
    return embed