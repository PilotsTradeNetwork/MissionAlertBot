"""
MissionGenerator.py

Functions relating to mission generation, management, and clean-up.

Dependencies: constants, database, helpers, Embeds, ImageHandling, MissionCleaner

"""
# import libraries
from typing import List, Optional
import aiohttp
import asyncio
import os
import pickle
from PIL import Image
import random
import traceback
import typing
from time import strftime


# import discord.py
import discord
from discord import Webhook
from discord.errors import HTTPException, Forbidden, NotFound
from discord.ui import View, Modal

# import local classes
from ptn.missionalertbot.classes.CarrierData import CarrierData
from ptn.missionalertbot.classes.MissionData import MissionData
from ptn.missionalertbot.classes.MissionParams import MissionParams

# import local constants
import ptn.missionalertbot.constants as constants
from ptn.missionalertbot.constants import bot, get_reddit, seconds_short, upvote_emoji, hauler_role, trainee_role, reddit_timeout, \
    get_guild, get_overwrite_perms, ptn_logo_discord, wineloader_role, o7_emoji, bot_spam_channel, discord_emoji, training_cat, \
    trade_cat, mcomplete_id, somm_role

# import local modules
from ptn.missionalertbot.database.database import backup_database, mission_db, missions_conn, find_carrier, CarrierDbFields, \
    find_commodity, find_mission, carrier_db, carriers_conn, find_webhook_from_owner, _update_carrier_last_trade
from ptn.missionalertbot.modules.DateString import get_formatted_date_string
from ptn.missionalertbot.modules.Embeds import _mission_summary_embed
from ptn.missionalertbot.modules.ErrorHandler import on_generic_error, CustomError, AsyncioTimeoutError, GenericError
from ptn.missionalertbot.modules.helpers import lock_mission_channel, unlock_mission_channel, check_mission_channel_lock, flexible_carrier_search_term
from ptn.missionalertbot.modules.ImageHandling import assign_carrier_image, create_carrier_reddit_mission_image, create_carrier_discord_mission_image
from ptn.missionalertbot.modules.MissionCleaner import remove_carrier_channel
from ptn.missionalertbot.modules.TextGen import txt_create_discord, txt_create_reddit_body, txt_create_reddit_title


# a class to hold all our Discord embeds
class DiscordEmbeds:
    def __init__(self, buy_embed, sell_embed, info_embed, help_embed, owner_text_embed, webhook_info_embed):
        self.buy_embed = buy_embed
        self.sell_embed = sell_embed
        self.info_embed = info_embed
        self.help_embed = help_embed
        self.owner_text_embed = owner_text_embed
        self.webhook_info_embed = webhook_info_embed


"""
Mission generator views

"""

# buttons for mission generation
class MissionSendView(View):
    def __init__(self, mission_params, author: typing.Union[discord.Member, discord.User], timeout=300):
        self.author = author
        self.mission_params: MissionParams = mission_params
        super().__init__(timeout=timeout)
        print(f"Sendflags: {self.mission_params.sendflags}")
        # set button styles based on input status
        self.notify_haulers_select_button.style=discord.ButtonStyle.primary if 'n' in self.mission_params.sendflags else discord.ButtonStyle.secondary
        # self.notify_wine_loader_select_button.style=discord.ButtonStyle.primary if 'b' in self.mission_params.sendflags else discord.ButtonStyle.secondary
        self.reddit_send_select_button.style=discord.ButtonStyle.primary if 'r' in self.mission_params.sendflags else discord.ButtonStyle.secondary
        self.webhooks_send_select_button.style=discord.ButtonStyle.primary if 'w' in self.mission_params.sendflags else discord.ButtonStyle.secondary
        self.text_gen_select_button.style=discord.ButtonStyle.primary if 't' in self.mission_params.sendflags else discord.ButtonStyle.secondary
        self.edmc_off_button.style=discord.ButtonStyle.primary if 'e' in self.mission_params.sendflags else discord.ButtonStyle.secondary
        self.message_button.style=discord.ButtonStyle.primary if self.mission_params.cco_message_text else discord.ButtonStyle.secondary

        # remove the webhook button if user has no webhooks
        if not self.mission_params.webhook_names:
            self.webhooks_send_select_button.disabled = True
            self.webhooks_send_select_button.style=discord.ButtonStyle.secondary

        # disable Notify Haulers and EDMC-OFF buttons for wine loads during BC
        if self.mission_params.booze_cruise:
            self.notify_haulers_select_button.disabled = True
            self.edmc_off_button.disabled = True

        """# only show the wine loader ping button if BC condition is active
        else:
            self.remove_item(self.notify_wine_loader_select_button)"""

        # disable external sends for low profit loads
        if self.mission_params.profit < 10:
            self.reddit_send_select_button.disabled = True
            self.reddit_send_select_button.style=discord.ButtonStyle.secondary
            self.webhooks_send_select_button.disabled = True
            self.webhooks_send_select_button.style=discord.ButtonStyle.secondary

    # row 0
    """@discord.ui.button(label="Discord", style=discord.ButtonStyle.primary, emoji=f"<:discord:{discord_emoji()}>", custom_id="send_discord", row=0, disabled=True)
    async def discord_send_select_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass"""

    @discord.ui.button(label="Notify Haulers", style=discord.ButtonStyle.secondary, emoji="🔔", custom_id="notify_haulers", row=0)
    async def notify_haulers_select_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if 'n' in self.mission_params.sendflags:
            print(f"{interaction.user.display_name} is deselecting Notify Haulers")
            self.mission_params.sendflags.remove('n')
        else:
            print(f"{interaction.user.display_name} is selecting Notify Haulers")
            self.mission_params.sendflags.append('n')
            # if 'b' in self.mission_params.sendflags: self.mission_params.sendflags.remove('b') # don't allow pinging both haulers and BubbleWineLoaders

        # update our button view - the button colors will automatically change
        view = MissionSendView(self.mission_params, self.author)
        await interaction.response.edit_message(embeds=self.mission_params.original_message_embeds, view=view)

    """@discord.ui.button(label="Notify Wine Loaders", style=discord.ButtonStyle.secondary, emoji="🍷", custom_id="notify_wine_loaders", row=0)
    async def notify_wine_loader_select_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if 'b' in self.mission_params.sendflags:
            print(f"{interaction.user.display_name} is deselecting Notify Wine Loaders")
            self.mission_params.sendflags.remove('b')
        else:
            print(f"{interaction.user.display_name} is selecting Notify Wine Loaders")
            self.mission_params.sendflags.append('b')
            if 'n' in self.mission_params.sendflags: self.mission_params.sendflags.remove('n') # don't allow pinging both haulers and BubbleWineLoaders

        # update our button view - the button colors will automatically change
        view = MissionSendView(self.mission_params, self.author)
        await interaction.response.edit_message(embeds=self.mission_params.original_message_embeds, view=view)"""

    @discord.ui.button(label="Reddit", style=discord.ButtonStyle.secondary, emoji=f"<:upvote:{upvote_emoji()}>", custom_id="send_reddit", row=0)
    async def reddit_send_select_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if 'r' in self.mission_params.sendflags:
            print(f"{interaction.user.display_name} is deselecting Reddit send")
            self.mission_params.sendflags.remove('r')
        else:
            print(f"{interaction.user.display_name} is selecting Reddit send")
            self.mission_params.sendflags.append('r')

        # update our button view - the button colors will automatically change
        view = MissionSendView(self.mission_params, self.author)
        await interaction.response.edit_message(embeds=self.mission_params.original_message_embeds, view=view)

    @discord.ui.button(label="Webhooks", style=discord.ButtonStyle.secondary, emoji="🌐", custom_id="send_webhooks", row=0)
    async def webhooks_send_select_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if 'w' in self.mission_params.sendflags:
            print(f"{interaction.user.display_name} is deselecting Webhooks send")
            self.mission_params.sendflags.remove('w')
        else:
            print(f"{interaction.user.display_name} is selecting Webhooks send")
            self.mission_params.sendflags.append('w')

        # update our button view - the button colors will automatically change
        view = MissionSendView(self.mission_params, self.author)
        await interaction.response.edit_message(embeds=self.mission_params.original_message_embeds, view=view)

    @discord.ui.button(label="Copy/Paste Text", style=discord.ButtonStyle.secondary, emoji="📃", custom_id="text_only", row=0)
    async def text_gen_select_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if 't' in self.mission_params.sendflags:
            print(f"{interaction.user.display_name} is deselecting Copy/Paste Text")
            self.mission_params.sendflags.remove('t')
        else:
            print(f"{interaction.user.display_name} is selecting Copy/Paste Text")
            self.mission_params.sendflags.append('t')

        # update our button view - the button colors will automatically change
        view = MissionSendView(self.mission_params, self.author)
        await interaction.response.edit_message(embeds=self.mission_params.original_message_embeds, view=view)

    # row 1
    @discord.ui.button(label="Send", style=discord.ButtonStyle.success, emoji="📢", custom_id="sendall", row=1)
    async def send_mission_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled=True
        print(f"▶ {interaction.user.display_name} is sending their mission with flags {self.mission_params.sendflags}")

        # this isn't really necessary but it's tidier
        if not self.mission_params.webhook_names:
            self.mission_params.sendflags.remove('w')

        try: # there's probably a better way to do this using an if statement
            self.clear_items()
            await interaction.response.edit_message(embeds=self.mission_params.original_message_embeds, view=self)
        except Exception as e:
            print(e)

        print("Calling mission generator from Send Mission button")
        await gen_mission(interaction, self.mission_params)

    @discord.ui.button(label="EDMC-OFF", style=discord.ButtonStyle.primary, emoji="🤫", custom_id="edmcoff", row=1)
    async def edmc_off_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if 'e' in self.mission_params.sendflags:
            print(f"{interaction.user.display_name} is deselecting EDMC-OFF")
            # reset sendflags to default
            self.mission_params.sendflags = ['d', 'n', 'r', 'w']
        else:
            print(f"{interaction.user.display_name} is selecting EDMC-OFF send profile")
            # reset our sendflags to edmc-off
            self.mission_params.sendflags = ['d', 'e', 'n']

        # update our button view - the button colors will automatically change
        view = MissionSendView(self.mission_params, self.author)
        await interaction.response.edit_message(embeds=self.mission_params.original_message_embeds, view=view)

    @discord.ui.button(label="Set Message", style=discord.ButtonStyle.secondary, emoji="✍", custom_id="message", row=1)
    async def message_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"{interaction.user.display_name} wants to add a message to their mission")
    
        await interaction.response.send_modal(AddMessageModal(self.mission_params, self.author))

    async def interaction_check(self, interaction: discord.Interaction): # only allow original command user to interact with buttons
        if interaction.user.id == self.author.id:
            return True
        else:
            embed = discord.Embed(
                description="Only the command author may use these interactions.",
                color=constants.EMBED_COLOUR_ERROR
            )
            embed.set_image(url='https://media1.tenor.com/images/939e397bf929b9768b24a8fa165301fe/tenor.gif?itemid=26077542')
            embed.set_footer(text="Seriously, are you 4? 🙄")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="✖", custom_id="cancel", row=1)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        print("Mission gen cancelled by user")
        button.disabled=True

        cancelled_embed = discord.Embed(
            description="Mission send cancelled by user.",
            color=constants.EMBED_COLOUR_ERROR
        )

        try:
            self.clear_items()
            embeds = []
            embeds.extend(self.mission_params.original_message_embeds)
            embeds.append(cancelled_embed)
            await interaction.response.edit_message(embeds=embeds, view=self) # mission gen ends here
        except Exception as e:
            print(e)

    async def on_timeout(self):
        # return a message to the user that the interaction has timed out
        print("Button View timed out")
        timeout_embed = discord.Embed(
            description="Timed out.",
            color=constants.EMBED_COLOUR_ERROR
        )

        # remove buttons
        self.clear_items()

        embeds = [self.mission_params.original_message_embeds, timeout_embed]

        try:
            await self.message.edit(embeds=embeds, view=self) # mission gen ends here
        except Exception as e:
            print(e)


