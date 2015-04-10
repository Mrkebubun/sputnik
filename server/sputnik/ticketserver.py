#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

__author__ = 'sameer'

import cgi
import json

from twisted.web.server import NOT_DONE_YET
from twisted.web.resource import Resource
from twisted.python import log


class TicketServer(Resource):
    isLeaf = True
    def __init__(self, administrator, zendesk, blockscore=None):
        self.administrator = administrator
        self.zendesk = zendesk
        self.blockscore = blockscore

        Resource.__init__(self)

    def getChild(self, path, request):
        """

        :param path:
        :param request:
        :returns: Resource
        """
        return self

    def log(self, request):
        """Log a request

        :param request:
        """
        log.msg(request.getClientIP(),
                     request.method,
                     request.uri,
                     request.clientproto,
                     request.code,
                     request.sentLength or "-",
                     request.getHeader("referer") or "-",
                     request.getHeader("user-agent") or "-",
                     request.getHeader("authorization") or "-")

    def create_kyc_ticket(self, request):
        """

        :param request:
        :type request: IRequest
        :returns: Deferred
        """
        headers = request.getAllHeaders()
        fields = cgi.FieldStorage(
                    fp = request.content,
                    headers = headers,
                    environ= {'REQUEST_METHOD': request.method,
                              'CONTENT_TYPE': headers['content-type'] }
                    )

        def onBlockScore(blockscore_result):
            def onFail(failure):
                """

                :param failure:
                """
                log.err("unable to create support ticket")
                log.err(failure)
                request.setResponseCode(422)
                request.setHeader("Content-Type", "application/json; charset=utf-8")
                request.write(json.dumps({'success': False, 'error': failure.value.args}).encode('utf-8'))
                request.finish()

            def onCheckSuccess(user):
                attachments = []
                file_fields = fields['file']
                if not isinstance(file_fields, list):
                    file_fields = [file_fields]

                for field in file_fields:
                    attachments.append({"filename": field.filename,
                                        "data": field.value,
                                        "type": field.type})

                try:
                    data = {'blockscore_result': blockscore_result,
                            'input_data': json.loads(fields['data'].value)}
                except ValueError:
                    data = {'error': "Invalid json data: %s" % fields['data'].value }

                def onCreateTicketSuccess(ticket_number):
                    def onRegisterTicketSuccess(result):
                        log.msg("Ticket registered successfully")
                        request.setHeader("Content-Type", "application/json; charset=utf-8")
                        request.write(json.dumps({'success': True, 'result': ticket_number}).encode('utf-8'))
                        request.finish()

                    log.msg("Ticket created: %s" % ticket_number)
                    d3 = self.administrator.register_support_ticket(username, nonce, 'Compliance', str(ticket_number))
                    d3.addCallbacks(onRegisterTicketSuccess, onFail)


                d2 = self.zendesk.create_ticket(user, "New compliance document submission",
                                                json.dumps(data, indent=4,
                                                           separators=(',', ': ')), attachments)
                d2.addCallbacks(onCreateTicketSuccess, onFail)

            username = fields['username'].value
            nonce = fields['nonce'].value
            d = self.administrator.check_support_nonce(username, nonce, 'Compliance')
            d.addCallbacks(onCheckSuccess, onFail)
            return d


        if self.blockscore is not None:
            input_data = json.loads(fields['data'].value)

            blockscore_input = {'name_first': input_data['first_name'],
                            'name_middle': input_data['middle_name'],
                            'name_last': input_data['last_name'],
                            'address_street1': input_data['address1'],
                            'address_street2': input_data['address2'],
                            'address_city': input_data['city'],
                            'address_subdivision': input_data['state'],
                            'address_postal_code': input_data['postal_code'],
                            'address_country_code': input_data['country_code'],
                            'document_type': input_data['id_type'],
                            'document_value': input_data['id_number'],
                            'birth_day': input_data['birth_day'],
                            'birth_month': input_data['birth_month'],
                            'birth_year': input_data['birth_year']
                            }
            log.msg("Sending to blockscore: %s" % blockscore_input)
            d = self.blockscore.verify(blockscore_input)
            d.addBoth(onBlockScore)
        else:
            d = onBlockScore({})

        return NOT_DONE_YET

    def render(self, request):
        """

        :param request:
        :returns: NOT_DONE_YET, None
        """
        self.log(request)
        if request.postpath[0] == 'create_kyc_ticket':
            return self.create_kyc_ticket(request)
        else:
            return None


