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
import typing

# import discord.py
import discord
from discord import Webhook
from discord.components import SelectOption
from discord.errors import HTTPException, Forbidden, NotFound
from discord.ui import View, Modal, Select

# import local classes
from ptn.missionalertbot.classes.MissionData import MissionData
from ptn.missionalertbot.classes.MissionParams import MissionParams

# import local constants
import ptn.missionalertbot.constants as constants
from ptn.missionalertbot.constants import bot, get_reddit, seconds_short, upvote_emoji, hauler_role, trainee_role, \
    get_guild, get_overwrite_perms, ptn_logo_discord, wineloader_role, o7_emoji, bot_spam_channel, discord_emoji, training_cat, trade_cat

# import local modules
from ptn.missionalertbot.database.database import backup_database, mission_db, missions_conn, find_carrier, CarrierDbFields, \
    find_commodity, find_mission, carrier_db, carriers_conn, find_webhook_from_owner
from ptn.missionalertbot.modules.DateString import get_formatted_date_string
from ptn.missionalertbot.modules.Embeds import _mission_summary_embed
from ptn.missionalertbot.modules.helpers import lock_mission_channel, unlock_mission_channel, check_mission_channel_lock
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
# select menu for mission generation
# class MissionSendMenu(View):


# select menu for mission generation
class MissionSendSelectMenu(Select):
    def __init__(self, mission_params, author):
        self.mission_params = mission_params
        self.author = author
        options=[
            discord.SelectOption(label="Discord", emoji=f"<:discord:{discord_emoji()}>", description="Sending to the PTN Discord is required."),
            discord.SelectOption(label="Notify Haulers", emoji="🔔", description="Send a notification ping to the appropriate Hauler role."),
            discord.SelectOption(label="Webhooks", emoji="🌐", description="Send mission to your webhooks."),
            discord.SelectOption(label="Reddit", emoji=discord.PartialEmoji.from_str(f"<:upvote:{upvote_emoji()}>"), description="Send mission to the PTN subreddit."),
            discord.SelectOption(label="EDMC-OFF", emoji="🤫", description="Flag the mission as EDMC-OFF: external sends blocked."),
            discord.SelectOption(label="Copy-Paste Text", emoji="📃", description="Create texts for copy/pasting."),
            discord.SelectOption(label="Return to menu", emoji="◀", description="Return to the main menu.")
        ] 
        super().__init__(placeholder="Select your options", max_values=5, min_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.mission_params.sendflags = []
        if 'Return to menu' in self.values:
            print("User wants to go back to the buttons")
            try:
                view = MissionSendView(self.mission_params, self.author)
                await interaction.response.edit_message(embeds=self.mission_params.original_message_embeds, view=view)
                # TODO we should add the message back for timeouts on the buttons
                # view.message = await self.message does not work
                return
            except Exception as e:
                print(e)
                return

        if 'Discord' in self.values:
            print("User chose Discord option")
            self.mission_params.sendflags.append('d')

        if 'Webhooks' in self.values:
            print("Adding webhook send")
            self.mission_params.sendflags.append('w')
        
        if 'Reddit' in self.values:
            print("Adding Reddit send")
            self.mission_params.sendflags.append('r')

        if 'Notify Haulers' in self.values:
            print("Adding hauler notify")
            self.mission_params.sendflags.append('n')

        if 'EDMC-OFF' in self.values:
            print("Adding EDMC-OFF flag")
            self.mission_params.sendflags.append('e')

        if 'Copy-Paste Text' in self.values:
            print("Adding textgen")
            self.mission_params.sendflags.append('t')

        try: 
            await interaction.response.edit_message(embeds=self.mission_params.original_message_embeds, view=None)
        except Exception as e:
            print(e)

        print("Calling mission generator from Send Mission select menu")
        await gen_mission(interaction, self.mission_params)


# select menu view for mission generation
class MissionSendSelectMenuView(View):
    def __init__(self, mission_params, author: typing.Union[discord.Member, discord.User], timeout=300):
        self.author = author
        self.mission_params = mission_params
        super().__init__(timeout=timeout)
        view = MissionSendSelectMenu(self.mission_params, self.author)
        self.add_item(view)
        

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

    async def on_timeout(self):
        # return a message to the user that the interaction has timed out
        print("Select View timed out")
        timeout_embed = discord.Embed(
            description="Timed out.",
            color=constants.EMBED_COLOUR_ERROR
        )

        # remove buttons
        self.clear_items()

        if not self.mission_params.sendflags:
            embeds = [self.mission_params.copypaste_embed, timeout_embed]
        else:
            embeds = [self.mission_params.copypaste_embed]
        try:
            await self.message.edit(embeds=embeds, view=self) # mission gen ends here
        except Exception as e:
            print(e)


# buttons for mission generation
class MissionSendView(View):
    def __init__(self, mission_params, author: typing.Union[discord.Member, discord.User], timeout=300):
        self.author = author
        self.mission_params = mission_params
        super().__init__(timeout=timeout)

    @discord.ui.button(label="Send All", style=discord.ButtonStyle.success, emoji="📢", custom_id="sendall", row=1)
    async def send_mission_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled=True
        print(f"{interaction.user.display_name} is sending their mission to all available sources using default send button")

        if self.mission_params.commodity_name == 'Wine': # for wine, just send to Discord, profit margins are too small for externals and we don't ping
            self.mission_params.sendflags = ['d']
        else:
            self.mission_params.sendflags = ['d', 'r', 'n']

            if self.mission_params.webhook_names:
                print("Found webhooks, adding webhook flag")
                self.mission_params.sendflags.append('w')
        
        try: # there's probably a better way to do this using an if statement
            self.clear_items()
            await interaction.response.edit_message(embeds=self.mission_params.original_message_embeds, view=self)
        except Exception as e:
            print(e)

        print("Calling mission generator from Send Mission button")
        await gen_mission(interaction, self.mission_params)

    @discord.ui.button(label="Send EDMC-OFF", style=discord.ButtonStyle.primary, emoji="🤫", custom_id="edmcoff", row=1)
    async def edmc_off_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled=True
        print(f"{interaction.user.display_name} is sending their mission via EDMC-OFF preset button")

        if self.mission_params.commodity_name == 'Wine': # for wine, just send to Discord, profit margins are too small for externals and we don't ping
            self.mission_params.sendflags = ['d']
        else:
            self.mission_params.sendflags = ['d', 'e', 'n']

        try: # there's probably a better way to do this using an if statement
            self.clear_items()
            await interaction.response.edit_message(embeds=self.mission_params.original_message_embeds, view=self)
        except Exception as e:
            print(e)

        print("Calling mission generator from Send Mission button")
        await gen_mission(interaction, self.mission_params)

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

    @discord.ui.button(label="Set Message", style=discord.ButtonStyle.secondary, emoji="✍", custom_id="message", row=2)
    async def message_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"{interaction.user.display_name} wants to add a message to their mission")
    
        await interaction.response.send_modal(AddMessageModal(self.mission_params, view=self))

    @discord.ui.button(label="Select Sends From Menu", style=discord.ButtonStyle.secondary, emoji="☑", custom_id="menu", row=2)
    async def menu_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"{interaction.user.display_name} wants to use select menu")

        try:
            self.clear_items()
            menuview = MissionSendSelectMenuView(self.mission_params, self.author)
            embed = discord.Embed(
                description="Mission will be sent to the PTN Discord as well as any options you select.",
                color=constants.EMBED_COLOUR_QU
            )
            embeds = []
            embeds.extend(self.mission_params.original_message_embeds)
            embeds.append(embed)
            await interaction.response.edit_message(embeds=embeds, view=menuview)

            # add the message attribute to the view so it can be retrieved by on_timeout
            menuview.message = await interaction.original_response()
            # await interaction.response.edit_message(content="Hello", view=menuview)
        except Exception as e:
            print(e)

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

    async def on_timeout(self):
        # return a message to the user that the interaction has timed out
        print("Button View timed out")
        timeout_embed = discord.Embed(
            description="Timed out.",
            color=constants.EMBED_COLOUR_ERROR
        )

        # remove buttons
        self.clear_items()

        if not self.mission_params.sendflags:
            embeds = [self.mission_params.copypaste_embed, timeout_embed]
        else:
            embeds = [self.mission_params.copypaste_embed]
        try:
            await self.message.edit(embeds=embeds, view=self) # mission gen ends here
        except Exception as e:
            print(e)


