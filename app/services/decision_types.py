"""
Shared constants mapping the Brain's task classification vocabulary
to the intent keys used by the task executor / action builder.

brain_service.py imports:
    ROUTE_TO_INTENT, INTENT_OPEN
"""

# Intent keys used throughout the task-execution pipeline.
INTENT_OPEN = "open"
INTENT_PLAY = "play"
INTENT_GENERATE_IMAGE = "generate_image"
INTENT_CONTENT = "content"
INTENT_GOOGLE_SEARCH = "google_search"
INTENT_YOUTUBE_SEARCH = "youtube_search"
INTENT_OPEN_WEBCAM = "open_webcam"
INTENT_CLOSE_WEBCAM = "close_webcam"

# Task types returned by BrainService.classify_task() map 1:1 onto
# intent keys today, but this indirection lets the vocabulary used by
# the classifier prompt drift from the executor's internal intent
# names without touching either side.
ROUTE_TO_INTENT = {
    "open": INTENT_OPEN,
    "play": INTENT_PLAY,
    "generate_image": INTENT_GENERATE_IMAGE,
    "content": INTENT_CONTENT,
    "google_search": INTENT_GOOGLE_SEARCH,
    "youtube_search": INTENT_YOUTUBE_SEARCH,
    "open_webcam": INTENT_OPEN_WEBCAM,
    "close_webcam": INTENT_CLOSE_WEBCAM,
}

# Which intents run instantly (return a URL/action right away) vs.
# which run in the background and get polled via /tasks/{id}.
INSTANT_INTENTS = {
    INTENT_OPEN,
    INTENT_PLAY,
    INTENT_GOOGLE_SEARCH,
    INTENT_YOUTUBE_SEARCH,
    INTENT_OPEN_WEBCAM,
    INTENT_CLOSE_WEBCAM,
}

BACKGROUND_INTENTS = {
    INTENT_GENERATE_IMAGE,
    INTENT_CONTENT,
}
