class HysysError(Exception):
    """可向用户展示的工程错误；不得包含凭据。"""


class RetryableHysysError(HysysError):
    """仅用于已确认重试安全的临时故障。"""


class UnverifiedAPIError(HysysError):
    pass
