# Production variables
PROD_FLAIR_MISSION_START = "d01e6808-9235-11eb-9cc0-0eb650439ee7"
PROD_FLAIR_MISSION_STOP = "eea2d818-9235-11eb-b86f-0e50eec082f5"

PROD_DISCORD_GUILD = 800080948716503040 # PTN Discord server
PROD_TRADE_ALERTS_ID = 801798469189763073  # trade alerts channel ID for PTN main server
PROD_WINE_ALERTS_LOADING_ID = 849249916676603944 # booze alerts channel ID for PTN main server [loading]
PROD_WINE_ALERTS_UNLOADING_ID = 932918003639648306 # booze alerts channel ID for PTN main server [unloading]
PROD_SUB_REDDIT = "PilotsTradeNetwork"  # subreddit for live
PROD_CHANNEL_UPVOTES = 828279034387103744    # The ID for the updoots channel
PROD_REDDIT_CHANNEL = 878029150336720936 # the ID for the Reddit Comments channel
PROD_MISSION_CHANNEL = 822603169104265276    # The ID for the production mission channel
PROD_BOT_COMMAND_CHANNEL = 802523724674891826   # Bot backend commands are locked to a channel
PROD_ADMIN_BOT_CHANNEL = 895083178761547806 # bot command channel for admins only
PROD_BOT_SPAM_CHANNEL = 801258393205604372 # Certain bot logging messages go here
PROD_UPVOTE_EMOJI = 828287733227192403 # upvote emoji on live server
PROD_HAULER_ROLE = 875313960834965544 # hauler role ID on live server
PROD_CC_ROLE = 869340261057196072 # CC role on live server
PROD_CC_CAT = 877107894452117544 # Community Carrier category on live server
PROD_CTEAM_ROLE = 863521103434350613 # Commnunity Team role on live server
PROD_CERTCARRIER_ROLE = 947253075561824327 # Certified Carrier role on live server
PROD_RESCARRIER_ROLE = 947253075561824327 # Fleet Reserve Carrier role on live server
PROD_TRADE_CAT = 801558838414409738 # Trade Carrier category on live server
PROD_ARCHIVE_CAT = 821542402836660284 # Archive category on live server
PROD_SECONDS_SHORT = 120
PROD_SECONDS_LONG = 900

# Testing variables

# reddit flair IDs - testing sub
TEST_FLAIR_MISSION_START = "3cbb1ab6-8e8e-11eb-93a1-0e0f446bc1b7"
TEST_FLAIR_MISSION_STOP = "4242a2e2-8e8e-11eb-b443-0e664851dbff"

TEST_DISCORD_GUILD = 818174236480897055 # test Discord server
TEST_TRADE_ALERTS_ID = 843252609057423361  # trade alerts channel ID for PTN test server
TEST_WINE_ALERTS_LOADING_ID = 870425638127943700 # booze alerts channel ID for PTN main server [loading]
TEST_WINE_ALERTS_UNLOADING_ID = 870425638127943700 # booze alerts channel ID for PTN main server [unloading]
TEST_SUB_REDDIT = "PTNBotTesting"  # subreddit for testing
TEST_CHANNEL_UPVOTES = 839918504676294666    # The ID for the updoots channel on test
TEST_REDDIT_CHANNEL = 878029350933520484 # the ID for the Reddit Comments channel
TEST_MISSION_CHANNEL = 842138710651961364    # The ID for the production mission channel
TEST_BOT_COMMAND_CHANNEL = 842152343441375283   # Bot backend commands are locked to a channel
TEST_ADMIN_BOT_CHANNEL = 842152343441375283 # bot command channel for admins only
TEST_BOT_SPAM_CHANNEL = 842525081858867211 # Bot logging messages on the test server
TEST_UPVOTE_EMOJI = 849388681382068225 # upvote emoji on test server
TEST_HAULER_ROLE = 875439909102575647 # hauler role ID on test server
TEST_CC_ROLE = 877220476827619399 # CC role on test server
TEST_CC_CAT = 877108931699310592 # Community Carrier category on test server
TEST_CTEAM_ROLE = 877586763672072193 # Community Team role on test server
TEST_CERTCARRIER_ROLE = 947519773925859370 # Certified Carrier role on test server
TEST_RESCARRIER_ROLE = 947520552766152744 # Fleet Reserve Carrier role on test server
TEST_TRADE_CAT = 876569219259580436 # Trade Carrier category on live server
TEST_ARCHIVE_CAT = 877244591579992144 # Archive category on live server
TEST_SECONDS_SHORT = 5
TEST_SECONDS_LONG = 10

