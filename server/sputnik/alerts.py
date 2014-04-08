import config

from twisted.internet import reactor, protocol

class SendmailProtocol(protocol.ProcessProtocol):
    def __init__(self, message):
        """

        :param message: the message we're sending to the recipient
        :type message: str
        """
        from_ = "From: " + config.get("alerts", "from")
        to = "To: " + config.get("alerts", "to")
        subject = "Subject: " + config.get("alerts", "subject")
        self.data = "\n".join([from_, to, subject, "", message, ""])

    def connectionMade(self):
        """Once the connection is made, send the message off


        """
        self.transport.write(self.data)
        self.transport.closeStdin()
        self.transport.loseConnection()

def alert(message):
    process = SendmailProtocol(message)
    sendmail = "/usr/sbin/sendmail"
    reactor.spawnProcess(process, sendmail, [sendmail, "-t", "-oi"])

