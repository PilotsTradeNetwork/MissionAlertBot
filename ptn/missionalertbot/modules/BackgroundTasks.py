"""
BackgroundTasks.py

"""

import sys

if __name__ == "__main__":
    # Prevent accidental independent execution of this file 
    print("This script should not be run independently. Please run it through application.py.")
    # Exit the script with an error code
    sys.exit(1)

# import libraries
import asyncio
from datetime import datetime, timezone, timedelta
import json
import traceback

# import discord
import discord
from discord import Forbidden
from discord.ext import tasks

# import local classes
from ptn.missionalertbot.classes.CarrierData import CarrierData
from ptn.missionalertbot.classes.MissionData import MissionData
from ptn.missionalertbot.classes.WMMData import WMMData

# import local constants
import ptn.missionalertbot.constants as constants
from ptn.missionalertbot.constants import get_reddit, reddit_channel, sub_reddit, bot_guild, certcarrier_role, rescarrier_role, \
    bot_spam_channel, cco_color_role, commodities_wmm, channel_cco_wmm_supplies, channel_wmm_stock

# import local modules
from ptn.missionalertbot.database.database import CarrierDbFields, carrier_db, mission_db, find_carrier, bot, _fetch_wmm_carriers, \
    _update_wmm_carrier, _update_carrier_capi
from ptn.missionalertbot.modules.helpers import clear_history
from ptn.missionalertbot.modules.StockHelpers import capi, get_fc_stock, chunk, notify_wmm_owner


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
            print(f"Processing carrier '{carrier_data.carrier_long_name}'. Last traded: {last_traded}")
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
                await spamchannel.send(f"Owner of {carrier_data.carrier_long_name} ({carrier_data.carrier_identifier}) with ID {carrier_data.ownerid} is invalid. "
                                        "Cannot process lasttrade_cron for this carrier.")
        print("All carriers have been processed.")
    except Exception as e:
        print(f"last trade cron failed: {e}")
        pass


# function to start WMM loop
async def start_wmm_task():
    if wmm_stock.is_running():
        print("def start_wmm_task: task is_running(), cannot start.")
        return False
    wmm_channel = bot.get_channel(channel_wmm_stock())
    ccochannel = bot.get_channel(channel_cco_wmm_supplies())
    print("Clearing last stock update message in #%s" % wmm_channel)
    await clear_history(wmm_channel)
    print("Starting WMM stock background task")
    message = await wmm_channel.send('⌛ WMM stock tracking initialized, preparing for update.')
    wmm_stock.start(message, wmm_channel, ccochannel)


