# a class to hold channel definitions for training mode
class ChannelDefs:
    def __init__(self, category_actual, alerts_channel_actual, mission_command_channel_actual, upvotes_channel_actual, wine_loading_channel_actual, wine_unloading_channel_actual, sub_reddit_actual, reddit_flair_in_progress, reddit_flair_completed):
        self.category_actual = category_actual
        self.alerts_channel_actual = alerts_channel_actual
        self.mission_command_channel_actual = mission_command_channel_actual
        self.upvotes_channel_actual = upvotes_channel_actual
        self.wine_loading_channel_actual = wine_loading_channel_actual
        self.wine_unloading_channel_actual = wine_unloading_channel_actual
        self.sub_reddit_actual = sub_reddit_actual
        self.reddit_flair_in_progress = reddit_flair_in_progress
        self.reddit_flair_completed = reddit_flair_completed