# modal for message button
class AddMessageModal(Modal):
    def __init__(self, mission_params, view, title = 'Add message to mission', timeout = None) -> None:
        self.mission_params = mission_params
        self.view = view
        super().__init__(title=title, timeout=timeout)

    message = discord.ui.TextInput(
        label='Enter your message below.',
        style=discord.TextStyle.long,
        placeholder='Normal Discord markdown works, but mentions and custom emojis require full code.',
        required=True,
        max_length=4000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        print("Message submitted")
        print(self.message.value)
        self.mission_params.cco_message_text = self.message.value
        """
        While self.message returns the inputted text if printed, it is actually a class holding
        all the attributes of the TextInput. View shows only the text the user inputted.

        This is important because it is a weak instance and cannot be pickled with mission_params,
        and we only want the value pickled anyway
        """
        print(self.mission_params.cco_message_text)
        message_embed = discord.Embed(
            title="Message added",
            description=self.mission_params.cco_message_text,
            color=constants.EMBED_COLOUR_RP
        )

        embeds = []
        embeds.extend(self.mission_params.original_message_embeds)
        embeds.append(message_embed)

        try:
            await interaction.response.edit_message(embeds=embeds, view=self.view)

        except Exception as e:
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
            description=f"❌ **ERROR**: Profit must be a number (int or float), e.g. `10` or `4.5` but not `ten` or `lots` or `{mission_params.profit_raw}`.",
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
            description=f"❌ **ERROR**: Pads must be `L` or `M`, or use autocomplete to select `Large` or `Medium`. `{mission_params.pads}` is right out.",
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
            description=f"❌ **ERROR**: Supply/demand must be a number (int or float), e.g. `20` or `16.5` but not `twenty thousand` or `loads` or `{mission_params.demand_raw}`.",
            color=constants.EMBED_COLOUR_ERROR
        )
        profit_error_embed.set_footer(text="You adorable scamp.")
        mission_params.returnflag = False
        print(f"Set returnflag {mission_params.returnflag}")
        return await interaction.channel.send(embed=profit_error_embed)
    elif float(mission_params.demand) > 25:
        profit_error_embed = discord.Embed(
            description=f"❌ **ERROR**: Supply/demand is expressed in thousands of tons (K), so cannot be higher than the maximum capacity of a Fleet Carrier (25K tons).",
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
            raise ValueError('Missing commodity data')


async def return_discord_alert_embed(interaction, mission_params):
    if mission_params.mission_type == 'load':
        embed = discord.Embed(description=mission_params.discord_text, color=constants.EMBED_COLOUR_LOADING)
    else:
        embed = discord.Embed(description=mission_params.discord_text, color=constants.EMBED_COLOUR_UNLOADING)
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar)
    return embed