# modal for message button
class AddMessageModal(Modal):
    def __init__(self, mission_params, author, title = 'Add message to mission', timeout = None) -> None:
        self.mission_params: MissionParams = mission_params
        self.author = author
        self.message.default = self.mission_params.cco_message_text if self.mission_params.cco_message_text else None
        super().__init__(title=title, timeout=timeout)

    message = discord.ui.TextInput(
        label='Enter your message below.',
        style=discord.TextStyle.long,
        placeholder='Normal Discord markdown works, but mentions and custom emojis require full code.',
        required=False,
        max_length=4000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            print("Message submitted")
            print(self.message.value)

            embeds = []
            embeds.extend(self.mission_params.original_message_embeds)

            # remove our old message embed if there is one
            if embeds and hasattr(embeds[-1], 'title') and "message" in embeds[-1].title.lower():
                embeds.pop()

            message_embed = discord.Embed(
                color=constants.EMBED_COLOUR_RP
            )

            if self.message.value:
                self.mission_params.cco_message_text = str(self.message.value)
                """
                While self.message returns the inputted text if printed, it is actually a class holding
                all the attributes of the TextInput. View shows only the text the user inputted.

                This is important because it is a weak instance and cannot be pickled with mission_params,
                and we only want the value pickled anyway
                """
                print(self.mission_params.cco_message_text)
                message_embed.title="✍ MESSAGE SET"
                message_embed.description=self.mission_params.cco_message_text

            else:
                self.mission_params.cco_message_text = None

                message_embed.title="🗑 MESSAGE REMOVED"

            embeds.append(message_embed)

            # update our master embeds list
            self.mission_params.original_message_embeds = embeds

            view = MissionSendView(self.mission_params, self.author)


            await interaction.response.edit_message(embeds=embeds, view=view)

        except Exception as e:
            traceback.print_exc()
            print(e)



"""
Mission generator helpers

"""

async def define_reddit_texts(mission_params):
    mission_params.reddit_title = txt_create_reddit_title(mission_params)
    mission_params.reddit_body = txt_create_reddit_body(mission_params)
    mission_params.reddit_img_name = await create_carrier_reddit_mission_image(mission_params)
    print("Defined Reddit elements")


async def validate_profit(interaction: discord.Interaction, mission_params):
    print("Validating profit")
    if not float(mission_params.profit):
        profit_error_embed = discord.Embed(
            description=f"❌ Profit must be a number (int or float), e.g. `10` or `4.5` but not `ten` or `lots` or `{mission_params.profit_raw}`.",
            color=constants.EMBED_COLOUR_ERROR
        )
        profit_error_embed.set_footer(text="You wonky banana.")
        mission_params.returnflag = False
        return await interaction.channel.send(embed=profit_error_embed)


async def validate_pads(interaction: discord.Interaction, mission_params):
    print("Validating pads")
    if mission_params.pads.upper() not in ['M', 'L']:
        # In case a user provides some junk for pads size, gate it
        print(f'Exiting mission generation requested by {interaction.user} as pad size is invalid, provided: {mission_params.pads}')
        pads_error_embed = discord.Embed(
            description=f"❌ Pads must be `L` or `M`, or use autocomplete to select `Large` or `Medium`. `{mission_params.pads}` is right out.",
            color=constants.EMBED_COLOUR_ERROR
        )
        pads_error_embed.set_footer(text="You silly goose.")
        print(f"Set returnflag {mission_params.returnflag}")
        mission_params.returnflag = False
        return await interaction.channel.send(embed=pads_error_embed)
    

async def validate_supplydemand(interaction: discord.Interaction, mission_params):
    print("Validating supply/demand")
    if not float(mission_params.demand):
        profit_error_embed = discord.Embed(
            description=f"❌ Supply/demand must be a number (int or float), e.g. `20` or `16.5` but not `twenty thousand` or `loads` or `{mission_params.demand_raw}`.",
            color=constants.EMBED_COLOUR_ERROR
        )
        profit_error_embed.set_footer(text="You adorable scamp.")
        mission_params.returnflag = False
        print(f"Set returnflag {mission_params.returnflag}")
        return await interaction.channel.send(embed=profit_error_embed)
    elif float(mission_params.demand) > 25:
        profit_error_embed = discord.Embed(
            description=f"❌ Supply/demand is expressed in thousands of tons (K), so cannot be higher than the maximum capacity of a Fleet Carrier (25K tons).",
            color=constants.EMBED_COLOUR_ERROR
        )
        profit_error_embed.set_footer(text="You loveable bumpkin.")
        mission_params.returnflag = False
        print(f"Set returnflag {mission_params.returnflag}")
        return await interaction.channel.send(embed=profit_error_embed)
    else:
        return


async def define_commodity(interaction: discord.Interaction, mission_params):
    # define commodity
    if mission_params.commodity_search_term in constants.commodities_common:
        # the user typed in the name perfectly or used autocomplete so we don't need to bother querying the commodities db
        mission_params.commodity_name = mission_params.commodity_search_term
    else: # check if commodity can be found based on user's search term, exit gracefully if not
        await find_commodity(mission_params, interaction)
        if not mission_params.returnflag:
            return # we've already given the user feedback on why there's a problem, we just want to quit gracefully now
        if not mission_params.commodity_name:  # error condition
            try:
                raise CustomError("You must input a valid commodity.", isprivate=False)
            except CustomError as e:
                print(e)
                await on_generic_error(interaction, e)


async def return_discord_alert_embed(interaction, mission_params: MissionParams):
    if mission_params.mission_type == 'load':
        embed = discord.Embed(description=mission_params.discord_text, color=constants.EMBED_COLOUR_LOADING)
    else:
        embed = discord.Embed(description=mission_params.discord_text, color=constants.EMBED_COLOUR_UNLOADING)
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar)
    return embed


