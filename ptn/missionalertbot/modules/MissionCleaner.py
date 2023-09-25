"""
MissionCleaner.py

Functions relating to mission clean-up.

Dependencies: constants, database, helpers

"""
# import libraries
import aiohttp
import asyncio
import random

# import discord.py
import discord
from discord import Webhook
from discord.errors import Forbidden, NotFound

# import local classes
from ptn.missionalertbot.classes.MissionData import MissionData
from ptn.missionalertbot.classes.MissionParams import MissionParams

# import local constants
import ptn.missionalertbot.constants as constants
from ptn.missionalertbot.constants import bot, bot_spam_channel, wine_alerts_loading_channel, wine_alerts_unloading_channel, trade_alerts_channel, get_reddit, sub_reddit, \
    reddit_flair_mission_stop, seconds_long, sub_reddit, mission_command_channel, ptn_logo_discord, reddit_flair_mission_start, channel_upvotes, trade_cat, seconds_very_short

# import local modules
from ptn.missionalertbot.database.database import backup_database, mission_db, missions_conn, find_carrier, CarrierDbFields
from ptn.missionalertbot.modules.DateString import get_final_delete_hammertime, get_mission_delete_hammertime
from ptn.missionalertbot.modules.helpers import lock_mission_channel, unlock_mission_channel, clean_up_pins, ChannelDefs, check_mission_channel_lock


"""
MISSION COMPLETE & CLEANUP
"""

