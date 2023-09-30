"""
Define classes for Views used by Interactions

Depends on: constants, database, Embeds, ErrorHandler, helpers, MissionCleaner

"""

# import libraries
import os
from datetime import datetime

# import discord.py
import discord
from discord.ui import View, Modal

# import local constants
import ptn.missionalertbot.constants as constants
from ptn.missionalertbot.constants import seconds_long, o7_emoji, bot_spam_channel, bot

# import local modules
from ptn.missionalertbot.database.database import delete_nominee_from_db, delete_carrier_from_db, _update_carrier_details_in_database, find_carrier, CarrierDbFields, mission_db, missions_conn
from ptn.missionalertbot.modules.DateString import get_mission_delete_hammertime
from ptn.missionalertbot.modules.Embeds import _configure_all_carrier_detail_embed, _generate_cc_notice_embed, role_removed_embed, role_granted_embed
from ptn.missionalertbot.modules.ErrorHandler import GenericError, on_generic_error
from ptn.missionalertbot.modules.helpers import _remove_cc_manager
from ptn.missionalertbot.modules.MissionCleaner import _cleanup_completed_mission


# buttons for confirm role add
class ConfirmGrantRoleView(View):
    def __init__(self, member: discord.Member, roles, remove_roles = [], timeout=30):
        print("ConfirmGrantRoleView init")
        self.member = member
        self.roles = roles
        self.remove_roles = remove_roles
        self.spamchannel = bot.get_channel(bot_spam_channel())
        super().__init__(timeout=timeout)

    @discord.ui.button(label="Grant", style=discord.ButtonStyle.success, emoji="✅", custom_id="grant")
    async def grant_role_button(self, interaction, button):
        print(f"{interaction.user} confirms grant role")

        embed = discord.Embed(
            description="⏳ Please wait a moment...",
            color=constants.EMBED_COLOUR_QU
        )
        await interaction.response.edit_message(embed=embed, view=None) # tell the user we're working on it

        try:
            self.embeds = []
            self.spam_embeds = []
            await self.member.add_roles(*self.roles)
            for role in self.roles:
                embed, bot_spam_embed = role_granted_embed(interaction, self.member, None, role)
                self.embeds.append(embed)
                self.spam_embeds.append(bot_spam_embed)
            if self.remove_roles:
                await self.member.remove_roles(*self.remove_roles)
                for role in self.remove_roles:
                    embed, bot_spam_embed = role_removed_embed(interaction, self.member, role)
                    self.embeds.append(embed)
                    self.spam_embeds.append(bot_spam_embed)
            await self.message.edit(embeds=self.embeds, view=None)
            await self.spamchannel.send(embeds=self.spam_embeds)
        except Exception as e:
            try:
                raise GenericError(e)
            except Exception as e:
                await on_generic_error(interaction, e)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖", custom_id="cancel")
    async def cancel_grant_role_button(self, interaction, button):
        print(f"{interaction.user} cancelled grant role")
        embed = discord.Embed(
            description="Cancelled.",
            color=constants.EMBED_COLOUR_OK
        )
        self.embeds = [embed]
        return await interaction.response.edit_message(embed=embed, view=None)

    async def on_timeout(self):
        # remove buttons
        self.clear_items()

        if not self.embeds:
        # return a message to the user that the interaction has timed out
            timeout_embed = discord.Embed(
                description="Timed out.",
                color=constants.EMBED_COLOUR_ERROR
            )
            self.embeds = [timeout_embed]

        try:
            await self.message.edit(embeds=self.embeds, view=self)
        except Exception as e:
            print(e)


