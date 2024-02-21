"""
Commands relating to carrier stock tracking.

"""

# libraries
import asyncio
import json
import re
import requests
from texttable import Texttable # TODO: remove this dependency

# discord.py
import discord
from discord.ext import commands

# local constants
import ptn.missionalertbot.constants as constants
from ptn.missionalertbot.constants import bot

# local modules
from ptn.missionalertbot.modules.StockHelpers import chunk, inara_fc_market_data, inara_find_fc_system, edsm_find_fc_system, save_carrier_data, \
    get_fc_stock, get_fccode



@bot.command(name='add_FC', help='Add a fleet carrier for stock tracking.\n'
                                 'FCCode: Carrier ID Code \n'
                                 'FCSys: Carrier current system, use "auto", "auto-edsm", or "auto-inara" to search. ("auto" uses edsm)\n'
                                 'FCName: The alias with which you want to refer to the carrier. Please use something '
                                 'simple like "orion" or "9oclock", as this is what you use to call the stock command!'
                                 '\n!!SYSTEMS WITH SPACES IN THE NAMES NEED TO BE "QUOTED LIKE THIS"!! ')
@commands.has_any_role('Bot Handler', 'Admin', 'Mod')
async def addFC(ctx, FCCode, FCSys, FCName):
    # Checking if FC is already in the list, and if FC name is in correct format
    # Stops if FC is already in list, or if incorrect name format
    matched = re.match("[a-zA-Z0-9][a-zA-Z0-9][a-zA-Z0-9]-[a-zA-Z0-9][a-zA-Z0-9][a-zA-Z0-9]", FCCode)
    isnt_match = not bool(matched)  # If it is NOT a match, we enter the Invalid FC Code condition

    if isnt_match:
        await ctx.send(f'Invalid Fleet Carrier Code format! Format should look like XXX-YYY')
        return
    elif FCCode.upper() in FCDATA.keys():
        await ctx.send(f'{FCCode} is a code that is already in the Carrier list!')
        return
    # iterate through our known carriers and check if the alias is already assigned.
    for fc_code, fc_data in FCDATA.items():
        if FCName.lower() in fc_data['FCName']:
            await ctx.send(f'{FCName} is an alias that is already in the alias list belonging to carrier {fc_code}!')
            return

    print(f'Format is good... Checking database...')

    search_data = None
    if FCSys == 'auto-inara':
        search_data = inara_find_fc_system(FCCode)
    elif FCSys == 'auto-edsm' or FCSys == 'auto':
        search_data = edsm_find_fc_system(FCCode)
    if search_data is False:
        await ctx.send(f'Could not find the FC system. please manually supply system name')
        return
    elif search_data is not None:
        FCSys = search_data['system']
    try:
        pmeters = {'systemName': FCSys, 'stationName': FCCode}
        r = requests.get('https://www.edsm.net/api-system-v1/stations/market', params=pmeters)
        mid = r.json()

        if r.text=='{}':
            await ctx.send(f'FC does not exist in the EDSM database, check to make sure the inputs are correct!')
            return
        else:
            await ctx.send(f'This FC is NOT a lie!')
    except:
        print("Failure getting edsm data")
        await ctx.send(f'Failed getting EDSM data, please try again.')
        return

    print(mid['marketId'])
    midstr = str(mid['marketId'])

    FCDATA[FCCode.upper()] = {'FCName': FCName.lower(), 'FCMid': midstr, 'FCSys': FCSys.lower()}
    save_carrier_data(FCDATA)

    await ctx.send(f'Added {FCCode} to the FC list, under reference name {FCName}')


