"""
InspireWorks demo IVR on Plivo.

Call flow:
    POST /call          -> asks Plivo to dial the target number
    /answer             -> caller picked up: ask for the OTP
    /otp                -> check the OTP; wrong = ask again, right = Level 1
    /language           -> Level 1: 1 = English, 2 = Spanish
    /action?lang=xx     -> Level 2: 1 = play audio, 2 = forward to associate
    /hangup             -> Plivo tells us the call ended
"""

import os
from collections import defaultdict
from datetime import datetime

import plivo
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request

import ivr

load_dotenv()

AUTH_ID = os.environ["PLIVO_AUTH_ID"]
AUTH_TOKEN = os.environ["PLIVO_AUTH_TOKEN"]
FROM_NUMBER = os.environ["PLIVO_FROM_NUMBER"]
ASSOCIATE_NUMBER = os.environ["ASSOCIATE_NUMBER"]
DEFAULT_TO_NUMBER = os.getenv("DEFAULT_TO_NUMBER", "")
OTP = os.getenv("OTP", "0106")  # birthdate in DDMM format
AUDIO_URL = os.getenv("AUDIO_URL", "https://s3.amazonaws.com/plivocloud/music.mp3")
BASE_URL = os.environ["PUBLIC_BASE_URL"].rstrip("/")  # public URL Plivo can reach

app = Flask(__name__)
plivo_client = plivo.RestClient(AUTH_ID, AUTH_TOKEN)

# In-memory log of what happened on each call, shown live on the web page.
call_events = defaultdict(list)


def log_event(message):
    call_uuid = request.values.get("CallUUID", "unknown")
    call_events[call_uuid].append({"time": datetime.now().strftime("%H:%M:%S"), "message": message})
    print(f"[{call_uuid}] {message}")


def xml(body):
    return Response(body, mimetype="application/xml")


# ---------- Web UI ----------

@app.get("/")
def index():
    return render_template("index.html", default_to=DEFAULT_TO_NUMBER)


@app.post("/call")
def make_call():
    to_number = (request.json or {}).get("to") or DEFAULT_TO_NUMBER
    to_number = to_number.replace(" ", "")
    if not to_number:
        return jsonify(error="Enter a phone number to call"), 400
    try:
        result = plivo_client.calls.create(
            from_=FROM_NUMBER,
            to_=to_number,
            answer_url=f"{BASE_URL}/answer",
            answer_method="POST",
            hangup_url=f"{BASE_URL}/hangup",
            hangup_method="POST",
        )
    except plivo.exceptions.PlivoRestError as e:
        return jsonify(error=str(e)), 502
    request_uuid = result.request_uuid
    print(f"Outbound call requested to {to_number}: {request_uuid}")
    return jsonify(request_uuid=request_uuid, to=to_number)


@app.get("/events")
def events():
    """All call logs, newest call first."""
    return jsonify([{"call_uuid": uuid, "events": evts} for uuid, evts in reversed(call_events.items())])


# ---------- Plivo webhooks (return Plivo XML) ----------

@app.route("/answer", methods=["GET", "POST"])
def answer():
    log_event("Call answered - asking for OTP")
    return xml(ivr.otp_prompt(BASE_URL, message="Welcome to Inspire Works."))


@app.post("/otp-menu")
def otp_menu():
    return xml(ivr.otp_prompt(BASE_URL))


@app.post("/otp")
def verify_otp():
    digits = request.values.get("Digits", "")
    if digits == OTP:
        log_event("OTP correct - caller authenticated")
        return xml(ivr.language_prompt(BASE_URL, message="Thank you. You are verified."))
    log_event(f"Wrong OTP entered ({digits or 'nothing'}) - asking again")
    return xml(ivr.otp_prompt(BASE_URL, message="The O T P you entered is incorrect. Please try again."))


@app.post("/language-menu")
def language_menu():
    return xml(ivr.language_prompt(BASE_URL))


@app.post("/language")
def choose_language():
    digits = request.values.get("Digits", "")
    lang = {"1": "en", "2": "es"}.get(digits)
    if not lang:
        log_event(f"Invalid language option ({digits or 'nothing'}) - repeating Level 1")
        return xml(ivr.language_prompt(BASE_URL, message="Sorry, that is not a valid option."))
    log_event(f"Language selected: {'English' if lang == 'en' else 'Spanish'}")
    return xml(ivr.action_prompt(BASE_URL, lang))


@app.post("/action-menu")
def action_menu():
    lang = request.args.get("lang", "en")
    return xml(ivr.action_prompt(BASE_URL, lang))


@app.post("/action")
def choose_action():
    lang = request.args.get("lang", "en")
    digits = request.values.get("Digits", "")
    if digits == "1":
        log_event("Level 2: playing audio message")
        return xml(ivr.play_audio(BASE_URL, lang, AUDIO_URL))
    if digits == "2":
        log_event(f"Level 2: forwarding to live associate {ASSOCIATE_NUMBER}")
        return xml(ivr.forward_to_associate(lang, ASSOCIATE_NUMBER, FROM_NUMBER))
    log_event(f"Invalid Level 2 option ({digits or 'nothing'}) - repeating menu")
    return xml(ivr.action_prompt(BASE_URL, lang, message=ivr.PROMPTS[lang]["invalid"]))


@app.post("/hangup")
def hangup():
    cause = request.values.get("HangupCause", "")
    log_event(f"Call ended ({cause})")
    return "", 204


if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", 5000)), debug=True)