EMBED_COLOUR_LOADING = 0x80ffff         # blue
EMBED_COLOUR_UNLOADING = 0x80ff80       # green
EMBED_COLOUR_REDDIT = 0xff0000          # red
EMBED_COLOUR_DISCORD = 0x8080ff         # purple
EMBED_COLOUR_RP = 0xff00ff              # pink
EMBED_COLOUR_ERROR = 0x800000           # dark red
EMBED_COLOUR_QU = 0x80ffff              # same as loading
EMBED_COLOUR_OK = 0x80ff80              # same as unloading
EMBED_COLOUR_WORDPRESS = 0xff80ff       #pinkish

REDDIT_DISCORD_LINK_URL = \
    'https://www.reddit.com/r/PilotsTradeNetwork/comments/l0y7dk/pilots_trade_network_intergalactic_discord_server/'

WORDPRESS_DISCORD_LINK_URL = "https://discord.gg/AfdM4mhh"


def get_constant(production: bool):
    """
    Function takes a boolean and returns a dict containing the various parameters for that object.

    :param bool production: Whether you want the production or test environment variable
    :returns: The constant object. Returns are strings, with exception of Trade alerts which are ints
    :rtype: dict
    """
    if production:
        result = {
            'MISSION_START': PROD_FLAIR_MISSION_START,
            'MISSION_STOP': PROD_FLAIR_MISSION_STOP,
            'BOT_GUILD': PROD_DISCORD_GUILD,
            'SUB_REDDIT': PROD_SUB_REDDIT,
            'TRADE_ALERTS_ID': PROD_TRADE_ALERTS_ID,
            'WINE_ALERTS_LOADING_ID': PROD_WINE_ALERTS_LOADING_ID,
            'WINE_ALERTS_UNLOADING_ID': PROD_WINE_ALERTS_UNLOADING_ID,
            'CHANNEL_UPVOTES': PROD_CHANNEL_UPVOTES,
            'REDDIT_CHANNEL' : PROD_REDDIT_CHANNEL,
            'MISSION_CHANNEL': PROD_MISSION_CHANNEL,
            'BOT_COMMAND_CHANNEL': PROD_BOT_COMMAND_CHANNEL,
            'ADMIN_BOT_CHANNEL' : PROD_ADMIN_BOT_CHANNEL,
            'BOT_SPAM_CHANNEL': PROD_BOT_SPAM_CHANNEL,
            'UPVOTE_EMOJI': PROD_UPVOTE_EMOJI,
            'HAULER_ROLE' : PROD_HAULER_ROLE,
            'CC_ROLE' : PROD_CC_ROLE,
            'CC_CAT' : PROD_CC_CAT,
            'CTEAM_ROLE' : PROD_CTEAM_ROLE,
            'CERTCARRIER_ROLE' : PROD_CERTCARRIER_ROLE,
            'RESCARRIER_ROLE' : PROD_RESCARRIER_ROLE,
            'TRADE_CAT' : PROD_TRADE_CAT,
            'ARCHIVE_CAT' : PROD_ARCHIVE_CAT,
            'SECONDS_SHORT' : PROD_SECONDS_SHORT,
            'SECONDS_LONG' : PROD_SECONDS_LONG,
        }
    else:
        result = {
            'MISSION_START': TEST_FLAIR_MISSION_START,
            'MISSION_STOP': TEST_FLAIR_MISSION_STOP,
            'BOT_GUILD': TEST_DISCORD_GUILD,
            'SUB_REDDIT': TEST_SUB_REDDIT,
            'TRADE_ALERTS_ID': TEST_TRADE_ALERTS_ID,
            'WINE_ALERTS_LOADING_ID': TEST_WINE_ALERTS_LOADING_ID,
            'WINE_ALERTS_UNLOADING_ID': TEST_WINE_ALERTS_UNLOADING_ID,
            'CHANNEL_UPVOTES': TEST_CHANNEL_UPVOTES,
            'REDDIT_CHANNEL' : TEST_REDDIT_CHANNEL,
            'MISSION_CHANNEL': TEST_MISSION_CHANNEL,
            'BOT_COMMAND_CHANNEL': TEST_BOT_COMMAND_CHANNEL,
            'ADMIN_BOT_CHANNEL' : TEST_ADMIN_BOT_CHANNEL,
            'BOT_SPAM_CHANNEL': TEST_BOT_SPAM_CHANNEL,
            'UPVOTE_EMOJI': TEST_UPVOTE_EMOJI,
            'HAULER_ROLE' : TEST_HAULER_ROLE,
            'CC_ROLE' : TEST_CC_ROLE,
            'CC_CAT' : TEST_CC_CAT,
            'CTEAM_ROLE' : TEST_CTEAM_ROLE,
            'CERTCARRIER_ROLE' : TEST_CERTCARRIER_ROLE,
            'RESCARRIER_ROLE' : TEST_RESCARRIER_ROLE,
            'TRADE_CAT' : TEST_TRADE_CAT,
            'ARCHIVE_CAT' : TEST_ARCHIVE_CAT,
            'SECONDS_SHORT' : TEST_SECONDS_SHORT,
            'SECONDS_LONG' : TEST_SECONDS_LONG,
        }

    return result
