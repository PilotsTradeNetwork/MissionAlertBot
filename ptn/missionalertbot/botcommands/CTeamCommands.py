"""
Cog for Community Team commands

"""

# import libaries
import os
import traceback

# import discord.py
import discord
from discord import Forbidden
from discord import app_commands
from discord.ext import commands

# import local classes
from ptn.missionalertbot.classes.CommunityCarrierData import CommunityCarrierData
from ptn.missionalertbot.classes.Views import RemoveCCView, SendNoticeModal, ConfirmRemoveRoleView, ConfirmRenameCC

# import local constants
import ptn.missionalertbot.constants as constants
from ptn.missionalertbot.constants import bot, cmentor_role, admin_role, cc_role, cc_cat, archive_cat, bot_spam_channel, cpillar_role, mod_role, \
    roleapps_channel, verified_role, fc_complete_emoji, event_organiser_role

# import local modules
from ptn.missionalertbot.database.database import carrier_db
from ptn.missionalertbot.modules.ErrorHandler import on_app_command_error, GenericError, on_generic_error, CustomError
from ptn.missionalertbot.modules.helpers import check_roles, _regex_alphanumeric_with_hyphens, _cc_owner_check, _cc_role_create_check, \
    _cc_create_channel, _cc_role_create, _cc_assign_permissions, _cc_db_enter, _remove_cc_role_from_owner, _cc_role_delete, _openclose_community_channel, \
    _community_channel_owner_check, check_command_channel, _cc_name_string_check
from ptn.missionalertbot.modules.Embeds import _generate_cc_notice_embed, verified_member_embed, event_organiser_embed, role_granted_embed, role_already_embed, \
    confirm_remove_role_embed, dm_forbidden_embed


"""
CTeam app commands - cannot be placed in the Cog

Uses bot.tree instead of app_commands

Send CC Notice
Edit CC Notice
Upload CC Thumb
Verify Member
Event Organiser
"""

