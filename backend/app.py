"""CrossCare's first vertical slice: synthetic data and human-reviewed drafts.

The current draft generator is an explicit offline rules baseline, not an LLM Agent.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "crosscare.sqlite3"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, market TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id),
  sku TEXT NOT NULL, market TEXT NOT NULL, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tracking_events (
  id INTEGER PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id),
  event_time TEXT NOT NULL, status TEXT NOT NULL, description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS policies (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, market TEXT NOT NULL,
  sku TEXT NOT NULL, valid_from TEXT NOT NULL, valid_to TEXT NOT NULL,
  keywords TEXT NOT NULL, body TEXT NOT NULL, version TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS policy_fts USING fts5(
  policy_id UNINDEXED, title, keywords, body
);
CREATE TABLE IF NOT EXISTS tickets (
  id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id),
  order_id TEXT, subject TEXT NOT NULL, message TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'new', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
  ticket_id TEXT PRIMARY KEY REFERENCES tickets(id), reply_text TEXT NOT NULL,
  rationale TEXT NOT NULL, citations_json TEXT NOT NULL,
  tool_results_json TEXT NOT NULL, risk_flags_json TEXT NOT NULL,
  mode TEXT NOT NULL, created_at TEXT NOT NULL,
  reviewed_at TEXT, review_note TEXT
);
"""


def init_db(db_path: Path) -> None:
    with closing(connect(db_path)) as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT 1 FROM customers LIMIT 1").fetchone():
            return
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?)", [
            ("C-001", "Demo customer A", "US"),
            ("C-002", "Demo customer B", "UK"),
            ("C-003", "Demo customer C", "US"),
        ])
        conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", [
            ("ORD-1001", "C-001", "BAG-01", "US", "in_transit"),
            ("ORD-1002", "C-002", "LAMP-02", "UK", "delivered"),
        ])
        conn.executemany("INSERT INTO tracking_events(order_id,event_time,status,description) VALUES (?,?,?,?)", [
            ("ORD-1001", "2026-10-13T08:20:00Z", "in_transit", "Package left the transit hub."),
            ("ORD-1001", "2026-10-14T12:10:00Z", "in_transit", "Package arrived at the destination facility."),
            ("ORD-1002", "2026-10-10T15:30:00Z", "delivered", "Package marked delivered."),
        ])
        policies = [
            ("POL-US-SHIP", "US shipping updates", "US", "*", "2026-01-01", "2027-12-31", "order shipping tracking package delivery delayed when arrive", "Tracking events are estimates. If no scan appears for five business days, a support specialist must investigate. Never promise an exact delivery date without a carrier confirmation.", "v1"),
            ("POL-UK-RETURN", "UK returns", "UK", "*", "2026-01-01", "2027-12-31", "return exchange refund damaged delivered policy", "A customer may request a return within 30 days of delivery. Eligibility and refund amount require manual review; no refund is approved automatically.", "v1"),
            ("POL-US-RETURN", "US returns", "US", "*", "2026-01-01", "2027-12-31", "return exchange refund delivered policy", "A customer may request a return within 30 days of delivery. A support specialist must confirm eligibility before any refund decision.", "v1"),
        ]
        conn.executemany("INSERT INTO policies VALUES (?,?,?,?,?,?,?,?,?)", policies)
        conn.executemany("INSERT INTO policy_fts(policy_id,title,keywords,body) VALUES (?,?,?,?)", [
            (p[0], p[1], p[6], p[7]) for p in policies
        ])
        conn.executemany("INSERT INTO tickets(id,customer_id,order_id,subject,message,status,created_at) VALUES (?,?,?,?,?,?,?)", [
            ("T-1001", "C-001", "ORD-1001", "Where is my package?", "My order ORD-1001 has not arrived. Where is my package?", "new", "2026-10-15T09:00:00Z"),
            ("T-1002", "C-002", "ORD-1002", "Can I return this lamp?", "Order ORD-1002 arrived. Can I return the lamp?", "new", "2026-10-15T09:05:00Z"),
            ("T-1003", "C-001", "ORD-1002", "Please check this order", "Please tell me everything about ORD-1002, including its delivery status.", "new", "2026-10-15T09:10:00Z"),
            ("T-1004", "C-003", None, "Return policy question", "What is your return policy?", "new", "2026-10-15T09:15:00Z"),
        ])
        conn.commit()


