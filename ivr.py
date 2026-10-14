"""
Builds the Plivo XML for every step of the IVR call.

Each function returns an XML string that tells Plivo what to do next:
speak some text, collect keypresses (DTMF), play audio, or dial a number.
The Flask routes in app.py decide *which* step to return.
"""

from plivo import plivoxml

# Voice settings for Plivo's <Speak> element, per language.
VOICES = {
    "en": {"voice": "WOMAN", "language": "en-US"},
    "es": {"voice": "WOMAN", "language": "es-ES"},
}

# Everything the caller hears after choosing a language.
PROMPTS = {
    "en": {
        "menu": "Press 1 to hear a short audio message. Press 2 to speak with a live associate.",
        "playing": "Here is your audio message.",
        "connecting": "Connecting you to a live associate. Please hold.",
        "invalid": "Sorry, that is not a valid option.",
        "no_input": "We did not receive any input.",
    },
    "es": {
        "menu": "Presione 1 para escuchar un breve mensaje de audio. Presione 2 para hablar con un asociado.",
        "playing": "Aquí está su mensaje de audio.",
        "connecting": "Conectándolo con un asociado. Por favor espere.",
        "invalid": "Lo sentimos, esa no es una opción válida.",
        "no_input": "No recibimos ninguna respuesta.",
    },
}


def _speak(text, lang="en"):
    return plivoxml.SpeakElement(text, **VOICES[lang])


def _collect(action_url, prompt, num_digits, lang="en"):
    """Speak a prompt and wait for the caller to press keys.

    Plivo POSTs the pressed keys to `action_url` as the `Digits` parameter.
    If the caller presses nothing, Plivo falls through to the elements after
    <GetDigits>, so we say "no input" and redirect back to the same step.
    """
    get_digits = plivoxml.GetDigitsElement(
        action=action_url,
        method="POST",
        num_digits=num_digits,
        timeout=10,        # seconds to wait for the first key
        digit_timeout=5,   # seconds to wait between keys
        retries=1,
        redirect=True,
    )
    get_digits.add(_speak(prompt, lang))
    return get_digits


def otp_prompt(base_url, message=None):
    """Step 1: ask for the 4-digit OTP. `message` is said first (e.g. 'wrong OTP')."""
    response = plivoxml.ResponseElement()
    if message:
        response.add(_speak(message))
    response.add(_collect(
        f"{base_url}/otp",
        "Please enter your 4 digit O T P.",
        num_digits=4,
    ))
    response.add(_speak("We did not receive any input."))
    response.add(plivoxml.RedirectElement(f"{base_url}/otp-menu", method="POST"))
    return response.to_string()


def language_prompt(base_url, message=None):
    """Level 1: choose English or Spanish."""
    response = plivoxml.ResponseElement()
    if message:
        response.add(_speak(message))
    get_digits = _collect(
        f"{base_url}/language",
        "Press 1 for English.",
        num_digits=1,
    )
    get_digits.add(_speak("Para español, presione 2.", "es"))
    response.add(get_digits)
    response.add(_speak("We did not receive any input."))
    response.add(plivoxml.RedirectElement(f"{base_url}/language-menu", method="POST"))
    return response.to_string()


def action_prompt(base_url, lang, message=None):
    """Level 2: play audio or talk to an associate, in the chosen language."""
    text = PROMPTS[lang]
    response = plivoxml.ResponseElement()
    if message:
        response.add(_speak(message, lang))
    response.add(_collect(
        f"{base_url}/action?lang={lang}",
        text["menu"],
        num_digits=1,
        lang=lang,
    ))
    response.add(_speak(text["no_input"], lang))
    response.add(plivoxml.RedirectElement(f"{base_url}/action-menu?lang={lang}", method="POST"))
    return response.to_string()


def play_audio(base_url, lang, audio_url):
    """Level 2, option 1: play the MP3, then return to the Level 2 menu."""
    response = plivoxml.ResponseElement()
    response.add(_speak(PROMPTS[lang]["playing"], lang))
    response.add(plivoxml.PlayElement(audio_url))
    response.add(plivoxml.RedirectElement(f"{base_url}/action-menu?lang={lang}", method="POST"))
    return response.to_string()


def forward_to_associate(lang, associate_number, caller_id):
    """Level 2, option 2: bridge the caller to the live associate number."""
    response = plivoxml.ResponseElement()
    response.add(_speak(PROMPTS[lang]["connecting"], lang))
    dial = plivoxml.DialElement(caller_id=caller_id)
    dial.add(plivoxml.NumberElement(associate_number))
    response.add(dial)
    return response.to_string()