async def return_discord_channel_embeds(mission_params):
    print("Called return_discord_channel_embeds")
    # generates embeds used for the PTN carrier channel as well as any webhooks

    # define owner avatar
    owner = await bot.fetch_user(mission_params.carrier_data.ownerid)
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

        sell_description=f"🎯 Fleet Carrier: **{mission_params.carrier_data.carrier_long_name}**" \
                         f"\n🔢 Carrier ID: **{mission_params.carrier_data.carrier_identifier}**" \
                         f"\n💰 Profit: **{mission_params.profit}K PER TON**" \
                         f"\n📥 Demand: **{mission_params.demand}K TONS**"
        
        sell_thumb = ptn_logo_discord()

        embed_colour = constants.EMBED_COLOUR_LOADING

    else: # embeds for an unloading mission
        buy_description=f"🎯 Fleet Carrier: **{mission_params.carrier_data.carrier_long_name}**" \
                        f"\n🔢 Carrier ID: **{mission_params.carrier_data.carrier_identifier}**" \
                        f"\n🌟 System: **{mission_params.system.upper()}**" \
                        f"\n📦 Commodity: **{mission_params.commodity_name.upper()}**"

        buy_thumb = ptn_logo_discord()

        sell_description=f"📌 Station: **{mission_params.station.upper()}**" \
                         f"\n🛬 Landing Pad: {pads}" \
                         f"\n💰 Profit: **{mission_params.profit}K PER TON**" \
                         f"\n📥 Demand: **{mission_params.demand}K TONS**"
        
        sell_thumb = constants.ICON_SELL

        embed_colour = constants.EMBED_COLOUR_UNLOADING

    print("Define sell embed")
    # desc used by the local PTN additional info embed
    additional_info_description = f"💎 Carrier Owner: <@{mission_params.carrier_data.ownerid}>" \
                                  f"\n🔤 Carrier information: </info:849040914948554766>" \
                                  f"\n📊 Stock information: `;stock {mission_params.carrier_data.carrier_short_name}`\n\n"

    print("Define help embed (local)")
    # desc used by the local PTN help embed
    edmc_off_text = ""
    if mission_params.edmc_off:
        edmc_off_text = "\n\n🤫 This mission is flagged **EDMC-OFF**. Please disable/quit **all journal reporting apps** such as EDMC, EDDiscovery, etc."
    help_description = "✅ Use </mission complete:849040914948554764> in this channel if the mission is completed, or unable to be completed (e.g. because of a station price change, or supply exhaustion)." \
                      f"\n\n💡 Need help? Here's our [complete guide to PTN trade missions](https://pilotstradenetwork.com/fleet-carrier-trade-missions/).{edmc_off_text}"

    print("Define descs")
    # desc used for sending cco_message_text
    owner_text_description = mission_params.cco_message_text

    # desc used by the webhook additional info embed    
    webhook_info_description = f"💎 Carrier Owner: <@{mission_params.carrier_data.ownerid}>" \
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


