"""
A module for helper functions specifically for the Stock Tracker function.

Depends on: constants, ErrorHandler

"""

# import libraries
import json
from bs4 import BeautifulSoup
import requests
import traceback

# import discord.py

# import local classes
from ptn.missionalertbot.classes.CarrierData import CarrierData

# import local constants
import ptn.missionalertbot.constants as constants
from ptn.missionalertbot.constants import bot

# import local modules
from ptn.missionalertbot.modules.ErrorHandler import CommandChannelError, CommandRoleError, CustomError, GenericError, on_generic_error


def inara_find_fc_system(fcid):
    #print("Searching inara for carrier %s" % ( fcid ))
    URL = "https://inara.cz/elite/station-market/?search=%s" % (fcid)
    try:
        page = requests.get(URL, headers={'User-Agent': 'PTNStockBot'})
        soup = BeautifulSoup(page.content, "html.parser")
        header = soup.find_all("div", class_="headercontent")
        header_info = header[0].find("h2")
        carrier_system_info = header_info.find_all('a', href=True)
        carrier = carrier_system_info[0].text
        system = carrier_system_info[1].text

        if fcid in carrier:
            # print("Carrier: %s (stationid %s) is at system: %s" % (carrier.text, stationid['href'][9:-1], system))
            return {'system': system, 'stationid': carrier_system_info[0]['href'][15:-1], 'full_name': carrier}
        else:
            print("Could not find exact match, aborting inara search")
            return False
    except Exception as e:
        print("No results from inara for %s, aborting search. Error: %s" % (fcid, e))
        return False


"""def edsm_find_fc_system(fcid):
    #print("Searching edsm for carrier %s" % ( fcid ))
    URL = "https://www.edsm.net/en/search/stations/index/name/%s/sortBy/distanceSol/type/31" % ( fcid )
    try:
        page = requests.get(URL)
        soup = BeautifulSoup(page.content, "html.parser")
        results = soup.find("table", class_="table table-hover").find("tbody").find_all("a")
        carrier = results[0].get_text()
        system = results[1].get_text()
        market_updated = results[6].find("i").attrs.get("title")[27:]
        if fcid == carrier:
            #print("Carrier: %s is at system: %s" % (carrier, system))
            return {'system': system, 'market_updated': market_updated}
        else:
            #print("Could not find exact match, aborting inara search")
            return False
    except:
        print("No results from edsm for %s, aborting search." % fcid)
        return False"""


def inara_fc_market_data(fcid):
    print("Searching inara market data for station: %s " % ( fcid ))
    try:
        url = "https://inara.cz/elite/station-market/?search=%s" % (fcid)
        print(url)
        page = requests.get(url, headers={'User-Agent': 'PTNStockBot'})
        soup = BeautifulSoup(page.content, "html.parser")
        mainblock = soup.find_all('div', class_='mainblock')

        # Find carrier and system info
        header = soup.find_all("div", class_="headercontent")
        header_info = header[0].find("h2")
        carrier_system_info = header_info.find_all('a', href=True)
        carrier = carrier_system_info[0].text
        system = carrier_system_info[1].text

        # Find market info
        updated = soup.find("div", text="Market update").next_sibling.get_text()
        # main_content = soup.find('div', class_="maincontent0")
        table = mainblock[1].find('table')
        tbody = table.find("tbody")
        rows = tbody.find_all('tr')
        marketdata = []
        for row in rows:
            rowclass = row.attrs.get("class") or []
            if "subheader" in rowclass:
                continue
            cells = row.find_all("td")
            rn = cells[0].get_text()
            commodity = {
                'id': rn,
                'name': rn,
                'sellPrice': int(cells[1].get_text().replace('-', '0').replace(',', '').replace(' Cr', '')),
                'buyPrice': int(cells[3].get_text().replace('-', '0').replace(',', '').replace(' Cr', '')),
                'demand': int(cells[2].get_text().replace('-', '0').replace(',', '')),
                'stock': int(cells[4].get_text().replace('-', '0').replace(',', ''))
            }
            marketdata.append(commodity)
        data = {}
        data['name'] = system
        data['currentStarSystem'] = system
        data['full_name'] = carrier
        data['sName'] = fcid
        data['market_updated'] = updated
        data['commodities'] = marketdata
        return data
    except Exception as e:
        print("Exception getting inara data for carrier: %s" % fcid)
        print(e)
        traceback.print_exc()
        return False


"""def capi_fc_market_data(fcid):
    # get stocks from capi and format as inara data.
    capi_response = capi(fcid)
    if capi_response.status_code != 200:
        print(f"Error from CAPI for {fcid}: {capi_response.status_code}")
        return False
    stn_data = capi_response.json()
    if 'market' not in stn_data:
        print(f"No market data for {fcid}")
        return False
    stn_data['name'] = stn_data['currentStarSystem']
    stn_data['sName'] = fcid
    stn_data['market_updated'] = 'cAPI'
    if 'commodities' in stn_data['market']:
        # remove commodity from list if it has name 'Drones'.
        # this is a bug in the CAPI data.
        # then sort by name alphabetically.
        stn_data['commodities'] = sorted([c for c in stn_data['market']['commodities'] if c['name'] != 'Drones'], key=lambda d: d['name'])
    return stn_data"""


def get_fc_stock(fccode, source='inara'):
    if source == 'inara':
        stn_data = inara_fc_market_data(fccode)
        if not stn_data:
            return False
    elif source == 'capi':
        # stn_data = capi_fc_market_data(fccode)
        if not stn_data:
            return False
    return stn_data


"""def oauth_new(carrierid, force=False):
    pmeters = {'token': API_TOKEN}
    if force:
        pmeters['force'] = "true"
    r = requests.get(f"{API_HOST}/generate/{carrierid}",params=pmeters)
    return r


def capi(carrierid, dev=False):
    pmeters = {'token': API_TOKEN}
    if dev:
        pmeters['dev'] = "true"
    r = requests.get(f"{API_HOST}/capi/{carrierid}",params=pmeters)
    return r"""


# function taken from FCMS
def from_hex(mystr):
    try:
        return bytes.fromhex(mystr).decode('utf-8')
    except TypeError:
        return "Unregistered Carrier"
    except ValueError:
        return "Unregistered Carrier"