# clean up a completed mission
async def _cleanup_completed_mission(interaction: discord.Interaction, mission_data, reddit_complete_text, discord_complete_embed: discord.Embed, message, is_complete):
    async with interaction.channel.typing():
        print("called _cleanup_completed_mission")

        status = "complete" if is_complete else "unable to complete"
        thumb = constants.ICON_FC_COMPLETE if is_complete else constants.ICON_FC_EMPTY
        print(status)

        try: # for backwards compatibility with missions created before the new column was added
            mission_params = mission_data.mission_params
            print("Found mission_params")
        except:
            print("No mission_params found, mission created pre-2.1.0?")

        if not mission_params:
            print("instantiating mission_params with channel defs")
            # instantiate a fresh instance of mission params with just channel_defs for channel definitions
            channel_defs = ChannelDefs(
                trade_cat(),
                trade_alerts_channel(),
                mission_command_channel(),
                channel_upvotes(),
                wine_alerts_loading_channel(),
                wine_alerts_unloading_channel(),
                sub_reddit(),
                reddit_flair_mission_start(),
                reddit_flair_mission_stop()
            )
            mission_params = MissionParams(dict(channel_defs = channel_defs))

        async with interaction.channel.typing():
            completed_mission_channel = bot.get_channel(mission_data.channel_id)
            mission_gen_channel = bot.get_channel(mission_params.channel_defs.mission_command_channel_actual)

            backup_database('missions')  # backup the missions database before going any further

            # delete Discord trade alert
            print("Delete Discord trade alert...")
            if mission_data.discord_alert_id and mission_data.discord_alert_id:
                try:  # try in case it's already been deleted, which doesn't matter to us in the slightest but we don't
                    # want it messing up the rest of the function

                    # first check if it's Wine, in which case it went to the booze cruise channel
                    if mission_data.commodity.title() == "Wine":
                        if mission_data.mission_type == 'load':
                            alert_channel = bot.get_channel(mission_params.channel_defs.wine_loading_channel_actual)
                        else:
                            alert_channel = bot.get_channel(mission_params.channel_defs.wine_unloading_channel_actual)
                    else:
                        alert_channel = bot.get_channel(mission_params.channel_defs.alerts_channel_actual)

                    discord_alert_id = mission_data.discord_alert_id

                    try:
                        msg = await alert_channel.fetch_message(discord_alert_id)
                        await msg.delete()
                    except:
                        print("No alert found, maybe user deleted it?")

                except:
                    print(f"Looks like this mission alert for {mission_data.carrier_name} was already deleted"
                        f" by someone else. We'll keep going anyway.")

                # send Discord carrier channel updates
                # try in case channel already deleted
                try:
                    discord_complete_embed.set_thumbnail(url=thumb)
                    await completed_mission_channel.send(embed=discord_complete_embed)
                except:
                    print(f"Unable to send completion message for {mission_data.carrier_name}, maybe channel deleted?")

            # add comment to Reddit post
            print("Add comment to Reddit post...")
            if mission_data.reddit_post_id:
                try:  # try in case Reddit is down
                    reddit_post_id = mission_data.reddit_post_id
                    reddit = await get_reddit()
                    await reddit.subreddit(mission_params.channel_defs.sub_reddit_actual)
                    submission = await reddit.submission(reddit_post_id)
                    await submission.reply(reddit_complete_text)
                    # mark original post as spoiler, change its flair
                    await submission.flair.select(mission_params.channel_defs.reddit_flair_completed)
                    await submission.mod.spoiler()
                except:
                    feedback_embed.add_field(name="Error", value="❌ Failed updating Reddit :(")


            # update webhooks
            print("Update sent webhooks...")
            try: # wrapping this in try for now to enable backwards compatibility. TODO: remove the 'try' wrapper after 2.1.0
                if mission_params.webhook_urls and mission_params.webhook_msg_ids and mission_params.webhook_jump_urls:
                    for webhook_url, webhook_msg_id, webhook_jump_url in zip(mission_params.webhook_urls, mission_params.webhook_msg_ids, mission_params.webhook_jump_urls):
                        try: 
                            async with aiohttp.ClientSession() as session:
                                print(f"Fetching webhook for {webhook_url} with jumpurl {webhook_jump_url} and ID {webhook_msg_id}")
                                webhook = Webhook.from_url(webhook_url, session=session, client=bot)
                                webhook_msg = await webhook.fetch_message(webhook_msg_id)

                                # edit the original message
                                print("Editing original webhook message...")
                                embed = discord.Embed(title="PTN TRADE MISSION CONCLUDED",
                                                        description=f"**{mission_params.carrier_data.carrier_long_name}** finished {mission_params.mission_type}ing "
                                                                    f"{mission_params.commodity_name} from **{mission_params.station}** in **{mission_params.system}**.",
                                                        color=constants.EMBED_COLOUR_QU)
                                embed.set_footer(text=f"Join {constants.DISCORD_INVITE_URL} for more trade opportunities.")
                                embed.set_thumbnail(url=ptn_logo_discord())
                                await webhook_msg.remove_attachments(webhook_msg.attachments)
                                await webhook_msg.edit(embed=embed)

                                reason = f"\n\n{message}" if not message == None else "" # TODO: change the reason to a separate embed or field

                                print("Sending webhook update message...")
                                # send a new message to update the target channel
                                embed = discord.Embed(title="PTN TRADE MISSION CONCLUDED",
                                                      description=f"The mission {webhook_jump_url} posted at <t:{mission_params.timestamp}:f> (<t:{mission_params.timestamp}:R>) "
                                                                  f"has been marked as {status} on the [PTN Discord]({constants.DISCORD_INVITE_URL}).{reason}",
                                                      color=constants.EMBED_COLOUR_OK)
                                await webhook.send(embed=embed, username='Pilots Trade Network', avatar_url=bot.user.avatar.url, wait=True)

                        except Exception as e:
                            print(f"Failed updating webhook message {webhook_jump_url} with URL {webhook_url}: {e}")
                            await feedback_embed.add_field(name="Error", value=f"❌ Failed updating webhook message {webhook_jump_url} with URL {webhook_url}: {e}")
            except: 
                print("No mission_params found to define webhooks, pre-2.1.0 mission?")

            # delete mission entry from db
            print("Remove from mission database...")
            mission_db.execute(f'''DELETE FROM missions WHERE carrier LIKE (?)''', ('%' + mission_data.carrier_name + '%',))
            missions_conn.commit()

            await clean_up_pins(completed_mission_channel)

            # command feedback
            print("Log usage in bot spam")
            spamchannel = bot.get_channel(bot_spam_channel())
            reason = f"\n\nReason given: `{message}`" if not message == None else ""
            embed = discord.Embed(title=f"Mission {status} for {mission_data.carrier_name}",
                                description=f"<@{interaction.user.id}> reported in <#{interaction.channel.id}> ({interaction.channel.name}).{reason}",
                                color=constants.EMBED_COLOUR_OK)
            embed.set_thumbnail(url=thumb)
            await spamchannel.send(embed=embed)

            if interaction.channel.id == mission_gen_channel.id: # tells us whether /cco complete was used or /mission complete
                print("Send feedback to the CCO")
                feedback_embed = discord.Embed(
                    title=f"Mission {status} for {mission_data.carrier_name}",
                    color=constants.EMBED_COLOUR_OK)
                feedback_embed.add_field(name="Explanation given", value=message, inline=True)
                feedback_embed.set_footer(text="Updated sent alerts and removed from mission list.")
                feedback_embed.set_thumbnail(url=thumb)
                await interaction.edit_original_response(embed=feedback_embed)

        # notify owner if not command user
        carrier_data = find_carrier(mission_data.carrier_name, CarrierDbFields.longname.name)
        if not interaction.user.id == carrier_data.ownerid:
            try:
                print("Notify carrier owner")
                # notify in channel - not sure this is needed anymore, leaving out for now
                # await interaction.channel.send(f"Notifying carrier owner: <@{carrier_data.ownerid}>")

                # notify by DM
                owner = await bot.fetch_user(carrier_data.ownerid)

                hammertime = get_mission_delete_hammertime()

                dm_embed = discord.Embed(
                    title=f"{carrier_data.carrier_long_name} MISSION {status.upper()}",
                    description=f"Ahoy CMDR! {interaction.user.display_name} has concluded the trade mission for your Fleet Carrier **{carrier_data.carrier_long_name}**. "
                                f"Its mission channel will be removed {hammertime} unless a new mission is started.",
                    color=constants.EMBED_COLOUR_QU
                    )
                dm_embed.set_thumbnail(url=thumb)
                if not message == None:
                    dm_embed.add_field(name="Explanation given", value=message, inline=True)
                await owner.send(embed=dm_embed)

            except Exception as e: # in case the user can't be DMed
                print(e)
                embed = discord.Embed(
                    description=f"Error sending mission complete DM to <@{carrier_data.ownerid}>: {e}",
                    color=constants.EMBED_COLOUR_ERROR
                )
                spamchannel.send(embed=embed)

    # remove channel
    await remove_carrier_channel(mission_data.channel_id, seconds_long())

    return


