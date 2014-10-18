__author__ = 'sameer'

import treq
import json
from twisted.internet import defer
from twisted.python import log
import string

class Zendesk(object):
    def __init__(self, domain, api_token, api_username):
        """

        :param domain:
        :type domain: str
        :param api_token:
        :type api_token: str
        :param api_username:
        :type api_username: str
        """
        self.api_token = api_token
        self.api_username = api_username
        self.domain = domain

    def create_ticket(self, user, subject, comment, attachments):
        """

        :param user: user details, nickname, email, etc
        :type user: dict
        :param subject: The subject of the ticket
        :type subject: str
        :param comment: the comments for the ticket
        :type comment: str
        :param attachments: files to attach
        :type attachments: list - of dicts with file data, names, and types
        :returns: DeferredList
        :raises: Exception
        """

        def uploads_done(tokens):
            """

            :param tokens: the upload tokens for the attachments
            :type tokens: list
            :returns: Deferred
            :raises: Exception
            """

            ticket = {"ticket": {"requester": {"name": user['nickname'],
                                               "email": user['email'] },
                                 "subject": subject,
                                 "comment": {"body": comment, "uploads": [str(t[1]) for t in tokens if t[0]]}}}

            def handle_response(response):
                """

                :param response:
                :returns: Deferred
                :raises: Exception
                """

                def parse_content(content):
                    """

                    :param content: the JSON string with the results from the post
                    :type content: str
                    :returns: int
                    :raises: Exception:
                    """
                    if response.code != 201:
                        # this should happen sufficiently rarely enough that it is
                        # worth logging here in addition to the failure
                        log.msg("Received code: %s from zendesk for new ticket %s: %s" % (response.code, str(ticket), content))
                        raise Exception("Zendesk returned code: %s with message: %s" % (response.code, content))
                    else:
                        log.msg("Received 201 Created from Zendesk. Ticket: %s. Content follows: %s" % (str(ticket), content))
                        # if the JSON cannot be decoded, let the error float up
                        ticket_returned = json.loads(content)
                        id = ticket_returned['ticket']['id']
                        return id

                return response.content().addCallback(parse_content)

            d = treq.post("https://%s.zendesk.com/api/v2/tickets.json" % self.domain, data=json.dumps(ticket),
                          headers={"Content-Type": "application/json"},
                          auth=("%s/token" % self.api_username, self.api_token))

            d.addCallback(handle_response)
            return d

        deferreds = []
        for attachment in attachments:
            d = self.upload_file(attachment['filename'], attachment['type'], attachment['data'])
            deferreds.append(d)

        dl = defer.DeferredList(deferreds)
        dl.addCallback(uploads_done)
        return dl

    def upload_file(self, name, content_type, file_data):
        """

        :param name: filename
        :type name: str
        :param content_type:
        :type content_type: str
        :param file_data:
        :type file_data:
        :returns: Deferred
        :raises: Exception
        """

        def handle_response(response):
            def parse_content(content):
                if response.code != 201:
                    log.msg("Received code: %s from zendesk for file upload: msg %s" % (response.code, content))
                    raise Exception("Zendesk returned code %s" % response.code)
                else:
                    log.msg("Received 201 Created from Zendesk. Content: %s" % content)
                    token_data = json.loads(content)
                    token = token_data['upload']['token']
                    return token

            return response.content().addCallback(parse_content)

        # replace spaces in name with _
        name = string.replace(name, ' ', '_')
        d = treq.post("https://%s.zendesk.com/api/v2/uploads.json?filename=%s" % (self.domain, name), data=file_data,
                      headers={"Content-Type": content_type},
                      auth=("%s/token" % self.api_username, self.api_token))
        d.addCallback(handle_response)
        return d

if __name__ == "__main__":
    from twisted.internet import reactor
    from pprint import pprint
    import sys
    log.startLogging(sys.stdout)

    user = { 'nickname': 'Test',
             'email': 'testmail@m2.io' }

    zd = Zendesk("mimetic", "5bZYIMtkHWTuaJijvkKuXVeaoXumETWdyCa2wTpN", 'sameer@m2.io')
    # d1 = zd.create_ticket(user, "Test Ticket", "Comment", [])
    # d1.addCallback(pprint)

    d2 = zd.create_ticket(user, "Test with Files", "Comment yay", [{'filename': 'content a',
                                                                    'type': 'unknown',
                                                                    'data': '2424234'},
                                                                   {'filename': 'content b',
                                                                    'type': 'unknown',
                                                                    'data': '242423534'}
    ])
    d2.addCallback(pprint)
    d2.addErrback(log.err)

    reactor.run()