async def return_discord_channel_embeds(mission_params: MissionParams):
    carrier_data: CarrierData = mission_params.carrier_data
    print("Called return_discord_channel_embeds")
    # generates embeds used for the PTN carrier channel as well as any webhooks

    # define owner avatar
    guild: discord.Guild = await get_guild()
    owner: discord.Member = guild.get_member(carrier_data.ownerid)
    owner_name = owner.display_name
    owner_avatar = owner.display_avatar
    pads = "**LARGE**" if 'l' in mission_params.pads.lower() else "**MEDIUM**"

    # define embed content
    print("Define buy embed")
    if mission_params.mission_type == 'load': # embeds for a loading mission
        buy_description=f"📌 Station: **{mission_params.station.upper()}**" \
                        f"\n🛬 Landing Pad: {pads}" \
                        f"\n🌟 System: **{mission_params.system.upper()}**" \
                        f"\n📦 Commodity: **{mission_params.commodity_name.upper()}**"
        
        buy_thumb = constants.ICON_BUY

        sell_description=f"🎯 Fleet Carrier: **{carrier_data.carrier_long_name}**" \
                         f"\n🔢 Carrier ID: **{carrier_data.carrier_identifier}**" \
                         f"\n💰 Profit: **{mission_params.profit}K PER TON**" \
                         f"\n📥 Demand: **{mission_params.demand}K TONS**"
        
        sell_thumb = ptn_logo_discord(strftime('%B'))

        embed_colour = constants.EMBED_COLOUR_LOADING

    else: # embeds for an unloading mission
        buy_description=f"🎯 Fleet Carrier: **{carrier_data.carrier_long_name}**" \
                        f"\n🔢 Carrier ID: **{carrier_data.carrier_identifier}**" \
                        f"\n🌟 System: **{mission_params.system.upper()}**" \
                        f"\n📦 Commodity: **{mission_params.commodity_name.upper()}**" \
                         f"\n📤 Supply: **{mission_params.demand}K TONS**"

        buy_thumb = ptn_logo_discord(strftime('%B'))

        sell_description=f"📌 Station: **{mission_params.station.upper()}**" \
                         f"\n🛬 Landing Pad: {pads}" \
                         f"\n💰 Profit: **{mission_params.profit}K PER TON**" \
        
        sell_thumb = constants.ICON_SELL

        embed_colour = constants.EMBED_COLOUR_UNLOADING

    print("Define sell embed")
    # desc used by the local PTN additional info embed
    additional_info_description = f"💎 Carrier Owner: <@{carrier_data.ownerid}>" \
                                  f"\n🔤 Carrier information: </info:849040914948554766>" \
                                  f"\n📊 Stock information: `;stock {carrier_data.carrier_short_name}`\n\n"

    print("Define help embed (local)")
    # desc used by the local PTN help embed
    if mission_params.edmc_off:
        edmc_text = "\n\n🤫 This mission is flagged **EDMC-OFF**. Please disable/quit **all journal reporting apps** such as EDMC, EDDiscovery, etc."
    else:
        edmc_text = f"\n\n:warning: cAPI stock is updated once per hour. Run [EDMC](https://github.com/EDCD/EDMarketConnector/wiki/Installation-&-Setup) " \
                    f"and use `;stock {carrier_data.carrier_short_name} inara` for more accurate stock tracking."
    help_description = f"✅ Use </mission complete:{mcomplete_id()}> in this channel if the mission is completed, or unable to be completed (e.g. because of a station price change, or supply exhaustion)." \
                       f"\n\n💡 Need help? Here's our [complete guide to PTN trade missions](https://pilotstradenetwork.com/fleet-carrier-trade-missions/).{edmc_text}"

    print("Define descs")
    # desc used for sending cco_message_text
    owner_text_description = mission_params.cco_message_text

    # desc used by the webhook additional info embed    
    webhook_info_description = f"💎 Carrier Owner: <@{carrier_data.ownerid}>" \
                               f"\n🔤 [PTN Discord](https://discord.gg/ptn)" \
                                "\n💡 [PTN trade mission guide](https://pilotstradenetwork.com/fleet-carrier-trade-missions/)"

    print("Define embed objects")
    buy_embed = discord.Embed(
        title="BUY FROM",
        description=buy_description,
        color=embed_colour
    )
    buy_embed.set_image(url=constants.BLANKLINE_400PX)
    buy_embed.set_thumbnail(url=buy_thumb)

    sell_embed = discord.Embed(
        title="SELL TO",
        description=sell_description,
        color=embed_colour
    )
    sell_embed.set_image(url=constants.BLANKLINE_400PX)
    sell_embed.set_thumbnail(url=sell_thumb)

    info_embed = discord.Embed(
        title="ADDITIONAL INFORMATION",
        description=additional_info_description,
        color=embed_colour
    )
    info_embed.set_image(url=constants.BLANKLINE_400PX)
    info_embed.set_thumbnail(url=owner_avatar)
    
    help_embed = discord.Embed(
        description=help_description,
        color=embed_colour
    )
    help_embed.set_image(url=constants.BLANKLINE_400PX)

    owner_text_embed = discord.Embed(
        title=f"MESSAGE FROM {owner_name}",
        description=owner_text_description,
        color=constants.EMBED_COLOUR_RP
    )
    owner_text_embed.set_image(url=constants.BLANKLINE_400PX)
    owner_text_embed.set_thumbnail(url=constants.ICON_DATA)

    webhook_info_embed = discord.Embed(
        title="ADDITIONAL INFORMATION",
        description=webhook_info_description,
        color=embed_colour
    )
    webhook_info_embed.set_image(url=constants.BLANKLINE_400PX)
    webhook_info_embed.set_thumbnail(url=owner_avatar)

    print("instantiate DiscordEmbeds class")
    discord_embeds = DiscordEmbeds(buy_embed, sell_embed, info_embed, help_embed, owner_text_embed, webhook_info_embed)

    mission_params.discord_embeds = discord_embeds

    return discord_embeds


