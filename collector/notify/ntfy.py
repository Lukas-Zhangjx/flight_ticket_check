"""ntfy.sh channel (https://ntfy.sh). JSON publish so Chinese/emoji titles
survive, per SPEC.md section 6's notify() requirement."""

import json
import os
import urllib.request

from .base import NotifyChannel

UA = {"User-Agent": "personal-flight-watch/1.0", "Content-Type": "application/json"}


class NtfyChannel(NotifyChannel):
    def __init__(self, topic=None, server=None, timeout=30):
        self.topic = topic if topic is not None else os.getenv("NTFY_TOPIC")
        self.server = (server if server is not None
                       else os.getenv("NTFY_SERVER", "https://ntfy.sh")).rstrip("/")
        self.timeout = timeout

    def is_configured(self):
        return bool(self.topic)

    def send(self, title, message, click_url=None):
        payload = {
            "topic": self.topic,
            "title": title[:60],
            "message": message,
            "tags": ["airplane"],
        }
        if click_url:
            payload["click"] = click_url
        req = urllib.request.Request(self.server, json.dumps(payload).encode(),
                                      headers=UA)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return r.read().decode("utf-8", "replace")
