"""Configuration for AWS Summit Singapore crawler."""

EVENTS_URL = (
    "https://site-assets.corrivium.live/cms/events/aws-summitsapj26/root/prod/events.json"
)
SESSION_FRONTEND_TEMPLATE = (
    "https://site-assets.corrivium.live/cms/events/aws-summitsapj26/"
    "{session_id}/prod/frontend.json"
)
DEFAULT_OUTPUT_DIR = "output"
SINGAPORE_SESSION_PREFIX = "sin-"

USER_AGENT = (
    "Mozilla/5.0 (compatible; AWS-Summit-Crawler/1.0; +https://github.com/)"
)

# HTTP tuning
REQUEST_TIMEOUT_SEC = 120
MAX_RETRIES = 3
RETRY_BACKOFF_SEC = 2.0
DEFAULT_DELAY_BETWEEN_SESSIONS_SEC = 1.5
