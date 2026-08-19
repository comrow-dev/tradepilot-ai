from datetime import datetime, timezone

LAST_SCAN = None
LAST_RESULTS = []
LAST_ERROR = None


def save_scan(results, error=None):
    global LAST_SCAN
    global LAST_RESULTS
    global LAST_ERROR

    LAST_SCAN = datetime.now(timezone.utc).isoformat()
    LAST_RESULTS = results
    LAST_ERROR = error


def get_state():
    return {
        "last_scan": LAST_SCAN,
        "results": LAST_RESULTS,
        "error": LAST_ERROR,
    }
