# Notes, to-dos and reminders: design and checklist

Keep notes and to-dos and get reminded, by typing or talking in chat ("remind me every Monday at 9
to pay the rent", "add milk to my shopping list", "note: the plumber is Ahmed, 0300 1234567") or
from the Notes & to-dos screen.

## Design

- **Notes are Markdown files** in a notes folder (default `Lumen Notes` in the first indexed
  folder; must be inside an indexed folder so search finds them). Frontmatter has the title,
  times and tags; notes written in any editor work too. Lumen writes there without asking each
  time (its own folder), but every change goes in the undo log, edits and deletes keep the
  earlier version, and a deleted note goes to the Trash. Test mode (`LUMEN_WRITE=0`) saves none.
- **To-do lists, to-dos and reminders** are in `planner.db` (data folder), versioned with
  `PRAGMA user_version`. Lists keep their order; to-dos have a priority (0-3), a due time and
  done; reminders are one-off or repeat daily, on weekdays, weekly or monthly.
- **Times in plain words** (`lumen/planner/times.py`): "in 20 minutes", "tomorrow at 5pm",
  "Monday at 9", "tonight", "on 3 November at 10", "every Monday 9am", "every month on the 1st".
  Unclear words give no time, and the user is asked; nothing is guessed. A general date library
  (dateparser) was tried first and read "Monday at 9" as 17 September 2027: not used.
- **Reminders go off** from a thread in `lumen serve` (every 15 s): a desktop notification
  (notify-send), said aloud on an open voice chat (between turns, never mid-answer), and a banner
  in the app until the user taps Done or Snooze. Repeats move to their next time; a reminder missed
  while the server was off goes off once ("Missed: ...") when it starts.
- **Chat and voice**: six tools (`add_note`, `add_todo`, `show_todos`, `complete_todo`,
  `set_reminder`, `cancel_reminder`). The model passes the user's words; the code works out times.
  Guards against what a small model does anyway (measured below):
  - a time the model "improved" ("tonight" -> "tonight at 11pm") is not used: the time comes from
    the user's own message when the model's words are not a faithful copy of it;
  - repeats come only from the words ("every ..."), never from an argument the model fills in
    (it marked "on Friday" and a birthday as weekly);
  - a list the user never mentioned is not used; a list the user named is used when the model
    leaves it out; "add eggs to shopping" is saved as "eggs";
  - a message clearly about notes, to-dos or reminders ("note:", "write down", "remind me",
    "... list", "done with ...") shows the model only these six tools, so it can't answer
    "write down ..." with create_file or "note: ..." with a file search.

## Checklist

### Server
- [x] `planner/store.py`: lists, to-dos, reminders; upgrades; a default "To-do" list
- [x] `planner/times.py`: plain words to times, repeats, "describe" for people
- [x] `planner/notes.py`: create, append, edit, rename, trash; undo through the change log
- [x] Settings: `notes_dir` (must be inside an indexed folder), `reminder_notify`, `reminder_speak`
- [x] API: `/api/notes`, `/api/lists`, `/api/todos`, `/api/reminders` (+ snooze, ack, due, restore)
- [x] `planner/scheduler.py`: notifications, voice, banner, repeats, missed reminders
- [x] Tests through the HTTP API (times, notes, lists, to-dos, reminders, the scheduler with a fake
      clock, voice), each guard checked by breaking it once

### Agent
- [x] Six tools, the current date and time in the prompt (every call, not once per chat)
- [x] Guards above, with tests for each mistake the model made
- [x] `scripts/planner_bench.py`: real model, what was actually saved (results below)

### App
- [x] Notes & to-dos screen (Notes · To-dos · Reminders), desktop sidebar and phone drawer
- [x] Chat cards with Undo; the due banner (Done, Snooze 10 min); Settings → General card
- [x] Tests and screenshots

### Ship
- [x] Tried by hand on the desktop: reminders from chat and voice (notification, banner, spoken),
      notes and to-dos from chat and from the screen
- [x] Desktop notifications: notify-send, or gdbus when libnotify-bin isn't installed (as on
      Pop!_OS/COSMIC); the .deb recommends libnotify-bin
- [x] README

## Real model (qwen3.5:2b, `scripts/planner_bench.py`)

34 phrases (typed and voice-style), each a fresh chat on a throwaway folder; a case passes when the
right tool was called and the right thing was saved (time and repeat, list, note text...). Six
are file questions that must not reach these tools. Warm, on the development laptop (RTX 3050 4 GB).

| Run | Score | What changed |
|---|---|---|
| 1 | 22/34 (65%) | the tools, times from the model's words checked against the user's message |
| 2 | 28/34 (82%) | the keyword pre-filter, unmentioned lists ignored, clearer tool descriptions, at most 5 tool steps per turn |
| 3 | **32/34 (94%)** | the user's "every ..." kept when the model moves it into the text; the same to-do written twice is not a question |

By kind in run 3: reminders 8/8, to-dos 6/7, notes 5/5, show 3/3, done 3/3, cancel 1/2, files 6/6
(no file question reached these tools). About 11 s per message.

What the model did that the guards now catch: "tonight" passed as "tonight at 11pm"; "on Friday"
and a birthday marked weekly; a bill put on the Shopping list; "note: ..." answered with a file
search and "write down ..." with create_file; "every day" moved into the reminder's text.

Still failing (known limits):
- "I need to renew my car insurance": nothing marks it as a to-do, so the model searches files
  (now stopped after 5 tool steps with an answer, instead of an error after ~50 s). Treating
  "I need to ..." as a to-do would break "I need to find my CV".
- "stop reminding me about the plants": the model lists the reminders but doesn't cancel one.
