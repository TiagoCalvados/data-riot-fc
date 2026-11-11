"""Verify the existing SMTP/IMAP and Roundcube containers, without a custom UI."""
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
import imaplib
import os
import httpx


class Inputs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'input' and values.get('name'):
            self.values[values['name']] = values.get('value', '')


def inbox(address):
    with imaplib.IMAP4('mailserver', 3143, timeout=10) as mail:
        mail.login(address, os.environ['LOCAL_MAIL_PASSWORD'])
        mail.select('INBOX', readonly=True)
        status, rows = mail.search(None, 'ALL')
        assert status == 'OK'
        messages = []
        for number in rows[0].split()[-100:]:
            status, data = mail.fetch(number, '(BODY.PEEK[])')
            assert status == 'OK'
            messages.extend(BytesParser(policy=policy.default).parsebytes(row[1])
                            for row in data if isinstance(row, tuple))
        return messages


def check_webmail(address):
    with httpx.Client(base_url='http://webmail', follow_redirects=True, timeout=15) as client:
        page = client.get('/')
        page.raise_for_status()
        inputs = Inputs()
        inputs.feed(page.text)
        assert inputs.values.get('_token'), 'Roundcube login form unavailable'
        response = client.post('/?_task=login', data={**inputs.values, '_task': 'login', '_action': 'login',
            '_user': address, '_pass': os.environ['LOCAL_MAIL_PASSWORD']})
        response.raise_for_status()
        assert '_task=mail' in str(response.url) and 'logout' in response.text, 'Roundcube mailbox login failed'
        print('Roundcube webmail login passed:', address)
