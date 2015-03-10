class RouterOptions:
    """
    Router options for creating routers.
    """

    URI_CHECK_LOOSE = "loose"
    URI_CHECK_STRICT = "strict"

    def __init__(self, uri_check = None):
        """

        :param uri_check: Method which should be applied to check WAMP URIs.
        :type uri_check: str
        """
        self.uri_check = uri_check or RouterOptions.URI_CHECK_STRICT


    def __str__(self):
        return "RouterOptions(uri_check = {0})".format(self.uri_check)