# buttons for confirm role removal
class ConfirmRemoveRoleView(View):
    def __init__(self, member: discord.Member, role, timeout=30):
        print("ConfirmRemoveRoleView init")
        self.member = member
        self.role = role
        self.spamchannel = bot.get_channel(bot_spam_channel())
        super().__init__(timeout=timeout)

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger, emoji="💥", custom_id="remove")
    async def remove_role_button(self, interaction, button):
        print(f"{interaction.user} confirms remove {self.role.name} role")

        embed = discord.Embed(
            description="⏳ Please wait a moment...",
            color=constants.EMBED_COLOUR_QU
        )
        await interaction.response.edit_message(embed=embed, view=None) # tell the user we're working on it

        try:
            await self.member.remove_roles(self.role)
            self.embed, spam_embed = role_removed_embed(interaction, self.member, self.role)
            await self.message.edit(embed=self.embed, view=None)
            await self.spamchannel.send(embed=spam_embed)
        except Exception as e:
            try:
                raise GenericError(e)
            except Exception as e:
                await on_generic_error(interaction, e)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖", custom_id="cancel")
    async def cancel_remove_role_button(self, interaction, button):
        print(f"{interaction.user} cancelled remove {self.role.name} role")
        self.embed = discord.Embed(
            description="Cancelled.",
            color=constants.EMBED_COLOUR_OK
        )
        return await interaction.response.edit_message(embed=self.embed, view=None)

    async def on_timeout(self):
        # remove buttons
        self.clear_items()

        if not self.embed:
        # return a message to the user that the interaction has timed out
            timeout_embed = discord.Embed(
                description="Timed out.",
                color=constants.EMBED_COLOUR_ERROR
            )
            self.embed = timeout_embed

        try:
            await self.message.edit(embed=self.embed, view=self)
        except Exception as e:
            print(e)


# buttons for mission manual delete
class MissionDeleteView(View):
    def __init__(self, mission_data, author, embed, timeout=30):
        self.mission_data = mission_data
        self.author = author
        self.original_embed = embed
        super().__init__(timeout=timeout)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="⚠", custom_id="delete")
    async def delete_button_callback(self, interaction, button):
        spamchannel = bot.get_channel(bot_spam_channel())
        print(f"Trying manual mission delete for {self.mission_data.carrier_name}")
        try:
            mission_db.execute(f'''DELETE FROM missions WHERE carrier LIKE (?)''', ('%' + self.mission_data.carrier_name + '%',))
            missions_conn.commit()
            embed = discord.Embed(
                description=f"Deleted mission for {self.mission_data.carrier_name}.",
                color=constants.EMBED_COLOUR_OK
            )
            await interaction.response.edit_message(embed=embed, view=None)

            # notify bot spam
            embed = discord.Embed(
                description=f"<@{interaction.user.id}> used /admin_delete_mission for {self.mission_data.carrier_name}.",
                color=constants.EMBED_COLOUR_QU
            )
            await spamchannel.send(embed=embed)

        except Exception as e:
            print(f"Error deleting mission: {e}")
            embed = discord.Embed(
                description=f"Error deleting mission for {self.mission_data.carrier_name}: {e}",
                color=constants.EMBED_COLOUR_ERROR
            )
            await interaction.response.edit_message(embed=embed, view=None)

            # notify bot spam
            embed = discord.Embed(
                description=f"<@{interaction.user.id}> used /admin_delete_mission for {self.mission_data.carrier_name}.",
                color=constants.EMBED_COLOUR_QU
            )
            await spamchannel.send(embed=embed)

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.success, emoji="❌", custom_id='cancel')
    async def cancel_button_callback(self, interaction, button):
        embed = discord.Embed(
            description="Cancelled.",
            color=constants.EMBED_COLOUR_OK
        )
        return await interaction.response.edit_message(embed=embed, view=None)

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
        timeout_embed = discord.Embed(
            description="Timed out.",
            color=constants.EMBED_COLOUR_ERROR
        )

        # remove buttons
        self.clear_items()

        embeds = [self.original_embed, timeout_embed]

        try:
            await self.message.edit(embeds=embeds, view=self) # mission gen ends here
        except Exception as e:
            print(e)