async def send_mission_to_discord(interaction: discord.Interaction, mission_params: MissionParams):
    print("User used option d, creating mission channel")

    # beyond this point we need to release channel lock if mission creation fails

    mission_params.mission_temp_channel_id = await create_mission_temp_channel(interaction, mission_params)
    mission_temp_channel = bot.get_channel(mission_params.mission_temp_channel_id)

    message_send = await interaction.channel.send("**Sending to Discord...**")
    try:
        # TRADE ALERT
        # send trade alert to trade alerts channel, or to wine alerts channel if loading wine for the BC
        submit_mission = await send_discord_alert(interaction, mission_params)
        if not submit_mission: return

        # CHANNEL MESSAGE
        submit_mission = await send_discord_channel_message(interaction, mission_params, mission_temp_channel)
        if not submit_mission: return

        print("Feeding back to user...")
        embed = discord.Embed(
            title=f"Discord trade alerts sent for {mission_params.carrier_data.carrier_long_name}",
            description=f"Check <#{mission_params.channel_alerts_actual}> for trade alert and "
                        f"<#{mission_params.mission_temp_channel_id}> for carrier channel alert.",
            color=constants.EMBED_COLOUR_DISCORD)
        embed.set_thumbnail(url=constants.ICON_DISCORD_CIRCLE)
        await interaction.channel.send(embed=embed)
        await message_send.delete()

        submit_mission = True

        return submit_mission, mission_temp_channel

    except Exception as e:
        print(f"Error sending to Discord: {e}")
        await interaction.channel.send(f"❌ Could not send to Discord, mission generation aborted: {e}")
        return


async def send_discord_alert(interaction: discord.Interaction, mission_params: MissionParams):
    # generate alert text
    mission_params.discord_text = txt_create_discord(interaction, mission_params)

    try:
        if (
            (hasattr(mission_params, 'booze_cruise') and mission_params.booze_cruise)
            or
            (not hasattr(mission_params, 'booze_cruise') and mission_params.commodity_name.title() == 'Wine') # pre-2.3.0 compatibility
        ): # condition for a BC wine load
            if mission_params.mission_type == 'load':
                alerts_channel = bot.get_channel(mission_params.channel_defs.wine_loading_channel_actual)
            else:   # unloading block
                alerts_channel = bot.get_channel(mission_params.channel_defs.wine_unloading_channel_actual)
        else:
            alerts_channel = bot.get_channel(mission_params.channel_defs.alerts_channel_actual)

        if (
            (hasattr(mission_params, 'booze_cruise') and not mission_params.booze_cruise)
            or
            (not hasattr(mission_params, 'booze_cruise') and mission_params.commodity_name.title() != 'Wine') # pre-2.3.0 compatibility
        ): # condition for if subject is not a BC wine load
            embed = await return_discord_alert_embed(interaction, mission_params)
            trade_alert_msg = await alerts_channel.send(embed=embed)
        else: # BC channels don't use embeds
            trade_alert_msg = await alerts_channel.send(mission_params.discord_text, suppress_embeds=True)
        mission_params.discord_alert_id = trade_alert_msg.id

        if mission_params.edmc_off:
            print('Reacting to #official-trade-alerts message with EDMC OFF')
            for r in ["🇪","🇩","🇲","🇨","📴"]:
                await trade_alert_msg.add_reaction(r)

        mission_params.channel_alerts_actual = alerts_channel.id

        return True

    except Exception as e:
        print(f"Error sending to Discord: {e}")
        await interaction.channel.send(f"❌ Could not send to Discord, mission generation aborted: {e}")
        return True


async def send_discord_channel_message(interaction: discord.Interaction, mission_params: MissionParams, mission_temp_channel: discord.TextChannel):
    try:
        if mission_params.edmc_off: # add in EDMC OFF header image
            edmc_off_banner_file = discord.File(constants.BANNER_EDMC_OFF, filename="image.png")
            await mission_temp_channel.send(file=edmc_off_banner_file)

        mission_params.discord_img_name = await create_carrier_discord_mission_image(mission_params)
        discord_file = discord.File(mission_params.discord_img_name, filename="image.png")

        print("Defining Discord embeds...")
        discord_embeds = await return_discord_channel_embeds(mission_params)

        send_embeds = [discord_embeds.buy_embed, discord_embeds.sell_embed, discord_embeds.info_embed, discord_embeds.help_embed]

        print("Checking for cco_message_text status...")
        if mission_params.cco_message_text is not None: send_embeds.append(discord_embeds.owner_text_embed)

        print("Sending image and embeds...")
        # pin the carrier trade msg sent by the bot
        pin_msg = await mission_temp_channel.send(content=mission_params.discord_msg_content, file=discord_file, embeds=send_embeds)
        mission_params.discord_msg_id = pin_msg.id
        print("Pinning sent message...")
        await pin_msg.pin()

        # EDMC OFF section
        if mission_params.edmc_off: # add in EDMC OFF embed
            print('Sending EDMC OFF messages to haulers')
            embed = discord.Embed(title='PLEASE STOP ALL 3RD PARTY SOFTWARE: EDMC, EDDISCOVERY, ETC',
                    description=("Maximising our haulers' profits for this mission means keeping market data at this station"
                            " **a secret**! For this reason **please disable/exit all journal reporting plugins/programs**"
                           f" and leave them off until all missions at this location are complete. Thanks CMDRs! <:o7:{o7_emoji()}>"),
                    color=constants.EMBED_COLOUR_REDDIT)

            # attach a random shush gif
            edmc_off_gif_url = random.choice(constants.shush_gifs)
            embed.set_image(url=edmc_off_gif_url)

            # send and pin message
            pin_edmc = await mission_temp_channel.send(embed=embed)
            await pin_edmc.pin()

            # notify user
            embed = discord.Embed(title=f"EDMC OFF messages sent for {mission_params.carrier_data.carrier_long_name}", description='External posts (Reddit, Webhooks) will be skipped.',
                        color=constants.EMBED_COLOUR_DISCORD)
            embed.set_thumbnail(url=constants.EMOJI_SHUSH)
            await interaction.channel.send(embed=embed)

        return True

    except Exception as e:
        print(f"Error sending to Discord: {e}")
        await interaction.channel.send(f"❌ Could not send to Discord, mission generation aborted: {e}")
        return False

async def check_profit_margin_on_external_send(interaction, mission_params):
    # check profit is above 10k/ton minimum
    if float(mission_params.profit) < 10:
        mission_params.returnflag = False
        print(f'Not posting the mission from {interaction.user} to reddit due to low profit margin <10k/t.')
        embed = discord.Embed(
            description=f"Skipped external send as {mission_params.profit}K/TON is below the PTN 10K/TON minimum profit margin."
        )
        embed.set_footer(text="Whoopsie-daisy.")
        embed.set_thumbnail(url=constants.ICON_FC_EMPTY)
        await interaction.channel.send(embed=embed)
    else:
        mission_params.returnflag = True


