"""
Commands for use by CCOs 

"""
# import libraries
import aiohttp
from typing import Union

# import discord.py
import discord
from discord import app_commands, Webhook
from discord.app_commands import Group, command, describe
from discord.ext import commands
from discord.ext.commands import GroupCog

# import local classes
from ptn.missionalertbot.classes.MissionParams import MissionParams

# import local constants
import ptn.missionalertbot.constants as constants
from ptn.missionalertbot.constants import bot, mission_command_channel, certcarrier_role, trainee_role, seconds_long, rescarrier_role, commodities_common, bot_spam_channel, \
    training_mission_command_channel

# import local modules
from ptn.missionalertbot.database.database import find_mission, find_webhook_from_owner, add_webhook_to_database, find_webhook_by_name, delete_webhook_by_name, CarrierDbFields, find_carrier
from ptn.missionalertbot.modules.helpers import on_app_command_error, convert_str_to_float_or_int, check_command_channel, check_roles, check_training_mode
from ptn.missionalertbot.modules.ImageHandling import assign_carrier_image
from ptn.missionalertbot.modules.MissionGenerator import confirm_send_mission_via_button
from ptn.missionalertbot.modules.MissionCleaner import _cleanup_completed_mission
from ptn.missionalertbot.modules.MissionEditor import edit_active_mission


"""
CERTIFIED CARRIER OWNER COMMANDS

/cco complete - CCO/mission
/cco done - alias of cco_complete
/cco image - CCO
/cco load - CCO/mission
/cco unload - CCO/mission
/cco webhook add - CCO/database
/cco webhook delete - CCO/database
/cco webhook view - CCO/database

"""


async def cco_mission_complete(interaction, carrier, is_complete, message):
    current_channel = interaction.channel

    status = "complete" if is_complete else "concluded"

    print(f'Request received from {interaction.user.display_name} to mark the mission of {carrier} as done from channel: '
        f'{current_channel}')

    mission_data = find_mission(carrier, "carrier")
    if not mission_data:
        embed = discord.Embed(
            description=f"**ERROR**: no trade missions found for carriers matching \"**{carrier}\"**.",
            color=constants.EMBED_COLOUR_ERROR)
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    else:
        embed = discord.Embed(
            description=f"Closing mission for **{mission_data.carrier_name}**...",
            color=constants.EMBED_COLOUR_QU
        )
        await interaction.response.send_message(embed=embed)

    # fill in some info for messages
    if not message == None:
        discord_msg = f"<@{interaction.user.id}>: {message}"
        reddit_msg = message
    else:
        discord_msg = ""
        reddit_msg = ""
    reddit_complete_text = f"    INCOMING WIDEBAND TRANSMISSION: P.T.N. CARRIER MISSION UPDATE\n\n**{mission_data.carrier_name}** mission {status}. o7 CMDRs!\n\n{reddit_msg}"
    discord_complete_embed = discord.Embed(title=f"{mission_data.carrier_name} MISSION {status.upper()}", description=f"{discord_msg}",
                            color=constants.EMBED_COLOUR_OK)
    discord_complete_embed.set_footer(text=f"This mission channel will be removed in {seconds_long()//60} minutes.")

    await _cleanup_completed_mission(interaction, mission_data, reddit_complete_text, discord_complete_embed, message, is_complete)

    return


