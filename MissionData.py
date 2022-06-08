class MissionData:

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

        # TODO: transform NULL into None at some stage

        self.carrier_name = info_dict.get('carrier', None)
        self.carrier_identifier = info_dict.get('cid', None)
        self.channel_id = info_dict.get('channelid', None)
        self.commodity = info_dict.get('commodity', None)
        self.mission_type = info_dict.get('missiontype', None)
        self.system = info_dict.get('system', None)
        self.station = info_dict.get('station', None)
        self.profit = info_dict.get('profit', None)
        self.pad_size = info_dict.get('pad', None)
        self.demand = info_dict.get('demand', None)
        self.rp_text = info_dict.get('rp_text', None)
        self.reddit_post_id = info_dict.get('reddit_post_id', None)
        self.reddit_post_url = info_dict.get('reddit_post_url', None)
        self.reddit_comment_id = info_dict.get('reddit_comment_id', None)
        self.reddit_comment_url = info_dict.get('reddit_comment_url', None)
        self.discord_alert_id = info_dict.get('discord_alert_id', None)
        self.wordpress_post_id = info_dict.get('wordpress_post_id', None)

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

    def __str__(self):
        """
        Overloads str to return a readable object

        :rtype: str
        """

        return 'MissionData: CarrierName:{0.carrier_name} CarrierIdentifier:{0.carrier_identifier} ' \
               'DiscordChannelID:{0.channel_id} Commodity:{0.commodity} ' \
               'MissingType:{0.mission_type} System:{0.system} Station:{0.station} Profit:{0.profit}' \
               'Pad:{0.pad_size} Demand:{0.demand} RpText:{0.rp_text} RedditPostId:{0.reddit_post_id}' \
               'RedditPostUrl:{0.reddit_post_url} RedditCommentId:{0.reddit_comment_id}' \
               'RedditCommentUrl:{0.reddit_comment_url} DiscordAlertId:{0.discord_alert_id}' \
               'WordpressPostId:{0.wordpress_post_id}' .format(self)

    def __bool__(self):
        """
        Override boolean to check if any values are set, if yes then return True, else False, where false is an empty
        class.

        :rtype: bool
        """
        return any([value for key, value in vars(self).items() if value])