# buttons for mission complete
class MissionCompleteView(View):
    def __init__(self, mission_data):
        self.mission_data = mission_data
        self.status_label = "Fully " + self.mission_data.mission_type + "ed"
        super().__init__()
        self.add_buttons()

    def add_buttons(self):
        complete_button = discord.ui.Button(label=self.status_label, style=discord.ButtonStyle.success, emoji="💰", custom_id="complete")
        failed_button = discord.ui.Button(label='Unable to complete', style=discord.ButtonStyle.secondary, emoji="🙁", custom_id="failed")
        cancel_button = discord.ui.Button(label='Cancel', style=discord.ButtonStyle.danger, emoji="❌", custom_id="cancel")

        async def complete(interaction: discord.Interaction):
            print(f"{interaction.user.display_name} confirms mission complete")
            is_complete = True

            embed = discord.Embed(
                description=f"Mission marked as complete <:o7:{o7_emoji()}>",
                color=constants.EMBED_COLOUR_OK
            )
            await interaction.response.edit_message(embed=embed, view=None)

            try:
                hammertime = get_mission_delete_hammertime()
                reddit_complete_text = f"    INCOMING WIDEBAND TRANSMISSION: P.T.N. CARRIER MISSION UPDATE\n\n**" \
                                    f"{self.mission_data.carrier_name}** mission complete. o7 CMDRs!\n\n\n\n*Reported on " \
                                    f"PTN Discord by {interaction.user.display_name}*"
                discord_complete_embed = discord.Embed(
                    title=f"{self.mission_data.carrier_name} MISSION COMPLETE",
                    description=f"<@{interaction.user.id}> reports mission complete! This mission channel will be removed {hammertime} unless a new mission is started.",
                    color=constants.EMBED_COLOUR_OK
                )
                print("Sending to _cleanup_completed_mission")
                message = None
                await _cleanup_completed_mission(interaction, self.mission_data, reddit_complete_text, discord_complete_embed, message, is_complete)
            except Exception as e:
                print(e)

        async def failed(interaction: discord.Interaction):
            await interaction.response.send_modal(MissionFailedModal(self.mission_data))

        async def cancel(interaction: discord.Interaction):
            embed = discord.Embed(
                title="Cancelled",
                description=f"Mission will remain listed <:o7:{o7_emoji()}>",
                color=constants.EMBED_COLOUR_OK
            )
            return await interaction.response.edit_message(embed=embed, view=None)

        complete_button.callback = complete
        failed_button.callback = failed
        cancel_button.callback = cancel
        self.add_item(complete_button)
        self.add_item(failed_button)
        self.add_item(cancel_button)


# Modal for Mission Failed on /mission_complete
class MissionFailedModal(Modal):
    def __init__(self, mission_data, title = 'Mission failed confirmation', timeout = None) -> None:
        self.mission_data = mission_data
        super().__init__(title=title, timeout=timeout)

    reason = discord.ui.TextInput(
        label='Mission failed reason',
        placeholder='Please give a short explanation as to why the mission cannot continue.',
        required=True,
        max_length=512,
    )

    async def on_submit(self, interaction: discord.Interaction):
        print(f"{interaction.user.display_name} confirms mission unable to complete for reason: {self.reason}")
        is_complete = False
        embed = discord.Embed(
            description=f"Mission marked as unable to complete <:o7:{o7_emoji()}>",
            color=constants.EMBED_COLOUR_OK
        )
        await interaction.response.edit_message(embed=embed, view=None)

        try:
            hammertime = get_mission_delete_hammertime()
            reddit_complete_text = f"    INCOMING WIDEBAND TRANSMISSION: P.T.N. CARRIER MISSION UPDATE\n\n**" \
                                f"{self.mission_data.carrier_name}** mission concluded (unable to complete). o7 CMDRs.\n\n\n\n*Reported on " \
                                f"PTN Discord by {interaction.user.display_name}*"
            discord_complete_embed = discord.Embed(
                title=f"{self.mission_data.carrier_name} MISSION CONCLUDED",
                description=f"<@{interaction.user.id}> reports this mission **cannot be completed** and has thus concluded. Reason:\n\n> {self.reason}."
                            f"\n\nThis mission channel will be removed {hammertime} unless a new mission is started.",
                color=constants.EMBED_COLOUR_ERROR
            )

            print("Sending to _cleanup_completed_mission")
            await _cleanup_completed_mission(interaction, self.mission_data, reddit_complete_text, discord_complete_embed, self.reason, is_complete)

        except Exception as e:
            print(e)


 # generic button for "Broadcast" function