async def send_mission_to_subreddit(interaction, mission_params):
    print("User used option r")
    await check_profit_margin_on_external_send(interaction, mission_params)

    if mission_params.returnflag == False:
        return

    else:
        print("Profit OK, proceeding")

    message_send = await interaction.channel.send("**Sending to Reddit...**")

    if not mission_params.reddit_title: await define_reddit_texts(mission_params)

    try:
        # post to reddit
        print("Defining Reddit elements")
        reddit = await get_reddit()
        subreddit = await reddit.subreddit(mission_params.channel_defs.sub_reddit_actual)
        try:
            async def _post_submission_to_reddit():
                print("⏳ Attempting Reddit post...")
                await subreddit.submit_image(mission_params.reddit_title, image_path=mission_params.reddit_img_name,
                                                flair_id=mission_params.channel_defs.reddit_flair_in_progress,
                                                without_websockets=True) # temporary ? workaround for PRAW error
                return
                
            await asyncio.wait_for(_post_submission_to_reddit(), timeout=reddit_timeout())

        except asyncio.TimeoutError:
            print("❌⏲ Reddit post send timed out.")
            await message_send.delete()
            error = "Timed out while trying to send to Reddit."
            try:
                raise AsyncioTimeoutError(error, False)
            except Exception as e:
                await on_generic_error(interaction, e)
            return

        except Exception as e:
            print(f"❌ Error posting to Reddit: {e}")
            traceback.print_exc()

        try:
            print("⏳ Attempting to retrieve Reddit post...") 
            async def _get_new_reddit_post(): # temporary ? workaround for PRAW error
                submission = None
                while True:
                    async for new_post in subreddit.new():
                        print(f"⏳ Testing submission {new_post}")
                        if new_post.title == mission_params.reddit_title:
                            print(f'✅ Found the matching submission: {new_post.title}')
                            submission = new_post
                            break
                    if submission:
                        break
                    await asyncio.sleep(5)  # how long to wait before trying again
                return submission

            submission = await asyncio.wait_for(_get_new_reddit_post(), timeout=reddit_timeout())

        except asyncio.TimeoutError:
            print("❌⏲ Reddit post retrieval timed out")
            await message_send.delete()
            error = "Timed out while trying to get Reddit post link. Reddit URL will not be saved to missions database."
            try:
                raise AsyncioTimeoutError(error, False)
            except Exception as e:
                await on_generic_error(interaction, e)
            return


        mission_params.reddit_post_url = submission.permalink
        mission_params.reddit_post_id = submission.id

        try:
            async def post_comment_to_reddit():
                print("⏳ Attempting to reply to Reddit post...")
                if mission_params.cco_message_text:
                    comment = await submission.reply(f"> {mission_params.cco_message_text}\n\n&#x200B;\n\n{mission_params.reddit_body}")
                else:
                    comment = await submission.reply(mission_params.reddit_body)
                mission_params.reddit_comment_url = comment.permalink
                mission_params.reddit_comment_id = comment.id
                print(f"✅ Submitted Reddit comment {comment}")

            await asyncio.wait_for(post_comment_to_reddit(), timeout=reddit_timeout())

        except Exception as e:
            print(f"❌ Reddit comment post failed: {e}")
            reddit_error_embed = discord.Embed(
                description=f"❌ Couldn't reply to Reddit post with trade details.",
                color=constants.EMBED_COLOUR_ERROR
            )
            reddit_error_embed.set_footer(text="Attempting to continue with other sends.")
            await interaction.channel.send(embed=reddit_error_embed)

        embed = discord.Embed(
            title=f"Reddit trade alert sent for {mission_params.carrier_data.carrier_long_name}",
            description=f"https://www.reddit.com{mission_params.reddit_post_url}",
            color=constants.EMBED_COLOUR_REDDIT)
        embed.set_thumbnail(url=constants.ICON_REDDIT)
        await interaction.channel.send(embed=embed)
        await message_send.delete()
        embed = discord.Embed(title=f"{mission_params.carrier_data.carrier_long_name} REQUIRES YOUR UPDOOTS",
                            description=f"https://www.reddit.com{mission_params.reddit_post_url}",
                            color=constants.EMBED_COLOUR_REDDIT)
        channel = bot.get_channel(mission_params.channel_defs.upvotes_channel_actual)
        upvote_message = await channel.send(embed=embed)
        emoji = bot.get_emoji(upvote_emoji())
        await upvote_message.add_reaction(emoji)
        return
    except Exception as e:
        print(f"Error posting to Reddit: {e}")
        traceback.print_exc()
        reddit_error_embed = discord.Embed(
            description=f"❌ Could not send to Reddit. {e}",
            color=constants.EMBED_COLOUR_ERROR
        )
        reddit_error_embed.set_footer(text="Attempting to continue with other sends.")
        await interaction.channel.send(embed=reddit_error_embed)
        await message_send.delete()


async def send_mission_to_webhook(interaction, mission_params):
    print("Processing option w")

    print("Checking if user has any webhooks...")

    if not mission_params.webhook_names:
        print("✖ No webhooks found, skipping this step")
        return
    else:
        print("Webhooks found for user, continuing")

    await check_profit_margin_on_external_send(interaction, mission_params)

    if mission_params.returnflag == False:
        return

    else:
        print("Profit OK, proceeding")

    message_send = await interaction.channel.send("**Sending to Webhooks...**")

    print("Defining Discord embeds...")
    discord_embeds = mission_params.discord_embeds
    webhook_embeds = [discord_embeds.buy_embed, discord_embeds.sell_embed, discord_embeds.webhook_info_embed]

    if mission_params.cco_message_text: webhook_embeds.append(discord_embeds.owner_text_embed)

    try:
        async with aiohttp.ClientSession() as session: # send messages to each webhook URL
            for webhook_url, webhook_name in zip(mission_params.webhook_urls, mission_params.webhook_names):
                try:
                    print(f"Sending webhook to {webhook_url}")
                    # insert webhook URL
                    webhook = Webhook.from_url(webhook_url, session=session, client=bot)

                    discord_file = discord.File(mission_params.discord_img_name, filename="image.png")

                    # send embeds and image to webhook
                    webhook_sent = await webhook.send(file=discord_file, embeds=webhook_embeds, username='Pilots Trade Network', avatar_url=bot.user.avatar.url, wait=True)
                    """
                    To return to the message later, we need its ID which is the .id attribute
                    By default, the object returned from webhook.send is only partial, which limits what we can do with it.
                    To access all its attributes and methods like a regular sent message, we first have to fetch it using its ID.
                    """
                    mission_params.webhook_msg_ids.append(webhook_sent.id) # add the message ID to our MissionParams
                    mission_params.webhook_jump_urls.append(webhook_sent.jump_url) # add the jump_url to our MissionParams for convenience

                    print(f"Sent webhook trade alert with ID {webhook_sent.id} for webhook URL {webhook_url}")

                    embed = discord.Embed(
                        title=f"Webhook trade alert sent for {mission_params.carrier_data.carrier_long_name}:",
                        description=f"Sent to your webhook **{webhook_name}**: {webhook_sent.jump_url}",
                        color=constants.EMBED_COLOUR_DISCORD)
                    embed.set_thumbnail(url=constants.ICON_WEBHOOK_PTN)

                    await interaction.channel.send(embed=embed)

                except Exception as e:
                    print(f"Error sending webhooks: {e}")
                    inloop_webhook_error_embed = discord.Embed(
                        description=f"❌ Could not send to Webhook {webhook_name}. {e}",
                        color=constants.EMBED_COLOUR_ERROR
                    )
                    inloop_webhook_error_embed.set_footer(text="Attempting to continue with other sends.")
                    await interaction.channel.send(embed=inloop_webhook_error_embed)

    except Exception as e:
        print(f"Error sending webhooks: {e}")
        webhook_error_embed = discord.Embed(
            description=f"❌ Could not send to Webhooks. {e}",
            color=constants.EMBED_COLOUR_ERROR
        )
        webhook_error_embed.set_footer(text="Attempting to continue with other sends.")
        await interaction.channel.send(embed=webhook_error_embed)
    
    await message_send.delete()


async def notify_hauler_role(interaction: discord.Interaction, mission_params: MissionParams, mission_temp_channel: discord.TextChannel):
    print("User used option n or b")

    """if mission_params.booze_cruise:
        # this code is a relic of when role pings weren't allowed for BC, we'll keep it around for a while 🤪
        embed = discord.Embed(
            description=f"Skipped hauler ping for Wine load."
        )
        embed.set_footer(text="As our glorious tipsy overlords, the Sommeliers, have decreed o7")
        embed.set_thumbnail(url=constants.ICON_FC_EMPTY)
        return await interaction.channel.send(embed=embed)"""

    # define role to be pinged
    if mission_params.training: # trainee role
        mission_params.role_ping_actual = trainee_role()
    elif 'n' in mission_params.sendflags: # Hauler role
        mission_params.role_ping_actual = hauler_role()
    elif 'b' in mission_params.sendflags: # BubbleWineLoader role
        mission_params.role_ping_actual = wineloader_role()
        # this is still here in case the somms change their minds in future

    notify_msg = await mission_temp_channel.send(f"<@&{mission_params.role_ping_actual}>: {mission_params.discord_text}", suppress_embeds=True)
    mission_params.notify_msg_id = notify_msg.id

    embed = discord.Embed(
        title=f"Mission notification sent for {mission_params.carrier_data.carrier_long_name}",
        description=f"Pinged <@&{mission_params.role_ping_actual}> in <#{mission_params.mission_temp_channel_id}>.",
        color=constants.EMBED_COLOUR_DISCORD)
    embed.set_thumbnail(url=constants.ICON_DISCORD_PING)
    await interaction.channel.send(embed=embed)


