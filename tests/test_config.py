"""Tests for optional config helpers (from_env)."""

import os

from wilrise import Wilrise, from_env


class TestFromEnv:
    """from_env() builds Wilrise kwargs from WILRISE_* env vars."""

    def test_returns_dict_with_expected_keys(self) -> None:
        os.environ.pop("WILRISE_LOG_LEVEL", None)
        d = from_env()
        assert set(d) >= {"debug", "max_batch_size", "max_request_size", "log_requests"}
        assert set(d) <= {
            "debug",
            "max_batch_size",
            "max_request_size",
            "log_requests",
            "log_level",
        }

    def test_log_level_via_env(self) -> None:
        import logging

        os.environ["WILRISE_LOG_LEVEL"] = "WARNING"
        try:
            d = from_env()
            assert d.get("log_level") == logging.WARNING
        finally:
            os.environ.pop("WILRISE_LOG_LEVEL", None)

    def test_defaults_without_env(self) -> None:
        # Clear WILRISE_* so defaults apply
        for key in (
            "WILRISE_DEBUG",
            "WILRISE_MAX_BATCH_SIZE",
            "WILRISE_MAX_REQUEST_SIZE",
            "WILRISE_LOG_REQUESTS",
            "WILRISE_LOG_LEVEL",
        ):
            os.environ.pop(key, None)
        d = from_env()
        assert d["debug"] is False
        assert d["max_batch_size"] == 50
        assert d["max_request_size"] == 1048576
        assert d["log_requests"] is True

    def test_wilrise_accepts_from_env(self) -> None:
        d = from_env()
        _ = Wilrise(**d)  # accepts these kwargs; behavior covered by other tests
        assert "debug" in d and "max_batch_size" in d

    def test_wilrise_debug_true_via_env(self) -> None:
        os.environ["WILRISE_DEBUG"] = "1"
        try:
            d = from_env()
            assert d["debug"] is True
        finally:
            os.environ.pop("WILRISE_DEBUG", None)

    def test_wilrise_debug_false_via_env(self) -> None:
        os.environ["WILRISE_DEBUG"] = "0"
        try:
            d = from_env()
            assert d["debug"] is False
        finally:
            os.environ.pop("WILRISE_DEBUG", None)
