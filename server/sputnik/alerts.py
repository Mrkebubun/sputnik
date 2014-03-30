import config

from twisted.internet import protocol
from twsited.reactor import internet

class SendmailProtocol(protocol.ProcessProtocol):
    def __init__(self, message):
        from_ = config.get("alerts", "from")
        to = config.get("alerts", "to")
        subject = config.get("alerts", "subject")
        self.data = "\n".join([from_, to, subject, "", message, ""])

    def connectionMade(self):
        self.transport.write(self.data)
        self.transport.closeStdin()
        self.transport.loseConnection()

def alert(message):
    process = SendmailProtocol(message)
    sendmail = "/usr/sbin/sendmail"
    reactor.spawnProcess(process, sendmail, [sendmail, "-t", "-oi"])

