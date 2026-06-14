#!/usr/bin/env python3
#
# Copyright (C) 2026 Andrea Chiarini
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# Test suite for claude-token-genmon.py. Pure stdlib (unittest) -- run with:
#     python3 -m unittest -v
# or, if you have pytest installed:
#     pytest -v
"""Unit and integration tests for the genmon widget.

The module under test has a hyphenated filename (it is an executable, not an
importable package name), so it is loaded by path. Tests isolate all on-disk
state into a temp dir and monkeypatch the network, never touching the real
~/.claude or contacting the API.
"""

import contextlib
import email.message
import importlib.util
import io
import json
import tempfile
import time
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "claude-token-genmon.py"


def load_module():
    """Load claude-token-genmon.py as a fresh module object."""
    spec = importlib.util.spec_from_file_location("ctg", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_urlopen_returning(payload):
    """Build a urlopen replacement yielding a context manager with .read()."""
    body = json.dumps(payload).encode()

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return body

    def _open(req, timeout=None):
        return _Resp()

    return _open


def http_error(code, retry_after=None):
    """Build a urlopen replacement that raises an HTTPError."""
    hdrs = email.message.Message()
    if retry_after is not None:
        hdrs["Retry-After"] = str(retry_after)

    def _open(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, code, "err", hdrs, None)

    return _open


class Base(unittest.TestCase):
    def setUp(self):
        self.m = load_module()
        self.tmp = Path(tempfile.mkdtemp(prefix="ctt-test-"))
        # Redirect every on-disk path into the temp sandbox.
        self.m.CACHE_DIR = self.tmp / "cache"
        self.m.USAGE_CACHE = self.m.CACHE_DIR / "usage.json"
        self.m.EVENTS_CACHE = self.m.CACHE_DIR / "events.json"
        self.m.CRED_FILE = self.tmp / "credentials.json"
        self.m.PROJECTS_DIR = self.tmp / "projects"
        self.m.PROJECTS_DIR.mkdir(exist_ok=True)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_main(self):
        """Run main() capturing stdout, returning the printed text."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.m.main()
        return buf.getvalue()


# --------------------------------------------------------------------------- #
# Pure helpers                                                                 #
# --------------------------------------------------------------------------- #
class TestHelpers(Base):
    def test_iso_to_epoch_variants(self):
        ep = self.m.iso_to_epoch("2026-06-15T00:00:00+00:00")
        self.assertEqual(ep, self.m.iso_to_epoch("2026-06-15T00:00:00Z"))
        self.assertIsInstance(ep, float)

    def test_iso_to_epoch_invalid(self):
        self.assertIsNone(self.m.iso_to_epoch("not-a-date"))
        self.assertIsNone(self.m.iso_to_epoch(None))

    def test_weighted_uses_module_weights(self):
        self.m.W_INPUT, self.m.W_OUTPUT = 1, 5
        self.m.W_CACHE_READ, self.m.W_CACHE_WRITE = 0.1, 1.25
        usage = {
            "input_tokens": 10,
            "output_tokens": 2,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 4,
        }
        # 10*1 + 2*5 + 100*0.1 + 4*1.25 = 10 + 10 + 10 + 5 = 35
        self.assertAlmostEqual(self.m.weighted(usage), 35.0)

    def test_weighted_missing_keys_default_zero(self):
        self.assertEqual(self.m.weighted({}), 0)

    def test_colour_thresholds(self):
        self.assertIsNone(self.m.colour(0))
        self.assertIsNone(self.m.colour(69.9))
        self.assertEqual(self.m.colour(70), "#e5c07b")   # amber boundary
        self.assertEqual(self.m.colour(89.9), "#e5c07b")
        self.assertEqual(self.m.colour(90), "#e06c75")   # red boundary
        self.assertEqual(self.m.colour(100), "#e06c75")

    def test_span_wraps_only_when_coloured(self):
        self.assertEqual(self.m.span("x", 10), "x")
        self.assertIn("foreground='#e06c75'", self.m.span("x", 95))

    def test_reset_hm(self):
        self.assertIsNone(self.m.reset_hm(None))
        epoch = time.time() + 3600
        iso = datetime.fromtimestamp(epoch).astimezone().isoformat()
        expected = datetime.fromtimestamp(epoch).strftime("%H:%M")
        self.assertEqual(self.m.reset_hm(iso), expected)


# --------------------------------------------------------------------------- #
# Credentials + network                                                        #
# --------------------------------------------------------------------------- #
class TestAccessToken(Base):
    def test_reads_token(self):
        self.m.CRED_FILE.write_text(
            json.dumps({"claudeAiOauth": {"accessToken": "abc123"}})
        )
        self.assertEqual(self.m.access_token(), "abc123")

    def test_missing_file(self):
        self.assertIsNone(self.m.access_token())

    def test_malformed_and_missing_key(self):
        self.m.CRED_FILE.write_text("{not json")
        self.assertIsNone(self.m.access_token())
        self.m.CRED_FILE.write_text(json.dumps({"other": {}}))
        self.assertIsNone(self.m.access_token())


class TestFetchLiveUsage(Base):
    def setUp(self):
        super().setUp()
        self.m.CRED_FILE.write_text(
            json.dumps({"claudeAiOauth": {"accessToken": "tok"}})
        )

    def test_no_token_fails(self):
        self.m.CRED_FILE.unlink()
        self.assertEqual(self.m.fetch_live_usage(), ("fail", None))

    def test_ok(self):
        payload = {"five_hour": {"utilization": 12.0}}
        self.m.urllib.request.urlopen = fake_urlopen_returning(payload)
        status, data = self.m.fetch_live_usage()
        self.assertEqual(status, "ok")
        self.assertEqual(data, payload)

    def test_429_uses_retry_after(self):
        self.m.urllib.request.urlopen = http_error(429, retry_after=200)
        self.assertEqual(self.m.fetch_live_usage(), ("backoff", 200))

    def test_429_without_header_defaults(self):
        self.m.urllib.request.urlopen = http_error(429, retry_after=None)
        status, retry = self.m.fetch_live_usage()
        self.assertEqual(status, "backoff")
        self.assertEqual(retry, 171)

    def test_other_http_error_fails(self):
        self.m.urllib.request.urlopen = http_error(500)
        self.assertEqual(self.m.fetch_live_usage(), ("fail", None))

    def test_network_error_fails(self):
        def boom(req, timeout=None):
            raise urllib.error.URLError("offline")

        self.m.urllib.request.urlopen = boom
        self.assertEqual(self.m.fetch_live_usage(), ("fail", None))


class TestStateCache(Base):
    def test_round_trip(self):
        self.m.write_state({"at": 1, "data": {"x": 1}, "retry_until": 0})
        self.assertEqual(self.m.read_state()["data"], {"x": 1})

    def test_read_missing_or_corrupt(self):
        self.assertEqual(self.m.read_state(), {})
        self.m.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.m.USAGE_CACHE.write_text("{bad")
        self.assertEqual(self.m.read_state(), {})


# --------------------------------------------------------------------------- #
# Fallback estimate                                                            #
# --------------------------------------------------------------------------- #
class TestEstimate(Base):
    def _write_transcript(self, name, rows):
        proj = self.m.PROJECTS_DIR / "p"
        proj.mkdir(exist_ok=True)
        lines = [json.dumps(r) for r in rows]
        (proj / name).write_text("\n".join(lines))

    def test_parse_events_filters(self):
        now = time.time()
        recent = datetime.fromtimestamp(now - 100).astimezone().isoformat()
        old = datetime.fromtimestamp(now - 999999).astimezone().isoformat()
        self._write_transcript(
            "a.jsonl",
            [
                {"timestamp": recent, "message": {"usage": {"output_tokens": 10}}},
                {"timestamp": old, "message": {"usage": {"output_tokens": 10}}},
                {"no": "usage here"},
                {"timestamp": recent, "message": {"usage": {}}},  # no token keys
            ],
        )
        path = self.m.PROJECTS_DIR / "p" / "a.jsonl"
        events = self.m.parse_events(path, horizon=now - 1000)
        self.assertEqual(len(events), 1)            # only the recent, real one
        self.assertAlmostEqual(events[0][1], 10 * self.m.W_OUTPUT)

    def test_five_hour_anchor_active_and_elapsed(self):
        now = time.time()
        self.m.WINDOW_5H = 5 * 3600
        # active window: last message 1h ago
        events = [(now - 3600, 1.0)]
        anchor, reset = self.m.five_hour_anchor(events, now)
        self.assertEqual(anchor, now - 3600)
        self.assertEqual(reset, now - 3600 + self.m.WINDOW_5H)
        # elapsed: last message 6h ago -> no active window
        self.assertEqual(self.m.five_hour_anchor([(now - 6 * 3600, 1.0)], now),
                         (None, None))

    def test_five_hour_anchor_reanchors(self):
        now = time.time()
        self.m.WINDOW_5H = 5 * 3600
        # two clusters >5h apart: anchor should jump to the later cluster
        events = [(now - 10 * 3600, 1.0), (now - 2 * 3600, 1.0)]
        anchor, _ = self.m.five_hour_anchor(events, now)
        self.assertEqual(anchor, now - 2 * 3600)

    def test_estimate_usage_math_and_shape(self):
        now = time.time()
        self.m.BUDGET_5H = 1000.0
        self.m.BUDGET_WEEK = 2000.0
        self.m.WINDOW_5H = 5 * 3600
        self.m.WINDOW_WEEK = 7 * 86400
        self.m.collect_events = lambda _now: [(now - 60, 500.0)]
        out = self.m.estimate_usage(now)
        self.assertAlmostEqual(out["five_hour"]["utilization"], 50.0)
        self.assertAlmostEqual(out["seven_day"]["utilization"], 25.0)
        self.assertIn("resets_at", out["five_hour"])

    def test_estimate_usage_empty(self):
        self.m.collect_events = lambda _now: []
        self.assertIsNone(self.m.estimate_usage(time.time()))

    def test_collect_events_tolerates_old_3tuple_cache(self):
        now = time.time()
        proj = self.m.PROJECTS_DIR / "p"
        proj.mkdir(exist_ok=True)
        f = proj / "a.jsonl"
        f.write_text("{}")
        st = f.stat()
        # cache written by an older version: 3-tuples (epoch, weighted, raw)
        self.m.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.m.EVENTS_CACHE.write_text(json.dumps({
            str(f): {"mtime": st.st_mtime, "size": st.st_size,
                     "events": [[now - 10, 5.0, 999]]}
        }))
        events = self.m.collect_events(now)
        self.assertEqual(events, [(now - 10, 5.0)])  # raw column dropped


# --------------------------------------------------------------------------- #
# Rendering                                                                    #
# --------------------------------------------------------------------------- #
class TestRender(Base):
    def setUp(self):
        super().setUp()
        self.m.newest_transcript_mtime = lambda: time.time()  # never idle

    def render(self, data, source, age=0.0):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.m.render(data, time.time(), source, age)
        return buf.getvalue()

    def test_live_label_and_tooltip(self):
        data = {"five_hour": {"utilization": 14.0, "resets_at": None},
                "seven_day": {"utilization": 6.0, "resets_at": None}}
        out = self.render(data, "live")
        self.assertIn("5h 14%", out)
        self.assertIn("7d 6%", out)
        self.assertIn("source: live", out)
        self.assertNotIn("(est)", out)

    def test_estimate_tagged(self):
        data = {"five_hour": {"utilization": 5.0}, "seven_day": {"utilization": 9.0}}
        self.assertIn("(est)", self.render(data, "estimate"))

    def test_idle_greys_label(self):
        self.m.newest_transcript_mtime = lambda: 0  # ancient -> idle
        data = {"five_hour": {"utilization": 1.0}, "seven_day": {"utilization": 1.0}}
        self.assertIn("#888888", self.render(data, "live"))

    def test_extra_usage_shown_when_enabled(self):
        data = {"five_hour": {"utilization": 1.0}, "seven_day": {"utilization": 1.0},
                "extra_usage": {"is_enabled": True, "utilization": 40.0,
                                "monthly_limit": 50, "currency": "USD"}}
        self.assertIn("extra usage", self.render(data, "live"))

    def test_icon_image_emitted_and_glyph_dropped(self):
        icon = self.tmp / "icon.png"
        icon.write_bytes(b"\x89PNG\r\n")
        self.m.ICON_IMG = str(icon)
        data = {"five_hour": {"utilization": 1.0}, "seven_day": {"utilization": 1.0}}
        out = self.render(data, "live")
        self.assertIn(f"<img>{icon}</img>", out)
        self.assertNotIn(self.m.ICON, out)   # text glyph replaced by image

    def test_text_glyph_when_icon_missing(self):
        self.m.ICON_IMG = str(self.tmp / "does-not-exist.png")
        data = {"five_hour": {"utilization": 1.0}, "seven_day": {"utilization": 1.0}}
        out = self.render(data, "live")
        self.assertNotIn("<img>", out)
        self.assertIn(self.m.ICON, out)


# --------------------------------------------------------------------------- #
# main() state machine                                                         #
# --------------------------------------------------------------------------- #
class TestMain(Base):
    def setUp(self):
        super().setUp()
        self.m.newest_transcript_mtime = lambda: time.time()
        self.live = {"five_hour": {"utilization": 14.0, "resets_at": None},
                     "seven_day": {"utilization": 6.0, "resets_at": None}}

    def _no_network(self):
        def boom():
            raise AssertionError("network must not be called")
        self.m.fetch_live_usage = boom

    def test_fresh_cache_served_without_polling(self):
        now = time.time()
        self.m.write_state({"at": now - 5, "data": self.live, "retry_until": 0})
        self._no_network()
        out = self.run_main()
        self.assertIn("source: live", out)
        self.assertIn("5h 14%", out)

    def test_live_fetch_ok_writes_state(self):
        self.m.fetch_live_usage = lambda: ("ok", self.live)
        out = self.run_main()
        self.assertIn("source: live", out)
        self.assertEqual(self.m.read_state()["data"], self.live)

    def test_backoff_keeps_last_good_and_sets_retry_until(self):
        now = time.time()
        # stale enough to attempt a poll
        self.m.write_state({"at": now - 999, "data": self.live, "retry_until": 0})
        self.m.fetch_live_usage = lambda: ("backoff", 150)
        out = self.run_main()
        self.assertIn("source: live", out)
        self.assertGreater(self.m.read_state()["retry_until"], now)

    def test_within_retry_until_does_not_poll(self):
        now = time.time()
        self.m.write_state({"at": now - 999, "data": self.live,
                            "retry_until": now + 120})
        self._no_network()
        self.assertIn("5h 14%", self.run_main())

    def test_fail_falls_back_to_stale_cache(self):
        now = time.time()
        self.m.LIVE_MIN_POLL = 60
        self.m.LIVE_STALE_MAX = 900
        self.m.write_state({"at": now - 300, "data": self.live, "retry_until": 0})
        self.m.fetch_live_usage = lambda: ("fail", None)
        out = self.run_main()
        self.assertIn("source: cached live", out)

    def test_fail_no_cache_falls_back_to_estimate(self):
        self.m.fetch_live_usage = lambda: ("fail", None)
        self.m.estimate_usage = lambda _now: {
            "five_hour": {"utilization": 3.0}, "seven_day": {"utilization": 4.0}}
        self.assertIn("(est)", self.run_main())

    def test_nothing_available_prints_na(self):
        self.m.fetch_live_usage = lambda: ("fail", None)
        self.m.estimate_usage = lambda _now: None
        self.assertIn("n/a", self.run_main())


if __name__ == "__main__":
    unittest.main()