class BroadcastView(View):
    def __init__(self, embed):
        self.embed = embed
        super().__init__()

    @discord.ui.button(label="Broadcast", style=discord.ButtonStyle.primary, emoji="📢", custom_id="broadcast")
    async def broadcast_button_callback(self, interaction, button):
        print(f"{interaction.user} broadcast their interaction in {interaction.channel.name}")
        try: # there's probably a better way to do this using an if statement
            self.clear_items()
            await interaction.response.edit_message(view=self)
            await interaction.delete_original_response()
        except:
            pass
        embed = self.embed
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        await interaction.channel.send(embed=embed)


# button interaction class for /nom_delete
class db_delete_View(View):
    def __init__(self, input_id, og_int): # call init to pass these arguments into self
        self.author = og_int.user # used to check button pusher is original interaction user
        self.input_id = input_id # the ID of the object to delete from the database
        self.called_from = og_int.command.name # used to check which command View was called from
        self.og_int = og_int
        super().__init__()

        if self.called_from == 'cp_delete_nominee_from_database':
            self.title, self.desc = "Nominee", f"<@{self.input_id}>"
        elif self.called_from == 'carrier_delete':
            self.title, self.desc = "Carrier", f"{self.input_id}"

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.author.id

    @discord.ui.button(label="Keep", style=discord.ButtonStyle.primary, emoji="✖", custom_id="cancel")
    async def keep_button_callback(self, interaction, button):
        embed = discord.Embed(title=f"Cancelled: Remove {self.title} from Database",
                        description=f"{self.title} {self.desc} was kept in the database.",
                        color=constants.EMBED_COLOUR_OK)
        self.clear_items()
        await interaction.response.edit_message(view=self, embed=embed)
        print("User cancelled their nom_delete command.")

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="💥", custom_id="delete")
    async def delete_button_callback(self, interaction, button):
        print("User wants to delete nomination.")
        # remove the database entry
        try:
            error_msg = await delete_nominee_from_db(self.input_id) if self.called_from == 'cp_delete_nominee_from_database' else await delete_carrier_from_db(self.input_id)
            if error_msg:
                return await interaction.followup.send(error_msg)

            print("User removed from nominees database.")
        except Exception as e:
            return await interaction.followup.send(f'Something went wrong, go tell the bot team "computer said: {e}"')
        embed = discord.Embed(title=f"Completed: Remove {self.title} from Database",
                        description=f"{self.title} {self.desc} was removed from database.",
                        color=constants.EMBED_COLOUR_OK)
        self.clear_items()
        await interaction.response.edit_message(view=self, embed=embed)


# button interaction classes for carrier_edit
class CarrierEditView(discord.ui.View):
    """
    Main trade view containing the:
        select menu, station|system modal, trade data modal
    If self.data is not set, create a dict with default keys set to ''
    """
    def __init__(self, carrier_data, orig_carrier_data):
        self.carrier_data = carrier_data
        self.orig_carrier_data = orig_carrier_data
        super().__init__()

    @discord.ui.button(label="Name|ID|ShortName", row=1, custom_id='name_id')
    async def name_callback(self, interaction, button):
        await interaction.response.send_modal(CarrierNameIDModal(title='Carrier Name | ID | ShortName', view=self))

    @discord.ui.button(label="Channel|Owner|LastTrade", row=1, custom_id='discord_data')
    async def discord_callback(self, interaction, button):
        await interaction.response.send_modal(CarrierDiscordDataModal(title='Channel | Owner | LastTrade', view=self))

    @discord.ui.button(label="Update Carrier", row=2, custom_id='update', style=discord.ButtonStyle.green)
    async def update_callback(self, interaction, button):
        if self.carrier_data == self.orig_carrier_data:
            embed = discord.Embed(title="No Edits made", color=constants.EMBED_COLOUR_ERROR)
            self.stop()
            return await interaction.response.edit_message(content=None, embed=embed, view=None)
        else:
            embed = discord.Embed(title="Review Carrier Changes", color=discord.Color.orange())
            embed = await _configure_all_carrier_detail_embed(embed, self.carrier_data)
            await interaction.response.edit_message(
                content=None,
                embed=embed,
                view=CarrierEditConfirmationView(self.carrier_data, self.orig_carrier_data)
            )

    @discord.ui.button(label="Cancel", row=2, custom_id='cancel', style=discord.ButtonStyle.red)
    async def quit_button_callback(self, interaction, button):
        embed = discord.Embed(title="Carrier Edit Cancelled", color=constants.EMBED_COLOUR_ERROR)
        await interaction.response.edit_message(content=None, embed=embed, view=None)
        print('Carrier Edit cancelled')
        self.stop()


