"""
Commands for use by CCOs 

"""
# import libraries
import aiohttp
import traceback
from time import strftime
from typing import Union

# import discord.py
import discord
from discord import app_commands, Webhook, Forbidden
from discord.app_commands import Group, command, describe
from discord.ext import commands
from discord.ext.commands import GroupCog

# import local constants
import ptn.missionalertbot.constants as constants
from ptn.missionalertbot.constants import bot, mission_command_channel, certcarrier_role, trainee_role, seconds_long, rescarrier_role, commodities_common, \
    bot_spam_channel, training_mission_command_channel, seconds_very_short, admin_role, mod_role, cco_mentor_role, aco_role, recruit_role, cco_color_role, \
    API_HOST, ptn_logo_discord, locations_wmm, bot_command_channel

# import local classes
from ptn.missionalertbot.classes.MissionParams import MissionParams
from ptn.missionalertbot.classes.Views import ConfirmRemoveRoleView, ConfirmGrantRoleView
from ptn.missionalertbot.classes.WMMData import WMMData

# import local modules
from ptn.missionalertbot.database.database import find_mission, find_webhook_from_owner, add_webhook_to_database, find_webhook_by_name, delete_webhook_by_name, \
    CarrierDbFields, find_carrier, _update_carrier_last_trade, add_carrier_to_database, _update_carrier_capi, _add_to_wmm_db, find_wmm_carrier, _remove_from_wmm_db, \
    _update_wmm_carrier
from ptn.missionalertbot.modules.DateString import get_mission_delete_hammertime, get_inactive_hammertime
from ptn.missionalertbot.modules.Embeds import role_granted_embed, confirm_remove_role_embed, role_already_embed, confirm_grant_role_embed, please_wait_embed
from ptn.missionalertbot.modules.ErrorHandler import on_app_command_error, on_generic_error, GenericError, CustomError
from ptn.missionalertbot.modules.helpers import convert_str_to_float_or_int, check_command_channel, check_roles, check_training_mode, flexible_carrier_search_term
from ptn.missionalertbot.modules.ImageHandling import assign_carrier_image
from ptn.missionalertbot.modules.MissionGenerator import confirm_send_mission_via_button
from ptn.missionalertbot.modules.MissionCleaner import _cleanup_completed_mission
from ptn.missionalertbot.modules.MissionEditor import edit_active_mission
from ptn.missionalertbot.modules.StockHelpers import capi, oauth_new
from ptn.missionalertbot.modules.BackgroundTasks import wmm_stock, start_wmm_task


"""
CERTIFIED CARRIER OWNER COMMANDS

/cco complete - CCO/mission
/cco done - alias of cco_complete
/cco image - CCO
/cco load - CCO/mission
/cco unload - CCO/mission
/cco edit - CCO/mission
/cco webhook add - CCO/database
/cco webhook delete - CCO/database
/cco webhook view - CCO/database

"""

