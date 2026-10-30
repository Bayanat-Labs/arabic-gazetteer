import pytest

from arabic_gazetteer import geonames


class _Resp:
    def __init__(self, status, body=b"x"):
        self.status_code = status
        self.headers = {"Last-Modified": "Fri, 30 Oct 2026 03:00:00 GMT"}
        self._body = body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def iter_content(self, n):
        yield self._body


class _Session:
    def __init__(self, status):
        self.headers = {}
        self.status = status
        self.urls = []

    def get(self, url, **kw):
        self.urls.append(url)
        return _Resp(self.status)


def test_fetch_writes_meta(tmp_path, monkeypatch):
    import requests

    s = _Session(200)
    monkeypatch.setattr(requests, "Session", lambda: s)
    monkeypatch.setattr(geonames, "MIN_REQUEST_GAP_S", 0)
    rows = geonames.fetch(str(tmp_path), ["SA"], log=lambda *_: None)
    assert len(rows) == len(s.urls) == 8
    assert s.headers["User-Agent"].startswith("BayanatLabs-OpenData/1.0")
    assert (tmp_path / "SA.zip.meta.json").exists()
    # a second run downloads nothing
    s.urls.clear()
    geonames.fetch(str(tmp_path), ["SA"], log=lambda *_: None)
    assert s.urls == []


def test_fetch_stops_on_429(tmp_path, monkeypatch):
    import requests

    monkeypatch.setattr(requests, "Session", lambda: _Session(429))
    monkeypatch.setattr(geonames, "MIN_REQUEST_GAP_S", 0)
    with pytest.raises(RuntimeError, match="429"):
        geonames.fetch(str(tmp_path), ["SA"], log=lambda *_: None)