async def remove_carrier_channel(completed_mission_channel_id, seconds): # seconds is either 900 or 120 depending on scenario
    # get channel ID to remove
    delchannel = bot.get_channel(completed_mission_channel_id)
    spamchannel = bot.get_channel(bot_spam_channel())

    # start a timer
    print(f"Starting {seconds} second countdown for deletion of {delchannel}")
    await asyncio.sleep(seconds)
    print("Channel removal timer complete")

    try:
        # try to acquire a channel lock, if unsuccessful after a period of time, abort and throw up an error
        try:
            await asyncio.wait_for(lock_mission_channel(delchannel.name), timeout=120)
            embed = discord.Embed(
                description=f"🔒 Lock acquired for `{delchannel.name}` (<#{delchannel.id}>) pending automatic deletion following conclusion of {seconds}-second timer.",
                color=constants.EMBED_COLOUR_QU
            )
            spamchannel = bot.get_channel(bot_spam_channel())
            await spamchannel.send(embed=embed)
        except asyncio.TimeoutError:
            print(f"No channel lock available for {delchannel}")
            return await spamchannel.send(f"<@211891698551226368> WARNING: No channel lock available on {delchannel} after 120 seconds. Deletion aborted.")

        mission_gen_channel = bot.get_channel(mission_command_channel())
        print(mission_gen_channel.name, mission_gen_channel.id)

        hammertime = get_final_delete_hammertime()
        print("Warning mission gen channel")
        embed = discord.Embed (
            title=":warning: Channel lock engaged for channel cleanup :warning:",
            description=f"Deletion {hammertime} of <#{completed_mission_channel_id}>, channel will be temporarily locked.",
            color=constants.EMBED_COLOUR_RP
        )
        print("Sending warning message to mission gen")
        warning = await mission_gen_channel.send(embed=embed)

        async with mission_gen_channel.typing():

            """
            # this is clunky but we want to know if a channel lock is because it's about to be deleted
            
            global deletion_in_progress
            deletion_in_progress = True
            """

            # check whether channel is in-use for a new mission
            mission_db.execute(f"SELECT * FROM missions WHERE "
                            f"channelid = {completed_mission_channel_id}")
            mission_data = MissionData(mission_db.fetchone())
            print(f'Mission data from remove_carrier_channel: {mission_data}')

            if mission_data:
                # abort abort abort
                print(f'New mission underway in this channel, aborting removal')
            else:
                print(f"Proceeding with channel deletion for {delchannel.name}")
                # delete channel after a parting gift
                gif = random.choice(constants.boom_gifs)
                try:
                    await delchannel.send(gif)
                    await asyncio.sleep(seconds_very_short())
                    await delchannel.delete()
                    print(f'Deleted {delchannel}')
                    embed = discord.Embed(
                        description=f":put_litter_in_its_place: Deleted expired mission channel {delchannel.name}.",
                        color=constants.EMBED_COLOUR_OK
                    )
                    await spamchannel.send(embed=embed)
                except Forbidden:
                    raise EnvironmentError(f"Could not delete {delchannel}, reason: Bot does not have permission.")
                except NotFound:
                    print("Channel appears to have been deleted by someone else, we'll just continue on.")
                    embed = discord.Embed(
                        description=f"Channel {delchannel} could not be deleted because it doesn't exist.",
                        color=constants.EMBED_COLOUR_QU
                    )
                    await spamchannel.send(embed=embed)
    finally:
        try:
            # now release the channel lock
            print("Releasing channel lock...")
            locked = check_mission_channel_lock(delchannel.name)
            if locked:
                await unlock_mission_channel(delchannel.name)
                print("Channel lock released")
                embed = discord.Embed(
                    description=f"🔓 Released lock for `{delchannel.name}` (<#{delchannel.id}>) ",
                    color=constants.EMBED_COLOUR_OK
                )
                await spamchannel.send(embed=embed)
        except Exception as e:
            print(e)
        try: 
            print("Deleting warning message, if exists")
            await warning.delete()
        except Exception as e:
            print(e)
        return


