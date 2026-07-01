"""One Apify actor-runner shared by every stage that scrapes.

Encapsulates the client → actor → call → dataset → items chain so callers
get a plain list back and don't reimplement Apify boilerplate.
"""
try:
    from apify_client import ApifyClient
except ImportError:
    ApifyClient = None


def run_actor(token: str, actor_id: str, run_input: dict) -> list[dict]:
    if not token:
        raise RuntimeError("APIFY_TOKEN not set")
    if ApifyClient is None:
        raise RuntimeError("apify_client package not installed")
    client = ApifyClient(token)
    run = client.actor(actor_id).call(run_input=run_input)
    return list(client.dataset(run.default_dataset_id).iterate_items())