@bot.tree.context_menu(name='Verify Member')
@check_roles([cmentor_role(), admin_role(), mod_role()])
@check_command_channel(roleapps_channel())
async def verify_member(interaction:  discord.Interaction, message: discord.Message):
    print(f"verify_member called by {interaction.user.display_name} for {message.author.display_name}")

    embed = discord.Embed(
        description=f"⏳ Making <@{message.author.id}> a Verified Member...",
        color=constants.EMBED_COLOUR_QU
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

    spamchannel = bot.get_channel(bot_spam_channel())

    member = message.author
    member_roles = member.roles
    vm_role = discord.utils.get(interaction.guild.roles, id=verified_role())
    role = True if vm_role in member_roles else False

    if not role: # check whether they have the role already
        print("Member does not already have role")

        try:
            print(f"Giving {vm_role.name} role to {member.name}")
            await member.add_roles(vm_role)

            fc_complete_reaction = f"<:fc_complete:{fc_complete_emoji()}>"
            await message.add_reaction(fc_complete_reaction)
            
            # feed back to the command user
            embed, bot_spam_embed = role_granted_embed(interaction, member, message, vm_role)
            await interaction.edit_original_response(embed=embed)
            await spamchannel.send(embed=bot_spam_embed)

            try:
                # dm the target user
                print("Notifying target user")
                embed = verified_member_embed(message)
                await member.send(embed=embed)
            except Forbidden:
                print(f"Couldn't message {member}- DMs are blocked (403 Forbidden).")
                embed = dm_forbidden_embed(member)
                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            try:
                raise GenericError(e)
            except Exception as e:
                await on_generic_error(interaction, e)


    else:
        print("Member has role already")
        embed = role_already_embed(message.author, vm_role)
        await interaction.edit_original_response(embed=embed)


@bot.tree.context_menu(name='Toggle Event Organiser')
@check_roles([cmentor_role(), admin_role(), mod_role()])
async def toggle_event_organiser(interaction:  discord.Interaction, member: discord.Member):
    print(f"toggle_event_organiser called by {interaction.user.display_name} for {member.display_name}")

    embed = discord.Embed(
        description=f"⏳ Toggling <@&{event_organiser_role()}> role for <@{member.id}>...",
        color=constants.EMBED_COLOUR_QU
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

    spamchannel = bot.get_channel(bot_spam_channel())

    member_roles = member.roles
    eo_role = discord.utils.get(interaction.guild.roles, id=event_organiser_role())
    role = True if eo_role in member_roles else False

    if not role: # check whether they have the role already
        print("Member does not already have role, granting...")

        try:
            print(f"Giving {eo_role.name} role to {member.name}")
            await member.add_roles(eo_role)
         
            # feed back to the command user
            embed, bot_spam_embed = role_granted_embed(interaction, member, None, eo_role)
            await interaction.edit_original_response(embed=embed)
            await spamchannel.send(embed=bot_spam_embed)

            try:
                # dm the target user
                print("Notifying target user")
                embed = event_organiser_embed()
                await member.send(embed=embed)
            except Forbidden:
                print(f"Couldn't message {member}- DMs are blocked (403 Forbidden).")
                embed = dm_forbidden_embed(member)
                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            try:
                raise GenericError(e)
            except Exception as e:
                await on_generic_error(interaction, e)

    else:
        print("Member has role already, asking if user wants to remove...")
        view = ConfirmRemoveRoleView(member, eo_role)

        embed = confirm_remove_role_embed(member, eo_role)

        await interaction.edit_original_response(embed=embed, view=view)
        view.message = await interaction.original_response()


# send_notice app command - alternative to slash command, just noms a message like adroomba but via right click
@bot.tree.context_menu(name='Send CC Notice')
@check_roles([cmentor_role(), admin_role(), cc_role()])
async def send_cc_notice(interaction:  discord.Interaction, message: discord.Message):
    print(f"{interaction.user.name} used send context menu in {interaction.channel.name}")

    community_carrier = await _community_channel_owner_check(interaction)
    if not community_carrier: return

    try:
        embed, file = await _generate_cc_notice_embed(message.channel.id, message.author.display_name, message.author.display_avatar.url, None, message.content, None) # get the embed
        if message.author.id == interaction.user.id:
            heading = f"<@&{community_carrier.role_id}> New message from <@{interaction.user.id}>"
        else:
            heading = f"<@&{community_carrier.role_id}>: <@{interaction.user.id}> has forwarded a message from <@{message.author.id}>"

        # send the embed
        if file: # this "file" is the message thumbnail, if any
            await interaction.channel.send(f":bell: {heading} for <#{interaction.channel.id}> :bell:", file=file, embed=embed)
        else:
            await interaction.channel.send(f":bell: {heading} for <#{interaction.channel.id}> :bell:", embed=embed)

        if message.author.id == interaction.user.id: await message.delete() # you can send anyone's message using this interaction
                                                                            # this check protects the messages of random users from being deleted if sent
        embed = discord.Embed(description="Your notice has been sent.", color=constants.EMBED_COLOUR_OK)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"Sorry, I couldn't send your message. Reason: {e}", ephemeral=True)


# edit notice app command - edits an existing sent notice
@bot.tree.context_menu(name='Edit CC Notice')
@check_roles([cmentor_role(), admin_role(), cc_role()])
async def edit_cc_notice(interaction:  discord.Interaction, message: discord.Message):
    print(f"{interaction.user.name} used edit CC notice context menu in {interaction.channel.name}")

    # check we're in a CC channel and get the CC data
    community_carrier = await _community_channel_owner_check(interaction)
    if not community_carrier: return

    """
    Now we check the message that we've been given. It must:
    1. be by MAB
    2. have been originally authored by the interaction.user
    3. have characteristics of a send_notice message
    We can check 2 & 3 with the same string
    """
    if not message.author.id == bot.user.id or not f"New message from <@{interaction.user.id}>" in message.content:
        await interaction.response.send_message(embed=discord.Embed(description=f"❌ This does not appear to be a CC Notice message, or a CC Notice message authored by you.", color=constants.EMBED_COLOUR_ERROR), ephemeral=True)

    # Zhu'li, do the thing
    # call the sendnotice modal to take the message
    await interaction.response.send_modal(SendNoticeModal(community_carrier.role_id, message))

    print("Back from modal interaction")

    try: # this to avoid annoying thinking response remaining bug if user cancels on mobile
        await interaction.response.defer()
    finally:
        return


# app command to upload cc thumbnail
@bot.tree.context_menu(name='Upload CC Thumb')
@check_roles([cmentor_role(), admin_role(), cc_role()])
async def upload_cc_thumb(interaction:  discord.Interaction, message: discord.Message):
    # check we're in the CC channel
    if not await _community_channel_owner_check(interaction): return

    if message.attachments:
        for attachment in message.attachments: # there can only be one attachment per message
            await attachment.save(f'{constants.CC_IMAGE_PATH}/{interaction.channel.id}.png')
        await interaction.response.send_message(embed = discord.Embed(description="Image saved as Channel notice thumbnail. It should appear when you use `/send_notice`.", color=constants.EMBED_COLOUR_OK), ephemeral=True)
    else:
        # we'll be super lazy and use this as the offially mandated way to delete thumbnails 🤷‍♀️
        await interaction.response.send_message(embed = discord.Embed(description="No image found in this message. If you had an existing thumbnail, it has been removed.", color=constants.EMBED_COLOUR_ERROR), ephemeral=True)

        # see if there's already a thumbnail file
        if os.path.isfile(f"{constants.CC_IMAGE_PATH}/{interaction.channel.id}.png"):
            print(f"Found image file {constants.CC_IMAGE_PATH}/{interaction.channel.id}.png")
            try: # try to delete it
                os.remove(f"{constants.CC_IMAGE_PATH}/{interaction.channel.id}.png")
            except Exception as e:
                await interaction.followup.send(embed = discord.Embed(description=f"❌ {e}", color=constants.EMBED_COLOUR_ERROR), ephemeral=True)
    return


"""
COMMUNITY TEAM COMMANDS

/close_community_channel - community
/community_channel_help - community
/create_community_channel - community
/open_community_channel -community
/rename_community_channel - community
/remove_community_channel - community
/restore_community_channel - community
/send_notice - community
/thanks - community

"""


# initialise the Cog and error handler
class CTeamCommands(commands.Cog):
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
    Community channel commands
    """


    # slash command to create a new community channel from scratch
    @app_commands.command(name="create_community_channel",
                          description="Create a Community Channel linked to a specific user.",)
    @app_commands.describe(owner='An @mention of the member who will be the registered owner of the new channel.',
                           channel_name='The name you want the new channel to have.',
                           channel_emoji='Optional: pick an emoji to go at the start of the channel name.')
    @check_roles([cmentor_role(), admin_role()])
    async def _create_community_channel(self, interaction:  discord.Interaction, owner: discord.Member, channel_name: str, channel_emoji: str = None):
        print(f"{interaction.user.name} used /create_community_channel")
        print(f"Params: {owner} {channel_name} {channel_emoji}")

        new_channel_name = await _cc_name_string_check(interaction, channel_emoji, channel_name)

        # CHECK: user already owns a channel
        if not await _cc_owner_check(interaction, owner): return

        # get the CC category as a discord channel category object
        cc_category = discord.utils.get(interaction.guild.categories, id=cc_cat())
        archive_category = discord.utils.get(interaction.guild.categories, id=archive_cat())

        # check the role validity here so we can stop if needed
        if not await _cc_role_create_check(interaction, new_channel_name): return

        # CHECK: existing channels
        new_channel = discord.utils.get(interaction.guild.channels, name=new_channel_name)

        if new_channel:
            # check whether it's an existing CC channel
            if new_channel.category == cc_category:
                embed = discord.Embed(description=f"❌ A Community channel <#{new_channel.id}> already exists."
                                    f" Please choose a different name for your Community channel.", color=constants.EMBED_COLOUR_ERROR)
                return await interaction.response.send_message(embed=embed)

            # check whether it's an archived CC channel
            elif new_channel.category == archive_category:
                embed = discord.Embed(description=f"❌ A Community channel <#{new_channel.id}> already exists in the archives."
                                    f" Use `/restore_community_channel` in the channel to restore it.", color=constants.EMBED_COLOUR_ERROR)
                return await interaction.response.send_message(embed=embed)

            # the channel must exist with that name elsewhere on the server and so can't be used
            else:
                embed = discord.Embed(description=f"❌ A channel <#{new_channel.id}> already exists on the server"
                                    f" and does not appear to be a Community channel."
                                    f" Please choose a different name for your Community channel.", color=constants.EMBED_COLOUR_ERROR)
                return await interaction.response.send_message(embed=embed)

        else:
            # channel does not exist, create it
            new_channel = await _cc_create_channel(interaction, new_channel_name, cc_category)

        # create the role
        new_role = await _cc_role_create(interaction, new_channel_name)

        # assign channel permissions
        await _cc_assign_permissions(interaction, owner, new_channel)

        # enter into the db
        await _cc_db_enter(interaction, owner, new_channel, new_role)

        # add a note in bot_spam
        spamchannel = bot.get_channel(bot_spam_channel())

        embed = discord.Embed(
            description=f"{interaction.user} used `/create_community_channel` in <#{interaction.channel.id}> to add {owner.display_name} as a Community channel owner with channel <#{new_channel.id}>",
            color=constants.EMBED_COLOUR_OK
        )

        await spamchannel.send(embed=embed)

        return


    # slash command to restore an archived community channel
    @app_commands.command(name="restore_community_channel",
        description="Restore an archived Community Channel.")
    @app_commands.describe(owner='An @mention of the user to become the owner of the restored channel.')
    @check_roles([cmentor_role(), admin_role()])
    async def _restore_community_channel(self, interaction:  discord.Interaction, owner: discord.Member):

        # get the CC categories as discord channel category objects
        cc_category = discord.utils.get(interaction.guild.categories, id=cc_cat())
        archive_category = discord.utils.get(interaction.guild.categories, id=archive_cat())

        # check we're in an archived community channel
        if not interaction.channel.category == archive_category:
            embed = discord.Embed(description=f"❌ This command can only be used in an archived Community channel in the <#{archive_cat()}> category.", color=constants.EMBED_COLOUR_QU)
            return await interaction.response.send_message(embed=embed)

        # now prep the channel
        # CHECK: user already owns a channel
        if not await _cc_owner_check(interaction, owner): return

        # check the role validity here so we can stop if needed
        if not await _cc_role_create_check(interaction, interaction.channel.name): return

        # move the channel from the archive to the CC category
        try:
            await interaction.channel.edit(category=cc_category)
            embed = discord.Embed(description=f"<#{interaction.channel.id}> moved to <#{cc_cat()}>.", color=constants.EMBED_COLOUR_OK)
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            embed = discord.Embed(description=f"❌ {e}", color=constants.EMBED_COLOUR_ERROR)
            await interaction.response.send_message(embed=embed)
            raise EnvironmentError(f"Error moving channel: {e}")

        # create the role
        new_role = await _cc_role_create(interaction, interaction.channel.name)

        # assign channel permissions
        await _cc_assign_permissions(interaction, owner, interaction.channel)

        # enter into the db
        await _cc_db_enter(interaction, owner, interaction.channel, new_role)

        # add a note in bot_spam
        spamchannel = bot.get_channel(bot_spam_channel())

        embed = discord.Embed(
            description=f"{interaction.user} used `/restore_community_channel` in <#{interaction.channel.id}> and granted ownership to {owner.display_name}.",
            color=constants.EMBED_COLOUR_OK
        )

        await spamchannel.send(embed=embed)

        return


    # delete a Community Carrier
    @app_commands.command(name="remove_community_channel",
                    description="Retires a community channel.")
    @check_roles([cmentor_role(), admin_role()])
    async def _remove_community_channel(self, interaction:  discord.Interaction):

        print(f"{interaction.user.name} called `/remove_community_channel` command in {interaction.channel.name}")
        author = interaction.user # define author here so we can use it to check the interaction later
        print(f"{interaction.user} is {author.name} as {author.display_name}")


        # check if we're in a community channel
        carrier_db.execute(f"SELECT * FROM community_carriers WHERE "
                        f"channelid = {interaction.channel.id}")
        community_carrier = CommunityCarrierData(carrier_db.fetchone())
        # if not, we return a notice and then try the db purge action
        if not community_carrier:
            embed = discord.Embed(description=f"This does not appear to be a community channel. Running purge task instead.", color=constants.EMBED_COLOUR_ERROR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            # this purges database entries with invalid channel ids so users aren't stuck with ghost channels if e.g. it was manually deleted
            carrier_db.execute(f"SELECT * FROM community_carriers")
            community_carriers = [CommunityCarrierData(carrier) for carrier in carrier_db.fetchall()]
            for carrier in community_carriers:
                if not bot.get_channel(carrier.channel_id):
                    print(f"Could not find channel for owner {carrier.owner_id}, deleting from db")
                    embed = discord.Embed(description=f"Found invalid channel for <@{carrier.owner_id}>, removing from database."
                                                    f"\nRemoving <@&{cc_role()}> from <@{carrier.owner_id}>."
                                                    f"\nDeleting associated channel role.", color=constants.EMBED_COLOUR_QU)
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    try:
                        carrier_db.execute(f"DELETE FROM community_carriers WHERE channelid = {carrier.channel_id}")
                        owner = interaction.guild.get_member(carrier.owner_id)
                        embed = await _remove_cc_role_from_owner(interaction, owner) # this returns an embed but we'll only use it to pass into the next function
                        await _cc_role_delete(interaction, carrier.role_id, embed) # this returns an embed but we won't use it

                    except Exception as e:
                        await interaction.followup.send(e, ephemeral=True)
            return

        elif community_carrier:
            print(f"Found data: {community_carrier.owner_id} owner of {community_carrier.channel_id}")
            owner_id = community_carrier.owner_id
            owner = await bot.fetch_user(owner_id)
            channel_id = community_carrier.channel_id
            role_id = community_carrier.role_id

        embed = discord.Embed(title="Remove Community Channel",
                            description=f"This will:\n\n• Remove the <@&{cc_role()}> role from <@{owner_id}>\n"
                                        f"• Delete the associated role <@&{role_id}>\n"
                                        f"• Delete or Archive the channel <#{channel_id}>\n\n"
                                        f"• **Archived** channels are moved to the archive and remain accessible to Community Team members. "
                                        f"They can be re-activated at any time using `/restore_community_channel` in-channel.\n\n"
                                        f"• **WARNING**: *Deleted* channels are gone forever and can NOT be recovered.",
                            color=constants.EMBED_COLOUR_QU)

        view = RemoveCCView(author)

        await interaction.response.send_message(embed=embed, view=view)

        return


    # open a community channel (i.e. set non private)
    @app_commands.command(name="open_community_channel",
        description="Use in a Community Channel to open it to visitors (set it non-private).", )
    @check_roles([cmentor_role(), admin_role(), cc_role()]) # allow owners to open/close their own channels
    async def _open_community_channel(self, interaction:  discord.Interaction):
        print(f"{interaction.user.name} used /open_community_channel in {interaction.channel.name}")
        open = True
        await _openclose_community_channel(interaction, open)

    # close a community channel (i.e. set private)
    @app_commands.command(name="close_community_channel",
        description="Use in a Community Channel to close it to visitors (set it private).", )
    @check_roles([cmentor_role(), admin_role(), cc_role()]) # allow owners to open/close their own channels
    async def _close_community_channel(self, interaction:  discord.Interaction):
        print(f"{interaction.user.name} used /close_community_channel in {interaction.channel.name}")
        open = False
        await _openclose_community_channel(interaction, open)


    # rename a community channel and role
    @app_commands.command(name="rename_community_channel",
        description="Use in a Community Channel to change the name of its channel and associated role.", )
    @app_commands.describe(new_name='The updated name for this community channel/role.',
                           new_emoji='Optional: pick an emoji to go at the start of the channel/role name.')
    @check_roles([cmentor_role(), admin_role(), cc_role()]) # allow owners to open/close their own channels
    async def _rename_community_channel(self, interaction:  discord.Interaction, new_name: str, new_emoji: str = None):
        print(f"{interaction.user.name} used /rename_community_channel in {interaction.channel.name}")
        try:
            old_channel_name = interaction.channel.name

            embed = discord.Embed(
                description="⏳ Please wait a moment...",
                color=constants.EMBED_COLOUR_QU
            )
            await interaction.response.send_message(embed=embed, ephemeral=True) # tell the user we're working on it

            # check the user has authority to do this
            community_carrier = await _community_channel_owner_check(interaction)
            if not community_carrier:
                await interaction.delete_original_response()
                return

            # process the new channel/role name
            new_channel_name = await _cc_name_string_check(interaction, new_emoji, new_name)

            # check it's not in use
            existing_channel = discord.utils.get(interaction.guild.channels, name=new_channel_name)
            if existing_channel:
                error=f'<#{existing_channel.id}> already exists. Please choose another.'
                await interaction.delete_original_response()
                try:
                    raise CustomError(error)
                except Exception as e:
                    return await on_generic_error(interaction, e)
            existing_role = discord.utils.get(interaction.guild.roles, name=new_channel_name)
            if existing_role:
                error=f'<@&{existing_role.id}> already exists. Please choose another.'
                await interaction.delete_original_response()
                try:
                    raise CustomError(error)
                except Exception as e:
                    return await on_generic_error(interaction, e)

            # confirm user choice
            view = ConfirmRenameCC(community_carrier, old_channel_name, new_channel_name)

            embed = discord.Embed(
                title='Confirm Rename',
                description=f"`{old_channel_name}` ▶ `{new_channel_name}`",
                color=constants.EMBED_COLOUR_QU
            )
            await interaction.edit_original_response(embed=embed, view=view)
            view.message = await interaction.original_response()

        except Exception as e:
            await interaction.delete_original_response()
            traceback.print_exc()
            try:
                raise GenericError(e)
            except Exception as e:
                await on_generic_error(interaction, e)

    # send a notice from a Community Carrier owner to their 'crew' - this is the long form command using a modal
    @app_commands.command(name="send_notice",
        description="Private command: Used by Community Channel owners to send notices to their participants.", )
    @check_roles([cmentor_role(), admin_role(), cc_role()]) # allow all owners for now then restrict during command
    async def _send_notice(self, interaction:  discord.Interaction):
        print(f"{interaction.user.name} used /send_notice in {interaction.channel.name}")

        # check the user has authority to do this
        community_carrier = await _community_channel_owner_check(interaction)
        if not community_carrier: return

        # create a modal to take the message
        await interaction.response.send_modal(SendNoticeModal(community_carrier.role_id, None)) # the None parameter tells the modal we are sending, not editing

        print("Back from modal interaction")

        try: # this to avoid annoying thinking response remaining bug if user cancels on mobile
            await interaction.response.defer()
        finally:
            return


    # help for Community Channel users. TODO when we refactor we'll work on having proper custom help available in more depth
    # TODO: import from a text file?
    @app_commands.command(name="community_channel_help",
        description="Private command: get help with Community Channel commands and functions.", )
    @check_roles([cmentor_role(), admin_role(), cc_role(), cpillar_role()])
    async def _community_channel_help(self, interaction:  discord.Interaction):
        print(f"{interaction.user.name} used /community_channel_help")
        embed = discord.Embed(title="Community Channel Help",
                            # sorry Kutu I'm not wrapping this too eagerly
                            description=f"**Community Channel commands:**\n\nAll commands require the <@&{cmentor_role()}> role unless specified."
                            "\n\n:arrow_forward: `/create_community_channel`:\n"
                            "**USE IN**: anywhere (but please use it in the back rooms only!)\n"
                            "**REQUIRES:** a **user**, a **channel name**, and optionally an **emoji** to go at the beginning of the channel name.\n"
                            "**FUNCTION**: creates a new Community Channel.\n"
                            "Best practice for channel name is a single word or short phrase of no more than 30 characters. Disallowed characters "
                            "are automatically stripped and spaces are converted to hyphens. The emoji, if supplied, is put at the beginning of the channel's name. "
                            "Each CC is registered to one user, known as the channel 'owner', and each user can only have one CC registered to them. "
                            "CC owners get full permissions on their channel and can rename them, pin messages, delete any message, etc. "
                            "Creating a Community Channel also creates an associated role which users can sign up to for notices. "
                            f"CC owners, as well as <@&{cmentor_role()}>s, can use a special command to send notices to this role. "
                            "Note: **new Community Channels are set to private** when created."
                            "\n\n:arrow_forward: `/open_community channel`:\n"
                            "**USE IN**: the target Community Channel\n"
                            f"**USED BY**: channel owner or any <@&{cmentor_role()}>\n"
                            "**FUNCTION**: Makes the channel no longer private, i.e. open for any P.T.N. Pilot to view."
                            "\n\n:arrow_forward: `/close_community channel`:\n"
                            "**USE IN**: the target Community Channel\n"
                            f"**USED BY**: channel owner or any <@&{cmentor_role()}>\n"
                            "**FUNCTION**: Makes the channel private again, i.e. hidden from normal users' view. Community roles and the channel's owner can still see private Community Channels."
                            "\n\n:arrow_forward: `/remove_community_channel`:\n"
                            "**USE IN**: the target Community Channel\n"
                            "**FUNCTION**: Deletes or Archives the Community Channel.\n"
                            "Archived CCs remain visible to Community team roles. If the channel's erstwhile owner has one of these roles, they will also be able to see it, but will no longer be considered "
                            "its 'owner'. **This command also has a secondary purpose**: if used *outside a Community Channel*, it will scan the database and check for "
                            "any orphaned owners (owners with a channel which is no longer valid) and purge them from the database. Useful if a community channel has "
                            "been accidentally deleted or the database update failed upon the bot removing it."
                            "\n\n:arrow_forward: `/restore_community_channel`:\n"
                            "**USE IN**: target archived Community Channel\n"
                            "**REQUIRES:** a **user** to be the channel's new owner\n"
                            "**FUNCTION**: moves the archived Community Channel back to the Community Channel category and assigns it an owner. "
                            "As with newly created  Community Channels, restored channels are also set to private until 'opened'.",
                            color=constants.EMBED_COLOUR_QU)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        embed = discord.Embed(title="Community Channel Help",
                                # sorry Kutu I'm not wrapping this too eagerly
                                description="\n\n**Broadcast message commands:**"
                                f"\n\n:arrow_forward: `/send_notice`:\n"
                                "**USE IN**: the target Community Channel\n"
                                f"**USED BY**: channel owner or any <@&{cmentor_role()}>\n"
                                "**FUNCTION**: This command gives its user a pop-out form in which to type a message which will be sent to the channel as an embed, pinging the channel's "
                                "associated role in the process. The embed can be up to 4000 characters and can optionally include a title and an image: images have to be linked, not uploaded,"
                                " but you can upload them to Discord (anywhere, even in a DM or another server) and use the link from that. It will also "
                                "feature the name and avatar of the sending user, and, if set up (see below), a thumbnail image."
                                "\n\n:arrow_forward: **\"Send CC Notice\"** context menu command:\n"
                                "**USE ON**: any message in the target Community Channel\n"
                                f"**USED BY**: channel owner or any <@&{cmentor_role()}>\n"
                                "**FUNCTION**: Similar to the above, this sends a notice to the channel's associated role, but it can be "
                                "used *on a message* in the channel. To access it:\n> :mouse_three_button: **Right click** or :point_up_2: **long press** on any message in the channel\n"
                                "> :arrow_right: **Apps**\n> :arrow_right: **Send CC Notice**\n"
                                "If the message was sent by the command's user, it will be consumed by the bot and spat out with a role ping and helpful information appended. "
                                "If the message was sent by anyone else, it will not be deleted, but the bot will instead copy it."
                                "\n\n:arrow_forward: **\"Upload CC Thumb\"** context menu command:\n"
                                "**USE ON**: any message in the target Community Channel\n"
                                f"**USED BY**: channel owner or any <@&{cmentor_role()}>\n"
                                "**FUNCTION**: if the message contains an attached image, that image will be uploaded for use as a thumbnail on `/send_notice` embeds. "
                                "If not, any existing thumbnail will be deleted. To use it:\n> :mouse_three_button: **Right click** or :point_up_2: **long press** on any message in the channel\n"
                                "> :arrow_right: **Apps**\n> :arrow_right: **Upload CC Thumb**\n"
                                "\n:arrow_forward: **\"Edit CC Notice\"** context menu command:\n"
                                "**USED BY**: author of a CC notice message\n"
                                "**FUNCTION**: Edits (recreates from scratch) any CC Notice message sent by MAB *of which the user is the original author*."
                                "You may not edit messages you forward from another user, or CC Notices sent by another user. To use it:\n"
                                "> :mouse_three_button: **Right click** or :point_up_2: **long press** on a CC Notice message in the channel\n"
                                "> :arrow_right: **Apps**\n> :arrow_right: **Edit CC Notice**\n",
                                color=constants.EMBED_COLOUR_QU)
        await interaction.followup.send(embed=embed, ephemeral=True)


    # prints information about /nominate to current channel
    @app_commands.command(name="thanks",
        description="COMMUNITY TEAM ONLY: Display information about the /nominate command.", )
    @check_roles([cpillar_role(), cmentor_role(), admin_role(), mod_role()]) 
    async def _thanks(self, interaction:  discord.Interaction):
        print(f"/thanks called by {interaction.user} in {interaction.channel.name}")
        embed = discord.Embed(title=":heart: NOMINATE TO APPRECIATE :heart:",
                            description="Did someone **go out of their way to be helpful**? Use the </nominate:878304221118742578> "
                                        "command to help them be considered "
                                        f"for <@&{cpillar_role()}> and show your appreciation!", color=constants.EMBED_COLOUR_QU)
        embed.set_thumbnail(url='https://pilotstradenetwork.com/wp-content/uploads/2021/08/PTN_Discord_Icon.png')
        await interaction.response.send_message(embed=embed)