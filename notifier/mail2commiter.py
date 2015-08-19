import smtplib
import datetime
import logging
from email.mime.multipart import MIMEMultipart

from nvnotifier import git
from .lib import convert_timeout_to_second

logger = logging.getLogger(__name__)


def send_mail(host, port, sender, receiver, subject, text):
    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = receiver
    msg.preamble = text

    try:
        s = smtplib.SMTP(host, port)
    except ConnectionRefusedError:
        logger.error("Cannot connect to SMTP server %s:%s" % (host, port))
        raise

    s.send_message(msg)
    s.quit()


class Notifier:
    def __init__(self, *args, timeout="0s", sender, saved={}, **kwargs):
        timeout_seconds = convert_timeout_to_second(timeout)
        now = datetime.datetime.now()
        self.deadline = now - datetime.timedelta(seconds=timeout_seconds)

        self.sender = sender
        self.default_receiver = kwargs.get("default_receiver", None)

        self.host = kwargs.get("host", "localhost")
        self.port = kwargs.get("port", 0)

        self.record = saved.copy()

    def send_raw_mail(self, receiver, subject, text):
        receiver = receiver or self.default_receiver

        send_mail(
            host=self.host,
            port=self.port,
            sender=self.sender,
            receiver=receiver,
            subject=subject,
            text=text)

        logger.info("Sent Email to %s" % receiver)
        logger.debug("Subject: %s" % subject)

    def send(self, pac, outtime):
        if outtime > self.deadline:
            return False

        objhash = pac.info
        if self.record.get(pac.name) == objhash:
            logger.info("Already sent mail to %s maintainer" % pac.name)
            return False

        receiver = git.git_latest_commiter(pac.path) or self.default_receiver
        if receiver:
            self.send_raw_mail(
                receiver=receiver,
                subject="Package %s is out-of-date" % pac.name,
                text="Local: %s\nRemote: %s" %
                     (pac.local_version, pac.remote_version))
        else:
            logger.warning("Don't know send email to whom (%s)" % pac)
            return False

        self.record[pac.name] = objhash
        return True

    def finish(self):
        return self.record
