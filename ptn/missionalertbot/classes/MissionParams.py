class MissionParams:
    """
    A class to store all parameters relating to mission generation.
    This class can be pickled into the missions database for later retrieval.
    Note we cannot pickle discord.py weak objects e.g. interactions
    """

    def __init__(self, info_dict=None):
        """
        Class represents a mission object as returned from the database.

        :param sqlite.Row info_dict: A single row from the sqlite query.
        """

        if info_dict:
            # Convert the sqlite3.Row object to a dictionary
            info_dict = dict(info_dict)
        else:
            info_dict = dict()

        self.carrier_name_search_term = info_dict.get('carrier_name_search_term', None) # the carrier name fragment to search for
        self.commodity_search_term = info_dict.get('commodity_search_term', None) # the commodity name fragment to search for
        self.system = info_dict.get('system', None).upper() # the target system
        self.station = info_dict.get('station', None).upper() # target station
        self.profit = info_dict.get('profit', None) # profit as int or float
        self.pads = info_dict.get('pads', None).upper() # size of largest landing pad L or M
        self.demand = info_dict.get('demand', None) # total supply/demand for commodity
        self.mission_type = info_dict.get('mission_type', None) # whether the mission is loading or unloading
        self.edmc_off = info_dict.get('edmc_off', None) # whether the mission is EDMC off flagged
        self.carrier_data = info_dict.get('carrier_data', None) # carrier data class retrieved from db
        self.commodity_data = info_dict.get('commodity_data', None) # commodity data class retrieved from db
        self.reddit_img_name = info_dict.get('reddit_img_name', None) # the Reddit image file name
        self.discord_img_name = info_dict.get('discord_img_name', None) # the Discord image file name
        self.cco_message_text = info_dict.get('cco_message_text', None) # roleplay text entered by user
        self.timestamp = info_dict.get('timestamp', None) # the posix time the mission was generated
        self.reddit_title = info_dict.get('reddit_title', None) # title for the subreddit post
        self.reddit_body = info_dict.get('reddit_body', None) # body text for the top-level comment on the subreddit post
        self.reddit_post_id = info_dict.get('reddit_post_id', None) # the ID of the mission's Reddit post
        self.reddit_post_url = info_dict.get('reddit_post_url', None) # the URL of the mission's Reddit post
        self.reddit_comment_id = info_dict.get('reddit_comment_id', None) # the ID of the mission's autogenerated Reddit top comment
        self.reddit_comment_url = info_dict.get('reddit_comment_url', None) # the URL of the mission's autogenerated Reddit top comment
        self.discord_text = info_dict.get('discord_text', None) # the text used for the trade alert sent to Discord
        self.discord_embeds = info_dict.get('discord_embeds', None) # embeds used for Discord channels/webhooks
        self.discord_alert_id = info_dict.get('discord_alert_id', None) # the message ID of the Discord trade alerts entry
        self.mission_temp_channel_id = info_dict.get('mission_temp_channel_id', None) # the channel ID of the Discord carrier mission channel
        self.webhook_urls = info_dict.get('webhook_urls', []) # a list of the URLs for any webhooks used
        self.webhook_names = info_dict.get('webhook_names', []) # identifiers for webhook URLs
        self.webhook_msg_ids = info_dict.get('webhook_msg_ids', []) # a list of the IDs of any messages sent via webhook
        self.webhook_jump_urls = info_dict.get('webhook_jump_urls', []) # webhook jump URL


    def print_values(self):
        try:
            print(f"carrier_name_search_term: {self.carrier_name_search_term}")
            print(f"commodity_search_term: {self.commodity_search_term}")
            print(f"system: {self.system}")
            print(f"station: {self.station}")
            print(f"profit: {self.profit}")
            print(f"pads: {self.pads}")
            print(f"demand: {self.demand}")
            print(f"mission_type: {self.mission_type}")
            print(f"edmc_off: {self.edmc_off}")
            print(f"carrier_data: {self.carrier_data}")
            print(f"commodity_data: {self.commodity_data}")
            print(f"reddit_img_name: {self.reddit_img_name}")
            print(f"discord_img_name: {self.discord_img_name}")
            print(f"cco_message_text: {self.cco_message_text}")
            print(f"timestamp: {self.timestamp}")
            print(f"reddit_title: {self.reddit_title}")
            print(f"reddit_body: {self.reddit_body}")
            print(f"reddit_post_id: {self.reddit_post_id}")
            print(f"reddit_post_url: {self.reddit_post_url}")
            print(f"reddit_comment_id: {self.reddit_comment_id}")
            print(f"reddit_comment_url: {self.reddit_comment_url}")
            print(f"discord_text: {self.discord_text}")
            print(f"discord_alert_id: {self.discord_alert_id}")
            print(f"mission_temp_channel_id: {self.mission_temp_channel_id}")
            print(f"webhook_urls: {self.webhook_urls}")
            print(f"webhook_msg_ids: {self.webhook_msg_ids}")
            print(f"webhook_jump_urls: {self.webhook_jump_urls}")
        except: pass # for values which haven't been incorporated yet


    def to_dictionary(self):
        """
        Formats the mission data into a dictionary for easy access.

        :returns: A dictionary representation for the mission data.
        :rtype: dict
        """
        response = {}
        for key, value in vars(self).items():
            if value is not None:
                response[key] = value
        return response


    def __bool__(self):
        """
        Override boolean to check if any values are set, if yes then return True, else False, where false is an empty
        class.

        :rtype: bool
        """
        return any([value for key, value in vars(self).items() if value])