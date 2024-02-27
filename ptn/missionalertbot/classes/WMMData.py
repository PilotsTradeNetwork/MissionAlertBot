class WMMData:

    def __init__(self, info_dict=None):
        """
        Class represents a WMM tracking object as returned from the database.

        :param sqlite.Row info_dict: A single row from the sqlite query.
        """
        if info_dict:
            # Convert the sqlite3.Row object to a dictionary
            info_dict = dict(info_dict)
        else:
            info_dict = dict()

        self.carrier_name = info_dict.get('carrier', None)
        self.carrier_identifier = info_dict.get('cid', None)
        self.carrier_location = info_dict.get('location', None)
        self.carrier_owner = info_dict.get('ownerid', None)
        self.notification_status = info_dict.get('notify', None)
        self.capi = info_dict.get('capi', None)


    def to_dictionary(self):
        """
        Formats the data into a dictionary for easy access.

        :returns: A dictionary representation for the carrier data.
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
        return 'WMMData: CarrierLongName:{0.carrier_name} CarrierIdentifier:{0.carrier_identifier} ' \
               'CarrierLocation:{0.carrier_location} NotificationStatus:{0.notification_status} ' \
               'Owner: {0.carrier_owner} CAPI:{0.capi}'.format(self)

    def __bool__(self):
        """
        Override boolean to check if any values are set, if yes then return True, else False, where false is an empty
        class.

        :rtype: bool
        """
        return any([value for key, value in vars(self).items() if value])