@bot.command(name='APItest', help='Test EDSM API')
@commands.has_role('Bot Handler')
async def APITest(ctx, mark):
    await ctx.send('Testing API with given marketId')
    pmeters = {'marketId': mark}
    r = requests.get('https://www.edsm.net/api-system-v1/stations/market',params=pmeters)
    stn_data = r.json()

    com_data = stn_data['commodities']
    loc_data = stn_data['name']
    if com_data == []:
        await ctx.send(f"{stn_data['sName']} is empty!")
        return

    name_data = ["" for x in range(len(com_data))]
    stock_data = ["" for x in range(len(com_data))]
    dem_data = ["" for x in range(len(com_data))]

    for i in range(len(com_data)):
        name_data[i] = com_data[i]['name']
        stock_data[i] = com_data[i]['stock']
        dem_data[i] = com_data[i]['demand']

    print('Creating embed...')
    embed = discord.Embed(title=f"{stn_data['sName']} stock")
    embed.add_field(name = 'Commodity', value = name_data, inline = True)
    embed.add_field(name = 'Amount', value = stock_data, inline = True)
    embed.add_field(name = 'FC Location', value = loc_data, inline= True)
    print('Embed created!')
    print(name_data)

    await ctx.send(embed=embed)
    print('Embed sent!')


@bot.command(name='stock', help='Returns stock of a PTN carrier (carrier needs to be added first)\n'
                                'source: Optional argument, one of "edsm" or "inara". Defaults to "edsm".')
async def stock(ctx, fcname, source='edsm'):
    fccode = get_fccode(fcname)
    if fccode not in FCDATA:
        await ctx.send('The requested carrier is not in the list! Add carriers using the add_FC command!')
        return

    await ctx.send(f'Fetching stock levels for **{fcname} ({fccode})**')

    stn_data = get_fc_stock(fccode, source)
    if stn_data is False:
        await ctx.send(f"{fcname} has no current market data.")
        return

    com_data = stn_data['commodities']
    loc_data = stn_data['name']
    if com_data == []:
        await ctx.send(f"{fcname} has no current market data.")
        return

    table = Texttable()
    table.set_cols_align(["l", "r", "r"])
    table.set_cols_valign(["m", "m", "m"])
    table.set_cols_dtype(['t', 'i', 'i'])
    #table.set_deco(Texttable.HEADER | Texttable.HLINES)
    table.set_deco(Texttable.HEADER)
    table.header(["Commodity", "Amount", "Demand"])

    for com in com_data:
        if com['stock'] != 0 or com['demand'] != 0:
            table.add_row([com['name'], com['stock'], com['demand']])

    msg = "```%s```\n" % ( table.draw() )
    #print('Creating embed...')
    embed = discord.Embed()
    embed.add_field(name = f"{fcname} ({stn_data['sName']}) stock", value = msg, inline = False)
    embed.add_field(name = 'FC Location', value = loc_data, inline = False)
    embed.set_footer(text = f"Data last updated: {stn_data['market_updated']}\nNumbers out of wack? Ensure EDMC is running!")
    #print('Embed created!')
    await ctx.send(embed=embed)
    #print('Embed sent!')


@bot.command(name='del_FC', help='Delete a fleet carrier from the tracking database.\n'
                                 'FCCode: Carrier ID Code')
@commands.has_any_role('Bot Handler', 'Admin', 'Mod')
async def delFC(ctx, FCCode):
    FCCode = FCCode.upper()
    matched = re.match("[a-zA-Z0-9][a-zA-Z0-9][a-zA-Z0-9]-[a-zA-Z0-9][a-zA-Z0-9][a-zA-Z0-9]", FCCode)
    isnt_match = not bool(matched)  # If it is NOT a match, we enter the Invalid FC Code condition

    if isnt_match:
        await ctx.send(f'Invalid Fleet Carrier Code format! Format should look like XXX-YYY')
        return
    if FCCode in FCDATA.keys():
        fcname = FCDATA[FCCode]['FCName']
        FCDATA.pop(FCCode)
        save_carrier_data(FCDATA)
        await ctx.send(f'Carrier {fcname} ({FCCode}) has been removed from the list')