async def send_mission_text_to_user(interaction: discord.Interaction, mission_params: MissionParams):
    print("User used option t")

    if not mission_params.reddit_title: await define_reddit_texts(mission_params)
    if not mission_params.discord_text:
        discord_text = txt_create_discord(interaction, mission_params)
        mission_params.discord_text = discord_text

    embed = discord.Embed(
        title="Trade Alert (Discord)",
        description=f"```{mission_params.discord_text}```",
        color=constants.EMBED_COLOUR_DISCORD
    )

    await interaction.channel.send(embed=embed)
    if mission_params.cco_message_text:
        embed = discord.Embed(
            title="Message text (raw)",
            description=mission_params.cco_message_text,
            color=constants.EMBED_COLOUR_RP
        )
        await interaction.channel.send(embed=embed)

    embed = discord.Embed(
        title="Reddit Post Title",
        description=f"`{mission_params.reddit_title}`",
        color=constants.EMBED_COLOUR_REDDIT
    )

    await interaction.channel.send(embed=embed)

    if mission_params.cco_message_text:
        embed = discord.Embed(
            title="Reddit Post Body - PASTE INTO MARKDOWN MODE",
            description=f"```> {mission_params.cco_message_text}\n\n&#x200B;\n\n{mission_params.reddit_body}```",
            color=constants.EMBED_COLOUR_REDDIT
        )
    else:
        embed = discord.Embed(
            title="Reddit Post Body - PASTE INTO MARKDOWN MODE",
            description=f"```{mission_params.reddit_body}```",
            color=constants.EMBED_COLOUR_REDDIT
        )
    embed.set_footer(text="**REMEMBER TO USE MARKDOWN MODE WHEN PASTING TEXT TO REDDIT.**")
    await interaction.channel.send(embed=embed)

    file = discord.File(mission_params.reddit_img_name, filename="image.png")
    embed = discord.Embed(
        title="Image with mission details",
        color=constants.EMBED_COLOUR_REDDIT
    )
    embed.set_image(url="attachment://image.png")
    await interaction.channel.send(file=file, embed=embed)

    embed = discord.Embed(title=f"Text Generation Complete for {mission_params.carrier_data.carrier_long_name}",
                        description="Paste Reddit content into **MARKDOWN MODE** in the editor. You can swap "
                                    "back to Fancy Pants afterwards and make any changes/additions or embed "
                                    "the image.\n\nBest practice for Reddit is an image post with a top level"
                                    " comment that contains the text version of the advert. This ensures the "
                                    "image displays with highest possible compatibility across platforms and "
                                    "apps. When mission complete, flag the post as *Spoiler* to prevent "
                                    "image showing and add a comment to inform.",
                        color=constants.EMBED_COLOUR_OK)
    await interaction.channel.send(embed=embed)
    print("E")

    return


"""
Mission generation

The core of MAB: its mission generator

"""
async def confirm_send_mission_via_button(interaction: discord.Interaction, mission_params: MissionParams):
    # this function does initial checks and returns send options to the user

    mission_params.returnflag = True # set the returnflag to true, any errors will change it to false
    
    await prepare_for_gen_mission(interaction, mission_params)

    if mission_params.returnflag == False:
        print("Problems found, mission gen will not proceed.")
        return

    if mission_params.returnflag == True:
        print("All checks complete, mission generation can continue")

        try:
            # check the details with the user
            confirm_embed = discord.Embed(
                title=f"{mission_params.mission_type.upper()}ING: {mission_params.carrier_data.carrier_long_name}",
                description=f"Confirm mission details and choose send targets for {mission_params.carrier_data.carrier_long_name}.",
                color=constants.EMBED_COLOUR_QU
            )
            thumb_url = constants.ICON_FC_LOADING if mission_params.mission_type == 'load' else constants.ICON_FC_UNLOADING
            confirm_embed.set_thumbnail(url=thumb_url)

            confirm_embed = _mission_summary_embed(mission_params, confirm_embed)

            low_profit_embed = None

            webhook_embed = None

            bc_embed = None

            if mission_params.profit < 10: # low profit load detection
                mission_params.sendflags = ['d']
                low_profit_embed = discord.Embed(
                    title=f"📉 Low-profit load detected",
                    description="External sends are disabled for missions offering under 10k/ton profit.",
                    color=constants.EMBED_COLOUR_WARNING
                )

            if mission_params.booze_cruise:
                mission_params.sendflags = ['d'] # default BC sendflags are just Discord
                bc_embed = discord.Embed(
                    title=f"🍷 Booze Cruise channels open",
                    description=f"Wine loads will be sent to <#{mission_params.channel_defs.wine_loading_channel_actual}>.",
                                # f"With <@&{somm_role()}> approval, you can choose to notify *either* the <@&{hauler_role()}> *or* <@&{wineloader_role()}> roles.",
                    color=constants.EMBED_COLOUR_WARNING
                )

            if mission_params.webhook_names and mission_params.profit > 10:
                webhook_embed = discord.Embed(
                    title=f"🌐 Webhooks found for {interaction.user.display_name}",
                    description="- Webhooks are saved to your user ID and therefore shared between all your registered Fleet Carriers.\n" \
                                "- Sending with the `🌐 Webhooks` option enabled (default) will send to *all* webhooks registered to your user.",
                    color=constants.EMBED_COLOUR_DISCORD
                )
                for webhook_name in mission_params.webhook_names:
                    webhook_embed.add_field(name="Webhook found", value=webhook_name)
                webhook_embed.set_thumbnail(url=constants.ICON_WEBHOOK_PTN)

            if low_profit_embed: mission_params.original_message_embeds.append(low_profit_embed) # append the low profit embed
            if bc_embed: mission_params.original_message_embeds.append(bc_embed) # append the BC embed if active
            if webhook_embed: mission_params.original_message_embeds.append(webhook_embed) # append the webhooks embed if user has any
            mission_params.original_message_embeds.append(confirm_embed)

            view = MissionSendView(mission_params, interaction.user) # buttons to add

            await interaction.edit_original_response(embeds=mission_params.original_message_embeds, view=view)

            # add the message attribute to the view so it can be retrieved by on_timeout
            view.message = await interaction.original_response()
        except Exception as e:
            print(e)
            traceback.print_exc()
            try:
                raise GenericError(e)
            except Exception as e:
                await on_generic_error(interaction, e)