@bot.tree.context_menu(name='Make CCO Trainee')
@check_roles([cco_mentor_role(), admin_role(), mod_role()])
async def toggle_cco_trainee(interaction:  discord.Interaction, member: discord.Member):
    print(f"toggle_cco_trainee called by {interaction.user.display_name} for {member.display_name}")

    embed = discord.Embed(
        description=f"⏳ Toggling <@&{trainee_role()}> role for <@{member.id}>...",
        color=constants.EMBED_COLOUR_QU
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

    spamchannel = bot.get_channel(bot_spam_channel())

    member_roles = member.roles
    cco_trainee_role_object = discord.utils.get(interaction.guild.roles, id=trainee_role())
    role = True if cco_trainee_role_object in member_roles else False

    if not role: # check whether they have the role already
        print("Member does not already have role, granting...")

        try:
            print(f"Giving {cco_trainee_role_object.name} role to {member.name}")
            await member.add_roles(cco_trainee_role_object)
         
            # feed back to the command user
            embed, bot_spam_embed = role_granted_embed(interaction, member, None, cco_trainee_role_object)
            await interaction.edit_original_response(embed=embed)
            await spamchannel.send(embed=bot_spam_embed)

        except Exception as e:
            try:
                raise GenericError(e)
            except Exception as e:
                await on_generic_error(interaction, e)

    else:
        print("Member has role already, asking if user wants to remove...")
        view = ConfirmRemoveRoleView(member, cco_trainee_role_object)

        embed = confirm_remove_role_embed(member, cco_trainee_role_object)

        await interaction.edit_original_response(embed=embed, view=view)
        view.message = await interaction.original_response()


@bot.tree.context_menu(name='Make Full CCO')
@check_roles([cco_mentor_role(), admin_role(), mod_role()])
async def toggle_cco(interaction:  discord.Interaction, member: discord.Member):
    print(f"toggle_cco called by {interaction.user.display_name} for {member.display_name}")

    embed = discord.Embed(
        description=f"⏳ Preparing to make <@{member.id}> a <@&{certcarrier_role()}>...",
        color=constants.EMBED_COLOUR_QU
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

    member_roles = member.roles
    cco_role = discord.utils.get(interaction.guild.roles, id=certcarrier_role())
    color_cco_role = discord.utils.get(interaction.guild.roles, id=cco_color_role())
    reserve_role = discord.utils.get(interaction.guild.roles, id=rescarrier_role())
    aco_role_object = discord.utils.get(interaction.guild.roles, id=aco_role())
    trainee_role_object = discord.utils.get(interaction.guild.roles, id=trainee_role())
    recruit_role_object = discord.utils.get(interaction.guild.roles, id=recruit_role())
    role = True if cco_role in member_roles else False # only checking for CCO role

    if not role: # check whether they have the role already
        print("Member does not already have role, checking user is sure about granting...")

        try:
            roles = [cco_role, reserve_role, color_cco_role]
            remove_roles = [aco_role_object, trainee_role_object, recruit_role_object]
            view = ConfirmGrantRoleView(member, roles, remove_roles)

            embed = confirm_grant_role_embed(member, cco_role)

            await interaction.edit_original_response(embed=embed, view=view)
            view.message = await interaction.original_response()

        except Exception as e:
            print(e)
            try:
                raise GenericError(e)
            except Exception as e:
                await on_generic_error(interaction, e)

    else:
        print("Member has role already")
        embed = role_already_embed(member, cco_role)
        whoops_embed = discord.Embed(
            description=f"😬 If they **shouldn't** have this role, please message a <@&{mod_role()}> or <@&{admin_role()}> immediately.",
            color=constants.EMBED_COLOUR_RP
        )
        embeds = [embed, whoops_embed]
        await interaction.edit_original_response(embeds=embeds)


async def cco_mission_complete(interaction, carrier, is_complete, message):
    current_channel = interaction.channel

    status = "complete" if is_complete else "concluded"

    print(f'Request received from {interaction.user.display_name} to mark the mission of {carrier} as done from channel: '
        f'{current_channel}')

    # resolve the carrier from the carriers db
    carrier_data = flexible_carrier_search_term(carrier)
    if not carrier_data:  # error condition
        try:
            error = f"No carrier found for '**{carrier}**.'"
            raise CustomError(error)
        except Exception as e:
            await on_generic_error(interaction, e)
            return

    try:
        mission_data = find_mission(carrier_data.carrier_long_name, "carrier")
        if not mission_data:
            try:
                raise CustomError(f"Search term `{carrier}` resolved to **{carrier_data.carrier_long_name}** but this carrier does not appear to have an active mission.")
            except Exception as e:
                return await on_generic_error(interaction, e)
    except Exception as e:
        try:
            raise GenericError(e)
        except Exception as e:
            return await on_generic_error(interaction, e)

    else:
        embed = discord.Embed(
            description=f"Closing mission for **{mission_data.carrier_name}**...",
            color=constants.EMBED_COLOUR_QU
        )
        await interaction.response.send_message(embed=embed)

    # fill in some info for messages
    hammertime = get_mission_delete_hammertime()
    if not message == None:
        discord_msg = f"<@{interaction.user.id}>: {message}"
        reddit_msg = message
    else:
        discord_msg = ""
        reddit_msg = ""
    reddit_complete_text = f"    INCOMING WIDEBAND TRANSMISSION: P.T.N. CARRIER MISSION UPDATE\n\n**{mission_data.carrier_name}** mission {status}. o7 CMDRs!\n\n{reddit_msg}"
    discord_complete_embed = discord.Embed(
        title=f"{mission_data.carrier_name} MISSION {status.upper()}",
        description=f"{discord_msg}\n\nThis mission channel will be removed {hammertime} unless a new mission is started.",
        color=constants.EMBED_COLOUR_OK
    )

    await _cleanup_completed_mission(interaction, mission_data, reddit_complete_text, discord_complete_embed, message, is_complete)

    return


# initialise the Cog and attach our global error handler
class CCOCommands(commands.Cog):
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


    """
    Load/unload commands
    """

    cco_group = Group(name='cco', description='CCO commands')

    webhook_group = Group(parent=cco_group, name='webhook', description='CCO webhook management')

    capi_group = Group(parent=cco_group, name='capi', description='CCO Frontier API commands')

    wmm_group = Group(parent=cco_group, name='wmm', description='CCO WMM commands')

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
    async def load(
        self,
        interaction: discord.Interaction,
        carrier: str,
        commodity: str,
        system: str,
        station: str,
        profit: str,
        pads: str,
        demand: str
    ):
        mission_type = 'load'

        pads = 'L' if 'l' in pads.lower() else 'M'

        training, channel_defs = check_training_mode(interaction)

        cp_embed = discord.Embed(
            title="📋 COPY/PASTE TEXT FOR THIS COMMAND",
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

        try:

            await confirm_send_mission_via_button(interaction, mission_params)

        except Exception as e:
            print(e)
            traceback.print_exc()


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
    async def unload(
        self,
        interaction: discord.Interaction,
        carrier: str,
        commodity: str,
        system: str,
        station: str,
        profit: str,
        pads: str,
        supply: str
    ):
        mission_type = 'unload'

        pads = 'L' if 'l' in pads.lower() else 'M'

        training, channel_defs = check_training_mode(interaction)

        cp_embed = discord.Embed(
            title="📋 COPY/PASTE TEXT FOR THIS COMMAND",
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

        try:

            await confirm_send_mission_via_button(interaction, mission_params)

        except Exception as e:
            print(e)
            traceback.print_exc()


    @cco_group.command(name='edit', description='Enter the details you wish to change for a mission in progress.')
    @describe(
        carrier = "A unique fragment of the Fleet Carrier name you want to search for.",
        commodity = "The commodity you want to unload.",
        system = "The system your mission takes place in.",
        station = "The station the Fleet Carrier is unloading to.",
        profit = 'The profit offered in thousands of credits, e.g. for 10k credits per ton enter \'10\'',
        pads = 'The size of the largest landing pad available at the station.',
        supply_or_demand = 'The total amount of the commodity required.',
        mission_type='Whether the mission is Loading or Unloading.'
        )
    @check_roles([certcarrier_role(), trainee_role(), rescarrier_role()])
    @check_command_channel([mission_command_channel(), training_mission_command_channel()])
    @app_commands.choices(mission_type=[
        discord.app_commands.Choice(name='Loading', value='load'),
        discord.app_commands.Choice(name='Unloading', value='unload')
    ])
    async def edit(self, interaction: discord.Interaction, carrier: str, commodity: str = None, system: str = None, station: str = None,
                profit: str = None, pads: str = None, supply_or_demand: str = None, mission_type: str = None ):
        print(f"/cco edit called by {interaction.user.display_name}")
        async with interaction.channel.typing():

            if pads:
                pads = 'L' if 'l' in pads.lower() else 'M'

            # find the target carrier
            print("Looking for carrier data")
            try:
                carrier_data = flexible_carrier_search_term(carrier)
                if not carrier_data:
                    raise CustomError(f"No carrier found matching {carrier}.")
            except CustomError as e:
                return await on_generic_error(interaction, e)

            # find mission data for carrier
            try:
                mission_data = find_mission(carrier_data.carrier_long_name, 'Carrier')
                if not mission_data:
                    raise CustomError(f"No active mission found for {carrier_data.carrier_long_name} ({carrier_data.carrier_identifier}).")
            except CustomError as e:
                return await on_generic_error(interaction, e)

            # define the original mission_params
            mission_params = mission_data.mission_params

            original_commodity = mission_params.commodity_name
            original_type = mission_params.mission_type

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
                        profit_raw = profit, profit = profit_convert, pads = pads, demand = supply_or_demand, mission_type = mission_type)

            print("Defined new_mission_params:")
            mission_params.print_values()

        await edit_active_mission(interaction, mission_params, original_commodity, original_type)

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
        print(f"{interaction.user.display_name} called /cco image for {carrier}")


        embed = discord.Embed(
            description="Searching for Fleet Carrier and image...",
            color=constants.EMBED_COLOUR_QU
        )

        embeds = []

        await interaction.response.send_message(embed=embed)

        await assign_carrier_image(interaction, carrier, embeds)

        return


    # set active status
    @cco_group.command(name='active', description='Toggle active CCO status; becoming active grants the CCO role for at least 28 days.')
    @check_roles([certcarrier_role(), rescarrier_role()])
    async def cco_active(self, interaction: discord.Interaction):
        print(f"{interaction.user} called /cco active")

        try:

            embed: discord.Embed = please_wait_embed()
            await interaction.response.send_message(embed=embed, ephemeral=True)

            # check if they have the CCO role
            print("⏳ Checking for CCO role...")
            cco_role = discord.utils.get(interaction.guild.roles, id=certcarrier_role())
            color_cco_role = discord.utils.get(interaction.guild.roles, id=cco_color_role())
            if cco_role in interaction.user.roles:
                print("▶ CCO role found. Transitioning user to inactive status.")
                # check they have the Fleet Reserve role
                reserve_role = discord.utils.get(interaction.guild.roles, id=rescarrier_role())
                if reserve_role not in interaction.user.roles:
                    print("⏳ No reserve role found. Adding...")
                    # grant the reserve role
                    await interaction.user.add_roles(reserve_role)
                # remove the CCO role
                print("▶ Removing CCO role")
                await interaction.user.remove_roles(cco_role)

                # check for color role
                if color_cco_role in interaction.user.roles:
                    print("▶ Removing color role")
                    await interaction.user.remove_roles(color_cco_role)
                embed.description = f'💤 **Removed your <@&{cco_role.id}>** role. You are now marked inactive in the <@&{reserve_role.id}>.'
                embed.set_footer(text='You can return to active status at any time by using this command again.')
                embed.color = constants.EMBED_COLOUR_OK

            else:
                print("▶ No CCO role found. Transitioning user to active status.")
                await interaction.user.add_roles(cco_role)
                await interaction.user.add_roles(color_cco_role)
                print("✅ Granted CCO role.")

                # check if user has an opt-in entry yet
                carrier_data = find_carrier(interaction.user.id, CarrierDbFields.shortname.name)
                if carrier_data:
                    print(f"Found opt-in database entry for {interaction.user}, updating lasttrade...")
                    await _update_carrier_last_trade(carrier_data.pid)
                else:
                    print("No opt-in entry found, creating now.")
                    await add_carrier_to_database(interaction.user.id, interaction.user.name, constants.OPT_IN_ID, interaction.user.name + '-opt-in-marker', 0, interaction.user.id)

                embed.description = f'⚡ **Gave you the <@&{cco_role.id}>** role. You will remain active until at least {get_inactive_hammertime()}. If you run any trade missions with' \
                            f' <@{bot.user.id}> during this period, your 28-day timer will reset from the time of each trade mission. '
                embed.set_footer(text='You can return to inactive status at any time by using this command again.')
                embed.color = constants.EMBED_COLOUR_OK

            await interaction.edit_original_response(embed=embed)

        except Exception as e:
            try:
                raise GenericError(e)
            except Exception as e:
                await on_generic_error(interaction, e)


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
                try:
                    if webhook.webhook_url == webhook_url:
                        print("Found duplicate webhook for URL")
                        raise CustomError(f"You already have a webhook with that URL called \"{webhook.webhook_name}\": {webhook.webhook_url}")

                    elif webhook.webhook_name == webhook_name:
                        print("Found duplicate webhook for name")
                        raise CustomError(f"You already have a webhook called \"{webhook.webhook_name}\": {webhook.webhook_url}")

                except CustomError as e:
                    return await on_generic_error(interaction, e)

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
                description=f"❌ {e}",
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
            try:
                raise GenericError(e)
            except Exception as e:
                await on_generic_error(interaction, e)

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
                try:
                    raise GenericError(e)
                except Exception as e:
                    return await on_generic_error(interaction, e)

        else: # no webhook data found
            try:
                raise CustomError(f"No webhook found matching identifier `{webhook_name}`. You can use `/cco webhook view` to view your webhooks.")
            except Exception as e:
                return await on_generic_error(interaction, e)

        return
    

    """
    Stock tracker
    """
    
    @capi_group.command(name='enable', description='Enable stock tracking via the Frontier API. Multiple carriers can be separated by a comma.')
    @describe(carriers = "One or more unique fragments of the carrier names you want to search for.")
    @check_roles([certcarrier_role(), trainee_role(), rescarrier_role()])
    @check_command_channel([mission_command_channel(), training_mission_command_channel(), bot_command_channel()])
    async def capi_enable(self, interaction: discord.Interaction, carriers: str):
        print(f"▶ cAPI tracking enable called by {interaction.user} for search term {carriers}")

        try:

            embed: discord.Embed = please_wait_embed()
            await interaction.response.send_message(embed=embed)

            if ", " in carriers:
                print("User requested multiple carriers")
                carrier_list = carriers.split(', ')
            elif "," in carriers:
                print("What kind of monster uses a comma without a trailing space?")
                carrier_list = carriers.split(',')
            else:
                carrier_list = [carriers]

            embeds = []

            for carrier in carrier_list:
                # attempt to find matching carrier data
                carrier_data = flexible_carrier_search_term(carrier)
                
                if not carrier_data:  # error condition
                    print(f"❌ No carrier found matching search term {carrier}")
                    carrier_error_embed = discord.Embed(
                        description=f"❌ No carrier found for '**{carrier}**'. Use `/owner` to see a list of your carriers. If it's not in the list, ask an Admin to add it for you.",
                        color=constants.EMBED_COLOUR_ERROR
                    )
                    embeds.append(carrier_error_embed)
                    continue # try other items in list

                fccode = carrier_data.carrier_identifier

                capi_response = capi(fccode)
                print(f"capi response: {capi_response.status_code}")
                if capi_response.status_code != 200:
                    r = oauth_new(fccode)
                    oauth_response = r.json()
                    print(f"capi_enable response {r.status_code} - {oauth_response}")
                    if 'token' in oauth_response:
                        try:
                            # DM the carrier owner with oauth link
                            owner = await bot.fetch_user(carrier_data.ownerid)

                            oauth_url = f"{API_HOST}/generate/{fccode}?token={oauth_response['token']}"

                            oauth_embed = discord.Embed(
                                title="🔗 Frontier Account Link Request",
                                description=f"Use the link below to **sign in to the Frontier Account** associated with **{carrier_data.carrier_long_name}** ({carrier_data.carrier_identifier})."
                                            f" This will authorise <@{bot.user.id}> to query this account for stock tracking purposes.\n\n"
                                            f"**[✅ Yes, authorise cAPI stock tracking for {carrier_data.carrier_long_name}]({oauth_url})**",
                                color=constants.EMBED_COLOUR_QU
                            )

                            oauth_embed.set_thumbnail(url=ptn_logo_discord(strftime('%B')))

                            await owner.send(embed=oauth_embed)

                        except Forbidden:
                            print(f"Couldn't message {owner}- DMs are blocked (403 Forbidden).")
                            try:
                                error = "Error 403 (Forbidden) while attempting to send your OAuth link. " \
                                    f"Please make sure you have allowed direct messages from <@{bot.user.id}> and try again."
                                raise CustomError(error)
                            except Exception as e:
                                return await on_generic_error(interaction, e)

                        embed.description=f"🔑 Please check <@{owner.id}>'s direct messages for Frontier account authorisation link, then repeat this command."

                        embeds.append(embed)

                        continue # stop there for this item

                    else:
                        try:
                            error = f"Could not generate auth URL for {carrier_data.carrier_long_name} ({carrier_data.carrier_identifier}): {e}"
                            raise CustomError(error)
                        except Exception as e:
                            return await on_generic_error(interaction, e)

                else:
                    embed = discord.Embed(
                        description=f"✅ cAPI auth already exists for **{carrier_data.carrier_long_name}** ({carrier_data.carrier_identifier}), enabling stock fetching.",
                        color=constants.EMBED_COLOUR_OK
                    )
                    embeds.append(embed)

                # write to the database
                await _update_carrier_capi(carrier_data.pid, 1)

                # check if the carrier is being tracked for WMM
                wmm_data: WMMData = find_wmm_carrier(carrier_data.carrier_identifier, 'cid')

                if wmm_data:
                    # update the WMM database
                    wmm_data.capi = 1
                    await _update_wmm_carrier(wmm_data)

                print("Finished updating cAPI flag.")

            # now return summary to user
            await interaction.edit_original_response(embeds=embeds)

        except Exception as e:
            try:
                raise GenericError(e)
            except Exception as e:
                traceback.print_exc()
                await on_generic_error(interaction, e)


    @capi_group.command(name='disable', description='Disable stock tracking via the Frontier API. Multiple carriers can be separated by a comma.')
    @describe(carriers = "One or more unique fragments of the carrier names you want to search for.")
    @check_roles([certcarrier_role(), trainee_role(), rescarrier_role()])
    @check_command_channel([mission_command_channel(), training_mission_command_channel(), bot_command_channel()])
    async def capi_disable(self, interaction: discord.Interaction, carriers: str):
        print(f"▶ cAPI tracking disable called by {interaction.user} for search term {carriers}")

        try:
            embed: discord.Embed = please_wait_embed()
            await interaction.response.send_message(embed=embed)

            if ", " in carriers:
                print("User requested multiple carriers")
                carrier_list = carriers.split(', ')
            elif "," in carriers:
                print("What kind of monster uses a comma without a trailing space?")
                carrier_list = carriers.split(',')
            else:
                carrier_list = [carriers]

            embeds = []

            for carrier in carrier_list:
                # attempt to find matching carrier data
                carrier_data = flexible_carrier_search_term(carrier)
                
                if not carrier_data:  # error condition
                    print(f"❌ No carrier found matching search term {carrier}")
                    carrier_error_embed = discord.Embed(
                        description=f"❌ No carrier found for '**{carrier}**'. Use `/owner` to see a list of your carriers. If it's not in the list, ask an Admin to add it for you.",
                        color=constants.EMBED_COLOUR_ERROR
                    )

                    embeds.append(carrier_error_embed)
                    continue

                if not carrier_data.capi:
                    print(f"cAPI already disabled for {carrier_data.carrier_long_name}")

                    embed = discord.Embed (
                        description=f"✅ Frontier API stock tracking is already disabled for **{carrier_data.carrier_long_name}** ({carrier_data.carrier_identifier}).",
                        color=constants.EMBED_COLOUR_OK
                    )

                    embeds.append(embed)
                    continue

                try:
                    print(f"⏳ Disabling cAPI for {carrier_data.carrier_long_name}...")

                    await _update_carrier_capi(carrier_data.pid, 0)

                    # check if the carrier is being tracked for WMM
                    wmm_data: WMMData = find_wmm_carrier(carrier_data.carrier_identifier, 'cid')

                    if wmm_data:
                        # update the WMM database
                        wmm_data.capi = 0
                        await _update_wmm_carrier(wmm_data)

                    embed = discord.Embed(
                        description=f"✅ Frontier API stock tracking disabled for **{carrier_data.carrier_long_name}** ({carrier_data.carrier_identifier}).",
                        color=constants.EMBED_COLOUR_OK
                    )

                    embeds.append(embed)
                    continue

                except Exception as e:
                    try:
                        error = f"Unable to disable cAPI for **{carrier_data.carrier_long_name}** ({carrier_data.carrier_identifier}): {e}"
                        raise CustomError(error)
                    except Exception as e:
                        await on_generic_error(interaction, e)
                        continue

            # now return summary to user
            await interaction.edit_original_response(embeds=embeds)

        except Exception as e:
            try:
                raise GenericError(e)
            except Exception as e:
                await on_generic_error(interaction, e)


    """
    WMM Commands
    """

    @wmm_group.command(name='enable', description='Begin WMM tracking for specified carrier.')
    @describe(carrier="A unique fragment of the carrier name you want to search for.")
    @check_roles([certcarrier_role(), trainee_role(), rescarrier_role()])
    @check_command_channel([mission_command_channel(), training_mission_command_channel(), bot_command_channel()])
    async def wmm_enable(self, interaction: discord.Interaction, carrier: str, station: str):
        print(f"▶ WMM tracking start called by {interaction.user} for search term {carrier} in {station}")
        try:
            embed: discord.Embed = please_wait_embed()

            await interaction.response.send_message(embed=embed)

            # attempt to find matching carrier data
            carrier_data = flexible_carrier_search_term(carrier)
            
            if not carrier_data:  # error condition
                print(f"❌ No carrier found matching search term {carrier}")
                carrier_error_embed = discord.Embed(
                    description=f"❌ No carrier found for '**{carrier}**'. Use `/owner` to see a list of your carriers. If it's not in the list, ask an Admin to add it for you.",
                    color=constants.EMBED_COLOUR_ERROR
                )
                return await interaction.edit_original_response(embed=carrier_error_embed)

            # check if carrier is being tracked already
            wmm_data: WMMData = find_wmm_carrier(carrier_data.carrier_identifier, 'cid')

            if wmm_data:
                # carrier is already being tracked, notify user
                print("Found existing wmm_data %s" % ( wmm_data ))
                embed.description=f"💸 **{carrier_data.carrier_long_name}** ({carrier_data.carrier_identifier}) is already being tracked at **{wmm_data.carrier_location.upper()}**."
                embed.color = constants.EMBED_COLOUR_OK
                await interaction.edit_original_response(embed=embed)
                return

            # add carrier to WMM database
            await _add_to_wmm_db(carrier_data.carrier_long_name, carrier_data.carrier_identifier, station.upper(), carrier_data.ownerid, carrier_data.capi)

            # edit our embed to notify user
            embed.description=f"💸 Added **{carrier_data.carrier_long_name}** ({carrier_data.carrier_identifier}) to the WMM stock list at station **{station.upper()}**."
            embed.color = constants.EMBED_COLOUR_OK

            # add a footer depending on state of cAPI
            if not carrier_data.capi:
                embed.set_footer(text="⚠ Consider enabling Frontier API to fetch stocks if this is a non-Epic Games carrier using /cco capi enable.")
            else:
                embed.set_footer(text="✅ Frontier API enabled for stock checks.")

            await interaction.edit_original_response(embed=embed)

        except Exception as e:
            try:
                raise GenericError(e)
            except Exception as e:
                await on_generic_error(interaction, e)
                traceback.print_exc()
                return


    @wmm_group.command(name='disable', description='Stop WMM tracking for specified carrier. Multiple carriers can be separated by a comma.')
    @describe(carriers = "One or more unique fragments of the carrier names you want to search for.")
    @check_roles([certcarrier_role(), trainee_role(), rescarrier_role()])
    @check_command_channel([mission_command_channel(), training_mission_command_channel(), bot_command_channel()])
    async def wmm_disable(self, interaction: discord.Interaction, carriers: str):
        print(f"▶ WMM tracking stop called by {interaction.user} for search term {carriers}")
        try:
            embed: discord.Embed = please_wait_embed()
            await interaction.response.send_message(embed=embed)

            if ", " in carriers:
                print("User requested multiple carriers")
                carrier_list = carriers.split(', ')
            elif "," in carriers:
                print("What kind of monster uses a comma without a trailing space?")
                carrier_list = carriers.split(',')
            else:
                carrier_list = [carriers]

            embeds = []

            for carrier in carrier_list:
                # attempt to find matching carrier data
                carrier_data = flexible_carrier_search_term(carrier)
                
                if not carrier_data:  # error condition
                    print(f"❌ No carrier found matching search term {carrier}")
                    carrier_error_embed = discord.Embed(
                        description=f"❌ No carrier found for '**{carrier}**'. Use `/owner` to see a list of your carriers. If it's not in the list, ask an Admin to add it for you.",
                        color=constants.EMBED_COLOUR_ERROR
                    )
                    embeds.append(carrier_error_embed)
                    continue

                # check if carrier is being tracked already
                wmm_data: WMMData = find_wmm_carrier(carrier_data.carrier_identifier, 'cid')

                if not wmm_data:
                    # carrier is already being tracked, notify user
                    print("No WMM data found for %s" % ( carrier_data.carrier_long_name ))

                    embed = discord.Embed(
                        description=f"✅ **{carrier_data.carrier_long_name}** ({carrier_data.carrier_identifier}) is not presently being tracked for WMMs.",
                        color = constants.EMBED_COLOUR_OK
                    )

                    embeds.append(embed)
                    continue

                # remove carrier from WMM database
                await _remove_from_wmm_db(carrier_data.carrier_identifier)

                # embed to notify user
                embed = discord.Embed(
                    description=f"🗑 Removed **{carrier_data.carrier_long_name}** ({carrier_data.carrier_identifier}) from the WMM stock list.",
                    color = constants.EMBED_COLOUR_OK
                )

                embeds.append(embed)
                continue

            # now return summary to user
            await interaction.edit_original_response(embeds=embeds)

        except Exception as e:
            try:
                raise GenericError(e)
            except Exception as e:
                await on_generic_error(interaction, e)
                traceback.print_exc()
                return


    # autocomplete WMM station names
    @wmm_enable.autocomplete("station")
    async def location_autocomplete(self, interaction: discord.Interaction, current: str):
        locations = [] # define the list we will return
        for location in locations_wmm: # iterate through our possible locations to append them as Choice options to our return list
            locations.append(app_commands.Choice(name=location, value=location))
        return locations # return the list of Choices
    

    @wmm_group.command(name='update', description='Refresh WMM stock without changing the update interval.')
    @check_roles([certcarrier_role(), trainee_role(), rescarrier_role()])
    @check_command_channel([mission_command_channel(), training_mission_command_channel(), bot_command_channel()])
    async def wmm_update(self, interaction: discord.Interaction):
        print(f"▶ Manual WMM refresh called by {interaction.user}")
        try:
            constants.wmm_trigger = True
            embed = discord.Embed(
                description=f"⏳ WMM stock update requested. Please wait a moment before checking <#{constants.channel_wmm_stock()}>.",
                color=constants.EMBED_COLOUR_QU
            )

            await interaction.response.send_message(embed=embed)

            spamchannel = bot.get_channel(bot_spam_channel())

            message: discord.Message = await interaction.original_response()

            embed.description = f"💸 :arrows_counterclockwise: WMM update called by <@{interaction.user.id}> at {message.jump_url}."

            notification = await spamchannel.send(embed=embed)

            if not wmm_stock.is_running() or wmm_stock.failed():
                print("wmm_stock task has failed, restarting.")

                embed = discord.Embed(
                description=":warning: WMM stock background task was not running. Restarting now.",
                color=constants.EMBED_COLOUR_WARNING
                )

                await interaction.followup.send(embed=embed)

                await start_wmm_task()

                command_channel = bot.get_channel(bot_command_channel())

                embed.description = f"💸 :warning: WMM background task was not running when update was called. Restart attempted. " \
                                    f"Use `/admin wmm status` in <#{command_channel.id}> to check status of background task."

                await notification.reply(embed=embed)

        except Exception as e:
            try:
                raise GenericError(e)
            except Exception as e:
                await on_generic_error(interaction, e)