"""
BackgroundTasks.py

"""

# import libraries
import discord
from discord.ext import tasks
from datetime import datetime, timezone, timedelta

# import local classes
from ptn.missionalertbot.classes.CarrierData import CarrierData
from ptn.missionalertbot.classes.MissionData import MissionData

# import local constants
import ptn.missionalertbot.constants as constants
from ptn.missionalertbot.constants import get_reddit, reddit_channel, sub_reddit, bot_guild, certcarrier_role, rescarrier_role, bot_spam_channel, cco_color_role

# import local modules
from ptn.missionalertbot.database.database import CarrierDbFields, carrier_db, mission_db, find_carrier, bot




# monitor reddit comments
@tasks.loop(seconds=60)
async def _monitor_reddit_comments():
    print("Reddit monitor started")
    while True:
        try:
            # TODO: what happens if there's an error in this process, e.g. reddit is down?

            comment_channel = bot.get_channel(reddit_channel())
            # establish a comment stream to the subreddit using async praw
            reddit = await get_reddit()
            subreddit = await reddit.subreddit(sub_reddit())
            async for comment in subreddit.stream.comments(skip_existing=True):
                print(f"New reddit comment: {comment}. Is_submitter is {comment.is_submitter}")
                # ignore comments from the bot / post author
                if not comment.is_submitter:
                    # log some data
                    print(f"{comment.author} wrote:\n {comment.body}\nAt: {comment.permalink}\nIn: {comment.submission}")

                    # get a submission object so we can interrogate it for the parent post title
                    submission = await reddit.submission(comment.submission)

                    # lookup the parent post ID with the mission database
                    mission_db.execute(f"SELECT * FROM missions WHERE "
                                    f"reddit_post_id = '{comment.submission}' ")

                    print('DB command ran, go fetch the result')
                    mission_data = MissionData(mission_db.fetchone())

                    if not mission_data:
                        print("No match in mission DB, mission must be complete.")

                        embed = discord.Embed(title=f"{submission.title}",
                                            description=f"This mission is **COMPLETED**.\n\nComment by **{comment.author}**\n{comment.body}"
                                                        f"\n\nTo view this comment click here:\nhttps://www.reddit.com{comment.permalink}",
                                                        color=constants.EMBED_COLOUR_QU)

                    elif mission_data:
                        # mission is active, we'll get info from the db and ping the CCO
                        print(f'Found mission data: {mission_data}')

                        # now we need to lookup the carrier data in the db
                        carrier_data = find_carrier(mission_data.carrier_name, CarrierDbFields.longname.name)

                        # We can't easily moderate Reddit comments so we'll post it to a CCO-only channel

                        await comment_channel.send(f"<@{carrier_data.ownerid}>, your Reddit trade post has received a new comment:")
                        embed = discord.Embed(title=f"{submission.title}",
                                            description=f"This mission is **IN PROGRESS**.\n\nComment by **{comment.author}**\n{comment.body}"
                                                        f"\n\nTo view this comment click here:\nhttps://www.reddit.com{comment.permalink}",
                                                        color=constants.EMBED_COLOUR_REDDIT)
                    await comment_channel.send(embed=embed)
                    print("Sent comment to channel")
        except Exception as e:
            print(f"Error while monitoring {sub_reddit()} for comments: {e}")


# lasttrade task loop:
# Every 24 hours, check the timestamp of the last trade for all carriers and remove
# 'Certified Carrier' role from owner if there has been no trade for 28 days.
# If not already present, add 'Fleet Reserve' role to the owner.
@tasks.loop(hours=24)
async def lasttrade_cron():
    print(f"last trade cron running.")
    try:
        # get roles
        guild = bot.get_guild(bot_guild())
        cc_role = discord.utils.get(guild.roles, id=certcarrier_role())
        cc_color_role = discord.utils.get(guild.roles, id=cco_color_role())
        fr_role = discord.utils.get(guild.roles, id=rescarrier_role())
        # get spam channel
        spamchannel = bot.get_channel(bot_spam_channel())
        # calculate epoch for 28 days ago
        now = datetime.now(tz=timezone.utc)
        lasttrade_max = now - timedelta(days=28)
        # get carriers who last traded >28 days ago
        # for owners with multiple carriers look at only the most recently used
        carrier_db.execute(f'''
                            SELECT p_ID, shortname, ownerid, lasttrade
                            FROM carriers c1
                            WHERE lasttrade = (SELECT MAX(lasttrade) FROM carriers c2 WHERE c1.ownerid = c2.ownerid)
                            and lasttrade < {int(lasttrade_max.timestamp())}
                            ''')
        carriers = [CarrierData(carrier) for carrier in carrier_db.fetchall()]
        for carrier_data in carriers:
            # check roles on owners, remove/add as needed.
            last_traded = datetime.fromtimestamp(carrier_data.lasttrade).strftime('%Y-%m-%d %H:%M:%S')
            print(f"Processing carrier '{carrier_data.carrier_short_name}'. Last traded: {last_traded}")
            owner = guild.get_member(carrier_data.ownerid)
            if owner:
                if cc_role in owner.roles:
                    print(f"{owner.name} has the Certified Carrier role, removing.")
                    await owner.remove_roles(cc_role)
                    await spamchannel.send(f"{owner.name} has been removed from the Certified Carrier role due to inactivity.")
                    # notify by DM
                    owner_dm = await bot.fetch_user(carrier_data.ownerid)
                    await owner_dm.send(f"Ahoy CMDR! Your last PTN Fleet Carrier trade was more than 28 days ago at {last_traded} so you have been automatically marked as inactive and placed in the PTN Fleet Reserve. You can visit <#939919613209223270> or use `/cco active` to **mark yourself as active and return to trading**. o7 CMDR!")
                    print(f"Notified {owner.name} by DM.")
                if cc_color_role in owner.roles:
                    print(f"{owner.name} has the CCO Color role, removing.")
                    await owner.remove_roles(cc_color_role)
                if fr_role not in owner.roles:
                    print(f"{owner.name} does not have the Fleet Reserve role, adding.")
                    await owner.add_roles(fr_role)
                    await spamchannel.send(f"{owner.name} has been added to the Fleet Reserve role.")
            else:
                print(f"Carrier owner id {carrier_data.ownerid} is invalid, skipping.")
                await spamchannel.send(f"Owner of {carrier_data.carrier_short_name} with ID {carrier_data.ownerid} is invalid. "
                                        "Cannot process lasttrade_cron for this carrier.")
        print("All carriers have been processed.")
    except Exception as e:
        print(f"last trade cron failed: {e}")
        pass