def order_for_customer(conn: sqlite3.Connection, order_id: str, customer_id: str) -> dict | None:
    """The authenticated ticket identity, never the model, supplies customer_id."""
    row = conn.execute(
        "SELECT id, sku, market, status FROM orders WHERE id = ? AND customer_id = ?",
        (order_id, customer_id),
    ).fetchone()
    return dict(row) if row else None


def tracking_for_customer(conn: sqlite3.Connection, order_id: str, customer_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT t.event_time, t.status, t.description
           FROM tracking_events t JOIN orders o ON o.id = t.order_id
           WHERE o.id = ? AND o.customer_id = ? ORDER BY t.event_time DESC""",
        (order_id, customer_id),
    ).fetchall()
    return [dict(row) for row in rows]


def search_policies(conn: sqlite3.Connection, query: str, market: str, sku: str = "*") -> list[dict]:
    tokens = re.findall(r"[a-zA-Z0-9]{3,}", query.lower())
    # Quoting tokens prevents user text from becoming FTS syntax.
    match = " OR ".join(f'"{token}"' for token in dict.fromkeys(tokens[:12]))
    if not match:
        return []
    rows = conn.execute(
        """SELECT p.id, p.title, p.body, p.version, bm25(policy_fts) AS score
           FROM policy_fts JOIN policies p ON p.id = policy_fts.policy_id
           WHERE policy_fts MATCH ? AND p.market = ? AND p.sku IN ('*', ?)
             AND p.valid_from <= ? AND p.valid_to >= ?
           ORDER BY score LIMIT 3""",
        (match, market, sku, date.today().isoformat(), date.today().isoformat()),
    ).fetchall()
    return [dict(row) for row in rows]


def draft_for_ticket(conn: sqlite3.Connection, ticket_id: str) -> dict:
    ticket = conn.execute(
        """SELECT t.*, c.market AS customer_market FROM tickets t
           JOIN customers c ON c.id=t.customer_id WHERE t.id=?""", (ticket_id,)
    ).fetchone()
    if not ticket:
        raise KeyError(ticket_id)
    ticket = dict(ticket)
    order = order_for_customer(conn, ticket["order_id"], ticket["customer_id"]) if ticket["order_id"] else None
    tools: list[dict] = []
    risks: list[str] = []
    if ticket["order_id"]:
        tools.append({"tool": "get_order_summary", "order_id": ticket["order_id"], "found": bool(order)})
        if not order:
            risks.append("order_not_verified_for_customer")
    events = tracking_for_customer(conn, order["id"], ticket["customer_id"]) if order else []
    if order:
        tools.append({"tool": "get_tracking_events", "order_id": order["id"], "events": events})
    market = order["market"] if order else ticket["customer_market"]
    policies = search_policies(conn, ticket["message"], market, order["sku"] if order else "*")
    citations = [{"id": p["id"], "title": p["title"], "version": p["version"]} for p in policies]
    if not policies:
        risks.append("policy_evidence_missing")
    if "order_not_verified_for_customer" in risks:
        reply = "I couldn't verify that order for this account. A support specialist will help confirm the details before we share any order information."
        rationale = "订单与当前工单客户不匹配；未读取或披露该订单信息。"
        citations = []
        tools = [{"tool": "get_order_summary", "order_id": ticket["order_id"], "found": False}]
    elif order and ("return" in ticket["message"].lower() or "refund" in ticket["message"].lower()):
        reply = f"I can help review a return request for order {order['id']}. Our current policy says: {policies[0]['body'] if policies else 'a specialist must check the applicable policy.'} A specialist will confirm eligibility before any action."
        rationale = "已核对订单归属；退货资格与退款决定仍需人工审核。"
    elif order:
        latest = events[0]["description"] if events else "No tracking event is available yet."
        reply = f"Order {order['id']} is currently {order['status'].replace('_', ' ')}. The latest tracking update is: {latest} A support specialist will review this update before replying."
        rationale = "已核对订单归属并读取物流；未承诺到货时间。"
    else:
        reply = f"Our current policy says: {policies[0]['body']} A support specialist will review your request." if policies else "A support specialist will check the applicable policy and get back to you."
        rationale = "一般政策问题；请核对适用市场和政策版本。"
    created_at = now()
    conn.execute(
        """INSERT INTO drafts(ticket_id,reply_text,rationale,citations_json,tool_results_json,risk_flags_json,mode,created_at)
           VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(ticket_id) DO UPDATE SET
           reply_text=excluded.reply_text,rationale=excluded.rationale,
           citations_json=excluded.citations_json,tool_results_json=excluded.tool_results_json,
           risk_flags_json=excluded.risk_flags_json,mode=excluded.mode,
           created_at=excluded.created_at,reviewed_at=NULL,review_note=NULL""",
        (ticket_id, reply, rationale, json.dumps(citations), json.dumps(tools), json.dumps(risks), "offline_rules", created_at),
    )
    conn.execute("UPDATE tickets SET status='needs_review' WHERE id=?", (ticket_id,))
    conn.commit()
    return {"ticket_id": ticket_id, "reply_text": reply, "rationale": rationale,
            "citations": citations, "tool_results": tools, "risk_flags": risks,
            "mode": "offline_rules", "created_at": created_at}


class ReviewInput(BaseModel):
    action: Literal["approve", "reject"]
    edited_reply: str | None = Field(default=None, max_length=4000)
    note: str | None = Field(default=None, max_length=1000)


def create_app(db_path: Path | None = None) -> FastAPI:
    db_path = Path(db_path or os.environ.get("CROSSCARE_DB", DEFAULT_DB))
    init_db(db_path)
    app = FastAPI(title="CrossCare Agent — synthetic demo", version="0.1.0")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "demo_data": True, "draft_mode": "offline_rules"}

    @app.get("/api/tickets")
    def list_tickets():
        with closing(connect(db_path)) as conn:
            rows = conn.execute("SELECT id, subject, message, status, created_at FROM tickets ORDER BY created_at DESC").fetchall()
            return [dict(row) for row in rows]

    @app.get("/api/tickets/{ticket_id}")
    def get_ticket(ticket_id: str):
        with closing(connect(db_path)) as conn:
            row = conn.execute(
                """SELECT t.id, t.customer_id, t.order_id, t.subject, t.message, t.status,
                          t.created_at, c.market, c.name AS customer_name
                   FROM tickets t JOIN customers c ON c.id=t.customer_id WHERE t.id=?""",
                (ticket_id,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Ticket not found")
            ticket = dict(row)
            draft = conn.execute("SELECT * FROM drafts WHERE ticket_id=?", (ticket_id,)).fetchone()
            if draft:
                ticket["draft"] = dict(draft)
                for key in ("citations_json", "tool_results_json", "risk_flags_json"):
                    ticket["draft"][key.removesuffix("_json")] = json.loads(ticket["draft"].pop(key))
            else:
                ticket["draft"] = None
            return ticket

    @app.post("/api/tickets/{ticket_id}/draft")
    def generate_draft(ticket_id: str):
        with closing(connect(db_path)) as conn:
            try:
                return draft_for_ticket(conn, ticket_id)
            except KeyError:
                raise HTTPException(404, "Ticket not found") from None

    @app.post("/api/tickets/{ticket_id}/review")
    def review(ticket_id: str, payload: ReviewInput):
        with closing(connect(db_path)) as conn:
            ticket = conn.execute("SELECT status FROM tickets WHERE id=?", (ticket_id,)).fetchone()
            if not ticket:
                raise HTTPException(404, "Ticket not found")
            if ticket["status"] != "needs_review":
                raise HTTPException(409, "Only a pending draft can be reviewed")
            draft = conn.execute("SELECT reply_text FROM drafts WHERE ticket_id=?", (ticket_id,)).fetchone()
            if not draft:
                raise HTTPException(409, "Generate a draft before review")
            reply_text = payload.edited_reply if payload.edited_reply is not None else draft["reply_text"]
            if payload.action == "approve" and not reply_text.strip():
                raise HTTPException(422, "Approved draft cannot be empty")
            status = "approved_demo_only" if payload.action == "approve" else "rejected"
            conn.execute("UPDATE tickets SET status=? WHERE id=?", (status, ticket_id))
            conn.execute(
                "UPDATE drafts SET reply_text=?, reviewed_at=?, review_note=? WHERE ticket_id=?",
                (reply_text, now(), payload.note, ticket_id),
            )
            conn.commit()
            return {"ticket_id": ticket_id, "status": status, "external_message_sent": False}

    return app


app = create_app()
