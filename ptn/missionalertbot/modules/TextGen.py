"""
TextGen.py

Functions to generate formatted texts for use by the bot.

Dependencies: constants
"""

# import local constants
import ptn.missionalertbot.constants as constants


"""
TEXT GEN FUNCTIONS
"""


def txt_create_discord(mission_params):
    discord_channel = f"<#{mission_params.mission_temp_channel_id}>" if mission_params.mission_temp_channel_id else f"#{mission_params.carrier_data.discord_channel}"
    discord_text = (
        f"{'**★ EDMC-OFF MISSION! ★** : ' if mission_params.edmc_off else ''}"
        f"{discord_channel} {'load' if mission_params.mission_type == 'load' else 'unload'}ing "
        f"{mission_params.commodity_name} "
        f"{'from' if mission_params.mission_type == 'load' else 'to'} **{mission_params.station.upper()}** station in system "
        f"**{mission_params.system.upper()}** : {mission_params.profit}k per unit profit : "
        f"{mission_params.demand}k {'demand' if mission_params.mission_type == 'load' else 'supply'} : {mission_params.pads.upper()}-pads."
    )
    return discord_text


def txt_create_reddit_title(mission_params):
    reddit_title = (
        f"{mission_params.carrier_data.carrier_long_name} {mission_params.carrier_data.carrier_identifier} {mission_params.mission_type}ing "
        f"{mission_params.commodity_name.upper()} in {mission_params.system.upper()} for {mission_params.profit}K/TON PROFIT"
    )
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
    return reddit_body