async def check_trade_channels_on_startup():
    """
    This function is called on bot.on_ready() to clean up any channels
    that had their timer lost during bot stop/restart
    """
    # get all active channel IDs
    print("Fetching active mission channels from DB...")
    mission_db.execute("SELECT channelid FROM missions")
    rows = mission_db.fetchall()
    trade_category = bot.get_channel(trade_cat())
    active_channel_ids = [row['channelid'] for row in rows]

    # get trade category as channel object
    trade_category = bot.get_channel(trade_cat())

    spamchannel = bot.get_channel(bot_spam_channel())

    print(f"Checking against extant channels in {trade_category.name}...")

    # Create a list to store the channel deletion tasks
    deletion_tasks = []

    for channel in trade_category.channels:
        if channel.id not in active_channel_ids:
            embed = discord.Embed(
                description=f"🧹 Startup: {channel.name} <#{channel.id}> appears orphaned, marking for cleanup.",
                color=constants.EMBED_COLOUR_QU
            )
            await spamchannel.send(embed=embed)
            print(f"{channel.name} appears orphaned, marking for cleanup")
            # Append the channel deletion task to the list without awaiting it
            deletion_task = remove_carrier_channel(channel.id, seconds_long())
            deletion_tasks.append(deletion_task)

    # Wait for all deletion tasks to complete concurrently
    await asyncio.gather(*deletion_tasks)
    print("Complete.")