async def send_mission_to_discord(interaction, mission_params):
    print("User used option d, creating mission channel")

    mission_params.discord_img_name = await create_carrier_discord_mission_image(mission_params)
    if not mission_params.discord_text:
        discord_text = txt_create_discord(mission_params)
        mission_params.discord_text = discord_text
    print("Defined discord elements")

    # beyond this point we need to release channel lock if mission creation fails

    mission_params.mission_temp_channel_id = await create_mission_temp_channel(interaction, mission_params)
    mission_temp_channel = bot.get_channel(mission_params.mission_temp_channel_id)

    # Recreate this text since we know the channel id
    mission_params.discord_text = txt_create_discord(mission_params)
    message_send = await interaction.channel.send("**Sending to Discord...**")
    try:
        # send trade alert to trade alerts channel, or to wine alerts channel if loading wine
        if mission_params.commodity_name.title() == "Wine":
            if mission_params.mission_type == 'load':
                alerts_channel = bot.get_channel(mission_params.channel_defs.wine_loading_channel_actual)
            else:   # unloading block
                alerts_channel = bot.get_channel(mission_params.channel_defs.wine_unloading_channel_actual)
        else:
            alerts_channel = bot.get_channel(mission_params.channel_defs.alerts_channel_actual)

        embed = await return_discord_alert_embed(interaction, mission_params)

        trade_alert_msg = await alerts_channel.send(embed=embed)
        mission_params.discord_alert_id = trade_alert_msg.id

        if mission_params.edmc_off: # add in EDMC OFF header image
            edmc_off_banner_file = discord.File(constants.BANNER_EDMC_OFF, filename="image.png")
            await mission_temp_channel.send(file=edmc_off_banner_file)

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

            embed = discord.Embed(title=f"EDMC OFF messages sent for {mission_params.carrier_data.carrier_long_name}", description='External posts (Reddit, Webhooks) will be skipped.',
                        color=constants.EMBED_COLOUR_DISCORD)
            embed.set_thumbnail(url=constants.EMOJI_SHUSH)
            await interaction.channel.send(embed=embed)

            print('Reacting to #official-trade-alerts message with EDMC OFF')
            for r in ["🇪","🇩","🇲","🇨","📴"]:
                await trade_alert_msg.add_reaction(r)
        # --- end of EDMC-OFF section ---

        print("Feeding back to user...")
        embed = discord.Embed(
            title=f"Discord trade alerts sent for {mission_params.carrier_data.carrier_long_name}",
            description=f"Check <#{alerts_channel.id}> for trade alert and "
                        f"<#{mission_params.mission_temp_channel_id}> for carrier channel alert.",
            color=constants.EMBED_COLOUR_DISCORD)
        embed.set_thumbnail(url=constants.ICON_DISCORD_CIRCLE)
        await interaction.channel.send(embed=embed)
        await message_send.delete()

        submit_mission = True

        return submit_mission, mission_temp_channel

    except Exception as e:
        print(f"Error sending to Discord: {e}")
        await interaction.channel.send(f"Error sending to Discord: {e}\nAttempting to continue with mission gen...")


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
        reddit = await get_reddit()
        subreddit = await reddit.subreddit(mission_params.channel_defs.sub_reddit_actual)
        submission = await subreddit.submit_image(mission_params.reddit_title, image_path=mission_params.reddit_img_name,
                                                flair_id=mission_params.channel_defs.reddit_flair_in_progress)
        mission_params.reddit_post_url = submission.permalink
        mission_params.reddit_post_id = submission.id
        if mission_params.cco_message_text:
            comment = await submission.reply(f"> {mission_params.cco_message_text}\n\n&#x200B;\n\n{mission_params.reddit_body}")
        else:
            comment = await submission.reply(mission_params.reddit_body)
        mission_params.reddit_comment_url = comment.permalink
        mission_params.reddit_comment_id = comment.id
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
        reddit_error_embed = discord.Embed(
            description=f"❌ **ERROR**: Could not send to Reddit. {e}",
            color=constants.EMBED_COLOUR_ERROR
        )
        reddit_error_embed.set_footer(text="Attempting to continue with other sends.")
        await interaction.channel.send(embed=reddit_error_embed)


