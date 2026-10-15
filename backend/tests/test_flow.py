import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import connect, create_app, order_for_customer, search_policies, tracking_for_customer


class CrossCareFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.sqlite3"
        self.client = TestClient(create_app(self.db))

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

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


if __name__ == "__main__":
    unittest.main()