class CarrierEditConfirmationView(discord.ui.View):
    """
    """
    def __init__(self, carrier_data, orig_carrier_data):
        self.carrier_data = carrier_data
        self.orig_carrier_data = orig_carrier_data
        super().__init__()

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def save_button_callback(self, interaction, button):
        await _update_carrier_details_in_database(self.carrier_data, self.orig_carrier_data.carrier_long_name)
        print(f'Carrier data now looks like:')
        print(f'\t Original: {self.orig_carrier_data}')
        print(f'\t Updated: {self.carrier_data}')
        if self.carrier_data.carrier_short_name != self.orig_carrier_data.carrier_short_name:
            print('Renaming the carriers image')
            os.rename(
                f'images/{self.orig_carrier_data.carrier_short_name}.png',
                f'images/{self.carrier_data.carrier_short_name}.png'
            )
            print(f'Carrier image renamed from: images/{self.orig_carrier_data.carrier_short_name}.png to '
                  f'images/{self.carrier_data.carrier_short_name}.png')

        updated_carrier_data = find_carrier(self.carrier_data.carrier_long_name, CarrierDbFields.longname.name)
        if updated_carrier_data:
            embed = discord.Embed(title=f"Reading the settings from DB:",
                                  description=f"Double check and re-run if incorrect the settings for old name: "
                                              f"{self.orig_carrier_data.carrier_long_name}",
                                  color=constants.EMBED_COLOUR_OK)
            embed = await _configure_all_carrier_detail_embed(embed, updated_carrier_data)
            self.stop()
            return await interaction.response.edit_message(content=None, view=None, embed=embed)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def quit_button_callback(self, interaction, button):
        embed = discord.Embed(title="Carrier Edit Cancelled", color=constants.EMBED_COLOUR_ERROR)
        await interaction.response.edit_message(content=None, embed=embed, view=None)
        print('Carrier Edit cancelled')
        self.stop()


# modal classes for carrier_edit
class CarrierNameIDModal(discord.ui.Modal):
    """
    """
    def __init__(self, title, view, timeout=None):
        self.view = view
        self.longname = discord.ui.TextInput(
            label = 'Long Name',
            custom_id = 'long_name',
            default = self.view.carrier_data.carrier_long_name
            )

        self.shortname = discord.ui.TextInput(
            label = 'Short Name',
            custom_id = 'short_name',
            default = self.view.carrier_data.carrier_short_name
            )

        self.cid = discord.ui.TextInput(
            label = 'Carrier Identifier',
            custom_id = 'c_id',
            default = self.view.carrier_data.carrier_identifier
            )
        super().__init__(title=title, timeout=timeout)
        self.add_item(self.longname)
        self.add_item(self.shortname)
        self.add_item(self.cid)

    async def on_submit(self, interaction):
        self.view.carrier_data.carrier_long_name = self.children[0].value.strip().upper()
        self.view.carrier_data.carrier_short_name = self.children[1].value.strip().lower()
        self.view.carrier_data.carrier_identifier = self.children[2].value.strip().upper()
        await interaction.response.edit_message(view=self.view)


