import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import (connect, create_app, model_draft_for_ticket, order_for_customer,
                         search_policies, tracking_for_customer)
from backend.model_agent import ModelAgentError


class CrossCareFlowTests(unittest.TestCase):
    def setUp(self):
        self.model_env = patch.dict(os.environ, {"OPENAI_API_KEY": "", "CROSSCARE_MODEL": ""})
        self.model_env.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.sqlite3"
        self.client = TestClient(create_app(self.db))

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()
        self.model_env.stop()

    def test_order_lookup_requires_ticket_customer(self):
        with closing(connect(self.db)) as conn:
            self.assertIsNotNone(order_for_customer(conn, "ORD-1001", "C-001"))
            self.assertIsNone(order_for_customer(conn, "ORD-1002", "C-001"))
            self.assertEqual(tracking_for_customer(conn, "ORD-1002", "C-001"), [])

        response = self.client.post("/api/tickets/T-1003/draft")
        self.assertEqual(response.status_code, 200)
        draft = response.json()
        self.assertIn("order_not_verified_for_customer", draft["risk_flags"])
        self.assertNotIn("delivered", draft["reply_text"].lower())
        self.assertNotIn("Package marked delivered", str(draft["tool_results"]))

    def test_policy_market_and_version_are_visible(self):
        with closing(connect(self.db)) as conn:
            result = search_policies(conn, "Can I return this lamp?", "UK", "LAMP-02")
        self.assertEqual(result[0]["id"], "POL-UK-RETURN")
        response = self.client.post("/api/tickets/T-1002/draft")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["citations"][0]["version"], "v1")

    def test_human_review_never_sends_external_message(self):
        self.assertEqual(self.client.post("/api/tickets/T-1001/review", json={"action": "approve"}).status_code, 409)
        self.client.post("/api/tickets/T-1001/draft")
        response = self.client.post("/api/tickets/T-1001/review", json={
            "action": "approve", "edited_reply": "A specialist will review your tracking update.", "note": "Checked."
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ticket_id": "T-1001", "status": "approved_demo_only", "external_message_sent": False})
        self.assertEqual(self.client.post("/api/tickets/T-1001/review", json={"action": "approve"}).status_code, 409)
        ticket = self.client.get("/api/tickets/T-1001").json()
        self.assertEqual(ticket["draft"]["reply_text"], "A specialist will review your tracking update.")

    def test_model_calls_read_only_tools_and_keeps_real_citations(self):
        observed = []

        def fake_model(input_items, tools):
            observed.append(input_items.copy())
            if len(observed) == 1:
                return {"output": [
                    {"type": "function_call", "call_id": "order", "name": "get_order_summary",
                     "arguments": '{"order_id":"ORD-1001"}'},
                    {"type": "function_call", "call_id": "tracking", "name": "get_tracking_events",
                     "arguments": '{"order_id":"ORD-1001"}'},
                    {"type": "function_call", "call_id": "policy", "name": "search_policies",
                     "arguments": '{"query":"shipping tracking package"}'},
                ]}
            return {"output": [{"type": "message", "content": [{"type": "output_text",
                "text": '{"reply_text":"Order ORD-1001 is in transit. A specialist will review the tracking update.","rationale":"Order and tracking were checked."}'
            }]}]}

        with closing(connect(self.db)) as conn:
            draft = model_draft_for_ticket(conn, "T-1001", fake_model)
        self.assertEqual(draft["mode"], "openai_tool_calling")
        self.assertEqual(draft["citations"][0]["id"], "POL-US-SHIP")
        self.assertEqual(len(draft["tool_results"]), 2)
        self.assertIn("Package arrived at the destination facility", str(observed[1]))

    def test_model_cannot_read_another_customers_order(self):
        observed = []

        def fake_model(input_items, tools):
            observed.append(input_items.copy())
            if len(observed) == 1:
                return {"output": [{"type": "function_call", "call_id": "order",
                    "name": "get_order_summary", "arguments": '{"order_id":"ORD-1002"}'}]}
            return {"output": [{"type": "message", "content": [{"type": "output_text",
                "text": '{"reply_text":"ORD-1002 was delivered.","rationale":"The order was checked."}'
            }]}]}

        with closing(connect(self.db)) as conn:
            draft = model_draft_for_ticket(conn, "T-1003", fake_model)
        self.assertIn("order_not_verified_for_customer", draft["risk_flags"])
        self.assertNotIn("delivered", draft["reply_text"].lower())
        self.assertNotIn("delivered", str(observed[1]).lower())
        self.assertEqual(draft["tool_results"][0]["found"], False)

    def test_model_must_use_an_evidence_tool(self):
        def fake_model(input_items, tools):
            return {"output": [{"type": "message", "content": [{"type": "output_text",
                "text": '{"reply_text":"Your package is delivered.","rationale":"Guess."}'
            }]}]}

        with closing(connect(self.db)) as conn:
            with self.assertRaises(ModelAgentError):
                model_draft_for_ticket(conn, "T-1001", fake_model)

    def test_api_selects_model_mode_only_when_configured(self):
        calls = 0

        def fake_model(input_items, tools):
            nonlocal calls
            calls += 1
            if calls == 1:
                return {"output": [{"type": "function_call", "call_id": "policy",
                    "name": "search_policies", "arguments": '{"query":"return policy"}'}]}
            return {"output": [{"type": "message", "content": [{"type": "output_text",
                "text": '{"reply_text":"A specialist will check the return policy.","rationale":"Policy was retrieved."}'
            }]}]}

        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-test-key", "CROSSCARE_MODEL": "fake-model"}):
            with TestClient(create_app(self.db, fake_model)) as client:
                self.assertEqual(client.get("/api/health").json()["draft_mode"], "openai_tool_calling")
                response = client.post("/api/tickets/T-1004/draft")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["mode"], "openai_tool_calling")
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
