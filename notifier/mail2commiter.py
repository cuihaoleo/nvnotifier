import smtplib
from email.mime.multipart import MIMEMultipart
from .. import git


def send_mail(host, port, sendto, sendfrom, subject, msg):
    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = sendfrom
    msg['To'] = sendto 
    msg.preamble = msg

    logger.info("Send Email to %s" % sendto)
    s = smtplib.SMTP(host, port)
    s.send_message(msg)
    s.quit()


class Notifier:
    def __init__(self, *args, timeout, sendfrom, saved={}, **kwargs):
        self.host = kwargs.get("host", "localhost")
        self.port = kwargs.get("port", 0)
        self.default_to = kwargs.get("default_to", None)
        self.sendfrom = sendfrom

        timeout = convert_timeout_to_second(timeout)
        self.yuz = int(time.time()) - int(timeout if timeout else 0)

        self.record = saved.copy()

    def send(self, pac, outtime):
        if outtime > self.yuz:
            return False

        objhash = hash(pac._info.values())
        if self.record.get(pac.name) == objhash:
            logger.info("%s has been marked out-of-date in GitHub" 
                        % pac.name)
            return False

        sendto = git_latest_commiter(pac.path) or self.default_to
        if sendto:
            send_mail(
                host=self.host,
                port=self.port,
                sendto=to,
                sendfrom=self.sendfrom,
                subject="Package %s is out-of-date" % pac.name,
                msg="Local: %s\n" % pac.local_version +
                    "Remote: %s" % pac.remote_version)
        else:
            logger.warning("Don't know send email to whom (%s)" % pac)

    def finish(self):
        return self.record
