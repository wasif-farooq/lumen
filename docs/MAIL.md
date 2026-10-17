# Mail: connect mailboxes and index them

Connect your mailboxes; Lumen reads them (read-only: nothing in the mailbox ever changes) and
indexes the mail and its attachments, so "the email from the bank about the loan" or "the invoice
PDF Omar sent" is found by search and chat like any file, opens in the viewer, and can be asked about.

Sorting mail into folders and to-dos/reminders from mail were measured first and are left for later
(results below). The calendar is a separate step.

## Design

- **One connector: IMAP**, read-only (`EXAMINE` and `BODY.PEEK`, so not even "read" flags change).
  Works with Gmail (an app password, with 2-step verification), Yahoo, iCloud, Fastmail and any
  IMAP server. Gmail and Outlook also accept IMAP sign-in with a token (XOAUTH2): "Sign in with
  Google / Microsoft" (step 2) feeds the same connector.
- **Accounts** in `mail-accounts.json`; passwords and tokens in `mail-secrets.json`, readable only
  by you and never sent to the app.
- **`mail.db`**: each message (account, folder, from, to, subject, date, size, attachments) and a
  full-text index of its text (HTML as text, quoted replies trimmed) and of its attachments' text
  (the same readers as files: PDF, Word, Excel, …, within the same size limits). Attachments aren't
  kept: opening one fetches it from the mailbox into a cache.
- **Sync**: a thread in `lumen serve`, every 10 minutes (and "Sync now"); new mail by UID since the
  last sync; at first, mail from a time you choose (default 1 year). All folders except Trash,
  Spam and Drafts.
- **Search**: `/api/search` and the agent's `search_files` return mail hits next to files; the
  viewer has a "mail" view (headers, text, attachments opened in the viewer); "Ask about it" works.
- **Removing an account** deletes its secrets, its mail index and its cached attachments.

## Checklist

### 0. Measure first
- [x] `scripts/mail_bench.py`: 200 made-up mails, qwen3.5:2b (results below)
- [x] `scripts/mail_earned_bench.py`: earned automatic moving per folder (results below)
- [x] Decision: sorting and to-dos from mail left for later; connect and index first

### 1. Connect and index (IMAP)
- [x] `lumen/mail/accounts.py`: accounts and secrets; add (tests the connection, lists folders), remove
- [x] `lumen/mail/imap.py`: read-only IMAP: folders (special-use: skip Trash/Junk/Drafts), new mail by UID
- [x] `lumen/mail/parse.py`: headers, text (HTML to text, quotes trimmed), attachments and their text
- [x] `lumen/mail/store.py`: `mail.db` with full-text index; sync state per folder
- [x] `lumen/mail/sync.py`: the sync thread, status per account, "Sync now"
- [x] API: `/api/mail/accounts` (list, add, remove, sync), `/api/mail/messages/{id}` and its attachments (fetched into `mail-cache`, opened by the viewer); mail in `/api/search` and the chat's `search_files`/`read_file`
- [x] Tests against a real IMAP server (GreenMail in Docker), made-up mail

### 2. Sign in with Google / Microsoft
- [ ] OAuth: Google (browser, local port), Microsoft (device code) → IMAP XOAUTH2; token refresh
- [ ] `docs/MAIL.md`: creating the client IDs (Google Cloud, Azure), the "In production" note

### 3. App
- [ ] Settings → Mail: add an account (known providers filled in), status, Sync now, remove
- [ ] Mail results in chat and search, the viewer's mail view, attachments
- [ ] Tests and screenshots (made-up mail)

### 4. Finish
- [ ] README; full checks; try it with your mailbox; merge and push (v0.6.0) when asked

## Measured: sorting and to-dos (left for later)

`scripts/mail_bench.py`, 200 made-up mails (template mail: an upper bound), qwen3.5:2b, 4.7 s per mail:

- **Folder right 70%.** Newsletters, Notifications, Receipts and Personal suggestions were right
  when made (100%), but Bills (50%) and Work (48%) collected other mail: anything from a person
  asking something went to Work (dinner invites, a doctor's appointment), "payment received" to Bills.
- **Its confidence is useless**: 0.95-1.0 for every mail, wrong ones included.
- **To-dos: found 36%** of the mails that need one, invented 1 in 98; deadlines, when found, right 83%.

`scripts/mail_earned_bench.py` (folders move mail on their own only after 95% of their last 30
suggestions were right; replayed on those answers, 1,000-mail streams, 50 runs): **~20% of mail moved
automatically, 99.4% right, ~1.3 wrong moves per 1,000 mails**; Bills and Work never earned it
(correctly), Travel rarely. Earned automation makes moving safe; how much is moved depends on
better suggestions (sender rules and history, headers, a focused to-do question): the next step
when sorting comes back.
