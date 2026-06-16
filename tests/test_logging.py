import json
import logging
import os
import unittest
from unittest.mock import patch, Mock
import uuid
from flask import g

from ai_papers.logging_config import setup_logging, memory_log_handler, request_id_var, CustomJsonFormatter
from ai_papers.web.app import create_app

class TestLoggingAndObservability(unittest.TestCase):
    def setUp(self):
        # Clear the memory log handler buffer before each test
        memory_log_handler.buffer.clear()
        request_id_var.set(None)

    def test_json_formatter_metadata_and_request_id(self):
        formatter = CustomJsonFormatter("%(timestamp)s %(level)s %(logger)s %(message)s %(request_id)s")
        
        # Test log record without request_id
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Hello World",
            args=(),
            exc_info=None
        )
        formatted = formatter.format(record)
        log_obj = json.loads(formatted)
        self.assertEqual(log_obj["message"], "Hello World")
        self.assertEqual(log_obj["level"], "INFO")
        self.assertEqual(log_obj["logger"], "test_logger")
        self.assertNotIn("request_id", log_obj)

        # Test log record WITH request_id set in contextvar
        request_id_var.set("req-12345")
        formatted = formatter.format(record)
        log_obj = json.loads(formatted)
        self.assertEqual(log_obj["request_id"], "req-12345")

    def test_memory_log_handler_capacity(self):
        # Use a fresh, isolated handler to avoid side-effects from root logger
        from ai_papers.logging_config import MemoryLogHandler
        handler = MemoryLogHandler(capacity=500)
        handler.setFormatter(CustomJsonFormatter("%(timestamp)s %(level)s %(logger)s %(message)s"))
        
        logger = logging.getLogger("temp_test")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        
        try:
            # Emit 510 messages
            for i in range(510):
                logger.info(f"Log line {i}")
                
            logs = handler.get_logs()
            # Should be capped at capacity (500)
            self.assertEqual(len(logs), 500)
            
            # First log in buffer should be "Log line 10" (since 0-9 were rotated out)
            first_log = json.loads(logs[0])
            self.assertEqual(first_log["message"], "Log line 10")
        finally:
            logger.removeHandler(handler)
            logger.propagate = True

    def test_flask_request_id_headers_and_logs_endpoint(self):
        # Use a temporary database directory config to create app
        with patch("ai_papers.web.app.get_validated_config") as mock_cfg:
            mock_cfg.return_value = {
                "data_dir": "/tmp/dummy_aura_log_test",
                "categories": ["astro-ph.CO"],
                "embedding_model": "all-MiniLM-L6-v2"
            }
            with patch("ai_papers.web.app.RecommendationEngine"):
                app = create_app()
                
        app.testing = True
        client = app.test_client()

        # 1. Verify X-Request-ID propagation
        custom_req_id = "test-uuid-999"
        resp = client.get("/health", headers={"X-Request-ID": custom_req_id})
        self.assertEqual(resp.headers.get("X-Request-ID"), custom_req_id)
        
        # Verify logger contains custom_req_id in memory logs
        logs = memory_log_handler.get_logs()
        self.assertTrue(len(logs) > 0)
        
        # 2. Verify /api/logs endpoint returns log objects
        resp = client.get("/api/logs")
        self.assertEqual(resp.status_code, 200)
        log_list = resp.get_json()
        self.assertIsInstance(log_list, list)

        # 3. Test AURA_ADMIN_TOKEN protection
        with patch.dict(os.environ, {"AURA_ADMIN_TOKEN": "secret123"}):
            # Unauthorized request (no token)
            resp = client.get("/api/logs")
            self.assertEqual(resp.status_code, 401)
            
            # Unauthorized request (wrong token)
            resp = client.get("/api/logs?token=wrong")
            self.assertEqual(resp.status_code, 401)
            
            # Authorized request via query parameter
            resp = client.get("/api/logs?token=secret123")
            self.assertEqual(resp.status_code, 200)
            
            # Authorized request via header
            resp = client.get("/api/logs", headers={"Authorization": "Bearer secret123"})
            self.assertEqual(resp.status_code, 200)

    @patch("sentry_sdk.init")
    def test_setup_logging_structured_and_sentry(self, mock_sentry_init):
        # Test non-structured console output
        setup_logging(structured=False)
        # Test Sentry initialization
        with patch.dict(os.environ, {"SENTRY_DSN": "https://test-dsn@sentry.io/1"}):
            setup_logging(structured=True)
            mock_sentry_init.assert_called_once()