@bot.command(name='rename_FC', help='Rename a Fleet Carrier alias. \n'
                                    'FCCode: Carrier ID Code \n'
                                    'FCName: new name for the Carrier ')
@commands.has_any_role('Bot Handler', 'Admin', 'Mod')
async def renameFC(ctx, FCCode, FCName):
    FCCode = FCCode.upper()
    FCName = FCName.lower()

    matched = re.match("[a-zA-Z0-9][a-zA-Z0-9][a-zA-Z0-9]-[a-zA-Z0-9][a-zA-Z0-9][a-zA-Z0-9]", FCCode)
    isnt_match = not bool(matched)  # If it is NOT a match, we enter the Invalid FC Code condition

    if isnt_match:
        await ctx.send(f'Invalid Fleet Carrier Code format! Format should look like XXX-YYY')
        return
    if FCCode in FCDATA.keys():
        fcname_old = FCDATA[FCCode]['FCName']
        FCDATA[FCCode]['FCName'] = FCName
        save_carrier_data(FCDATA)
        await ctx.send(f'Carrier {fcname_old} ({FCCode}) has been renamed to {FCName}')


@bot.command(name='list', help='Lists all tracked carriers. \n'
                               'Filter: use "wmm" to show only wmm-tracked carriers.')
async def fclist(ctx, Filter=None):
    names = []
    for fc_code, fc_data in FCDATA.items():
        if Filter and 'wmm' not in fc_data:
            continue
        if 'wmm' in fc_data:
            names.append("%s (%s) - WMM" % ( fc_data['FCName'], fc_code))
        else:
            names.append("%s (%s)" % ( fc_data['FCName'], fc_code))
    if not names:
        names = ['No Fleet Carriers are being tracked, add one!']
    print('Listing active carriers')

    carriers = sorted(names)  # Joining the list with newline as the delimeter

    def validate_response(react, user):
        return user == ctx.author and str(react.emoji) in ["◀️", "▶️"]
        # This makes sure nobody except the command sender can interact with the "menu"

    pages = [page for page in chunk(carriers)]

    max_pages = len(pages)
    current_page = 1

    embed = discord.Embed(title=f"{len(carriers)} Tracked Fleet Carriers, Page: #{current_page} of {max_pages}")
    embed.add_field(name = 'Carrier Names', value = '\n'.join(pages[0]))

    # Now go send it and wait on a reaction
    message = await ctx.send(embed=embed)

    # From page 0 we can only go forwards
    if max_pages > 1:
        await message.add_reaction("▶️")

    # 60 seconds time out gets raised by Asyncio
    while True:
        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=60, check=validate_response)
            if str(reaction.emoji) == "▶️" and current_page != max_pages:

                print(f'{ctx.author} requested to go forward a page.')
                current_page += 1   # Forward a page
                new_embed = discord.Embed(title=f"{len(carriers)} Tracked Fleet Carriers, Page: #{current_page} of {max_pages}")
                new_embed.add_field(name='Carrier Names', value='\n'.join(pages[current_page-1]))
                await message.edit(embed=new_embed)

                await message.add_reaction("◀️")
                if current_page == 2:
                    await message.clear_reaction("▶️")
                    await message.add_reaction("▶️")
                elif current_page == max_pages:
                    await message.clear_reaction("▶️")
                else:
                    await message.remove_reaction(reaction, user)

            elif str(reaction.emoji) == "◀️" and current_page > 1:
                print(f'{ctx.author} requested to go back a page.')
                current_page -= 1   # Go back a page

                new_embed = discord.Embed(title=f"{len(carriers)} Tracked Fleet Carriers, Page: #{current_page} of {max_pages}")
                new_embed.add_field(name='Carrier Names', value='\n'.join(pages[current_page-1]))


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
            print(f'Timeout hit during carrier request by: {ctx.author}')
            await ctx.send(f'Closed the active carrier list request from: {ctx.author} due to no input in 60 seconds.')
            await message.delete()
            break