# WMM loop
# TODO: introduce tracking of status and errors to bot-spam
@tasks.loop(seconds=30)
async def wmm_stock(message, wmm_channel, ccochannel):
    print("▶ Starting WMM stock check loop.")

    #print(f"wmm_stock function start")
    wmm_systems = []

    # retrieve all WMM carriers
    wmm_carriers = _fetch_wmm_carriers()

    carrier: WMMData

    # populate active WMM systems
    for carrier in wmm_carriers:
        if carrier.carrier_location not in wmm_systems:
            wmm_systems.append(carrier.carrier_location)

    # Message to send to the WMM channel if no carriers are being tracked
    # TODO: harmonise with MAB formats
    if wmm_systems == []:
        nofc = "WMM Stock: No Fleet Carriers are currently being tracked for WMM. Please add some to the list!"
        try:
            await message.edit(content=nofc)
        except:
            await clear_history(wmm_channel)
            await wmm_channel.send(nofc)
        return

    content = {}
    ccocontent = {}
    wmm_stock = {}
    wmm_station_stock = {}

    for carrier in wmm_carriers:
        print(f"Interrogating {carrier} for stock...")
        carrier_has_stock = False
        if carrier.capi:
            print(f"Calling CAPI for {carrier.carrier_name}")
            capi_response = capi(carrier.carrier_identifier)
            stn_data = capi_response.json()

            print(f"capi response: {capi_response.status_code}")
            if capi_response.status_code != 200:
                # TODO handle missing carriers, auth errors etc.
                print(f"Error from CAPI for {carrier.carrier_identifier}: {capi_response.status_code} - {stn_data}")
                if capi_response.status_code == 500:
                    # this is an internal stockbot api error, dont re-auth for this.
                    print(f"Internal stockbot API error, someone check the logs")
                    continue
                elif capi_response.status_code == 418:
                    # capi is down for maintenance.
                    await clear_history(wmm_channel)
                    message = f"Bleep Bloop: Frontier API is down for maintenance, unable to retrieve stocks for all carriers. Retrying in 60 seconds."
                    await wmm_channel.send(message)
                    await asyncio.sleep(60)
                    return
                elif capi_response.status_code == 400 or capi_response.status_code == 401:
                    print(f"cAPI auth failed for {carrier.carrier_name}")

                    # User needs to re-auth. (400 = EGS, 401 = Expired Token)

                    # remove CAPI flag from databases
                    carrier.capi = 0
                    await _update_wmm_carrier(carrier)
                    await _update_carrier_capi(carrier.carrier_identifier, 0)

                    embed = discord.Embed(
                        description=f"<@{bot.user.id}> was unable to retrieve stock levels for {carrier.carrier_name} ({carrier.carrier_identifier}) from the Frontier API. "
                                    "Please use `/cco capi enable` to re-enable authentication for this fleet carrier. Inara will be used to fetch stock levels until cAPI is re-enabled.",
                        color = constants.EMBED_COLOUR_WARNING
                    )

                    message = f"<@{carrier.carrier_owner} Unable to send you a direct message relating to WMM tracking status. " \
                              f"Your Frontier API authentication has expired for {carrier.carrier_name} ({carrier.carrier_identifier}). " \
                              f"Please enable direct messages from <@{bot.user.id}> and use `/cco capi enable` to proceed."

                    # notify the owner
                    await notify_wmm_owner(carrier, embed, message)
                    
                else:
                    # all other unknown errors.
                    print(f"Unknown error from CAPI, see above for details.")
                    continue
            else:
                carrier_name = f"**{carrier.carrier_name} ({carrier.carrier_identifier})**"
                market_updated = ''

        # this catches the case where we remove the cAPI flag above if auth fails.
        if not carrier.capi:
            stn_data = get_fc_stock(carrier.carrier_identifier, 'inara')
            if not stn_data:
                print(f"no inara market data for {carrier.carrier_identifier}")
                continue
            carrier_name = stn_data['full_name'].upper()
            stn_data['currentStarSystem'] = stn_data['name'].title()
            stn_data['market'] = {'commodities': stn_data['commodities']}
            try:
                utc_time = datetime.strptime(stn_data['market_updated'].split('(')[1][0:-1], "%d %b %Y, %I:%M%p")
                market_updated = "(As of <t:%d:R>)" % utc_time.timestamp()
            except:
                market_updated = "(As of %s)" % stn_data['market_updated']
                pass
        if 'market' not in stn_data:
            print(f"No market data for {carrier.carrier_identifier}")
            continue

        # now we interrogate the carrier's stock levels
        com_data = stn_data['market']['commodities']
        print("Market data for %s: %s" % ( carrier.carrier_name, com_data ))

        # check for if market is empty
        if com_data == []:
            # TODO: how should this look?
            content[carrier.carrier_location].append("**%s** - %s (%s) has no current market data. please visit the carrier with EDMC running" % (
                carrier.carrier_name, stn_data['currentStarSystem'], carrier.carrier_location )
            )
            continue

        # iterate through commodities
        for com in com_data:
            # add carrier location to the wmm_stock list if not already there
            if carrier.carrier_location not in wmm_stock:
                wmm_stock[carrier.carrier_location] = []
            if stn_data['currentStarSystem'] not in wmm_station_stock:
                wmm_station_stock[stn_data['currentStarSystem']] = {}
            if carrier.carrier_location not in wmm_station_stock[stn_data['currentStarSystem']]:
                wmm_station_stock[stn_data['currentStarSystem']][carrier.carrier_location] = {}

            # add commodity to the master list if not already there
            if com['name'].title() not in commodities_wmm:
                continue

            # if carrier has stock of the commodity
            if com['stock'] != 0:
                carrier_has_stock = True
                if com['name'].lower() not in wmm_station_stock[stn_data['currentStarSystem']][carrier.carrier_location]:
                    wmm_station_stock[stn_data['currentStarSystem']][carrier.carrier_location][com['name'].lower()] = int(com['stock'])
                else:
                    wmm_station_stock[stn_data['currentStarSystem']][carrier.carrier_location][com['name'].lower()] += int(com['stock'])

                # if commodity stock is low 
                if int(com['stock']) < 1000:
                    wmm_stock[carrier.carrier_location].append("%s x %s - %s (%s) - **%s** - Price: %s - LOW STOCK %s" % (
                        com['name'], format(com['stock'], ','), stn_data['currentStarSystem'], carrier.carrier_location, carrier_name, format(com['buyPrice'], ','), market_updated )
                    )

                    # Notify the owner once per commodity per wmm_tracking session.
                    notification_status = json.loads(carrier.notification_status) if carrier.notification_status else []
                    if com['name'] not in notification_status:
                        print(f"Generating low stock warning for {carrier.carrier_name} to DM to owner")
                        
                        embed = discord.Embed(
                            description=f"📉 Your fleet carrier {carrier.carrier_name} ({carrier.carrier_identifier}) is low on %s - %s remaining." 
                                         % ( com['name'], com['stock'] ),
                            color=constants.EMBED_COLOUR_WARNING
                        )

                        message = f"<@{carrier.carrier_owner}>: Your fleet carrier {carrier.carrier_name} ({carrier.carrier_identifier}) is low on %s - %s remaining.\n\n" \
                                  f"*Please enable direct messages from <@{bot.user.id}> to receive these alerts via DM.*" % ( com['name'], com['stock'] )
                        
                        await notify_wmm_owner(carrier, embed, message)

                        # tell the db we've notified for this commodity
                        if not notification_status:
                            notification_status = []

                        notification_status.append(com['name'])
                        carrier.notification_status = notification_status

                        await _update_wmm_carrier(carrier)

                # has stock, not low
                else:
                    wmm_stock[carrier.carrier_location].append("%s x %s - %s (%s) - **%s** - Price: %s %s" % (
                        com['name'], format(com['stock'], ','), stn_data['currentStarSystem'].upper(), carrier.carrier_location, carrier_name, format(com['buyPrice'], ','), market_updated )
                    )

        # no stock at all
        if not carrier_has_stock:
            wmm_stock[carrier.carrier_location].append("**%s** - %s (%s) has no stock of any WMM commodity! %s" % (
                carrier_name, stn_data['currentStarSystem'].upper(), carrier.carrier_location, market_updated )
            )

    for system in wmm_systems:
        content[system] = []
        content[system].append('-')
        if system not in wmm_stock:
            content[system].append("Could not find any carriers with stock in %s" % system)
        else:
            for line in wmm_stock[system]:
                content[system].append(line)

    try:
        wmm_updated = "<t:%d:R>" % datetime.now().timestamp()
    except:
        wmm_updated = datetime.now().strftime("%d %b %Y %H:%M:%S")
        pass

    # clear message history
    await clear_history(wmm_channel)

    # for each station, use a new message.
    # and split messages over 10 lines.
    # each line is between 120-200 chars
    # using max: 2000 / 200 = 10
    for (system, stncontent) in content.items():
        if len(stncontent) == 1:
            # this station has no carriers, dont bother printing it.
            continue
        pages = [page for page in chunk(stncontent, 10)]
        for page in pages:
            page.insert(0, ':')
            await wmm_channel.send('\n'.join(page))

    footer = []
    footer.append(':')
    footer.append("-\nCarrier stocks last checked %s" % ( wmm_updated ))
    footer.append("Carriers with no timestamp are fetched from cAPI and are accurate to within an hour.")
    footer.append("Carriers with (As of ...) are fetched from Inara. Ensure EDMC is running to update stock levels!")
    await wmm_channel.send('\n'.join(footer))

    print("Current list of stations:")
    print(wmm_station_stock)

    for system in wmm_station_stock:
        ccocontent[system] = []
        for station in wmm_station_stock[system]:
            ccocontent[system].append('-')
            for commodity in commodities_wmm:
                if commodity.lower() not in wmm_station_stock[system][station]:
                    ccocontent[system].append(f"{commodity.title()} x NO STOCK !! - {system} ({station})")
                else:
                    ccocontent[system].append(f"{commodity.title()} x {format(wmm_station_stock[system][station][commodity.lower()], ',')} - {system} ({station})")

    # for each station, use a new message.
    # and split messages over 10 lines.
    # each line is roughly 50 chars
    # using max: 2000 / 50 = 40
    await clear_history(ccochannel)
    for (system, stncontent) in ccocontent.items():
        if len(stncontent) == 1:
            # this station has no carriers, dont bother printing it.
            continue
        pages = [page for page in chunk(stncontent, 40)]
        for page in pages:
            page.insert(0, ':')
            await ccochannel.send('\n'.join(page))

    # the following code allows us to change sleep time dynamically
    # waiting at least 10 seconds before checking constants.wmm_interval again
    # This also checks for the trigger to manually update.
    constants.wmm_slept_for = 0
    while constants.wmm_slept_for < constants.wmm_interval:
        # wmm_trigger is set by ;wmm_stock command
        if constants.wmm_trigger:
            print("Manual WMM stock refresh triggered.")
            constants.wmm_trigger = False
            constants.wmm_slept_for = constants.wmm_interval
        else:
            await asyncio.sleep(10)
            constants.wmm_slept_for = constants.wmm_slept_for + 10

@wmm_stock.after_loop
async def wmm_after_loop():
    if not wmm_stock.is_running() or wmm_stock.failed():
        print("wmm_stock after_loop(). task has failed.\n")

@wmm_stock.error
async def wmm_stock_error(error):
    if not wmm_stock.is_running() or wmm_stock.failed():
        print("wmm_stock error(). task has failed.\n")
    traceback.print_exc()