async def prepare_for_gen_mission(interaction: discord.Interaction, mission_params: MissionParams):

    """
    - check validity of inputs
    - check if carrier data can be found
    - check if carrier is on a mission
    - return webhooks and commodity data
    - return wine channel status if wine load
    - check if carrier has a valid mission image
    """

    # validate profit
    await validate_profit(interaction, mission_params)

    # validate pads
    await validate_pads(interaction, mission_params)

    # validate supply/demand
    await validate_supplydemand(interaction, mission_params)
    print(f"Returnflag status: {mission_params.returnflag}")

    # check if the carrier can be found, exit gracefully if not
    carrier_data = flexible_carrier_search_term(mission_params.carrier_name_search_term)
    
    if not carrier_data:  # error condition
        carrier_error_embed = discord.Embed(
            description=f"❌ No carrier found for '**{mission_params.carrier_name_search_term}**'. Use `/owner` to see a list of your carriers. If it's not in the list, ask an Admin to add it for you.",
            color=constants.EMBED_COLOUR_ERROR
        )
        carrier_error_embed.set_footer(text="You silly sausage.")
        mission_params.returnflag = False
        return await interaction.channel.send(embed=carrier_error_embed)
    mission_params.carrier_data = carrier_data
    print(f"Returnflag status: {mission_params.returnflag}")

    # check carrier isn't already on a mission TODO change to ID lookup
    mission_data = find_mission(carrier_data.carrier_long_name, "carrier")
    if mission_data:
        mission_error_embed = discord.Embed(
            description=f"{mission_data.carrier_name} is already on a mission, please "
                        f"use `/cco complete` to mark it complete before starting a new mission.",
            color=constants.EMBED_COLOUR_ERROR)
        mission_params.returnflag = False
        return await interaction.channel.send(embed=mission_error_embed) # error condition
    print(f"Returnflag status: {mission_params.returnflag}")

    # check if the carrier has an associated image
    image_name = carrier_data.carrier_short_name + '.png'
    image_path = os.path.join(constants.IMAGE_PATH, image_name)
    if os.path.isfile(image_path):
        print("Carrier mission image found, checking size...")
        image = Image.open(image_path)
        image_is_good = image.size == (506, 285)
        # all good, let's go
    else:
        image_is_good = False
    if not image_is_good:
        print(f"No valid carrier image found for {carrier_data.carrier_long_name}")
        # send the user to upload an image
        continue_embed = discord.Embed(description="**YOUR FLEET CARRIER MUST HAVE A VALID MISSION IMAGE TO CONTINUE**.", color=constants.EMBED_COLOUR_QU)

        continue_embeds = []
        continue_embeds.extend(mission_params.original_message_embeds)
        continue_embeds.append(continue_embed)

        await interaction.edit_original_response(embeds=continue_embeds)

        success_embed = await assign_carrier_image(interaction, carrier_data.carrier_long_name, mission_params.original_message_embeds)
        mission_params.original_message_embeds.append(success_embed)
        # OK, let's see if they fixed the problem. Once again we check the image exists and is the right size
        if os.path.isfile(image_path):
            print("Found an image file, checking size")
            image = Image.open(image_path)
            image_is_good = image.size == (506, 285)
        else:
            image_is_good = False
        if not image_is_good:
            print("Still no good image, aborting")
            embed = discord.Embed(description="❌ You must have a valid mission image to continue.", color=constants.EMBED_COLOUR_ERROR)
            mission_params.returnflag = False
            return await interaction.channel.send(embed=embed) # error condition
    print(f"image check returnflag status: {mission_params.returnflag}")

    # define commodity
    await define_commodity(interaction, mission_params)
    print(f"define_commodity returnflag status: {mission_params.returnflag}")

    if mission_params.commodity_name.title() == 'Wine':
        winechannel = bot.get_channel(mission_params.channel_defs.wine_loading_channel_actual)
        mission_params.booze_cruise = winechannel.permissions_for(interaction.guild.default_role).view_channel
        # this only returns true if commodity is wine AND the BC channels are open, otherwise it is false

    # add any webhooks to mission_params
    webhook_data = find_webhook_from_owner(interaction.user.id)
    if webhook_data:
        for webhook in webhook_data:
            mission_params.webhook_urls.append(webhook.webhook_url)
            mission_params.webhook_names.append(webhook.webhook_name)

    print(f"Returnflag status: {mission_params.returnflag}")

    return


# mission generator called by loading/unloading commands
async def gen_mission(interaction: discord.Interaction, mission_params: MissionParams):
    # generate a timestamp for mission creation
    mission_params.timestamp = get_formatted_date_string()[2]

    current_channel = interaction.channel

    mission_params.print_values()

    submit_mission = False

    print(f'Mission generation type: {mission_params.mission_type} requested by {interaction.user}. Request triggered from '
        f'channel {current_channel}.')
    
    if mission_params.training:
        print("Training mode is active.")

    try: # this try/except block is to try and ensure the channel lock is released if something breaks during mission gen
         # otherwise the bot freezes next time the lock is attempted

        mission_params.edmc_off = True if "e" in mission_params.sendflags else False

        if "x" in mission_params.sendflags:
            async with interaction.channel.typing():
                # immediately stop if there's an x anywhere in the message, even if there are other proper inputs
                embed = discord.Embed(
                    description="**Mission creation cancelled.**",
                    color=constants.EMBED_COLOUR_ERROR
                )
                await interaction.channel.send(embed=embed)
                print("User cancelled mission generation")
                return

        if "t" in mission_params.sendflags: # send full text to mission gen channel
            async with interaction.channel.typing():
                await send_mission_text_to_user(interaction, mission_params)
            if not "d" in mission_params.sendflags: # skip the rest of mission gen as sending to Discord is required
                print("No discord send option selected, ending here")
                cleanup_temp_image_file(mission_params.reddit_img_name)
                return

        if "d" in mission_params.sendflags: # send to discord and save to mission database
            async with interaction.channel.typing():
                submit_mission, mission_temp_channel = await send_mission_to_discord(interaction, mission_params)
                if not submit_mission: # error condition, cleanup after ourselves
                    cleanup_temp_image_file(mission_params.discord_img_name)
                    if mission_params.mission_temp_channel_id:
                        await remove_carrier_channel(interaction, mission_params.mission_temp_channel_id, seconds_short)

            if "r" in mission_params.sendflags and not mission_params.edmc_off: # send to subreddit
                async with interaction.channel.typing():
                    await send_mission_to_subreddit(interaction, mission_params)

            if "w" in mission_params.sendflags and "d" in mission_params.sendflags and not mission_params.edmc_off: # send to webhook
                async with interaction.channel.typing():
                    await send_mission_to_webhook(interaction, mission_params)

            if ("n" in mission_params.sendflags or "b" in mission_params.sendflags) and "d" in mission_params.sendflags: # notify role ping
                async with interaction.channel.typing():
                    await notify_hauler_role(interaction, mission_params, mission_temp_channel)

            if any(letter in mission_params.sendflags for letter in ["r", "w"]) and mission_params.edmc_off: # scold the user for being very silly
                embed = discord.Embed(
                    title=f"EXTERNAL SENDS SKIPPED FOR {mission_params.carrier_data.carrier_long_name}",
                    description="Cannot send to Reddit or Webhooks as you flagged the mission as **EDMC-OFF**.",
                    color=constants.EMBED_COLOUR_ERROR
                )
                embed.set_footer(text="You silly billy.")
                await interaction.channel.send(embed=embed)

        else: # for mission gen to work and be stored in the database, the d option MUST be selected.
            embed = discord.Embed(
                description="❌ Sending to Discord is **required**. Please try again.",
                color=constants.EMBED_COLOUR_ERROR
            )
            embed.set_footer(text="No gentle snark this time. Only mild disapproval.")
            await interaction.channel.send(embed=embed)
            submit_mission = False

        print("All options worked through, now clean up")

        if submit_mission:
            await mission_add(mission_params)
            await mission_generation_complete(interaction, mission_params)
        try:
            print("Calling cleanup for temp files")
            cleanup_temp_image_file(mission_params.discord_img_name)
            cleanup_temp_image_file(mission_params.reddit_img_name)
        except Exception as e:
            print(e)

        print("Reached end of mission generator")
        return

    except Exception as e:
        print("Error on mission generation:")
        print(e)
        traceback.print_exc()
        mission_data = None
        try:
            mission_data = find_mission(mission_params.carrier_data.carrier_long_name, "carrier")
            print("Mission data found, mission was added to the database before exception")
        except:
            print("No mission data found, mission was not added to database")

        if mission_data:
            text = "Mission **was** entered into the database. Use `/missions` or `/mission` in the carrier channel to check its details." \
               "You can use `/cco complete` to close the mission if you need to re-generate it."
        else:
            text = "Mission was **not** entered into the database. It may require manual cleanup of channels etc."

        embed = discord.Embed(
            description=f"❌ {e}\n\n{text}",
            color=constants.EMBED_COLOUR_ERROR
        )
        await interaction.channel.send(embed=embed)

        # notify bot spam
        spamchannel = bot.get_channel(bot_spam_channel())

        message = await interaction.original_response()

        embed = discord.Embed(
            description=f"Error on mission generation by <@{interaction.user.id}> at {message.jump_url}:\n\n{e}\n\n{text}",
            color=constants.EMBED_COLOUR_ERROR
        )
        await spamchannel.send(embed=embed)

        try:
            print("Releasing channel lock...")
            locked = check_mission_channel_lock(mission_params.carrier_data.discord_channel)
            if locked:
                await unlock_mission_channel(mission_temp_channel.name)
                print("Channel lock released")
                embed = discord.Embed(
                    description=f"🔓 Released lock for `{mission_temp_channel.name}` (<#{mission_temp_channel.id}>) because of error in mission generation.",
                    color=constants.EMBED_COLOUR_OK
                )
                await spamchannel.send(embed=embed)
        except Exception as e:
            print(e)
        if mission_params.mission_temp_channel_id:
            await remove_carrier_channel(interaction, mission_params.mission_temp_channel_id, seconds_short)


