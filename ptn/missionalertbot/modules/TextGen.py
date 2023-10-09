"""
TextGen.py

Functions to generate formatted texts for use by the bot.

Dependencies: constants
"""
# import discord.Interaction
from discord import Interaction

# import local constants
import ptn.missionalertbot.constants as constants

# import local classes
from ptn.missionalertbot.classes.MissionParams import MissionParams

# import local modules
from ptn.missionalertbot.modules.DateString import get_formatted_date_string


"""
TEXT GEN FUNCTIONS
"""


def txt_create_discord(interaction: Interaction, mission_params: MissionParams, preview=False):
    discord_channel_id = mission_params.mission_temp_channel_id if not preview else None
    discord_channel = f"<#{discord_channel_id}>" if discord_channel_id else f"**#{mission_params.carrier_data.discord_channel}**"
    emoji = f'<:loading_emoji:{constants.loading_emoji()}>' if mission_params.mission_type == 'load' else f'<:unloading_emoji:{constants.unloading_emoji()}>' 

    if hasattr(mission_params, "booze_cruise") and mission_params.booze_cruise: # pre-2.3.0 backwards compatibility
        print("Generating BC wine alert...")
        # **[Carriername (CAR-IDX)]** | @[Cmdr Name] | [Loading System]/[Loading Station] - **[Amount of Wine]k** :wine_glass:+ **[Amount of Tritium]**:oil: @[Purchase Price of Tritium above Gal Avg]k/t
        if preview:
            name_link = mission_params.carrier_data.carrier_long_name
        else:
            name_link = f"[{mission_params.carrier_data.carrier_long_name}](https://discord.com/channels/{interaction.guild.id}/{discord_channel_id})"
        discord_text = (
            f"{'**★ EDMC-OFF MISSION! ★** : ' if mission_params.edmc_off else ''}"
            f"**{name_link}** "
            f"**({mission_params.carrier_data.carrier_identifier})** | "
            f" <@{mission_params.carrier_data.ownerid}> | {mission_params.system.title()}/{mission_params.station.title()} - "
            f"**{mission_params.demand}k :wine_glass:**"
            f"{mission_params.cco_message_text if mission_params.cco_message_text else ''}"
        )
    else:
        print("Generating trade alert...")
        discord_text = (
            f"{'**★ EDMC-OFF MISSION! ★** : ' if mission_params.edmc_off else ''}"
            f"{discord_channel} {'load' if mission_params.mission_type == 'load' else 'unload'}ing "
            f"{mission_params.commodity_name} "
            f"{'from' if mission_params.mission_type == 'load' else 'to'} **{mission_params.station.upper()}** station in system "
            f"**{mission_params.system.upper()}** : {mission_params.profit}k per unit profit : "
            f"{mission_params.demand}k {'demand' if mission_params.mission_type == 'load' else 'supply'} : {mission_params.pads.upper()}-pads."
        )

    print(f"Defined discord trade alert text:")
    print(discord_text)
    return discord_text


def txt_create_reddit_title(mission_params):
    elite_time = get_formatted_date_string()[0]
    reddit_title = (
        f"{mission_params.carrier_data.carrier_long_name} {mission_params.carrier_data.carrier_identifier} {mission_params.mission_type}ing "
        f"{mission_params.commodity_name.upper()} in {mission_params.system.upper()} for {mission_params.profit}K/TON PROFIT ({elite_time})"
    )
    print("Defined reddit title text")
    return reddit_title


def txt_create_reddit_body(mission_params):

    if mission_params.mission_type == 'load':
        reddit_body = (
            f"    INCOMING WIDEBAND TRANSMISSION: P.T.N. CARRIER LOADING MISSION IN PROGRESS\n"
            f"\n\n"
            f"**BUY FROM**: station **{mission_params.station.upper()}** ({mission_params.pads.upper()}-pads) in system **{mission_params.system.upper()}**\n\n**COMMODITY**: "
            f"{mission_params.commodity_name}\n\n&#x200B;\n\n**SELL TO**: Fleet Carrier **{mission_params.carrier_data.carrier_long_name} "
            f"{mission_params.carrier_data.carrier_identifier}**\n\n**PROFIT**: {mission_params.profit}k/unit : {mission_params.demand}k "
            f"demand\n\n\n\n[Join us on Discord]({constants.REDDIT_DISCORD_LINK_URL}) for "
            f"mission updates and discussion, channel **#{mission_params.carrier_data.discord_channel}**.")
    else:
        reddit_body = (
            f"    INCOMING WIDEBAND TRANSMISSION: P.T.N. CARRIER UNLOADING MISSION IN PROGRESS\n"
            f"\n\n"
            f"**BUY FROM**: Fleet Carrier **{mission_params.carrier_data.carrier_long_name} {mission_params.carrier_data.carrier_identifier}**"
            f"\n\n**COMMODITY**: {mission_params.commodity_name}\n\n&#x200B;\n\n**SELL TO**: station "
            f"**{mission_params.station.upper()}** ({mission_params.pads.upper()}-pads) in system **{mission_params.system.upper()}**\n\n**PROFIT**: {mission_params.profit}k/unit "
            f": {mission_params.demand}k supply\n\n\n\n[Join us on Discord]({constants.REDDIT_DISCORD_LINK_URL}) for mission updates"
            f" and discussion, channel **#{mission_params.carrier_data.discord_channel}**.")
    print("Defined reddit comment text")
    return reddit_body