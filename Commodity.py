import sqlite3


class Commodity:

    def __init__(self, info_dict=None):
        """
        Class represents a commodity object as returned from the database.

        :param sqlite.Row info_dict: A single row from the sqlite query.
        """

        if info_dict:
            # Convert the sqlite3.Row object to a dictionary
            info_dict = dict(info_dict)
        else:
            info_dict = dict()

        self.name = info_dict.get('commodity', None)
        self.average_sell = info_dict.get('avgsell', None)
        self.average_buy = info_dict.get('avgbuy', None)
        self.max_sell = info_dict.get('maxsell', None)
        self.min_buy = info_dict.get('minbuy', None)
        self.max_profit = info_dict.get('maxprofit', None)

    def to_dictionary(self):
        """
        Formats the commodity data into a dictionary for easy access.

        :returns: A dictionary representation for the commodity data.
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
        return 'Commodity: Name: "{0.name}" AverageSell: {0.average_sell} AverageBuy: {0.average_buy} ' \
               'MaxSell: {0.max_sell} MinBuy: {0.min_buy} MaxProfit: {0.max_profit}'.format(self)

    def __bool__(self):
        """
        Override boolean to check if any values are set, if yes then return True, else False, where false is an empty
        class.

        :rtype: bool
        """
        return any([value for key, value in vars(self).items() if value])