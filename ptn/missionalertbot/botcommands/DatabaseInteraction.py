"""
A Cog for commands that are primarily concerned with the bot's databases.

"""

# import libraries
import asyncio
import copy
import os
import re
from typing import List

# import discord.py
import discord
from discord import app_commands
from discord.app_commands import Group, command, describe
from discord.ext import commands

# local classes
from ptn.missionalertbot.classes.CarrierData import CarrierData
from ptn.missionalertbot.classes.CommunityCarrierData import CommunityCarrierData
from ptn.missionalertbot.classes.NomineesData import NomineesData
from ptn.missionalertbot.classes.Views import db_delete_View, BroadcastView, CarrierEditView, MissionDeleteView, AddCarrierButtons, ConfirmPurgeView

# local constants
import ptn.missionalertbot.constants as constants
from ptn.missionalertbot.constants import bot, cmentor_role, admin_role, cteam_bot_channel, cteam_bot_channel, bot_command_channel, cc_role, \
    admin_role, mod_role, bot_spam_channel, fc_complete_emoji, get_guild

# local modules
from ptn.missionalertbot.database.database import find_nominee_with_id, carrier_db, CarrierDbFields, find_carrier, backup_database, \
    add_carrier_to_database, find_carriers_mult, find_commodity, find_community_carrier, CCDbFields
from ptn.missionalertbot.modules.ErrorHandler import on_app_command_error, CustomError, on_generic_error, GenericError
from ptn.missionalertbot.modules.helpers import check_roles, check_command_channel, _regex_alphanumeric_with_hyphens, extract_carrier_ident_strings
from ptn.missionalertbot.modules.Embeds import _add_common_embed_fields, _configure_all_carrier_detail_embed, orphaned_carrier_summary_embed


@bot.tree.context_menu(name='Add Carrier')
@check_roles([admin_role()])
async def add_carrier(interaction:  discord.Interaction, message: discord.Message):
    print(f"add_carrier called by {interaction.user.display_name} for {message.author.display_name}")

    embed = discord.Embed(
        description="⏳ Please wait a moment...",
        color=constants.EMBED_COLOUR_QU
    )

    await interaction.response.send_message(embed=embed)

    # extract matching strings from message
    carrier_details: dict = extract_carrier_ident_strings(message)

    if not carrier_details:
        try:
            error = f"No valid carrier details found in {message.jump_url}. Details should be in format " \
                     "`P.T.N. Full Name (ABC-123)` (Any variation on 'PTN' is fine)"
            await interaction.delete_original_response()
            raise CustomError(error, False)
        except Exception as e:
            return await on_generic_error(interaction, e)

    # print the extracted values
    for details in carrier_details:
        long_name = details['long_name']
        carrier_id = details['carrier_id']
        short_name = details['short_name']
        index = details['index']
        owner_id = details['owner_id']
        channel_name = details['channel_name']

        # replace the letter 'O' with the number '0'
        if "o" in carrier_id.lower():
            carrier_id = carrier_id.replace("O", "0").replace("o", "0")


        print(f"Index {index} is '{long_name}' ({carrier_id}) with generated shortname {short_name}")
        embed.add_field(
            name=f"{f'Match {index+1}' if len(carrier_details) > 1 else 'Matched Details'}",
            value=f'Longname: `{long_name}` • Shortname: `{short_name}` • ID: `{carrier_id}` • Owner: <@{owner_id}> • ChannelName: #`{channel_name}`',
            inline=False
        )

    # TODO check no two fields are identical

    embed.title="🔎 CARRIER DETAILS FOUND IN MESSAGE"
    embed.description=None

    view = AddCarrierButtons(message, carrier_details, interaction.user)

    await interaction.edit_original_response(embed=embed, view=view)
    view.message = await interaction.original_response()



"""
DATABASE INTERACTIONS

/carrier_add - database
/carrier_delete - database
carrier_list - database
cc_list - community/database
cc_owner - community/database
/cp_nominees_list - community/database
/cp_delete_nominee_from_database - community/database
/cp_nomination_details - community/database
/carrier_edit - database
find - database
/find - general/database
findcomm - database
findid - database
findshort - database
/info - general/database
/owner - general/database

"""


