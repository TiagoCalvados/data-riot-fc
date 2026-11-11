import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
from sqlalchemy import select
from app.config import settings
from app.models import Invitation, Outbox, Shift, User, utcnow, aware
from app.planning import policy, valid_shift, cancel_invitation, linked_fixtures
from app.security import decrypt_payload


def deliver_outbox(db, smtp_factory=None):
    config = settings()
    sent = 0
    for item in db.scalars(select(Outbox).where(Outbox.state == 'queued',
                                               Outbox.next_attempt_at <= utcnow()).order_by(Outbox.id).limit(50)):
        invitation = db.get(Invitation, item.invitation_id)
        shift = db.get(Shift, invitation.shift_id)
        if item.kind == 'invitation' and valid_shift(db, shift, require_fresh=False) and not valid_shift(db, shift):
            item.error = 'Wedstrijdfeed ouder dan 24 uur; verzending wacht op een actuele controle.'
            continue
        if item.kind == 'invitation' and (invitation.state != 'queued' or not valid_shift(db, shift)
                                          or aware(shift.starts_at) <= utcnow() + timedelta(hours=2)):
            item.state = 'cancelled'
            item.encrypted_payload = ''
            if invitation.state == 'queued':
                cancel_invitation(db, invitation, 'Dienst niet langer beschikbaar.')
            continue
        capture = config.local_mail_capture and config.demo_mode and shift.is_demo
        simulated = config.demo_mode and shift.is_demo and not capture
        if not simulated and not capture and (config.demo_mode or not config.mail_ready):
            item.error = 'E-mail niet actief: configureer SMTP en schakel demonstratiemodus uit.'
            continue
        payload = decrypt_payload(item.encrypted_payload)
        if capture and (not db.get(User, invitation.user_id).is_demo
                        or not payload['to'].lower().endswith('@example.invalid')):
            item.error = 'Lokale testinbox: alleen fictieve example.invalid-adressen zijn toegestaan.'
            continue
        # Synthetic recipients must never leave the application, even in production.
        if not simulated and not capture and (shift.is_demo or payload['to'].lower().endswith(('.invalid', '.test', '@example.com'))):
            item.error = 'Testadres: verzending geblokkeerd.'
            continue
        deadline = min(utcnow() + timedelta(hours=policy(db).response_hours), aware(shift.starts_at) - timedelta(hours=2))
        try:
            if not simulated:
                msg = EmailMessage()
                msg['From'] = config.smtp_from
                msg['To'] = payload['to']
                msg['Subject'] = payload['subject']
                msg['Message-ID'] = f'<sdw-{item.id}-{invitation.token_hash[:16]}@{config.smtp_from.split("@")[-1]}>'
                msg.set_content(payload['body'])
                factory = smtp_factory or (smtplib.SMTP_SSL if config.smtp_port == 465 else smtplib.SMTP)
                kwargs = {'timeout': 20}
                if config.smtp_port == 465:
                    kwargs['context'] = ssl.create_default_context()
                with factory(config.smtp_host, config.smtp_port, **kwargs) as smtp:
                    if not capture and config.smtp_port != 465:
                        smtp.ehlo()
                        smtp.starttls(context=ssl.create_default_context())
                        smtp.ehlo()
                    if not capture:
                        smtp.login(config.smtp_username, config.smtp_password)
                    smtp.send_message(msg)
            item.state = 'simulated' if simulated or capture else 'sent'
            item.sent_at = utcnow()
            item.error = ''
            # Erase delivered links from stored email bodies; only hashes remain on invitations.
            item.encrypted_payload = ''
            if item.kind == 'invitation':
                invitation.state = 'pending'
                invitation.sent_at = item.sent_at
                invitation.expires_at = deadline
            sent += 1
        except (smtplib.SMTPException, OSError) as exc:
            item.attempts += 1
            # Never record exception strings which may contain authentication credentials.
            item.error = f'Verzending mislukt ({type(exc).__name__}); nieuwe poging volgt.'
            item.next_attempt_at = utcnow() + timedelta(minutes=min(360, 5 * 2 ** min(item.attempts, 7)))
        db.flush()
    return sent
