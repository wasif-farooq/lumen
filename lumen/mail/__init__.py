"""Mail: connected mailboxes, read-only, indexed so mail is found like files (docs/MAIL.md).

accounts  mailboxes and their sign-in (secrets only in a file this user can read)
imap      reading a mailbox over IMAP without changing anything in it
parse     a mail's text (HTML as text, quotes left out) and its attachments' text
store     mail.db: messages and their full-text index
sync      the background thread that reads new mail
search    mail hits for search and chat
"""