# initialise the Cog and error handler
class DatabaseInteraction(commands.Cog):
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
    CP Nomination Commands
    """


    # command to delete nominations for a nominee
    @app_commands.command(name='cp_delete_nominee_from_database',
                          description='Completely removes all nominations for a user by user ID. NOT RECOVERABLE.')
    @app_commands.describe(userid='The Discord ID of the user whose nominations you wish to delete.')
    @check_roles([cmentor_role(), admin_role()])
    @check_command_channel(cteam_bot_channel())
    async def cp_delete_nominee_from_database(self, interaction: discord.Interaction, userid: str):
        print(f"{interaction.command.name} called by {interaction.user}")
        author = interaction.user

        # check whether user has any nominations
        nominees_data = find_nominee_with_id(userid)
        if not nominees_data:
            embed = discord.Embed(title="Failed: Remove Nominee from Database",
                                  description=f'No results for user with ID {userid}',
                                  color=constants.EMBED_COLOUR_ERROR)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # now check they're sure they want to delete

        embed = discord.Embed(title="Confirm: Remove Nominee from Database",
                              description=f"Are you **sure** you want to completely remove <@{userid}> from the nominees database? **The data is gone forever**.",
                              color=constants.EMBED_COLOUR_QU)

        view = db_delete_View(userid, interaction)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        return


    # command to display a list of nominees who meet a given threshhold for number of nominations
    @app_commands.command(name='cp_nominees_list', description='Shows all users with a given nomination threshhold.')
    @app_commands.describe(number='The number of nominations needed for a nominee to appear in the list output.')
    @check_roles([cmentor_role(), admin_role()])
    @check_command_channel(cteam_bot_channel())
    async def cp_nominees_list(self, interaction: discord.Interaction, number: int):

        embed = discord.Embed(
            description="⏳ Please wait while I fetch user data for all desired nominees. This could take some time if the nominees list is large.",
            color=constants.EMBED_COLOUR_QU
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

        numberint = int(number)

        print(f"cp_nominees_list called by {interaction.user}")
        embed=discord.Embed(title="Community Pillar nominees", description=f"Showing all with {number} nominations or more.", color=constants.EMBED_COLOUR_OK)

        print("reading database")

        # we need to 1: get a list of unique pillars then 2: send only one instance of each unique pillar to nom_count_user

        # 1: get a list of unique pillars
        carrier_db.execute(f"SELECT DISTINCT pillarid FROM nominees")
        nominees_data = [NomineesData(nominees) for nominees in carrier_db.fetchall()]
        for nominees in nominees_data:
            print(f"Iterating for {nominees.pillar_id}...")

            # 2: pass each unique pillar through to the counting function to retrieve the number of times they appear in the table

            def nom_count_user(pillarid):
                """
                Counts how many active nominations a nominee has.
                """
                nominees_data = find_nominee_with_id(pillarid)

                count = len(nominees_data)
                print(f"{count} for {pillarid}")

                return count

            count = nom_count_user(nominees.pillar_id)
            print(f"{nominees.pillar_id} has {count}")

            # only show those with a count >= the number the user specified
            if count >= numberint:
                try: # try to get a user object for this nominee
                    print("Fetching user object...")
                    nominee = await bot.fetch_user(nominees.pillar_id)
                    nominee_name = f"({nominee.display_name}/`{nominee.name}`)"
                except Exception as e:
                    print(f"Unable to fetch Discord user object for {nominees.pillar_id}: {e}")
                    nominee_name = ""

                embed.add_field(name=f'{count} nominations', value=f"<@{nominees.pillar_id}> {nominee_name}", inline=False)

        view = BroadcastView(embed)

        await interaction.edit_original_response(embed=embed, view=view)
        return print("nom_count complete")


    # command to retrieve text for all nominations for a given user from the database
    @app_commands.command(name='cp_nomination_details', description='Shows details of all nominations for a given user by ID.')
    @app_commands.describe(userid='The Discord ID of the target user. Use Developer Mode to retrieve user IDs.')
    @check_roles([cmentor_role(), admin_role()])
    @check_command_channel(cteam_bot_channel())
    async def cp_nomination_details(self, interaction: discord.Interaction, userid: str):

        embed = discord.Embed(
            description="⏳ Please wait while I fetch user data for this nominee.",
            color=constants.EMBED_COLOUR_QU
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

        try: # check if we can find the user object, otherwise user is probably not on server anymore
            member = await bot.fetch_user(userid)
            print(f"looked for member with {userid} and found {member}")
            member_names = f"({member.display_name}/`{member.name}`)"
        except Exception as e:
            embed = discord.Embed(
                description=f"❌ Unable to resolve a Discord user on this server with ID {userid}: {e}",
                color=constants.EMBED_COLOUR_ERROR
            )
            return await interaction.edit_original_response(embed=embed)

        print(f"cp_nomination_details called by {interaction.user} for member: {member}")

        embed=discord.Embed(title=f"Nomination details", description=f"Discord user <@{member.id}> {member_names}", color=constants.EMBED_COLOUR_OK)

        # look up specified user and return every entry for them as embed fields. TODO: This will break after too many nominations, would need to be paged.
        # if an empty list is returned, update the embed description and color
        nominees_data = find_nominee_with_id(userid)
        if nominees_data:
            for nominees in nominees_data:
                try:
                    nominator = await bot.fetch_user(nominees.nom_id)
                    embed.add_field(name=f'Nominator: {nominator.display_name}',
                                    value=f"{nominees.note}", inline=False)
                except Exception as e:
                    print(f"Unable to get nominating user: {nominees.nom_id}: {e}")
        else:
            embed.description = f'No nominations found for <@{member.id}>'
            embed.color = constants.EMBED_COLOUR_REDDIT

        view = BroadcastView(embed)

        await interaction.edit_original_response(embed=embed, view=view)


    """
    Carrier DB commands
    """

    carrier_group = Group(name='carrier', description='Carrier DB commands')

    # purge database of carrier owners who are no longer on the server
    @carrier_group.command(name='purge', description='Generate a list of carriers belonging to departed owners, with option to purge.')
    @check_roles([admin_role()])
    @check_command_channel(bot_command_channel())
    async def purge(self, interaction: discord.Interaction):
        print(f"Carrier database purge called by {interaction.user}")

        embed = discord.Embed(
            description="⏳ Please wait a moment...",
            color=constants.EMBED_COLOUR_QU
        )
        await interaction.response.send_message(embed=embed) # tell the user we're working on it

        async with interaction.channel.typing():
            # define empty list of candidate carriers
            carrier_list = []
            summary_list = []

            # define guild
            guild = await get_guild()

            # get all carriers from database
            # TODO: paginate this for future-proofing
            carrier_db.execute(f"""
                SELECT * from carriers
                               """)
            carrier_data: CarrierData = [CarrierData(carrier) for carrier in carrier_db.fetchall()]

            # check if owner exists on server
            carrier: CarrierData
            for carrier in carrier_data:
                owner = None
                try:
                    owner = guild.get_member(carrier.ownerid)
                except:
                    print(f"No active owner found for: {carrier}")
                    owner = None
                if not owner:
                    carrier_list.append(carrier)
                    summary_list.append(f"**{carrier.carrier_long_name}** ({carrier.carrier_identifier}) DBID `{carrier.pid}` Owner `{carrier.ownerid}` <@{carrier.ownerid}>")

        # exit if no orphans found
        if len(carrier_list) == 0:
            print("No orphaned carriers found.")
            embed = discord.Embed(
                description="🔍 No orphaned carriers found.",
                color = constants.EMBED_COLOUR_OK
            )
            await interaction.edit_original_response(embed=embed)
            return

        summary_text = "\n".join(["- " + string for string in summary_list])
        # generate summary embed
        embed = orphaned_carrier_summary_embed(summary_text)

        view = ConfirmPurgeView(embed, carrier_list, interaction.user)

        await interaction.edit_original_response(embed=embed, view=view)

        view.message = await interaction.original_response()

    # add FC to database
    @carrier_group.command(name='add', description='Add a Fleet Carrier to the database.')
    @describe(short_name='The name used by the ;stock command.',
                           long_name='The full name of the Fleet Carrier (will be converted to UPPERCASE).',
                           carrier_id='The carrier\'s registration in the format XXX-XXX.',
                           owner_id='The Discord ID of the carrier\'s owner.')
    @check_roles([admin_role()])
    @check_command_channel(bot_command_channel())
    async def add(self, interaction: discord.Interaction, short_name: str, long_name: str, carrier_id: str, owner_id: str):

        # check the ID code is correct format (thanks boozebot code!)
        if not re.match(r"\w{3}-\w{3}", carrier_id):
            print(f'{interaction.user}, the carrier ID was invalid, XXX-XXX expected received, {carrier_id}.')
            return await interaction.response.send_message(f'ERROR: Invalid carrier ID. Expected: XXX-XXX, received `{carrier_id}`.', ephemeral=True)

        # replace the letter 'O' with the number '0'
        if "o" in carrier_id.lower():
            carrier_id = carrier_id.replace("O", "0").replace("o", "0")

        # convert owner_id to int (slash commands have a cannot exceed the integer size limit, so we have to pass IDs as strings)
        # and check it is valid
        try:
            owner_id = int(owner_id)
        except Exception as e:
            return await interaction.response.send_message(f'ERROR: Invalid owner ID. Expected an ID in the format `824243421145333770`, received `{owner_id}`.', ephemeral=True)

        # Only add to the carrier DB if it does not exist, if it does exist then the user should not be adding it.
        # TODO: merge with Add Carrier
        carrier_data = find_carrier(long_name, CarrierDbFields.longname.name)
        if carrier_data:
            # Carrier exists already, go skip it.
            print(f'Request recieved from {interaction.user} to add a carrier that already exists in the database ({long_name}).')

            embed = discord.Embed(title="Fleet carrier already exists, use /carrier_edit to change its details.",
                                description=f"Carrier data matched for {long_name}", color=constants.EMBED_COLOUR_OK)
            embed = _add_common_embed_fields(embed, carrier_data, interaction)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        backup_database('carriers')  # backup the carriers database before going any further

        # now generate a string to use for the carrier's channel name based on its long name
        stripped_name = _regex_alphanumeric_with_hyphens(long_name)

        # find carrier owner as a user object so we know they're a valid user
        # TODO: move error to handler
        try:
            owner = await bot.fetch_user(owner_id)
            print(f"Owner identified as {owner.display_name}")
        except:
            raise EnvironmentError(f'Could not find Discord user matching ID {owner_id}')

        # finally, send all the info to the db
        # TODO: merge with Add Carrier
        await add_carrier_to_database(short_name.lower(), long_name.upper(), carrier_id.upper(), stripped_name.lower(), 0, owner_id)

        carrier_data = find_carrier(long_name, CarrierDbFields.longname.name)
        info_embed = discord.Embed(title="Fleet Carrier successfully added to database",
                            color=constants.EMBED_COLOUR_OK)
        info_embed = _add_common_embed_fields(info_embed, carrier_data, interaction)

        cp_embed = discord.Embed(
            title="Copy/Paste code for Stockbot",
            description=f"```;add_FC {carrier_data.carrier_identifier} {carrier_data.carrier_short_name} {carrier_data.ownerid}```",
            color=constants.EMBED_COLOUR_QU
        )

        embeds = [info_embed, cp_embed]

        await interaction.response.send_message(embeds=embeds)

        # notify bot-spam
        spamchannel: discord.TextChannel = bot.get_channel(bot_spam_channel())
        message: discord.Message = await interaction.original_response()
        embed = discord.Embed(
            description=f"<:fc_complete:{fc_complete_emoji()}> **NEW FLEET CARRIER** added by <@{interaction.user.id}> at {message.jump_url}",
            color=constants.EMBED_COLOUR_OK
        )
        embed = _add_common_embed_fields(embed, carrier_data, interaction)
        return await spamchannel.send(embed=embed)


    # remove FC from database
    @carrier_group.command(name='delete', description='Delete a Fleet Carrier from the database using its database entry ID#.',)
    @describe(db_id='The database ID number of the carrier to delete. Use /find to retrieve the carrier ID.')
    @check_roles([admin_role()])
    @check_command_channel(bot_command_channel())
    async def delete(self, interaction: discord.Interaction, db_id: int):
        print(f"{interaction.command.name} called by {interaction.user.display_name}")

        try:
            carrier_data = find_carrier(db_id, CarrierDbFields.p_id.name)
            if carrier_data:
                embed = discord.Embed(title="Confirm: Remove Carrier from Database",
                                       description=f"Are you **sure** you want to completely remove the following carrier from the database?",
                                    color=constants.EMBED_COLOUR_QU)

                # now check they're sure they want to delete

                view = db_delete_View(db_id, interaction)

                await interaction.response.send_message(embed=embed, view=view)

                info_embed = discord.Embed(title="Fleet Carrier Search Result",
                                           description=f"Showing carrier {db_id}",
                                           color=constants.EMBED_COLOUR_OK)
                info_embed = _add_common_embed_fields(info_embed, carrier_data, interaction)

                await interaction.channel.send(embed=info_embed)

            else:
                print(f'No carrier with given ID found in database.')
                embed = discord.Embed(
                    description=f"❌ Couldn't find a carrier with ID #{db_id}.",
                    color=constants.EMBED_COLOUR_ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

        except TypeError as e:
            print(f'Error while finding carrier to delete: {e}.')


    @carrier_group.command(name="edit",
                          description="Edit a specific carrier in the database")
    @describe(carrier_name_search_term='A string to search for that should match part of the target carrier\'s full name.')
    @check_roles([admin_role()])
    @check_command_channel(bot_command_channel())
    async def edit(self, interaction: discord.Interaction, carrier_name_search_term: str):
        """
        Edits a carriers information in the database. Provide a carrier name that can be partially matched and follow the
        steps.

        :param discord.interaction interaction: The discord interaction
        :param str carrier_name_search_term: The carrier name to find
        :returns: None
        """
        print(f'/carrier_edit called by {interaction.user} to update the carrier: {carrier_name_search_term} from channel: {interaction.channel}')

        # Go fetch the carrier details by searching for the name

        carrier_data = copy.copy(find_carrier(carrier_name_search_term, CarrierDbFields.longname.name))
        orig_carrier_data = copy.copy(carrier_data)
        print(carrier_data)
        if carrier_data:
            embed = discord.Embed(title="Original Carrier Data", color=discord.Color.green())
            embed = await _configure_all_carrier_detail_embed(embed, carrier_data)
            return await interaction.response.send_message(
                embed=embed,
                view=CarrierEditView(carrier_data=carrier_data,orig_carrier_data=orig_carrier_data), ephemeral=True) # should this be ephemeral? if not we'd need checks on button interactions
        else:
            embed = discord.Embed(title='Error',
                                  description=f'No result found for the carrier: "{carrier_name_search_term}"', color=constants.EMBED_COLOUR_ERROR)
            return await interaction.response.send_message(embed=embed, ephemeral=True)


    # list FCs
    # TODO: slashify
    @commands.command(name='carrier_list', help='List all Fleet Carriers in the database. This times out after 60 seconds')
    @commands.has_any_role(*constants.any_elevated_role)
    async def carrier_list(self, ctx):

        print(f'Carrier List requested by user: {ctx.author}')

        carrier_db.execute(f"SELECT * FROM carriers")
        carriers = [CarrierData(carrier) for carrier in carrier_db.fetchall()]

        def chunk(chunk_list, max_size=10):
            """
            Take an input list, and an expected max_size.

            :returns: A chunked list that is yielded back to the caller
            :rtype: iterator
            """
            for i in range(0, len(chunk_list), max_size):
                yield chunk_list[i:i + max_size]

        def validate_response(react, user):
            return user == ctx.author and str(react.emoji) in ["◀️", "❌", "▶️"]
            # This makes sure nobody except the command sender can interact with the "menu"

        # TODO: should pages just be a list of embed_fields we want to add?
        pages = [page for page in chunk(carriers)]

        max_pages = len(pages)
        current_page = 1

        embed = discord.Embed(title=f"{len(carriers)} Registered Fleet Carriers Page:#{current_page} of {max_pages}")
        count = 0   # Track the overall count for all carriers
        # Go populate page 0 by default
        for carrier in pages[0]:
            count += 1
            embed.add_field(name=f"{count}: {carrier.carrier_long_name} ({carrier.carrier_identifier})",
                            value=f"<@{carrier.ownerid}>, <t:{carrier.lasttrade}:R>", inline=False)
        # Now go send it and wait on a reaction
        message = await ctx.send(embed=embed)

        await message.add_reaction("❌")
        # From page 0 we can only go forwards
        if not current_page == max_pages: await message.add_reaction("▶️")

        # 60 seconds time out gets raised by Asyncio
        while True:
            try:
                reaction, user = await bot.wait_for('reaction_add', timeout=60, check=validate_response)
                if str(reaction.emoji) == "❌":
                    print(f'Closed list carrier request by: {ctx.author}')
                    embed = discord.Embed(description=f'Closed the active carrier list.', color=constants.EMBED_COLOUR_OK)
                    await ctx.send(embed=embed)
                    await message.delete()
                    await ctx.message.delete()
                    return

                elif str(reaction.emoji) == "▶️" and current_page != max_pages:
                    print(f'{ctx.author} requested to go forward a page.')
                    current_page += 1   # Forward a page
                    new_embed = discord.Embed(title=f"{len(carriers)} Registered Fleet Carriers Page:{current_page}")
                    for carrier in pages[current_page-1]:
                        # Page -1 as humans think page 1, 2, but python thinks 0, 1, 2
                        count += 1
                        new_embed.add_field(name=f"{count}: {carrier.carrier_long_name} ({carrier.carrier_identifier})",
                                            value=f"<@{carrier.ownerid}>, <t:{carrier.lasttrade}:R>", inline=False)

                    await message.edit(embed=new_embed)

                    # Ok now we can go back, check if we can also go forwards still
                    if current_page == max_pages:
                        await message.clear_reaction("▶️")

                    await message.remove_reaction(reaction, user)
                    await message.add_reaction("◀️")

                elif str(reaction.emoji) == "◀️" and current_page > 1:
                    print(f'{ctx.author} requested to go back a page.')
                    current_page -= 1   # Go back a page

                    new_embed = discord.Embed(title=f"{len(carriers)} Registered Fleet Carriers Page:{current_page}")
                    # Start by counting back however many carriers are in the current page, minus the new page, that way
                    # when we start a 3rd page we don't end up in problems
                    count -= len(pages[current_page - 1])
                    count -= len(pages[current_page])

                    for carrier in pages[current_page - 1]:
                        # Page -1 as humans think page 1, 2, but python thinks 0, 1, 2
                        count += 1
                        new_embed.add_field(name=f"{count}: {carrier.carrier_long_name} ({carrier.carrier_identifier})",
                                            value=f"<@{carrier.ownerid}>, <t:{carrier.lasttrade}:R>", inline=False)

                    await message.edit(embed=new_embed)
                    # Ok now we can go forwards, check if we can also go backwards still
                    if current_page == 1:
                        await message.clear_reaction("◀️")

                    await message.remove_reaction(reaction, user)
                    await message.add_reaction("▶️")
                else:
                    # It should be impossible to hit this part, but lets gate it just in case.
                    print(f'HAL9000 error: {ctx.author} ended in a random state while trying to handle: {reaction.emoji} '
                        f'and on page: {current_page}.')
                    # HAl-9000 error response.
                    error_embed = discord.Embed(title=f"I'm sorry {ctx.author.name}, I'm afraid I can't do that.")
                    await message.edit(embed=error_embed)
                    await message.remove_reaction(reaction, user)

            except asyncio.TimeoutError:
                if ctx.fetch_message(message.id) and ctx.fetch_message(ctx.message.id):
                    print(f'Timeout hit during carrier request by: {ctx.author}')
                    embed = discord.Embed(description=f'Closed the active carrier list request from {ctx.author} due to no input in 60 seconds.', color=constants.EMBED_COLOUR_QU)
                    await ctx.send(embed=embed)
                    await message.delete()
                    await ctx.message.delete()
                    break
                else:
                    return


    """
    Carrier db search commands
    """


    # find FC based on longname
    @commands.command(name='find', help='Find a carrier based on a partial match with any part of its full name\n'
                                '\n'
                                'Syntax: m.find <search_term>')
    async def find(self, ctx, carrier_name_search_term: str):
        try:
            carriers = find_carriers_mult(carrier_name_search_term, CarrierDbFields.longname.name)
            if carriers:
                carrier_data = None

                if len(carriers) == 1:
                    print('Single carrier found, returning that directly')
                    # if only 1 match, just assign it directly
                    carrier_data = carriers[0]
                elif len(carriers) > 3:
                    # If we ever get into a scenario where more than 3 carriers can be found with the same search
                    # directly, then we need to revisit this limit
                    print(f'More than 3 carriers found for: "{carrier_name_search_term}", {ctx.author} needs to search better.')
                    await ctx.send(f'Please narrow down your search, we found {len(carriers)} matches for your '
                                f'input choice: "{carrier_name_search_term}"')
                    return None  # Just return None here and let the calling method figure out what is needed to happen
                else:
                    print(f'Between 1 and 3 carriers found for: "{carrier_name_search_term}", asking {ctx.author} which they want.')
                    # The database runs a partial match, in the case we have more than 1 ask the user which they want.
                    # here we have less than 3, but more than 1 match
                    embed = discord.Embed(title=f"Multiple carriers ({len(carriers)}) found for input: {carrier_name_search_term}",
                                        color=constants.EMBED_COLOUR_OK)

                    count = 0
                    response = None  # just in case we try to do something before it is assigned, give it a value of None
                    for carrier in carriers:
                        count += 1
                        embed.add_field(name='Carrier Name', value=f'{carrier.carrier_long_name}', inline=True)

                    embed.set_footer(text='Please select the carrier with 1, 2 or 3')

                    def check(message):
                        return message.author == ctx.author and message.channel == ctx.channel and \
                            len(message.content) == 1 and message.content.lower() in ["1", "2", "3"]

                    message_confirm = await ctx.send(embed=embed)
                    try:
                        # Wait on the user input, this might be better by using a reaction?
                        response = await bot.wait_for("message", check=check, timeout=15)
                        print(f'{ctx.author} responded with: "{response.content}", type: {type(response.content)}.')
                        index = int(response.content) - 1  # Users count from 1, computers count from 0
                        carrier_data = carriers[index]
                    except asyncio.TimeoutError:
                        print('User failed to respond in time')
                        pass
                    await message_confirm.delete()
                    if response:
                        await response.delete()

                if carrier_data:
                    embed = discord.Embed(title="Fleet Carrier Search Result",
                                        description=f"Displaying match for {carrier_name_search_term}",
                                        color=constants.EMBED_COLOUR_OK)
                    embed = _add_common_embed_fields(embed, carrier_data, ctx)
                    return await ctx.send(embed=embed)
        except TypeError as e:
            print('Error in carrier search: {}'.format(e))
        await ctx.send(f'No result for {carrier_name_search_term}.')


    # slash version of m.find, private
    # TODO: replace with broadcast option
    # TODO: implement multiple result logic from m.find
    @app_commands.command(name="find",
                          description="Private command: Search for a fleet carrier by partial match for its name.")
    @app_commands.describe(carrier_name_search_term='Part of the full name of the carrier you wish to find.')
    async def _find(self, interaction: discord.Interaction, carrier_name_search_term: str):
        print(f"{interaction.user} used /find for '{carrier_name_search_term}' in {interaction.channel}")

        try:
            carrier_data = find_carrier(carrier_name_search_term, CarrierDbFields.longname.name)
            if carrier_data:
                print(f"Found {carrier_data}")
                embed = discord.Embed(title="Fleet Carrier Search Result",
                                    description=f"Displaying first match for {carrier_name_search_term}", color=constants.EMBED_COLOUR_OK)
                embed = _add_common_embed_fields(embed, carrier_data, interaction)
                return await interaction.response.send_message(embed=embed, ephemeral=True)

        except TypeError as e:
            print('Error in carrier long search: {}'.format(e))
        await interaction.response.send_message(f'No result for {carrier_name_search_term}.', ephemeral=True)


    # find FC based on ID
    @commands.command(name='findid', help='Find a carrier based on its database ID\n'
                                    'Syntax: findid <integer>')
    async def findid(self, ctx, db_id: int):
        try:
            if not isinstance(db_id, int):
                try:
                    db_id = int(db_id)
                    # Someone passed in a non integer, because this gets passed in with the wrapped quotation marks, it is
                    # probably impossible to convert. Just go return an error and call the user an fool of a took
                except ValueError:
                    return await ctx.send(
                        f'Computer says "The input must be a valid integer, you gave us a {type(db_id)} with value: '
                        f'{db_id}"')
            carrier_data = find_carrier(db_id, CarrierDbFields.p_id.name)
            if carrier_data:
                embed = discord.Embed(title="Fleet Carrier DB# Search Result",
                                    description=f"Displaying carrier with DB# {carrier_data.pid}",
                                    color=constants.EMBED_COLOUR_OK)
                embed = _add_common_embed_fields(embed, carrier_data, ctx)
                await ctx.send(embed=embed)
                return  # We exit here

        except TypeError as e:
            print('Error in carrier findid search: {}'.format(e))
        await ctx.send(f'No result for {db_id}.')


    # find commodity
    @app_commands.command(name="find_commodity",
                          description="Search for a commodity by partial match for its name.")
    @app_commands.describe(commodity_search_term='Part of the full name of the commodity you wish to find.')
    async def search_for_commodity(self, interaction: discord.Interaction, commodity_search_term: str):
        print(f'search_for_commodity called by {interaction.user} to search for {commodity_search_term}')
        class Commodity:
            def __init__(self, commodity_search_term):
                self.commodity_search_term = commodity_search_term

        commodity_wrapper = Commodity(commodity_search_term)

        await interaction.response.send_message(f"Searching for commodity {commodity_search_term}...")

        try:
            commodity = await find_commodity(commodity_wrapper, interaction)
            if commodity:
                return await interaction.edit_original_response(content=f'✅ {commodity}')
            else:
                return await interaction.edit_original_response(content=f'❌ No such commodity found for: "{commodity_search_term}".')
        except Exception as e:
            # Catch any exception
            print(e)
            return


    # find FC based on shortname
    @commands.command(name='findshort', help='Use to find a carrier by searching for its shortname.\n'
                                        '\n'
                                        'Syntax: m.findshort <search_term>\n'
                                        '\n'
                                        'Partial matches will work but only if they incorporate part of the shortname.\n'
                                        'To find a carrier based on a match with part of its full name, use the /find '
                                        'command.')
    async def findshort(self, ctx, shortname_search_term: str):
        try:
            carriers = find_carriers_mult(shortname_search_term, CarrierDbFields.shortname.name)
            if carriers:
                carrier_data = None

                if len(carriers) == 1:
                    print('Single carrier found, returning that directly')
                    # if only 1 match, just assign it directly
                    carrier_data = carriers[0]
                elif len(carriers) > 3:
                    # If we ever get into a scenario where more than 3 can be found with the same search
                    # directly, then we need to revisit this limit
                    print(f'More than 3 carriers found for: "{shortname_search_term}", {ctx.author} needs to search better.')
                    await ctx.send(f'Please narrow down your search, we found {len(carriers)} matches for your '
                                f'input choice: "{shortname_search_term}"')
                    return None  # Just return None here and let the calling method figure out what is needed to happen
                else:
                    print(f'Between 1 and 3 carriers found for: "{shortname_search_term}", asking {ctx.author} which they want.')
                    # The database runs a partial match, in the case we have more than 1 ask the user which they want.
                    # here we have less than 3, but more than 1 match
                    embed = discord.Embed(title=f"Multiple carriers ({len(carriers)}) found for input: {shortname_search_term}",
                                        color=constants.EMBED_COLOUR_OK)

                    count = 0
                    response = None  # just in case we try to do something before it is assigned, give it a value of None
                    for carrier in carriers:
                        count += 1
                        embed.add_field(name='Carrier Name', value=f'{carrier.carrier_long_name}', inline=True)

                    embed.set_footer(text='Please select the carrier with 1, 2 or 3')

                    def check(message):
                        return message.author == ctx.author and message.channel == ctx.channel and \
                            len(message.content) == 1 and message.content.lower() in ["1", "2", "3"]

                    message_confirm = await ctx.send(embed=embed)
                    try:
                        # Wait on the user input, this might be better by using a reaction?
                        response = await bot.wait_for("message", check=check, timeout=15)
                        print(f'{ctx.author} responded with: "{response.content}", type: {type(response.content)}.')
                        index = int(response.content) - 1  # Users count from 1, computers count from 0
                        carrier_data = carriers[index]
                    except asyncio.TimeoutError:
                        print('User failed to respond in time')
                        pass
                    await message_confirm.delete()
                    if response:
                        await response.delete()

                if carrier_data:
                    embed = discord.Embed(title="Fleet Carrier Shortname Search Result",
                                        description=f"Displaying first match for {shortname_search_term}",
                                        color=constants.EMBED_COLOUR_OK)
                    embed = _add_common_embed_fields(embed, carrier_data, ctx)
                    return await ctx.send(embed=embed)
        except TypeError as e:
            print('Error in carrier search: {}'.format(e))
        await ctx.send(f'No result for {shortname_search_term}.')


    @app_commands.command(name="info",
                          description="Private command: Use in a Fleet Carrier's channel to show information about it.")
    async def info(self, interaction: discord.Interaction):

        print(f'/info command carrier_data called by {interaction.user} in {interaction.channel}')

        # take a note of channel name and ID
        msg_channel_name = interaction.channel.name
        msg_channel_id = interaction.channel.id

        # look for a match for the ID in the community carrier database
        carrier_db.execute(f"SELECT * FROM community_carriers WHERE "
                        f"channelid = {msg_channel_id}")
        community_carrier_data = CommunityCarrierData(carrier_db.fetchone())

        if community_carrier_data:
            embed = discord.Embed(title="COMMUNITY CHANNEL",
                                description=f"<#{interaction.channel.id}> is a P.T.N. Community channel "
                                            f"registered to <@{community_carrier_data.owner_id}>.\n\n"
                                            f"Community channels are for events and community building and "
                                            f"are administered by the <@&{cc_role()}> and <@&{cmentor_role()}>s. See channel pins and description "
                                            f"more information about this channel's purpose and associated event(s).", color=constants.EMBED_COLOUR_OK)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return # if it was a Community Carrier, we're done and gone. Otherwise we keep looking.

        # now look for a match for the channel name in the carrier DB
        carrier_db.execute(f"SELECT * FROM carriers WHERE "
                        f"discordchannel = '{msg_channel_name}' ;")
        carrier_data = CarrierData(carrier_db.fetchone())

        if not carrier_data.discord_channel:
            print(f"/info failed, {interaction.channel} doesn't seem to be a carrier channel")
            # if there's no channel match, return an error
            embed = discord.Embed(description="Try again in a **🚛Trade Carriers** channel.", color=constants.EMBED_COLOUR_QU)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        else:
            print(f'Found data: {carrier_data}')
            embed = discord.Embed(title=f"Welcome to {carrier_data.carrier_long_name} ({carrier_data.carrier_identifier})", color=constants.EMBED_COLOUR_OK)
            embed = _add_common_embed_fields(embed, carrier_data, interaction)
            carrier_owner_obj = bot.get_user(carrier_data.ownerid)
            image_name = carrier_data.carrier_short_name + '.png'
            image_path = os.path.join(constants.IMAGE_PATH, image_name)
            thumbnail_file = discord.File(image_path, filename="image.png")
            embed.set_thumbnail(url="attachment://image.png")
            embed.set_author(name=carrier_owner_obj.name, icon_url=carrier_owner_obj.display_avatar)
            interaction.user = carrier_owner_obj
            return await interaction.response.send_message(file=thumbnail_file, embed=embed, ephemeral=True)


    # find what fleet carriers are owned by a user - private slash command
    @app_commands.command(name="owner",
                          description="Private command: Use with @User to find out what fleet carriers that user owns.")
    @app_commands.describe(owner='An @mention of the user whose Fleet Carriers you wish to list.')
    async def _owner(self, interaction: discord.Interaction, owner: discord.Member):

        try:
            # look for matches for the owner ID in the carrier DB
            carrier_list = find_carriers_mult(owner.id, CarrierDbFields.ownerid.name)

            if not carrier_list:
                await interaction.response.send_message(f"No carriers found owned by <@{owner.id}>", ephemeral=True)
                return print(f"No carriers found for owner {owner.id}")

            embed = discord.Embed(description=f"Showing registered Fleet Carriers owned by <@{owner.id}>:",
                                    color=constants.EMBED_COLOUR_OK)

            for carrier_data in carrier_list:
                embed.add_field(name=f"{carrier_data.carrier_long_name} ({carrier_data.carrier_identifier})",
                                value=f"Last Trade: <t:{carrier_data.lasttrade}> (<t:{carrier_data.lasttrade}:R>)",
                                inline=False)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except TypeError as e:
            print('Error: {}'.format(e))


    """
    Community Carrier search functions
    TODO: update to slash commands
    """


    # list all community carriers
    @commands.command(name='cc_list', help='List all Community Channels.')
    @commands.has_any_role(cmentor_role(), admin_role())
    async def cc_list(self, ctx):

        carrier_db.execute(f"SELECT * FROM community_carriers")
        community_carriers = [CommunityCarrierData(carrier) for carrier in carrier_db.fetchall()]

        def chunk(chunk_list, max_size=10):
            """
            Take an input list, and an expected max_size.

            :returns: A chunked list that is yielded back to the caller
            :rtype: iterator
            """
            for i in range(0, len(chunk_list), max_size):
                yield chunk_list[i:i + max_size]

        def validate_response(react, user):
            return user == ctx.author and str(react.emoji) in ["◀️", "❌", "▶️"]
            # This makes sure nobody except the command sender can interact with the "menu"

        # TODO: should pages just be a list of embed_fields we want to add?
        pages = [page for page in chunk(community_carriers)]

        max_pages = len(pages)
        current_page = 1

        embed = discord.Embed(title=f"{len(community_carriers)} Registered Community Carriers Page:#{current_page} of {max_pages}")
        count = 0   # Track the overall count for all carriers
        # Go populate page 0 by default
        for community_carriers in pages[0]:
            count += 1
            embed.add_field(name="\u200b",
                            value=f"{count}: <@{community_carriers.owner_id}> owns <#{community_carriers.channel_id}>, <@&{community_carriers.role_id}>", inline=False)
        # Now go send it and wait on a reaction
        message = await ctx.send(embed=embed)

        await message.add_reaction("❌")
        # From page 0 we can only go forwards
        if not current_page == max_pages: await message.add_reaction("▶️")

        # 60 seconds time out gets raised by Asyncio
        while True:
            try:
                reaction, user = await bot.wait_for('reaction_add', timeout=60, check=validate_response)
                if str(reaction.emoji) == "❌":
                    print(f'Closed list community channel request by: {ctx.author}')
                    embed = discord.Embed(description=f'Closed the active Community Channel list.', color=constants.EMBED_COLOUR_OK)
                    await ctx.send(embed=embed)
                    await message.delete()
                    await ctx.message.delete()
                    return

                elif str(reaction.emoji) == "▶️" and current_page != max_pages:
                    print(f'{ctx.author} requested to go forward a page.')
                    current_page += 1   # Forward a page
                    new_embed = discord.Embed(title=f"{len(community_carriers)} Registered Community Channels Page:{current_page}")
                    for community_carriers in pages[current_page-1]:
                        # Page -1 as humans think page 1, 2, but python thinks 0, 1, 2
                        count += 1
                        new_embed.add_field(name="\u200b",
                                            value=f"{count}: <@{community_carriers.owner_id}> owns <#{community_carriers.channel_id}>, <@&{community_carriers.role_id}>", inline=False)

                    await message.edit(embed=new_embed)

                    # Ok now we can go back, check if we can also go forwards still
                    if current_page == max_pages:
                        await message.clear_reaction("▶️")

                    await message.remove_reaction(reaction, user)
                    await message.add_reaction("◀️")

                elif str(reaction.emoji) == "◀️" and current_page > 1:
                    print(f'{ctx.author} requested to go back a page.')
                    current_page -= 1   # Go back a page

                    new_embed = discord.Embed(title=f"{len(community_carriers)} Registered Community Channels Page:{current_page}")
                    # Start by counting back however many carriers are in the current page, minus the new page, that way
                    # when we start a 3rd page we don't end up in problems
                    count -= len(pages[current_page - 1])
                    count -= len(pages[current_page])

                    for community_carriers in pages[current_page - 1]:
                        # Page -1 as humans think page 1, 2, but python thinks 0, 1, 2
                        count += 1
                        new_embed.add_field(name="\u200b",
                                            value=f"{count}: <@{community_carriers.owner_id}> owns <#{community_carriers.channel_id}>, <@&{community_carriers.role_id}>", inline=False)

                    await message.edit(embed=new_embed)
                    # Ok now we can go forwards, check if we can also go backwards still
                    if current_page == 1:
                        await message.clear_reaction("◀️")

                    await message.remove_reaction(reaction, user)
                    await message.add_reaction("▶️")
                else:
                    # It should be impossible to hit this part, but lets gate it just in case.
                    print(f'HAL9000 error: {ctx.author} ended in a random state while trying to handle: {reaction.emoji} '
                        f'and on page: {current_page}.')
                    # HAl-9000 error response.
                    error_embed = discord.Embed(title=f"I'm sorry {ctx.author}, I'm afraid I can't do that.")
                    await message.edit(embed=error_embed)
                    await message.remove_reaction(reaction, user)

            except asyncio.TimeoutError:
                if ctx.fetch_message(message.id) and ctx.fetch_message(ctx.message.id):
                    print(f'Timeout hit during community channel request by: {ctx.author}')
                    embed = discord.Embed(description=f'Closed the active community channel list request from {ctx.author} due to no input in 60 seconds.', color=constants.EMBED_COLOUR_QU)
                    await ctx.send(embed=embed)
                    await message.delete()
                    await ctx.message.delete()
                    break
                else:
                    return


    # find a community carrier channel by owner
    @commands.command(name='cc_owner', help='Search for an owner by @ mention in the Community Carrier database.\n'
                                'Format: m.cc_owner @owner\n')
    @commands.has_any_role(cmentor_role(), admin_role())
    async def cc_owner(self, ctx, owner: discord.Member):

        community_carrier_data = find_community_carrier(owner.id, CCDbFields.ownerid.name)
        if community_carrier_data:
            # TODO: this should be fetchone() not fetchall but I can't make it work otherwise
            for community_carrier in community_carrier_data:
                print(f"Found data: {community_carrier.owner_id} owner of {community_carrier.channel_id}")
                await ctx.send(f"User {owner.display_name} is registered as a Community Carrier with channel <#{community_carrier.channel_id}>")
                return
        else:
            await ctx.send(f"No Community Carrier registered to {owner.display_name}")


