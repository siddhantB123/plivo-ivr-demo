# InspireWorks IVR Demo (Plivo Voice API)

A small Flask app that places an outbound call with Plivo, authenticates the caller with a DTMF OTP, and then runs a two-level IVR menu.

## Call flow

```
"Call me" button ──► Plivo dials your phone
                         │
                    You answer
                         ▼
          Enter 4-digit OTP (birthdate DDMM) ◄──┐
                         │                       │ wrong OTP / no input
                         ├───────────────────────┘
                     correct
                         ▼
     Level 1: 1 = English, 2 = Spanish  ◄── invalid / no input repeats
                         ▼
     Level 2: 1 = play audio (then back to Level 2)
              2 = forward to live associate
                         ◄── invalid / no input repeats
```

| Route | What it does |
|---|---|
| `GET /` | Web page to trigger the call and watch a live call log |
| `POST /call` | Calls Plivo's API to start the outbound call |
| `/answer` | Plivo hits this when the call is answered: welcome + asks for the OTP |
| `POST /otp` | Checks the OTP: wrong = ask again, right = Level 1 |
| `POST /language` | Level 1: language choice |
| `POST /action?lang=en\|es` | Level 2: play audio or dial the associate |
| `POST /otp-menu`, `/language-menu`, `/action-menu` | Replay a menu (used after no input or after the audio) |
| `POST /hangup` | Plivo reports the call ended |

All call steps are returned as **Plivo XML** (built in [`ivr.py`](ivr.py)); the routing logic is in [`app.py`](app.py).

## Prerequisites

- Python 3.10+
- A Plivo account: **Auth ID**, **Auth Token** (Plivo Console → Overview) and a Plivo phone number
- A way to expose your local server publicly, because Plivo must reach your webhooks. This guide uses [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/) (no account needed). ngrok works too.

## Setup

```bash
git clone https://github.com/siddhantB123/plivo-ivr-demo.git
cd plivo-ivr-demo
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill it in:

| Variable | Description |
|---|---|
| `PLIVO_AUTH_ID` | Plivo Auth ID |
| `PLIVO_AUTH_TOKEN` | Plivo Auth Token |
| `PLIVO_FROM_NUMBER` | Plivo number the call comes from (E.164, e.g. `+918035454161`) |
| `ASSOCIATE_NUMBER` | Live associate number for Level 2 option 2 (E.164) |
| `DEFAULT_TO_NUMBER` | Number pre-filled in the web page (optional) |
| `OTP` | Birthdate in DDMM format (hardcoded OTP) |
| `AUDIO_URL_EN` | MP3 for Level 2 option 1 in English. Leave empty to use the bundled 10-second spoken message `static/message.mp3` |
| `AUDIO_URL_ES` | MP3 for Level 2 option 1 in Spanish. Leave empty to use Plivo's public sample `music.mp3` |
| `PUBLIC_BASE_URL` | Public URL of this app (from the tunnel), no trailing slash |

`.env` is git-ignored, so credentials are never committed.

## Run

1. Download `cloudflared` from the [official releases page](https://github.com/cloudflare/cloudflared/releases/latest) (Windows: `cloudflared-windows-amd64.exe`, rename to `cloudflared.exe`; macOS: `brew install cloudflared`). Start a tunnel to port 5000 and copy the `https://....trycloudflare.com` URL it prints:
   ```bash
   cloudflared tunnel --url http://localhost:5000
   ```
   On Windows with the downloaded exe in the project folder: `.\cloudflared.exe tunnel --url http://localhost:5000`
2. Put that URL in `.env` as `PUBLIC_BASE_URL`.
3. Start the app:
   ```bash
   python app.py
   ```
4. Open http://localhost:5000, enter your number and click **Call me**.

## Test script

1. Answer the call. You will hear "Welcome to Inspire Works. Please enter your 4 digit OTP."
2. Enter a **wrong** OTP (e.g. `1234`): you hear "incorrect" and get asked again.
3. Enter the **correct** OTP: you hear "You are verified" and the language menu.
4. Press `1` (English) or `2` (Spanish). Any other key repeats the menu.
5. Press `1` to hear the audio message (English: a 10-second spoken message; Spanish: Plivo's sample MP3). Afterwards you return to this menu. Press `2` to be connected to the live associate.

The web page shows each step in its call log as it happens.

## Notes

- If the Plivo account is a trial account, it can only call numbers verified in the Plivo console.
- The call log is kept in memory and resets when the app restarts. No database is needed.
- The quick-tunnel URL changes each time `cloudflared` restarts; update `PUBLIC_BASE_URL` and restart the app when it does.

## Possible production improvements

- Validate the `X-Plivo-Signature-V3` header on webhooks so only Plivo can drive the call flow.
- Hang up after a few rounds of no input instead of repeating the menu indefinitely.
- Store call logs in a database instead of memory.
