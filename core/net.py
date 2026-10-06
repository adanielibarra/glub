"""HTTPS requests through the QGIS network manager.

Using QgsNetworkAccessManager instead of urllib means the user's QGIS proxy,
SSL and network timeout settings are honoured. Works in background threads
(QgsNetworkAccessManager.instance() gives one manager per thread).

Redirects are followed by hand (https only, headers kept) so the CDSE bearer
token survives the jump from zipper to the download host.
"""
from qgis.PyQt.QtCore import QByteArray, QEventLoop, QTimer, QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.core import QgsNetworkAccessManager

MAX_REDIRECTS = 5

_ATTR = QNetworkRequest.Attribute
_STATUS = _ATTR.HttpStatusCodeAttribute
_TARGET = _ATTR.RedirectionTargetAttribute
_NO_ERROR = QNetworkReply.NetworkError.NoError
_OP_CANCELED = QNetworkReply.NetworkError.OperationCanceledError


class NetError(Exception):
    """Network failure with no usable HTTP answer (DNS, proxy, SSL, timeout, cancel)."""


def check_https(url):
    if not str(url).startswith("https://"):
        raise NetError(f"Refusing a non-https URL: {str(url)[:60]}")


def _request(url, headers):
    check_https(url)
    req = QNetworkRequest(QUrl(url))
    for k, v in (headers or {}).items():
        req.setRawHeader(QByteArray(k.encode()), QByteArray(str(v).encode()))
    # we follow redirects ourselves (see module docstring)
    policy = getattr(QNetworkRequest, "RedirectPolicy", None)
    if policy is not None:
        req.setAttribute(_ATTR.RedirectPolicyAttribute, policy.ManualRedirectPolicy)
    else:  # very old Qt
        req.setAttribute(_ATTR.FollowRedirectsAttribute, False)
    # never keep big downloads in the QGIS network disk cache
    req.setAttribute(_ATTR.CacheSaveControlAttribute, False)
    return req


def _exec(loop):
    (loop.exec if hasattr(loop, "exec") else loop.exec_)()


def _wait(reply, timeout, is_canceled=None, on_data=None):
    """Run a local event loop until the reply finishes.

    timeout is an idle timeout in seconds: it restarts every time data arrives.
    Returns 'timeout', 'canceled' or None.
    """
    state = {"why": None}
    loop = QEventLoop()
    idle = QTimer()
    idle.setSingleShot(True)
    poll = QTimer()

    def on_idle():
        state["why"] = "timeout"
        reply.abort()

    def on_poll():
        if is_canceled and is_canceled():
            state["why"] = "canceled"
            reply.abort()

    def on_ready():
        idle.start(int(timeout * 1000))
        if is_canceled and is_canceled():
            state["why"] = "canceled"
            reply.abort()
            return
        if on_data:
            on_data(reply)

    idle.timeout.connect(on_idle)
    poll.timeout.connect(on_poll)
    reply.readyRead.connect(on_ready)
    reply.finished.connect(loop.quit)
    idle.start(int(timeout * 1000))
    poll.start(200)
    if not reply.isFinished():
        _exec(loop)
    idle.stop()
    poll.stop()
    return state["why"]


def _status(reply):
    code = reply.attribute(_STATUS)
    return int(code) if code is not None else None


def _raise_if_failed(reply, why, url):
    if why == "canceled":
        raise NetError("Canceled.")
    if why == "timeout":
        raise NetError(f"No answer from {QUrl(url).host()} (timeout).")
    if reply.error() not in (_NO_ERROR,) and _status(reply) is None:
        if reply.error() == _OP_CANCELED:
            raise NetError("Canceled.")
        raise NetError(f"Network error with {QUrl(url).host()}: {reply.errorString()}")


def _send(method, url, headers, data, timeout, is_canceled=None, on_data=None):
    """One request, following redirects. Returns the finished reply and its status."""
    nam = QgsNetworkAccessManager.instance()
    for _ in range(MAX_REDIRECTS + 1):
        req = _request(url, headers)
        if method == "POST":
            reply = nam.post(req, QByteArray(data or b""))
        else:
            reply = nam.get(req)
        why = _wait(reply, timeout, is_canceled, on_data)
        _raise_if_failed(reply, why, url)
        status = _status(reply)
        target = reply.attribute(_TARGET)
        if status in (301, 302, 303, 307, 308) and target is not None:
            url = reply.url().resolved(target).toString()
            reply.deleteLater()
            if status == 303:
                method, data = "GET", None
            continue
        return reply, status
    raise NetError("Too many redirects.")


def request(method, url, headers=None, data=None, timeout=60):
    """Small request (token, search). Returns (status, body bytes)."""
    reply, status = _send(method, url, headers, data, timeout)
    body = bytes(reply.readAll())
    reply.deleteLater()
    return status, body


def download(url, fileobj, headers=None, progress=None, is_canceled=None, timeout=300,
             expected_size=None):
    """Stream a GET into an open binary file.

    progress(done, total) and is_canceled() are optional callbacks.
    Returns (status, first bytes of the body when status is not 200).
    """
    state = {"done": 0, "err": b""}

    def on_data(reply):
        if _status(reply) in (301, 302, 303, 307, 308):
            reply.readAll()  # body of a redirect, not the product
            return
        buf = bytes(reply.readAll())
        if _status(reply) != 200:
            state["err"] = (state["err"] + buf)[:2000]
            return
        fileobj.write(buf)
        state["done"] += len(buf)
        if progress:
            total = reply.header(QNetworkRequest.KnownHeaders.ContentLengthHeader)
            progress(state["done"], int(total or expected_size or 0))

    reply, status = _send("GET", url, headers, None, timeout, is_canceled, on_data)
    on_data(reply)  # anything left after the last readyRead
    reply.deleteLater()
    return status, state["err"]