async def send_mission_to_webhook(interaction, mission_params):
    print("User used option w")

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
                        description=f"❌ **ERROR**: Could not send to Webhook {webhook_name}. {e}",
                        color=constants.EMBED_COLOUR_ERROR
                    )
                    inloop_webhook_error_embed.set_footer(text="Attempting to continue with other sends.")
                    await interaction.channel.send(embed=inloop_webhook_error_embed)

    except Exception as e:
        print(f"Error sending webhooks: {e}")
        webhook_error_embed = discord.Embed(
            description=f"❌ **ERROR**: Could not send to Webhooks. {e}",
            color=constants.EMBED_COLOUR_ERROR
        )
        webhook_error_embed.set_footer(text="Attempting to continue with other sends.")
        await interaction.channel.send(embed=webhook_error_embed)
    
    await message_send.delete()


async def notify_hauler_role(interaction, mission_params, mission_temp_channel):
    print("User used option n")

    if mission_params.commodity_name == 'Wine':
        embed = discord.Embed(
            description=f"Skipped hauler ping for Wine load."
        )
        embed.set_footer(text="As our glorious tipsy overlords, the Sommeliers, have decreed o7")
        embed.set_thumbnail(url=constants.ICON_FC_EMPTY)
        await interaction.channel.send(embed=embed)

    if mission_params.training:
        ping_role_id = trainee_role()
    else:
        ping_role_id = wineloader_role() if mission_params.commodity_name == 'Wine' else hauler_role()
    notify_msg = await mission_temp_channel.send(f"<@&{ping_role_id}>: {mission_params.discord_text}")
    mission_params.notify_msg_id = notify_msg.id

    embed = discord.Embed(
        title=f"Mission notification sent for {mission_params.carrier_data.carrier_long_name}",
        description=f"Pinged <@&{ping_role_id}> in <#{mission_params.mission_temp_channel_id}>.",
        color=constants.EMBED_COLOUR_DISCORD)
    embed.set_thumbnail(url=constants.ICON_DISCORD_PING)
    await interaction.channel.send(embed=embed)


