"""
Commands relating to carrier stock tracking.

Dependencies: Constants, Database, Helpers, StockHelpers, ErrorHandler

Stock tracker original code by DudeInCorner and Durzo
"""

# libraries
import asyncio
import json
import re
import requests
from texttable import Texttable # TODO: remove this dependency
import traceback

# discord.py
import discord
from discord import app_commands
from discord.app_commands import Group, command, describe
from discord.ext import commands

# local classes
from ptn.missionalertbot.classes.MissionParams import MissionParams

# local constants
import ptn.missionalertbot.constants as constants
from ptn.missionalertbot.constants import bot, certcarrier_role, trainee_role, rescarrier_role, mission_command_channel, training_mission_command_channel, \
    bot_spam_channel, get_guild

# local modules
from ptn.missionalertbot.database.database import find_carrier, find_mission
from ptn.missionalertbot.modules.helpers import check_roles, check_command_channel, flexible_carrier_search_term
from ptn.missionalertbot.modules.StockHelpers import get_fc_stock
from ptn.missionalertbot.modules.ErrorHandler import on_app_command_error, on_generic_error, CustomError, GenericError
from ptn.missionalertbot.modules.MissionEditor import edit_discord_alerts


# initialise the Cog and attach our global error handler
class StockTracker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # custom global error handler
    # attaching the handler when the cog is loaded
    # and storing the old handler
    def cog_load(self):
        tree = self.bot.tree
        self._old_tree_error = tree.on_error
        tree.on_error = on_app_command_error

    # detaching the handler when the cog is unloaded
    def cog_unload(self):
        tree = self.bot.tree
        tree.on_error = self._old_tree_error


    @app_commands.command(name='stock', description='Returns stock of a PTN carrier.')
    @app_commands.describe(
           carrier = "A unique fragment of the Fleet Carrier name you want to search for.",
           source = "Choose data source between Frontier API or Inara. Defaults to Frontier API."
        )
    @app_commands.choices(source=[
        discord.app_commands.Choice(name='Frontier API', value='capi'),
        discord.app_commands.Choice(name='Inara', value='inara')
        ])
    async def stock(self, interaction: discord.Interaction, carrier: str = None, source: str = 'capi'):
        carrier_string = f' for carrier {carrier}' if carrier else ''
        source_string = f' from source {source}'
        source_formal = 'Frontier API' if source == 'capi' else 'Inara.cz'
        print(f"📈 Stock check called by {interaction.user} in {interaction.channel}" + carrier_string + source_string)

        try:
            embed = discord.Embed(
                description="⏳ Please wait a moment...",
                color=constants.EMBED_COLOUR_QU
            )

            await interaction.response.send_message(embed=embed)


            # attempt to find matching carrier data
            if not carrier:
                # check if we're in a carrier's channel
                carrier_data = find_carrier(interaction.channel.name, "discordchannel")

                if not carrier_data:
                    # no carrier data found, return a helpful error
                    embed.description="❌ Please try again in a Trade Carrier's channel, or use the 'carrier' option to input the name of the carrier you wish to check the stock for."
                    embed.color=constants.EMBED_COLOUR_ERROR

                    return await interaction.edit_original_response(embed=embed)
                
            else:
                # check for carriers by given search term
                carrier_data = flexible_carrier_search_term(carrier)
                
                if not carrier_data:  # error condition
                    print(f"❌ No carrier found matching search term {carrier}")
                    carrier_error_embed = discord.Embed(
                        description=f"❌ No carrier found for '**{carrier}**'. Use `/owner` to see a list of your carriers. If it's not in the list, ask an Admin to add it for you.",
                        color=constants.EMBED_COLOUR_ERROR
                    )
                    return await interaction.edit_original_response(embed=carrier_error_embed)

            # decide what to say about EDMC in the response footer
            edmc_string = "Run EDMC for more accurate and up-to-date stock information."
            mission_data = find_mission(carrier_data.carrier_long_name, "carrier")
            if mission_data:
                print(f"{carrier_data.carrier_long_name} is on a mission: {mission_data}")
                mission_params: MissionParams = mission_data.mission_params
                if mission_params.edmc_off:
                    edmc_string = "⚠ Please keep EDMC disabled for this mission. ⚠"

            # fetch stock levels
            fcname = carrier_data.carrier_long_name

            try:
                stn_data = get_fc_stock(carrier_data.carrier_identifier, source)
                print("Returned data from %s: %s" % ( carrier_data.carrier_identifier, stn_data ))
            except Exception as e:
                try:
                    error = f"Error getting data for carrier {carrier_data.carrier_identifier}: {e}"
                    raise CustomError(error)
                except Exception as e:
                    await on_generic_error(interaction, e)
                    traceback.print_exc()
                    stn_data = False

            if stn_data is False:
                embed.description = f"📉 No market data for {carrier_data.carrier_long_name}."
                embed.color=constants.EMBED_COLOUR_QU
                embed.set_footer(text = f"Data source: {source_formal}" + (f"\n{edmc_string}" if source == 'inara' else ""))
                await interaction.edit_original_response(embed=embed)
                return

            com_data = stn_data['commodities']
            loc_data = stn_data['name']
            if com_data == []:
                embed.description = f"📉 No market data for {carrier_data.carrier_long_name}."
                embed.color=constants.EMBED_COLOUR_QU
                embed.set_footer(text = f"Data source: {source_formal}" + (f"\n{edmc_string}" if source == 'inara' else ""))
                await interaction.edit_original_response(embed=embed)
                return

            table = Texttable()
            table.set_cols_align(["l", "r", "r"])
            table.set_cols_valign(["m", "m", "m"])
            table.set_cols_dtype(['t', 'i', 'i'])
            #table.set_deco(Texttable.HEADER | Texttable.HLINES)
            table.set_deco(Texttable.HEADER)
            table.header(["Commodity", "Amount", "Demand"])

            for com in com_data:
                if com['stock'] != 0 or com['demand'] != 0:
                    table.add_row([com['name'], com['stock'], com['demand']])

            msg = "```%s```\n" % ( table.draw() )

            embed = discord.Embed()
            embed.color = constants.EMBED_COLOUR_OK
            embed.add_field(name = f"{fcname} ({stn_data['sName']}) stock", value = msg, inline = False)
            embed.add_field(name = 'FC Location', value = loc_data, inline = False)
            embed.set_footer(text = f"Data last updated: {stn_data['market_updated']}\nData source: {source_formal}\n" \
                             + (f"\n{edmc_string}" if source == 'inara' else ""))

            await interaction.edit_original_response(embed=embed)

            # update mission alert if carrier was on a mission
            if mission_data:
                print("⌛ Evaluating stock for trade alert update...")
                mission_params: MissionParams = mission_data.mission_params
                # define our mission commodity without spaces
                mission_commodity = mission_params.commodity_name.title().replace(" ", "" )
                # check if commodity from stock check matches from mission params
                print("Checking for match for %s" % ( mission_commodity ))

                # create a list of commodities in stock - this is to handle future planned multi-commodity support
                commodities_in_stock = []
                for com in com_data:
                    if com['name'].lower() == mission_commodity.lower():
                        print("Found match: %s %s %s" % ( com['name'].title(), com['stock'], com['demand'] ))
                        # retrieve correct value for supply or demand
                        if com['stock'] != 0 or com['demand'] != 0:
                            if mission_data.mission_type.lower() == 'load' and com['demand'] != 0:
                                commodity = {'name': com['name'].title(), 'stock': com['demand'], 'type': 'demand'}
                            elif mission_data.mission_type.lower() == 'unload' and com['stock'] != 0:
                                commodity = {'name': com['name'].title(), 'stock': com['stock'], 'type': 'supply'}
                            else:
                                print("Supply/demand does not match mission type '%s', ignoring." % (mission_data.mission_type))
                                # matching commodity but supply/demand does not match mission type, skip
                                continue
                            # add DICT to our list
                            commodities_in_stock.append(commodity)

                if commodities_in_stock:
                    for commodity in commodities_in_stock:
                        print("Found matching commodity %s %s at %s" % ( commodity['type'], commodity['name'], commodity['stock'] ))

                    spamchannel = bot.get_channel(bot_spam_channel())

                    await edit_discord_alerts(interaction, mission_params, spamchannel, commodities_in_stock)

        except Exception as e:
            try:
                raise GenericError(e)
            except Exception as e:
                traceback.print_exc()
                await on_generic_error(interaction, e)