# initialise the Cog and attach our global error handler
class CCOCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # custom global error handler
    # attaching the handler when the cog is loaded
    # and storing the old handler
    # this is required for option 1
    def cog_load(self):
        tree = self.bot.tree
        self._old_tree_error = tree.on_error
        tree.on_error = on_app_command_error

    # detaching the handler when the cog is unloaded
    def cog_unload(self):
        tree = self.bot.tree
        tree.on_error = self._old_tree_error


    """
    Load/unload commands
    """

    cco_group = Group(name='cco', description='CCO commands')

    webhook_group = Group(parent=cco_group, name='webhook', description='CCO webhook management')

    # load subcommand
    @cco_group.command(name='load', description='Generate a Fleet Carrier loading mission.')
    @describe(
        carrier = "A unique fragment of the carrier name you want to search for.",
        commodity = "The commodity you want to load.",
        system = "The system your mission takes place in.",
        station = "The station the Fleet Carrier is loading from.",
        profit = 'The profit offered in thousands of credits, e.g. for 10k credits per ton enter \'10\'',
        pads = 'The size of the largest landing pad available at the station.',
        demand = 'The total demand for the commodity on the Fleet Carrier.'
        )
    @check_roles([certcarrier_role(), trainee_role(), rescarrier_role()])
    @check_command_channel([mission_command_channel(), training_mission_command_channel()])
    async def load(self, interaction: discord.Interaction, carrier: str, commodity: str, system: str, station: str,
                profit: str, pads: str, demand: str):
        mission_type = 'load'

        training, channel_defs = check_training_mode(interaction)

        cp_embed = discord.Embed(
            title="COPY/PASTE TEXT FOR THIS COMMAND",
            description=f"```/cco load carrier:{carrier} commodity:{commodity} system:{system} station:{station}"
                        f" profit:{profit} pads:{pads} demand:{demand}```",
            color=constants.EMBED_COLOUR_QU
        )

        if training:
            cp_embed.set_footer(text="TRAINING MODE ACTIVE: ALL SENDS WILL GO TO TRAINING CHANNELS")

        await interaction.response.send_message(embed=cp_embed)

        # convert profit from STR to an INT or FLOAT
        profit_convert = convert_str_to_float_or_int(profit)

        demand_convert = convert_str_to_float_or_int(demand)

        params_dict = dict(carrier_name_search_term = carrier, commodity_search_term = commodity, system = system, station = station, profit_raw = profit,
                           profit = profit_convert, pads = pads, demand_raw = demand, demand = demand_convert, mission_type = mission_type, copypaste_embed = cp_embed, channel_defs = channel_defs, training = training)

        mission_params = MissionParams(params_dict)

        mission_params.original_message_embeds = [cp_embed]

        mission_params.print_values()

        await confirm_send_mission_via_button(interaction, mission_params)


    # unload subcommand
    @cco_group.command(name='unload', description='Generate a Fleet Carrier unloading mission.')
    @describe(
        carrier = "A unique fragment of the Fleet Carrier name you want to search for.",
        commodity = "The commodity you want to unload.",
        system = "The system your mission takes place in.",
        station = "The station the Fleet Carrier is unloading to.",
        profit = 'The profit offered in thousands of credits, e.g. for 10k credits per ton enter \'10\'',
        pads = 'The size of the largest landing pad available at the station.',
        supply = 'The total amount of the commodity available to buy on the Fleet Carrier.'
        )
    @check_roles([certcarrier_role(), trainee_role(), rescarrier_role()])
    @check_command_channel([mission_command_channel(), training_mission_command_channel()])
    async def unload(self, interaction: discord.Interaction, carrier: str, commodity: str, system: str, station: str,
                profit: str, pads: str, supply: str):
        mission_type = 'unload'

        training, channel_defs = check_training_mode(interaction)

        cp_embed = discord.Embed(
            title="COPY/PASTE TEXT FOR THIS COMMAND",
            description=f"```/cco unload carrier:{carrier} commodity:{commodity} system:{system} station:{station}"
                        f" profit:{profit} pads:{pads} supply:{supply}```",
            color=constants.EMBED_COLOUR_QU
        )

        if training:
            cp_embed.set_footer(text="TRAINING MODE ACTIVE: ALL SENDS WILL GO TO TRAINING CHANNELS")

        await interaction.response.send_message(embed=cp_embed)

        # convert profit from STR to an INT or FLOAT
        profit_convert = convert_str_to_float_or_int(profit)

        supply_convert = convert_str_to_float_or_int(supply)

        params_dict = dict(carrier_name_search_term = carrier, commodity_search_term = commodity, system = system, station = station, profit_raw = profit,
                           profit = profit_convert, pads = pads, demand_raw = supply, demand = supply_convert, mission_type = mission_type, copypaste_embed = cp_embed, channel_defs = channel_defs, training = training)

        mission_params = MissionParams(params_dict)

        mission_params.original_message_embeds = [cp_embed]

        mission_params.print_values()

        await confirm_send_mission_via_button(interaction, mission_params)


    @cco_group.command(name='edit', description='Enter the details you wish to change for a mission in progress.')
    @describe(
        carrier = "A unique fragment of the Fleet Carrier name you want to search for.",
        commodity = "The commodity you want to unload.",
        system = "The system your mission takes place in.",
        station = "The station the Fleet Carrier is unloading to.",
        profit = 'The profit offered in thousands of credits, e.g. for 10k credits per ton enter \'10\'',
        pads = 'The size of the largest landing pad available at the station.',
        supply_or_demand = 'The total amount of the commodity required.'
        )
    @check_roles([certcarrier_role(), trainee_role(), rescarrier_role()])
    @check_command_channel([mission_command_channel(), training_mission_command_channel()])
    async def edit(self, interaction: discord.Interaction, carrier: str, commodity: str = None, system: str = None, station: str = None,
                profit: str = None, pads: str = None, supply_or_demand: str = None):
        print(f"/cco edit called by {interaction.user.display_name}")
        async with interaction.channel.typing():

            if pads:
                pads = pads.upper()

            # find the target carrier
            print("Looking for carrier data")
            carrier_data = find_carrier(carrier, CarrierDbFields.longname.name)
            if not carrier_data:
                embed = discord.Embed(
                    description=f"Error: no carrier found matching {carrier}.",
                    color=constants.EMBED_COLOUR_ERROR
                )
                return await interaction.response.send_message(embed=embed)

            # find mission data for carrier
            mission_data = find_mission(carrier_data.carrier_long_name, 'Carrier')
            if not mission_data:
                embed = discord.Embed(
                    description=f"Error: no active mission found for {carrier_data.carrier_long_name} ({carrier_data.carrier_identifier}).",
                    color=constants.EMBED_COLOUR_ERROR
                )
                return await interaction.response.send_message(embed=embed)

            # define the original mission_params
            mission_params = mission_data.mission_params

            original_commodity = mission_params.commodity_name

            print("defined original mission parameters")
            mission_params.print_values()

            # convert profit from STR to an INT or FLOAT
            print("Processing profit")
            if not profit == None:
                profit_convert = convert_str_to_float_or_int(profit)
            else:
                profit_convert = None

            def update_params(mission_params, **kwargs): # a function to update any values that aren't None
                for attr, value in kwargs.items():
                    if value is not None:
                        mission_params.__dict__[attr] = value

            # define the new mission_params
            update_params(mission_params, carrier_name_search_term = carrier, commodity_search_term = commodity, system = system, station = station,
                        profit_raw = profit, profit = profit_convert, pads = pads, demand = supply_or_demand)

            print("Defined new_mission_params:")
            mission_params.print_values()

        await edit_active_mission(interaction, mission_params, original_commodity)

        """
        1. perform checks on profit, pads, commodity
        2. edit original sends with new info

        """
        pass

    # autocomplete common commodities
    @load.autocomplete("commodity")
    @unload.autocomplete("commodity")
    @edit.autocomplete("commodity")
    async def commodity_autocomplete(self, interaction: discord.Interaction, current: str):
        commodities = [] # define the list we will return
        for commodity in commodities_common: # iterate through our common commodities to append them as Choice options to our return list
            commodities.append(app_commands.Choice(name=commodity, value=commodity))
        return commodities # return the list of Choices
    
    # autocomplete pads
    @load.autocomplete("pads")
    @unload.autocomplete("pads")
    @edit.autocomplete("pads")
    async def commodity_autocomplete(self, interaction: discord.Interaction, current: str):
        pads = []
        pads.append(app_commands.Choice(name="Large", value="L"))
        pads.append(app_commands.Choice(name="Medium", value="M"))
        return pads
    

    """
    CCO mission complete command
    """
    # alias for cco complete
    @cco_group.command(name='done', description='Alias for /cco complete.')
    @describe(message='A message to send to the mission channel and carrier\'s owner')
    @check_roles([certcarrier_role(), trainee_role(), rescarrier_role()])
    @check_command_channel([mission_command_channel(), training_mission_command_channel()])
    async def done(self, interaction: discord.Interaction, carrier: str, *, status: str = "Complete", message: str = None):
        is_complete = True if not status == "Failed" else False
        await cco_mission_complete(interaction, carrier, is_complete, message)

    # CCO command to quickly mark mission as complete, optionally send a reason
    @cco_group.command(name='complete', description='Marks a mission as complete for specified carrier.')
    @describe(message='A message to send to the mission channel and carrier\'s owner')
    @check_roles([certcarrier_role(), trainee_role(), rescarrier_role()])
    @check_command_channel([mission_command_channel(), training_mission_command_channel()])
    async def complete(self, interaction: discord.Interaction, carrier: str, *, status: str = "Complete", message: str = None):
        is_complete = True if not status == "Failed" else False
        await cco_mission_complete(interaction, carrier, is_complete, message)


    # autocomplete mission status
    @done.autocomplete("status")
    @complete.autocomplete("status")
    async def cco_complete_autocomplete(self, interaction: discord.Interaction, current: str):
        is_complete = []
        is_complete.append(app_commands.Choice(name="Complete", value="Complete"))
        is_complete.append(app_commands.Choice(name="Failed", value="Failed"))
        return is_complete


    """
    Change FC image command
    """


    # change FC background image
    @cco_group.command(name='image', description='View, set, or change a carrier\'s background image.')
    @describe(carrier='A unique fragment of the full name of the target Fleet Carrier')
    @check_roles([certcarrier_role(), trainee_role(), rescarrier_role()])
    @check_command_channel([mission_command_channel(), training_mission_command_channel()])
    async def image(self, interaction: discord.Interaction, carrier: str):
        print(f"{interaction.user.display_name} called m.carrier_image for {carrier}")


        embed = discord.Embed(
            description="Searching for Fleet Carrier and image...",
            color=constants.EMBED_COLOUR_QU
        )

        embeds = []

        await interaction.response.send_message(embed=embed)

        await assign_carrier_image(interaction, carrier, embeds)

        return

    """
    Webhook management
    """

    # CCO command to add a webhook to their carriers
    @webhook_group.command(name="add", description="Add a webhook to your library for sending mission alerts.")
    @describe(webhook_url='The URL of your webhook.',
              webhook_name='A short (preferably one-word) descriptor you can use to identify your webhook.')
    @check_roles([certcarrier_role(), trainee_role()])
    @check_command_channel([mission_command_channel(), training_mission_command_channel()])
    async def webhook_add(self, interaction: discord.Interaction, webhook_url: str, webhook_name: str):
        print(f"Called webhook add for {interaction.user.display_name}")

        spamchannel = bot.get_channel(bot_spam_channel())

        embed = discord.Embed (
            description="Validating...",
            color=constants.EMBED_COLOUR_QU
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # first check the webhook URL and name aren't in the DB already
        print("Looking up existing webhook data...")
        webhook_data = find_webhook_from_owner(interaction.user.id)
        if webhook_data:
            for webhook in webhook_data:
                if webhook.webhook_url == webhook_url:
                    print("Found duplicate webhook for URL")
                    embed = discord.Embed(
                        description=f"ERROR: You already have a webhook with that URL called \"{webhook.webhook_name}\": {webhook.webhook_url}",
                        color=constants.EMBED_COLOUR_ERROR
                    )
                    await interaction.edit_original_response(embed=embed)
                    return

                elif webhook.webhook_name == webhook_name:
                    print("Found duplicate webhook for name")
                    embed = discord.Embed(
                        description=f"ERROR: You already have a webhook called \"{webhook.webhook_name}\": {webhook.webhook_url}",
                        color=constants.EMBED_COLOUR_ERROR
                    )
                    await interaction.edit_original_response(embed=embed)
                    return
                
                else:
                    print("Webhook is not duplicate, proceeding")

        # check the webhook is valid
        try:
            async with aiohttp.ClientSession() as session:
                webhook = Webhook.from_url(webhook_url, session=session, client=bot)

                embed = discord.Embed(
                    description="Verifying webhook...",
                    color=constants.EMBED_COLOUR_QU
                )

                webhook_sent = await webhook.send(embed=embed, username='Pilots Trade Network', avatar_url=bot.user.avatar.url, wait=True)

                webhook_msg = await webhook.fetch_message(webhook_sent.id)

                await webhook_msg.delete()

        except Exception as e: # webhook could not be sent
            embed = discord.Embed(
                description=f"ERROR: {e}",
                color=constants.EMBED_COLOUR_ERROR
            )
            embed.set_footer(text="Webhook could not be validated: unable to send message to webhook.")
            # this is a fail condition, so we exit out
            print(f"Webhook validation failed for {interaction.user.display_name}: {e}")
            spamchannel_embed = discord.Embed(
                description=f"<@{interaction.user.id}> failed adding webhook: {e}"
            )
            await spamchannel.send(embed=spamchannel_embed)
            return await interaction.edit_original_response(embed=embed)

        # enter the webhook into the database
        try:
            await add_webhook_to_database(interaction.user.id, webhook_url, webhook_name)
        except Exception as e:
            embed = discord.Embed(
                description=f"ERROR: {e}",
                color=constants.EMBED_COLOUR_ERROR
            )
            await interaction.edit_original_response(embed=embed)

            # notify in bot_spam
            embed = discord.Embed(
                description=f"Error on /webhook_add by {interaction.user}: {e}",
                color=constants.EMBED_COLOUR_ERROR
            )
            await spamchannel.send(embed=embed)
            return print(f"Error on /webhook_add by {interaction.user}: {e}")

        # notify user of success
        embed = discord.Embed(title="WEBHOOK ADDED",
                              description="Remember, webhooks can be used by *anyone* to post *anything* and therefore **MUST** be kept secret from other users.",
                              color=constants.EMBED_COLOUR_OK)
        embed.add_field(name="Identifier", value=webhook_name, inline=False)
        embed.add_field(name="URL", value=webhook_url)
        embed.set_thumbnail(url=interaction.user.display_avatar)
        await interaction.edit_original_response(embed=embed)

        # also tell bot-spam
        embed = discord.Embed(
            description=f"<@{interaction.user.id}> added a webhook.",
            color=constants.EMBED_COLOUR_QU
        )
        await spamchannel.send(embed=embed)
        return print("/webhook_add complete")
    

    # command for a CCO to view all their webhooks
    @webhook_group.command(name='view', description='Shows details of all your registered webhooks.')
    @check_roles([certcarrier_role(), trainee_role()])
    @check_command_channel([mission_command_channel(), training_mission_command_channel()])
    async def webhooks_view(self, interaction: discord.Interaction):
        print(f"webhook view called by {interaction.user.display_name}")

        webhook_data = find_webhook_from_owner(interaction.user.id)
        if not webhook_data: # no webhooks to show
            embed = discord.Embed(
                description=f"No webhooks found. You can add webhooks using `/cco webhook add`",
                color=constants.EMBED_COLOUR_ERROR
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        embed = discord.Embed(
            description=f"Showing webhooks for <@{interaction.user.id}>"
                         "\nRemember, webhooks can be used by *anyone* to post *anything* and therefore **MUST** be kept secret from other users.",
            color=constants.EMBED_COLOUR_OK
        )
        embed.set_thumbnail(url=interaction.user.display_avatar)

        for webhook in webhook_data:
            embed.add_field(name=webhook.webhook_name, value=webhook.webhook_url, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


    # command for a CCO to delete a webhook
    @webhook_group.command(name="delete", description="Remove one of your webhooks from MAB's database.")
    @describe(webhook_name='The name (identifier) of the webhook you wish to remove.')
    @check_roles([certcarrier_role(), trainee_role()])
    @check_command_channel([mission_command_channel(), training_mission_command_channel()])
    async def webhook_delete(self, interaction: discord.Interaction, webhook_name: str):

        print(f"{interaction.user.display_name} called webhook delete for {webhook_name}")

        # find the webhook
        webhook_data = find_webhook_by_name(interaction.user.id, webhook_name)

        if webhook_data:
            try:
                await delete_webhook_by_name(interaction.user.id, webhook_name)
                embed = discord.Embed(
                    description=f"Webhook removed: **{webhook_data.webhook_name}**\n{webhook_data.webhook_url}",
                    color=constants.EMBED_COLOUR_OK
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception as e:
                embed = discord.Embed(
                    description=f"ERROR: {e}",
                    color=constants.EMBED_COLOUR_ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

        else: # no webhook data found
            embed = discord.Embed(
                description=f"No webhook found matching {webhook_data.webhook_name}",
                color=constants.EMBED_COLOUR_ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        return