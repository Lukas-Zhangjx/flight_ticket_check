"""Common interface every notification channel implements, so adding a new
channel (e.g. WeChat) later never touches the callers."""


class NotifyChannel:
    def is_configured(self):
        raise NotImplementedError

    def send(self, title, message, click_url=None):
        raise NotImplementedError