async def create_mission_temp_channel(interaction, mission_params):
    # create the carrier's channel for the mission

    # first check whether channel already exists

    # we need to lock the channel to stop it being deleted mid process
    print("Waiting for Mission Generator channel lock...")
    embed = discord.Embed(
        description=f"⏳ Waiting to acquire lock for `{mission_params.carrier_data.discord_channel}`...",
        color=constants.EMBED_COLOUR_QU
    )
    lockwait_msg = await interaction.channel.send(embed=embed)
    try:
        await asyncio.wait_for(lock_mission_channel(mission_params.carrier_data.discord_channel), timeout=20)
        embed = discord.Embed(
            description=f"🔒 Lock acquired for `{mission_params.carrier_data.discord_channel}` for mission creation.",
            color=constants.EMBED_COLOUR_QU
        )
        spamchannel = bot.get_channel(bot_spam_channel())
        await spamchannel.send(embed=embed)
    except asyncio.TimeoutError as e:
        embed = discord.Embed(
            description=f"❌ Could not acquire lock for `{mission_params.carrier_data.discord_channel}` after 20 seconds: {e}",
            color=constants.EMBED_COLOUR_ERROR
        )
        await spamchannel.send(embed=embed)
        print(f"No channel lock available for {mission_params.carrier_data.discord_channel} after 20 seconds, giving up.")
        embed = discord.Embed(
            description=f"❌ Could not acquire lock for `{mission_params.carrier_data.discord_channel}` after 10 seconds. Please try mission generation again. If the problem persists, contact an Admin.",
            color=constants.EMBED_COLOUR_ERROR
        )
        return await interaction.channel.send("❌ Channel lock could not be acquired, please try again. If the problem persists please contact an Admin.")

    await lockwait_msg.delete()

    mission_channel_name = mission_params.carrier_data.discord_channel
    mission_temp_channel = False

    # only check for the channel in the target category
    if mission_params.training:
        # check for the channel in the training category
        category = bot.get_channel(training_cat())
    else:
        # check for the channel in the trade carriers category
        category = bot.get_channel(trade_cat())

    for channel in category.channels:
        if channel.name == mission_channel_name:
            print(f"Found existing channel in category {category}")
            mission_temp_channel = channel

    if mission_temp_channel:
        # channel exists, so reuse it
        mission_temp_channel_id = mission_temp_channel.id
        embed = discord.Embed(
            description=f"Found existing mission channel <#{mission_temp_channel_id}>.",
            color=constants.EMBED_COLOUR_DISCORD
        )
        await interaction.channel.send(embed=embed)
        print(f"Found existing {mission_temp_channel}")
    else:
        # channel does not exist, create it

        topic = f"Use \";stock {mission_params.carrier_data.carrier_short_name}\" to retrieve stock levels for this carrier."

        category = discord.utils.get(interaction.guild.categories, id=mission_params.channel_defs.category_actual)
        mission_temp_channel = await interaction.guild.create_text_channel(mission_params.carrier_data.discord_channel, category=category, topic=topic)
        mission_temp_channel_id = mission_temp_channel.id
        print(f"Created {mission_temp_channel}")

    if not mission_temp_channel:
        raise EnvironmentError(f'Could not create carrier channel {mission_params.carrier_data.discord_channel}')

    # we made it this far, we can change the returnflag
    gen_mission.returnflag = True

    # find carrier owner as a user object
    guild = await get_guild()
    try:
        member = await guild.fetch_member(mission_params.carrier_data.ownerid)
        print(f"Owner identified as {member.display_name}")
    except:
        raise EnvironmentError(f'Could not find Discord user matching ID {mission_params.carrier_data.ownerid}')

    overwrite = await get_overwrite_perms()

    try:
        # first make sure it has the default permissions for the category
        await mission_temp_channel.edit(sync_permissions=True)
        print("Synced permissions with parent category")
        # now add the owner with superpermissions
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


"""
Mission database
"""


# add mission to DB, called from mission generator
async def mission_add(mission_params):
    print("Called mission_add")
    backup_database('missions')  # backup the missions database before going any further

    # pickle the mission_params
    print("Pickle the params")
    attrs = vars(mission_params)
    print(attrs)
    pickled_mission_params = pickle.dumps(mission_params)

    print("Called mission_add to write to database")
    mission_db.execute(''' INSERT INTO missions VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ''', (
        mission_params.carrier_data.carrier_long_name, mission_params.carrier_data.carrier_identifier, mission_params.mission_temp_channel_id,
        mission_params.commodity_name.title(), mission_params.mission_type.lower(), mission_params.system.title(), mission_params.station.title(),
        mission_params.profit, mission_params.pads.upper(), mission_params.demand, mission_params.cco_message_text, mission_params.reddit_post_id,
        mission_params.reddit_post_url, mission_params.reddit_comment_id, mission_params.reddit_comment_url, mission_params.discord_alert_id, pickled_mission_params
    ))
    missions_conn.commit()
    print("Mission added to db")

    print("Updating last trade timestamp for carrier")
    await _update_carrier_last_trade(mission_params.carrier_data.pid)

    spamchannel = bot.get_channel(bot_spam_channel())

    # now we can release the channel lock
    try:
        locked = check_mission_channel_lock(mission_params.carrier_data.discord_channel)
        if locked: # this SHOULD be locked at this point, but we'll still check
            await unlock_mission_channel(mission_params.carrier_data.discord_channel)
            print("Channel lock released")
            embed = discord.Embed(
                description=f"🔓 Released lock for `{mission_params.carrier_data.discord_channel}`",
                color=constants.EMBED_COLOUR_OK
            )
            await spamchannel.send(embed=embed)
    except Exception as e:
        embed = discord.Embed(
            description=f"❌ Could not release lock for `{mission_params.carrier_data.discord_channel}`: {e}",
            color=constants.EMBED_COLOUR_ERROR
        )
        await spamchannel.send(embed=embed)
        print(f"Couldn't release lock for {mission_params.carrier_data.discord_channel}: {e}")
    return


async def mission_generation_complete(interaction: discord.Interaction, mission_params):
    print("reached mission_generation_complete")

    try:
        print("Making absolutely sure channel lock isn't engaged")
        locked = check_mission_channel_lock(mission_params.carrier_data.discord_channel)
        if locked:
            await unlock_mission_channel(mission_params.carrier_data.discord_channel)
            embed = discord.Embed(
                description=f"🔓 Released lock for `{mission_params.carrier_data.discord_channel}`",
                color=constants.EMBED_COLOUR_OK
            )
            spamchannel = bot.get_channel(bot_spam_channel())
            await spamchannel.send(embed=embed)
    finally:
        # nothing to do here, lock should already be disengaged
        pass

    # fetch data we just committed back

    mission_data = find_mission(mission_params.carrier_data.carrier_long_name, 'carrier')

    # return result to user

    # define return embed colours/icons based on mission type
    if mission_data.mission_type == 'load':
        embed_colour = constants.EMBED_COLOUR_LOADING
        thumbnail_url = constants.ICON_FC_LOADING
    else:
        embed_colour = constants.EMBED_COLOUR_UNLOADING
        thumbnail_url = constants.ICON_FC_UNLOADING

    embed = discord.Embed(
        title=f"{mission_data.mission_type.upper()}ING {mission_data.carrier_name} ({mission_data.carrier_identifier})",
        description="Mission successfully entered into the missions database. You can use `/missions` to view a list of active missions" \
                   f" or `/mission information` in <#{mission_data.channel_id}> to view its mission information from the database.",
        color=embed_colour
    )
    embed.set_thumbnail(url=thumbnail_url)

    # update the embed with mission data fields
    embed = _mission_summary_embed(mission_data.mission_params, embed)

    embed.set_footer(text="You can use /cco complete <carrier> to mark the mission complete.")

    await interaction.channel.send(embed=embed)

    # notify bot spam
    try:
        spamchannel = bot.get_channel(bot_spam_channel())

        message = await interaction.original_response()

        embed = discord.Embed(
            description=f"<@{interaction.user.id}> started or updated a mission for {mission_data.carrier_name} from <#{interaction.channel.id}>: {message.jump_url}",
            color=constants.EMBED_COLOUR_QU
        )
        await spamchannel.send(embed=embed)
    except Exception as e:
        print(e)
    print("Mission generation complete")
    return