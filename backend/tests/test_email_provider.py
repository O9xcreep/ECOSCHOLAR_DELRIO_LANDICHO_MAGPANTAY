# -*- coding: utf-8 -*-
"""send_email() dispatches to Resend or Mailjet based on EMAIL_PROVIDER, a
flippable config switch. Both are best-effort: a failure or missing config
returns False and never raises. Config lives in helpers.py and is patched
there directly, since a function's globals resolve from its defining
module, not wherever it's re-exported."""
from unittest.mock import patch, MagicMock

import app as app_module
import helpers


class TestEmailProviderDispatch:
    def test_resend_skipped_when_not_configured(self, monkeypatch):
        # EMAIL_PROVIDER is read from the real .env at import time (even under
        # pytest), so every test here pins it explicitly via monkeypatch
        # rather than relying on whatever a dev machine has configured.
        monkeypatch.setattr(helpers, 'EMAIL_PROVIDER', 'resend')
        monkeypatch.setattr(helpers, 'RESEND_API_KEY', '')
        monkeypatch.setattr(helpers, 'SMTP_FROM_EMAIL', 'x@test.com')
        assert app_module.send_email('to@test.com', 'Subject', '<p>Hi</p>') is False

    def test_mailjet_skipped_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(helpers, 'EMAIL_PROVIDER', 'mailjet')
        monkeypatch.setattr(helpers, 'MAILJET_API_KEY', '')
        monkeypatch.setattr(helpers, 'MAILJET_API_SECRET', '')
        monkeypatch.setattr(helpers, 'SMTP_FROM_EMAIL', 'x@test.com')
        assert app_module.send_email('to@test.com', 'Subject', '<p>Hi</p>') is False

    def test_resend_calls_resend_api(self, monkeypatch):
        monkeypatch.setattr(helpers, 'EMAIL_PROVIDER', 'resend')
        monkeypatch.setattr(helpers, 'RESEND_API_KEY', 'test-key')
        monkeypatch.setattr(helpers, 'SMTP_FROM_EMAIL', 'x@test.com')
        mock_resp = MagicMock(raise_for_status=lambda: None)
        with patch.object(app_module.requests, 'post', return_value=mock_resp) as mock_post:
            assert app_module.send_email('to@test.com', 'Subject', '<p>Hi</p>') is True
            assert mock_post.call_args.args[0] == 'https://api.resend.com/emails'
            assert mock_post.call_args.kwargs['headers']['Authorization'] == 'Bearer test-key'

    def test_mailjet_calls_mailjet_api(self, monkeypatch):
        monkeypatch.setattr(helpers, 'EMAIL_PROVIDER', 'mailjet')
        monkeypatch.setattr(helpers, 'MAILJET_API_KEY', 'mj-key')
        monkeypatch.setattr(helpers, 'MAILJET_API_SECRET', 'mj-secret')
        monkeypatch.setattr(helpers, 'SMTP_FROM_EMAIL', 'x@test.com')
        mock_resp = MagicMock(raise_for_status=lambda: None)
        with patch.object(app_module.requests, 'post', return_value=mock_resp) as mock_post:
            assert app_module.send_email('to@test.com', 'Subject', '<p>Hi</p>') is True
            assert mock_post.call_args.args[0] == 'https://api.mailjet.com/v3.1/send'
            assert mock_post.call_args.kwargs['auth'] == ('mj-key', 'mj-secret')
            message = mock_post.call_args.kwargs['json']['Messages'][0]
            assert message['To'] == [{'Email': 'to@test.com'}]
            assert message['Subject'] == 'Subject'

    def test_send_failure_returns_false_not_raise(self, monkeypatch):
        monkeypatch.setattr(helpers, 'EMAIL_PROVIDER', 'resend')
        monkeypatch.setattr(helpers, 'RESEND_API_KEY', 'test-key')
        monkeypatch.setattr(helpers, 'SMTP_FROM_EMAIL', 'x@test.com')
        with patch.object(app_module.requests, 'post', side_effect=Exception('network down')):
            assert app_module.send_email('to@test.com', 'Subject', '<p>Hi</p>') is False
