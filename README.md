# Zoom Coach

A live coach for your calls. It follows the transcript while you talk, reads your project
context and your notes, and keeps a side panel updated with:

- **Say next**: the single most useful thing to say right now
- **Tips**: questions to ask, when to steer, when to just listen, risks to handle, moments to close
- **Goals**: live status of each goal for the call (not started / in progress / achieved / at risk)
- **Risks & open threads**: objections and questions raised that haven't been handled yet
- **End & debrief**: a summary, decisions, action items, missed opportunities and a ready-to-send follow-up email

Everything is saved to `sessions/` as Markdown and JSON when you debrief or stop the app.

Coaching is powered by Claude (`claude-opus-5` by default) through the Anthropic API.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .                 # add ".[audio]" to transcribe audio locally
export ANTHROPIC_API_KEY=sk-ant-...
```

## Try it with the demo call

```bash
zoom-coach --source replay --file examples/sample_call.txt \
  --context context/ --me Robert \
  --goal "Get agreement to a one-branch pilot with a start date" \
  --goal "Get a meeting with Sam Patel (CFO) booked" \
  --open
```

The panel opens at http://127.0.0.1:8765. Put the window beside Zoom.

## Add your project context

Put briefs, account notes, pricing, past call summaries, stakeholder lists and so on in a
folder (`.md`, `.txt`, `.csv`, `.json`, `.yaml`) and pass it with `--context`. Pass
`--context` more than once to combine folders. `context/example-project.md` shows the
kind of information that leads to the most useful tips.

During the call, use **Note to coach** to add things as they happen ("they're worried about
security", "I want to push for a CTO meeting"). Notes take priority over everything else and
start a new update straight away. You can also edit the goals in the panel.

## Getting the live transcript from Zoom

Pick whichever works for your setup:

| Source | How | When to use it |
|---|---|---|
| **Local audio** `--source audio` | Transcribes an audio device on your machine with Whisper (runs locally, free). | Works with any meeting app and needs no Zoom settings. |
| **Transcript file** `--source file --file PATH` | Follows a file that another tool keeps writing. Supports glob patterns and follows the newest match. | You already use a captioning or notes tool that writes a transcript file. |
| **Paste / API** `--source none` | Paste lines in the panel, or `POST` them to `/api/transcript`. | Hooking up another tool, or catching the coach up mid-call. |

### Local audio (recommended)

```bash
pip install -e ".[audio]"
zoom-coach --list-devices                 # find your device
zoom-coach --source audio --device "BlackHole 2ch" --context context/ --goal "..." --open
```

The coach needs to hear **both sides** of the call, not just your microphone:

- **macOS:** install [BlackHole](https://existential.audio/blackhole/). In Audio MIDI Setup,
  create a Multi-Output Device (your speakers + BlackHole) and pick it as Zoom's speaker. For
  your own voice as well, create an Aggregate Device (BlackHole + mic) and use that as `--device`.
- **Windows:** enable "Stereo Mix", or install VB-Audio Cable, and use it as `--device`.
- **Linux:** use the PulseAudio/PipeWire monitor source of your output device.

Whisper can't tell speakers apart, so the coach works out who is talking from context.
`--whisper-model base.en` is faster; `medium.en` is more accurate.

### Transcript file

Zoom's desktop app can save captions (Settings → Accessibility → "Save captions", or
**Save transcript** in the Captions panel). It writes them to your Zoom folder, e.g.

```bash
zoom-coach --source file --file "~/Documents/Zoom/*/meeting_saved_closed_caption.txt" --context context/
```

Zoom only writes this file when captions are saved, so it's usually not live. For live
coaching, local audio is more dependable. The file source also works with any other tool
that appends to a text file (Otter exports, VTT files, custom scripts).

Supported formats: Zoom saved captions (`[Name] 10:01:22` followed by text), WebVTT,
`10:01:22 Name: text`, `Name: text`, and plain lines.

### Pushing lines from another tool

```bash
curl -X POST localhost:8765/api/transcript -H 'Content-Type: application/json' \
  -d '{"speaker": "Dana", "text": "Price is going to come up."}'
# or send a block of transcript text to be parsed:
curl -X POST localhost:8765/api/transcript -H 'Content-Type: application/json' \
  -d '{"raw": true, "text": "Dana: hello\nRobert: hi"}'
```

This is also the hook for a Zoom Realtime Media Streams (RTMS) app, if you want a
Zoom-native integration later.

## Options

| Flag | Default | What it does |
|---|---|---|
| `--goal TEXT` | none | Goal for the call (repeatable). The coach steers toward these. |
| `--context PATH` | none | Project context file or folder (repeatable). |
| `--me NAME` | none | Your name as it appears in the transcript. |
| `--title TEXT` | `Live call` | Call name, used for the saved notes. |
| `--effort` | `low` | Effort for live tips. `medium` gives deeper tips but takes longer. |
| `--debrief-effort` | `high` | Effort for the post-call debrief. |
| `--interval SEC` | `20` | Minimum seconds between automatic updates. |
| `--min-new-chars N` | `200` | How much new conversation triggers an update. |
| `--model ID` | `claude-opus-5` | Claude model (or set `ZOOM_COACH_MODEL`). |
| `--no-fallbacks` | off | Disables server-side model fallback when a request is declined. |
| `--port` / `--host` | `8765` / `127.0.0.1` | Where the panel is served. |
| `--sessions-dir` | `sessions` | Where call notes are saved. |

**Tip now** in the panel asks for an update immediately, and **Pause** stops automatic
updates, e.g. during small talk. Click a tip to cross it off.

## Cost and privacy

- Every update sends the transcript so far, your goals, your notes and your project context
  to the Anthropic API. The project context is prompt-cached, so repeat updates cost much less.
  With the defaults you get an update roughly every 20–60 seconds while people are talking.
- Local audio transcription never leaves your machine; only the transcribed text is sent.
- The server only listens on `127.0.0.1` unless you change `--host`. It has no login, so
  don't expose it to a network.
- Tell the people on the call that you're transcribing it, and follow your local recording
  consent laws.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Code layout: `zoom_coach/coach.py` (prompts and Claude calls), `server.py` (session, coaching
loop, API, event stream), `transcript.py` (storage and format parsing), `sources/` (audio,
file, replay), `static/index.html` (the panel).
