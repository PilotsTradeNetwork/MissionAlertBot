# Production variables
PROD_FLAIR_MISSION_START = "d01e6808-9235-11eb-9cc0-0eb650439ee7"
PROD_FLAIR_MISSION_STOP = "eea2d818-9235-11eb-b86f-0e50eec082f5"

PROD_DISCORD_GUILD = 1081339111111131197 # PTN Discord server
PROD_TRADE_ALERTS_ID = 1082235773719425094  # trade alerts channel ID for PTN main server
PROD_LEGACY_ALERTS_ID = 1082235776525418506 # trade alerts channel ID for legacy trade alerts on the PTN main server
PROD_WINE_ALERTS_LOADING_ID = 1082235903721885716 # booze alerts channel ID for PTN main server [loading]
PROD_WINE_ALERTS_UNLOADING_ID = 1082235898315427890 # booze alerts channel ID for PTN main server [unloading]
PROD_SUB_REDDIT = "PilotsTradeNetwork"  # subreddit for live
PROD_CHANNEL_UPVOTES = 1082235693805346816    # The ID for the updoots channel
PROD_REDDIT_CHANNEL = 1082235695273365524 # the ID for the Reddit Comments channel
PROD_MISSION_CHANNEL = 1082235692295397476    # The ID for the production mission channel
PROD_BOT_COMMAND_CHANNEL = 1082235710553206906   # Bot backend commands are locked to a channel
PROD_ADMIN_BOT_CHANNEL = 1082235673882394634 # bot command channel for admins only
PROD_BOT_SPAM_CHANNEL = 1082235660167020625 # Certain bot logging messages go here
PROD_DEV_CHANNEL = 1082235716769169409 # Development channel for MAB on live
PROD_UPVOTE_EMOJI = 1082240200073281616 # upvote emoji on live server
PROD_HAULER_ROLE = 1082235467363262505 # hauler role ID on live server
PROD_LEGACY_HAULER__ROLE = 1082235489819578399 # legacy hauler role ID on live server
PROD_CC_ROLE = 1082235395904901170 # CC role on live server
PROD_CC_CAT = 1082235536313417728 # Community Carrier category on live server
PROD_ADMIN_ROLE = 1082235383011618826 # MAB Bot Admin role on live server (currently @Council)
PROD_CMENTOR_ROLE = 1082235386836815944 # Community Mentor role on live server
PROD_CERTCARRIER_ROLE = 1082235400170516540 # Certified Carrier role on live server
PROD_RESCARRIER_ROLE = 1082235401172942909 # Fleet Reserve Carrier role on live server
PROD_TRAINEE_ROLE = 1082235416188567602 # CCO Trainee role on live server
PROD_CPILLAR_ROLE = 1082235394508197909 # Community Pillar role on live server
PROD_DEV_ROLE = 1082235421515329536 # Developer role ID on live
PROD_MOD_ROLE = 1082235385033273414 # Mod role ID on Live
PROD_TRADE_CAT = 1082235543515037716 # Trade Carrier category on live server
PROD_ARCHIVE_CAT = 1082235551236755507 # Archive category on live server
PROD_SECONDS_SHORT = 120
PROD_SECONDS_LONG = 900

# Testing variables

# reddit flair IDs - testing sub
TEST_FLAIR_MISSION_START = "3cbb1ab6-8e8e-11eb-93a1-0e0f446bc1b7"
TEST_FLAIR_MISSION_STOP = "4242a2e2-8e8e-11eb-b443-0e664851dbff"

TEST_DISCORD_GUILD = 818174236480897055 # test Discord server
TEST_TRADE_ALERTS_ID = 843252609057423361  # trade alerts channel ID for PTN test server
TEST_LEGACY_ALERTS_ID = 1047113662743183410 # trade alerts channel ID for legacy trade alerts on the PTN test server
TEST_WINE_ALERTS_LOADING_ID = 870425638127943700 # booze alerts channel ID for PTN test server [loading]
TEST_WINE_ALERTS_UNLOADING_ID = 870425638127943700 # booze alerts channel ID for PTN test server [unloading]
TEST_SUB_REDDIT = "PTNBotTesting"  # subreddit for testing
TEST_CHANNEL_UPVOTES = 839918504676294666    # The ID for the updoots channel on test
TEST_REDDIT_CHANNEL = 878029350933520484 # the ID for the Reddit Comments channel
TEST_MISSION_CHANNEL = 842138710651961364    # The ID for the production mission channel
TEST_BOT_COMMAND_CHANNEL = 842152343441375283   # Bot backend commands are locked to a channel
TEST_ADMIN_BOT_CHANNEL = 842152343441375283 # bot command channel for admins only
TEST_BOT_SPAM_CHANNEL = 842525081858867211 # Bot logging messages on the test server
TEST_DEV_CHANNEL = 1063765215457583164 # Development channel for MAB on test
TEST_UPVOTE_EMOJI = 849388681382068225 # upvote emoji on test server
TEST_HAULER_ROLE = 875439909102575647 # hauler role ID on test server
TEST_LEGACY_HAULER__ROLE = 1047152762707787786 # legacy hauler role ID on test server
TEST_CC_ROLE = 877220476827619399 # CC role on test server
TEST_CC_CAT = 877108931699310592 # Community Carrier category on test server
TEST_ADMIN_ROLE = 836367194979041351 # Bot Admin role on test server
TEST_MOD_ROLE = 903292469049974845 # Mod role on test server
TEST_CMENTOR_ROLE = 877586763672072193 # Community Mentor role on test server
TEST_CERTCARRIER_ROLE = 822999970012463154 # Certified Carrier role on test server
TEST_RESCARRIER_ROLE = 947520552766152744 # Fleet Reserve Carrier role on test server
TEST_TRAINEE_ROLE = 1048912218344923187 # CCO Trainee role on test server
TEST_CPILLAR_ROLE = 903289927184314388 # Community Pillar role on test server
TEST_DEV_ROLE = 1048913812163678278 # Dev role ID on test
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