class CarrierDiscordDataModal(discord.ui.Modal):
    """
    """
    def __init__(self, title, view, timeout=None):
        self.view = view

        self.discord_channel = discord.ui.TextInput(
            label = 'Discord Channel',
            custom_id = 'discord_channel',
            default = self.view.carrier_data.discord_channel
            )
        self.ownerid = discord.ui.TextInput(
            label = 'Owner ID',
            custom_id = 'owner_id',
            default = self.view.carrier_data.ownerid
            )
        self.lasttrade = discord.ui.TextInput(
            label = 'Last Trade',
            custom_id = 'last_trade',
            default = self.view.carrier_data.lasttrade
            )
        super().__init__(title=title, timeout=timeout)
        self.add_item(self.discord_channel)
        self.add_item(self.ownerid)
        self.add_item(self.lasttrade)

    async def on_submit(self, interaction):
        self.view.carrier_data.discord_channel = self.children[0].value.strip().lower()
        self.view.carrier_data.ownerid = self.children[1].value.strip()
        self.view.carrier_data.lasttrade = self.children[2].value.strip()

        await interaction.response.edit_message(view=self.view)


# button interaction class for /remove_community_channel
class RemoveCCView(View):
    def __init__(self, author): # call init to pass through the author variable
        self.author = author
        super().__init__()

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.author.id

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="💥", custom_id="delete")
    async def delete_button_callback(self, interaction, button):
        delete_channel = 1
        print("User wants to delete channel.")
        await _remove_cc_manager(interaction, delete_channel, self)

    @discord.ui.button(label="Archive", style=discord.ButtonStyle.primary, emoji="📂", custom_id="archive")
    async def archive_button_callback(self, interaction, button):
        delete_channel = 0
        print("User chose to archive channel.")
        await _remove_cc_manager(interaction, delete_channel, self)
        

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray, emoji="✖", custom_id="cancel")
    async def cancel_button_callback(self, interaction, button):
        embed = discord.Embed(title="Remove Community Channel",
                          description=f"Operation cancelled by user.",
                          color=constants.EMBED_COLOUR_OK)
        self.clear_items()
        await interaction.response.edit_message(view=self, embed=embed)
        print("User cancelled cc_del command.")


# modal for send_notice
class SendNoticeModal(Modal):
    def __init__(self, role_id, orginal_message, title = 'Send to Community Channel', timeout = None) -> None:
        self.role_id = role_id # we need to use the role_id in the response
        self.original_message = orginal_message # if used via edit, this will be a discord.Message object
        super().__init__(title=title, timeout=timeout)

    embedtitle = discord.ui.TextInput(
        label='Optional: give your message a title',
        placeholder='Leave blank for none.',
        required=False,
        max_length=256,
    )
    message = discord.ui.TextInput(
        label='Enter your message below.',
        style=discord.TextStyle.long,
        placeholder='Normal Discord markdown works, but mentions and custom emojis require full code.',
        required=True,
        max_length=4000,
    )
    image = discord.ui.TextInput(
        label='Optional: include an image',
        placeholder='Enter the image\'s URL or leave blank for none.',
        required=False,
        max_length=512,
    )

    async def on_submit(self, interaction: discord.Interaction):
        print(self.role_id)

        embed, file = await _generate_cc_notice_embed(interaction.channel.id, interaction.user.display_name, interaction.user.display_avatar.url, self.embedtitle, self.message, self.image)

        header_text = f":bell: <@&{self.role_id}> New message from <@{interaction.user.id}> for <#{interaction.channel.id}> :bell:"

        if self.original_message: # if the modal was called by the edit command, we'll edit instead of sending a new message
            print("Editing existing message")
            await self.original_message.edit(content=f"{header_text}\n*(edited {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')})*", embed=embed)
            await interaction.response.send_message(embed=discord.Embed(description=f"Message edited: {self.original_message.jump_url}", color=constants.EMBED_COLOUR_OK), ephemeral=True)

        else:
            await interaction.response.defer() # this gives us time to upload the file, but also responses and followups do not ping
            print("Sending new message")
            # send the message to the CC channel
            if file: # "file" is the thumbnail image
                await interaction.channel.send(header_text, file=file, embed=embed)
            else:
                await interaction.channel.send(header_text, embed=embed)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message(f'Oops! Something went wrong: {error}', ephemeral=True)