async def send_mission_text_to_user(interaction, mission_params):
    print("User used option t")

    if not mission_params.reddit_title: await define_reddit_texts(mission_params)
    if not mission_params.discord_text:
        discord_text = txt_create_discord(mission_params)
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
async def confirm_send_mission_via_button(interaction: discord.Interaction, mission_params):
    # this function does initial checks and returns send options to the user

    mission_params.returnflag = True # set the returnflag to true, any errors will change it to false
    
    await prepare_for_gen_mission(interaction, mission_params)

    if mission_params.returnflag == False:
        print("Problems found, mission gen will not proceed.")
        return

    if mission_params.returnflag == True:
        print("All checks complete, mission generation can continue")

        # check the details with the user
        confirm_embed = discord.Embed(
            title=f"{mission_params.mission_type.upper()}ING: {mission_params.carrier_data.carrier_long_name}",
            description=f"Confirm mission details and choose send targets for {mission_params.carrier_data.carrier_long_name}.",
            color=constants.EMBED_COLOUR_QU
        )
        thumb_url = constants.ICON_FC_LOADING if mission_params.mission_type == 'load' else constants.ICON_FC_UNLOADING
        confirm_embed.set_thumbnail(url=thumb_url)

        confirm_embed = _mission_summary_embed(mission_params, confirm_embed)

        webhook_embed = None

        if mission_params.webhook_names:
            webhook_embed = discord.Embed(
                title=f"Webhooks found for {interaction.user.display_name}",
                description="- Webhooks are saved to your user ID and therefore shared between all your registered Fleet Carriers.\n" \
                            "- Clicking `📢 Send All` or choosing the `🌐 Webhooks` option from the Send Menu will send to *all* webhooks registered to your user.",
                color=constants.EMBED_COLOUR_DISCORD
            )
            for webhook_name in mission_params.webhook_names:
                webhook_embed.add_field(name="Webhook found", value=webhook_name)
            webhook_embed.set_thumbnail(url=constants.ICON_WEBHOOK_PTN)

        mission_params.sendflags = None # used to check for timeout status in View

        if webhook_embed: mission_params.original_message_embeds.append(webhook_embed)
        mission_params.original_message_embeds.append(confirm_embed)

        view = MissionSendView(mission_params, interaction.user) # buttons to add

        await interaction.edit_original_response(embeds=mission_params.original_message_embeds, view=view)

        # add the message attribute to the view so it can be retrieved by on_timeout
        view.message = await interaction.original_response()


async def prepare_for_gen_mission(interaction: discord.Interaction, mission_params):

    """
    - check validity of inputs
    - check if carrier data can be found
    - check if carrier is on a mission
    - return webhooks and commodity data
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
    carrier_data = find_carrier(mission_params.carrier_name_search_term, CarrierDbFields.longname.name)
    if not carrier_data:  # error condition
        carrier_error_embed = discord.Embed(
            description=f"❌ **ERROR**: No carrier found for '**{mission_params.carrier_name_search_term}**'. Use `/owner` to see a list of your carriers. If it's not in the list, ask an Admin to add it for you.",
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
            embed = discord.Embed(description="**ERROR**: You must have a valid mission image to continue.", color=constants.EMBED_COLOUR_ERROR)
            mission_params.returnflag = False
            return await interaction.channel.send(embed=embed) # error condition
    print(f"image check returnflag status: {mission_params.returnflag}")

    # define commodity
    await define_commodity(interaction, mission_params)
    print(f"define_commodity returnflag status: {mission_params.returnflag}")

    # add any webhooks to mission_params
    webhook_data = find_webhook_from_owner(interaction.user.id)
    if webhook_data:
        for webhook in webhook_data:
            mission_params.webhook_urls.append(webhook.webhook_url)
            mission_params.webhook_names.append(webhook.webhook_name)

    print(f"Returnflag status: {mission_params.returnflag}")

    return


# mission generator called by loading/unloading commands
async def gen_mission(interaction: discord.Interaction, mission_params):
    # generate a timestamp for mission creation
    mission_params.timestamp = get_formatted_date_string()[2]

    current_channel = interaction.channel

    mission_params.print_values()

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

            if "r" in mission_params.sendflags and not mission_params.edmc_off: # send to subreddit
                async with interaction.channel.typing():
                    await send_mission_to_subreddit(interaction, mission_params)

            if "w" in mission_params.sendflags and "d" in mission_params.sendflags and not mission_params.edmc_off: # send to webhook
                async with interaction.channel.typing():
                    await send_mission_to_webhook(interaction, mission_params)

            if "n" in mission_params.sendflags and "d" in mission_params.sendflags: # notify haulers with role ping
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
                description="❌ **ERROR**: Sending to Discord is **required**. Please try again.",
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
            description=f"❌ **ERROR**: {e}\n\n{text}",
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
            await remove_carrier_channel(mission_params.mission_temp_channel_id, seconds_short)


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
        return await interaction.channel.send("❌ **ERROR**: Channel lock could not be acquired, please try again. If the problem persists please contact an Admin.")

    await lockwait_msg.delete()

    mission_channel_name = mission_params.carrier_data.discord_channel

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
    carrier_db.execute(''' UPDATE carriers SET lasttrade=strftime('%s','now') WHERE p_ID=? ''', ( [ mission_params.carrier_data.pid ] ))
    carriers_conn.commit()

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