REDDIT_DISCORD_LINK_URL = \
    'https://www.reddit.com/r/PilotsTradeNetwork/comments/l0y7dk/pilots_trade_network_intergalactic_discord_server/'


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
            'LEGACY_ALERTS_ID': PROD_LEGACY_ALERTS_ID,
            'WINE_ALERTS_LOADING_ID': PROD_WINE_ALERTS_LOADING_ID,
            'WINE_ALERTS_UNLOADING_ID': PROD_WINE_ALERTS_UNLOADING_ID,
            'CHANNEL_UPVOTES': PROD_CHANNEL_UPVOTES,
            'REDDIT_CHANNEL' : PROD_REDDIT_CHANNEL,
            'MISSION_CHANNEL': PROD_MISSION_CHANNEL,
            'BOT_COMMAND_CHANNEL': PROD_BOT_COMMAND_CHANNEL,
            'ADMIN_BOT_CHANNEL' : PROD_ADMIN_BOT_CHANNEL,
            'BOT_SPAM_CHANNEL': PROD_BOT_SPAM_CHANNEL,
            'BOT_DEV_CHANNEL' : PROD_DEV_CHANNEL,
            'UPVOTE_EMOJI': PROD_UPVOTE_EMOJI,
            'HAULER_ROLE' : PROD_HAULER_ROLE,
            'LEGACY_HAULER_ROLE' : PROD_LEGACY_HAULER__ROLE,
            'CC_ROLE' : PROD_CC_ROLE,
            'CC_CAT' : PROD_CC_CAT,
            'ADMIN_ROLE' : PROD_ADMIN_ROLE,
            'MOD_ROLE' : PROD_MOD_ROLE,
            'CMENTOR_ROLE' : PROD_CMENTOR_ROLE,
            'CERTCARRIER_ROLE' : PROD_CERTCARRIER_ROLE,
            'RESCARRIER_ROLE' : PROD_RESCARRIER_ROLE,
            'TRAINEE_ROLE' : PROD_TRAINEE_ROLE,
            'CPILLAR_ROLE' : PROD_CPILLAR_ROLE,
            'DEV_ROLE' : PROD_DEV_ROLE,
            'TRADE_CAT' : PROD_TRADE_CAT,
            'ARCHIVE_CAT' : PROD_ARCHIVE_CAT,
            'SECONDS_SHORT' : PROD_SECONDS_SHORT,
            'SECONDS_LONG' : PROD_SECONDS_LONG
        }
    else:
        result = {
            'MISSION_START': TEST_FLAIR_MISSION_START,
            'MISSION_STOP': TEST_FLAIR_MISSION_STOP,
            'BOT_GUILD': TEST_DISCORD_GUILD,
            'SUB_REDDIT': TEST_SUB_REDDIT,
            'TRADE_ALERTS_ID': TEST_TRADE_ALERTS_ID,
            'LEGACY_ALERTS_ID': TEST_LEGACY_ALERTS_ID,
            'WINE_ALERTS_LOADING_ID': TEST_WINE_ALERTS_LOADING_ID,
            'WINE_ALERTS_UNLOADING_ID': TEST_WINE_ALERTS_UNLOADING_ID,
            'CHANNEL_UPVOTES': TEST_CHANNEL_UPVOTES,
            'REDDIT_CHANNEL' : TEST_REDDIT_CHANNEL,
            'MISSION_CHANNEL': TEST_MISSION_CHANNEL,
            'BOT_COMMAND_CHANNEL': TEST_BOT_COMMAND_CHANNEL,
            'ADMIN_BOT_CHANNEL' : TEST_ADMIN_BOT_CHANNEL,
            'BOT_SPAM_CHANNEL': TEST_BOT_SPAM_CHANNEL,
            'BOT_DEV_CHANNEL' : TEST_DEV_CHANNEL,
            'UPVOTE_EMOJI': TEST_UPVOTE_EMOJI,
            'HAULER_ROLE' : TEST_HAULER_ROLE,
            'LEGACY_HAULER_ROLE' : TEST_LEGACY_HAULER__ROLE,
            'CC_ROLE' : TEST_CC_ROLE,
            'CC_CAT' : TEST_CC_CAT,
            'ADMIN_ROLE' : TEST_ADMIN_ROLE,
            'MOD_ROLE' : TEST_MOD_ROLE,
            'CMENTOR_ROLE' : TEST_CMENTOR_ROLE,
            'CERTCARRIER_ROLE' : TEST_CERTCARRIER_ROLE,
            'RESCARRIER_ROLE' : TEST_RESCARRIER_ROLE,
            'TRAINEE_ROLE' : TEST_TRAINEE_ROLE,
            'CPILLAR_ROLE' : TEST_CPILLAR_ROLE,
            'DEV_ROLE' : TEST_DEV_ROLE,
            'TRADE_CAT' : TEST_TRADE_CAT,
            'ARCHIVE_CAT' : TEST_ARCHIVE_CAT,
            'SECONDS_SHORT' : TEST_SECONDS_SHORT,
            'SECONDS_LONG' : TEST_SECONDS_LONG
        }

    return result
