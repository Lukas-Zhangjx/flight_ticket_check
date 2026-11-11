"""Unified notify(title, message, click_url) that fans out to every
configured channel. Today that's just ntfy; adding WeChat later means
adding a channel class here, not touching any caller."""

from .ntfy import NtfyChannel


def get_channels():
    channels = [NtfyChannel()]
    return [c for c in channels if c.is_configured()]


def notify(title, message, click_url=None):
    channels = get_channels()
    if not channels:
        print("[no notification channel configured]\n" + message)
        return
    for channel in channels:
        try:
            channel.send(title, message, click_url)
            print(f"{channel.__class__.__name__}: sent")
        except Exception as e:
            print(f"{channel.__class__.__name__} failed: {e}")
