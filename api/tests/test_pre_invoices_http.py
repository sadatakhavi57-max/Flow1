"""Stage 4 over HTTP against the real database: DRAFT/issue/cancel/replace, roles and ownership, tenant isolation, numbering,
request-cancel guard, concurrency, PDF (fake renderer, controllable clock), audit allow-list.
WRITTEN, NOT YET RUN by its author - the owner runs it (api/run_tests.sh)."""
import hashlib
import json
import re
import threading
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from tests import pg, support
from tests.test_requests_http import R, RequestsBase, err
from tradeflow_core import numbering
from tradeflow_core import pre_invoice as pi

API = "/api/v1"
PI = f"{API}/pre-invoices"
SECRET_TEXT = "TOP-SECRET-RENDERER-MESSAGE"


class FakeRenderer:
    """Controllable PDF renderer: mode in ok | raise | big | invalid | unavailable."""
    def __init__(self):
        self.mode, self.calls, self.models = "ok", 0, []

    def render(self, model):
        self.calls += 1
        self.models.append(model)
        if self.mode == "raise":
            raise RuntimeError(SECRET_TEXT)
        if self.mode == "unavailable":
            raise pi.RendererUnavailable()
        if self.mode == "big":
            return b"%PDF-" + b"x" * pi.MAX_PDF_BYTES
        if self.mode == "invalid":
            return b"<html>not a pdf</html>"
        return b"%PDF-1.7\n% fake " + str(self.calls).encode() + b"\n" + json.dumps(model["number"]).encode()


class PreInvoiceBase(RequestsBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.renderer = FakeRenderer()
        cls.offset = timedelta(0)
        cls.c = TestClient(support.make_app(pdf_renderer=cls.renderer, clock=lambda: datetime.now(timezone.utc) + cls.offset))

    def setUp(self):
        type(self).offset = timedelta(0)
        self.renderer.mode, self.renderer.calls, self.renderer.models = "ok", 0, []

    # ---- helpers
    def submitted(self, headers=None, customer_id=None, **kw):
        if customer_id:
            kw["customer_id"] = customer_id
        d = self.mk(headers=headers or self.sales, items=[self.item()], **kw)
        r = self.c.post(f"{R}/{d['id']}/submit", headers=headers or self.sales)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["data"]

    def draft(self, rid, headers=None, body=None, expect=201):
        r = self.c.post(f"{R}/{rid}/pre-invoices", json=body if body is not None else {}, headers=headers or self.sales)
        self.assertEqual(r.status_code, expect, r.text)
        return r.json()["data"] if expect == 201 else r

    def issue(self, pid, headers=None, expect=200):
        r = self.c.post(f"{PI}/{pid}/issue", headers=headers or self.acct)
        self.assertEqual(r.status_code, expect, r.text)
        return r.json()["data"] if expect == 200 else r

    def issued(self, **kw):
        req = self.submitted(**kw)
        return req, self.issue(self.draft(req["id"])["id"])

    def pdf_post(self, pid, headers=None):
        return self.c.post(f"{PI}/{pid}/pdf", headers=headers or self.acct)

    def detail(self, pid, headers=None):
        r = self.c.get(f"{PI}/{pid}", headers=headers or self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["data"]

    def audit(self, pid):
        r = self.c.get(f"{API}/audit-logs", params={"entity_type": "PRE_INVOICE", "entity_id": pid, "page_size": 200}, headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        return list(reversed(r.json()["items"]))

    @staticmethod
    def seq_of(number):
        return numbering.parse_request_number(number.replace("PI-", "", 1))[1] if number else None


class Drafts(PreInvoiceBase):
    def test_draft_is_a_snapshot_without_number(self):
        req = self.submitted()
        d = self.draft(req["id"])
        self.assertEqual((d["status"], d["pre_invoice_number"], d["version"], d["supersedes_id"], d["pdf"]), ("DRAFT", None, None, None, None))
        self.assertEqual(d["chain_id"], d["id"])
        self.assertEqual((d["subtotal"], d["grand_total"], d["source_request"]["id"], d["source_request"]["request_number"]),
                         (req["subtotal"], req["grand_total"], req["id"], req["request_number"]))
        self.assertEqual(len(d["items"]), 1)
        self.assertEqual(d["items"][0]["quantity"], req["items"][0]["quantity"])
        self.assertEqual(d["items"][0]["specifications"], req["items"][0]["specifications"])
        self.assertEqual(d["customer"]["name"], req["customer"]["name"])
        self.assertNotIn("credit_limit", json.dumps(d))
        self.assertNotIn("pdf_data", json.dumps(d))
        self.assertEqual(self.detail(d["id"]), d)

    def test_source_request_must_be_submitted(self):
        draft_req = self.mk(headers=self.sales, items=[self.item()])
        r = self.draft(draft_req["id"], expect=409)
        self.assertEqual((err(r)["code"], err(r)["details"]["reason"]), ("STATE_CONFLICT", "SOURCE_NOT_SUBMITTED"))
        cancelled = self.submitted()
        self.assertEqual(self.c.post(f"{R}/{cancelled['id']}/cancel", json={"reason": "x"}, headers=self.sales).status_code, 200)
        self.assertEqual(err(self.draft(cancelled["id"], expect=409))["details"]["reason"], "SOURCE_NOT_SUBMITTED")

    def test_one_open_draft_per_request_and_cancel_frees_the_slot(self):
        req = self.submitted()
        a = self.draft(req["id"])
        r = self.draft(req["id"], expect=409)
        self.assertEqual((err(r)["code"], err(r)["details"]["reason"], err(r)["details"]["pre_invoice_id"]), ("STATE_CONFLICT", "OPEN_DRAFT_EXISTS", a["id"]))
        c = self.c.post(f"{PI}/{a['id']}/cancel", json={}, headers=self.sales)                         # DRAFT: reason optional
        self.assertEqual((c.status_code, c.json()["data"]["status"], c.json()["data"]["cancel_reason"]), (200, "CANCELLED", None))
        self.assertEqual(self.draft(req["id"])["status"], "DRAFT")

    def test_validation_and_unknown_ids(self):
        req = self.submitted()
        for body in ({"x": 1}, {"supersedes_id": "nope"}, {"supersedes_id": 5}, []):
            r = self.draft(req["id"], body=body, expect=422)
            self.assertEqual(err(r)["code"], "VALIDATION_ERROR", body)
        r = self.c.post(f"{R}/{uuid.uuid4()}/pre-invoices", json={}, headers=self.sales)
        self.assertEqual((r.status_code, err(r)["code"]), (404, "NOT_FOUND"))
        self.assertEqual(self.c.get(f"{PI}/not-a-uuid", headers=self.admin).status_code, 422)
        self.assertEqual(self.c.get(f"{PI}/{uuid.uuid4()}", headers=self.admin).status_code, 404)

    def test_snapshot_does_not_follow_later_master_data_changes(self):
        cust = self.c.post(f"{API}/customers", json={"customer_type": "COMPANY", "name": "Snap-" + uuid.uuid4().hex[:8]}, headers=self.admin).json()["data"]
        req = self.submitted(headers=self.admin, customer_id=cust["id"])
        p = self.issue(self.draft(req["id"], headers=self.admin)["id"])
        r = self.c.patch(f"{API}/customers/{cust['id']}", json={"name": "Renamed-" + uuid.uuid4().hex[:8], "updated_at": cust["updated_at"]}, headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.detail(p["id"])["customer"]["name"], cust["name"])


class Permissions(PreInvoiceBase):
    def test_roles_and_ownership(self):
        req = self.submitted(headers=self.sales)
        d = self.draft(req["id"], headers=self.sales)
        # create
        r = self.draft(req["id"], headers=self.sales2, expect=403)
        self.assertEqual(err(r)["code"], "FORBIDDEN_NOT_OWNER")
        r = self.draft(req["id"], headers=self.acct, expect=403)
        self.assertEqual(err(r)["code"], "FORBIDDEN_ROLE")
        # read: own only for SALES; everything for ACCOUNTING and ADMIN
        self.assertEqual(self.c.get(f"{PI}/{d['id']}", headers=self.sales).status_code, 200)
        r = self.c.get(f"{PI}/{d['id']}", headers=self.sales2)
        self.assertEqual((r.status_code, err(r)["code"]), (403, "FORBIDDEN_NOT_OWNER"))
        for h in (self.acct, self.admin):
            self.assertEqual(self.c.get(f"{PI}/{d['id']}", headers=h).status_code, 200)
        ids = lambda h: {x["id"] for x in self.c.get(PI, params={"page_size": 200}, headers=h).json()["items"]}
        self.assertIn(d["id"], ids(self.sales))
        self.assertNotIn(d["id"], ids(self.sales2))
        self.assertIn(d["id"], ids(self.acct))
        self.assertIn(d["id"], ids(self.admin))
        # issue: SALES never
        r = self.c.post(f"{PI}/{d['id']}/issue", headers=self.sales)
        self.assertEqual((r.status_code, err(r)["code"]), (403, "FORBIDDEN_ROLE"))
        # cancel a DRAFT: owner SALES yes, other SALES no, ACCOUNTING no
        r = self.c.post(f"{PI}/{d['id']}/cancel", json={}, headers=self.sales2)
        self.assertEqual((r.status_code, err(r)["code"]), (403, "FORBIDDEN_NOT_OWNER"))
        r = self.c.post(f"{PI}/{d['id']}/cancel", json={}, headers=self.acct)
        self.assertEqual((r.status_code, err(r)["code"]), (403, "FORBIDDEN_ROLE"))
        self.assertEqual(self.detail(d["id"])["status"], "DRAFT")
        # ACCOUNTING issues; then SALES cannot cancel the ISSUED document, ACCOUNTING can
        self.issue(d["id"], headers=self.acct)
        r = self.c.post(f"{PI}/{d['id']}/cancel", json={"reason": "x"}, headers=self.sales)
        self.assertEqual((r.status_code, err(r)["code"]), (403, "FORBIDDEN_ROLE"))
        # PDF: SALES cannot generate; may only download its own
        r = self.pdf_post(d["id"], headers=self.sales)
        self.assertEqual((r.status_code, err(r)["code"]), (403, "FORBIDDEN_ROLE"))
        self.assertEqual(self.pdf_post(d["id"], headers=self.acct).status_code, 200)
        self.assertEqual(self.c.get(f"{PI}/{d['id']}/pdf", headers=self.sales).status_code, 200)
        r = self.c.get(f"{PI}/{d['id']}/pdf", headers=self.sales2)
        self.assertEqual((r.status_code, err(r)["code"]), (403, "FORBIDDEN_NOT_OWNER"))

    def test_admin_may_do_everything_on_any_request(self):
        req = self.submitted(headers=self.sales)
        d = self.draft(req["id"], headers=self.admin)
        self.issue(d["id"], headers=self.admin)
        self.assertEqual(self.pdf_post(d["id"], headers=self.admin).status_code, 200)
        r = self.c.post(f"{PI}/{d['id']}/cancel", json={"reason": "admin"}, headers=self.admin)
        self.assertEqual((r.status_code, r.json()["data"]["status"]), (200, "CANCELLED"))

    def test_other_organization_sees_nothing(self):
        req, p = self.issued()
        for call in (lambda: self.c.get(f"{PI}/{p['id']}", headers=self.other),
                     lambda: self.c.post(f"{PI}/{p['id']}/issue", headers=self.other),
                     lambda: self.c.post(f"{PI}/{p['id']}/cancel", json={"reason": "x"}, headers=self.other),
                     lambda: self.c.post(f"{PI}/{p['id']}/pdf", headers=self.other),
                     lambda: self.c.get(f"{PI}/{p['id']}/pdf", headers=self.other),
                     lambda: self.c.post(f"{R}/{req['id']}/pre-invoices", json={}, headers=self.other)):
            r = call()
            self.assertEqual((r.status_code, err(r)["code"]), (404, "NOT_FOUND"))
        self.assertNotIn(p["id"], {x["id"] for x in self.c.get(PI, params={"page_size": 200}, headers=self.other).json()["items"]})
        mine = self.submitted(headers=self.admin)
        r = self.c.post(f"{R}/{mine['id']}/pre-invoices", json={"supersedes_id": p["id"]}, headers=self.other)
        self.assertEqual(r.status_code, 404)

    def test_unauthenticated(self):
        for r in (self.c.get(PI), self.c.post(f"{PI}/{uuid.uuid4()}/issue"), self.c.get(f"{PI}/{uuid.uuid4()}/pdf")):
            self.assertEqual((r.status_code, err(r)["code"]), (401, "AUTH_TOKEN_INVALID"))


class IssueAndCancel(PreInvoiceBase):
    def test_issue_assigns_number_version_and_a_pending_document(self):
        req = self.submitted()
        d = self.draft(req["id"])
        p = self.issue(d["id"])
        year = numbering.series_for(datetime.now(timezone.utc))
        self.assertRegex(p["pre_invoice_number"], rf"^PI-{year}-\d{{6}}$")
        self.assertEqual((p["status"], p["version"], p["issued_by"] is not None, p["pdf"]["status"], p["pdf"]["attempt_count"]), ("ISSUED", 1, True, "pending", 0))
        r = self.c.post(f"{PI}/{d['id']}/issue", headers=self.acct)
        self.assertEqual((r.status_code, err(r)["code"]), (409, "STATE_CONFLICT"))
        n2 = self.issued()[1]
        self.assertEqual(self.seq_of(n2["pre_invoice_number"]), self.seq_of(p["pre_invoice_number"]) + 1)

    def test_numbers_are_taken_from_the_pi_series_and_do_not_move_request_numbers(self):
        a = self.submitted()
        self.issued()                                                                         # consumes one PI number and one request number
        b = self.mk(headers=self.sales)
        self.assertTrue(re.match(r"^\d{4}-\d{6}$", b["request_number"]))                      # request numbers keep their own format
        sa, na = numbering.parse_request_number(a["request_number"])
        sb, nb = numbering.parse_request_number(b["request_number"])
        self.assertEqual((sa, nb), (sb, na + 2))                                              # a, (issued()'s own request), b: no PI number leaked in

    def test_failed_issue_gives_the_number_back(self):
        first = self.issued()[1]
        doomed_req = self.submitted()
        doomed = self.draft(doomed_req["id"])
        self.assertEqual(self.c.post(f"{R}/{doomed_req['id']}/cancel", json={"reason": "x"}, headers=self.admin).status_code, 200)
        r = self.issue(doomed["id"], expect=409)
        self.assertEqual((err(r)["code"], err(r)["details"]["reason"]), ("STATE_CONFLICT", "SOURCE_NOT_SUBMITTED"))
        self.assertEqual(self.detail(doomed["id"])["status"], "DRAFT")
        self.assertIsNone(self.detail(doomed["id"])["pre_invoice_number"])
        nxt = self.issued()[1]
        self.assertEqual(self.seq_of(nxt["pre_invoice_number"]), self.seq_of(first["pre_invoice_number"]) + 1)      # no gap

    def test_request_with_an_issued_pre_invoice_cannot_be_cancelled(self):
        req, p = self.issued()
        r = self.c.post(f"{R}/{req['id']}/cancel", json={"reason": "x"}, headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"], err(r)["details"]["reason"]), (409, "STATE_CONFLICT", "ACTIVE_PRE_INVOICE"))
        self.assertEqual(self.get(req["id"])["status"], "SUBMITTED")
        c = self.c.post(f"{PI}/{p['id']}/cancel", json={"reason": "customer changed mind"}, headers=self.acct)
        self.assertEqual((c.status_code, c.json()["data"]["status"]), (200, "CANCELLED"))
        r = self.c.post(f"{R}/{req['id']}/cancel", json={"reason": "x"}, headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)

    def test_cancel_reason_rules(self):
        _, p = self.issued()
        for body in ({}, {"reason": None}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * 501}, {"reason": 5}, {"reason": "a", "x": 1}):
            r = self.c.post(f"{PI}/{p['id']}/cancel", json=body, headers=self.acct)
            self.assertEqual((r.status_code, err(r)["code"]), (422, "VALIDATION_ERROR"), body)
        self.assertEqual(self.detail(p["id"])["status"], "ISSUED")
        r = self.c.post(f"{PI}/{p['id']}/cancel", json={"reason": "  trimmed  "}, headers=self.acct)
        self.assertEqual((r.status_code, r.json()["data"]["cancel_reason"]), (200, "trimmed"))

    def test_final_states(self):
        req, p = self.issued()
        self.c.post(f"{PI}/{p['id']}/cancel", json={"reason": "r"}, headers=self.acct)
        for call in (lambda: self.c.post(f"{PI}/{p['id']}/cancel", json={"reason": "again"}, headers=self.acct),
                     lambda: self.c.post(f"{PI}/{p['id']}/issue", headers=self.acct)):
            r = call()
            self.assertEqual((r.status_code, err(r)["code"]), (409, "STATE_CONFLICT"))
        d = self.draft(self.submitted()["id"])
        self.c.post(f"{PI}/{d['id']}/cancel", json={}, headers=self.sales)
        r = self.c.post(f"{PI}/{d['id']}/issue", headers=self.acct)
        self.assertEqual((r.status_code, err(r)["code"]), (409, "STATE_CONFLICT"))

    def test_concurrent_issue_of_one_draft_only_one_wins(self):
        d = self.draft(self.submitted()["id"])
        out, bar = [], threading.Barrier(6)

        def go():
            c = TestClient(self.c.app)
            bar.wait()
            out.append(c.post(f"{PI}/{d['id']}/issue", headers=self.acct).status_code)
        ts = [threading.Thread(target=go) for _ in range(6)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(sorted(out), [200] + [409] * 5)

    def test_parallel_issues_get_unique_numbers(self):
        drafts = [self.draft(self.submitted()["id"]) for _ in range(8)]
        out, bar = [], threading.Barrier(8)

        def go(pid):
            c = TestClient(self.c.app)
            bar.wait()
            r = c.post(f"{PI}/{pid}/issue", headers=self.acct)
            out.append((r.status_code, r.json()["data"]["pre_invoice_number"] if r.status_code == 200 else r.text))
        ts = [threading.Thread(target=go, args=(d["id"],)) for d in drafts]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(sorted({s for s, _ in out}), [200])
        nums = sorted(self.seq_of(n) for _, n in out)
        self.assertEqual(nums, list(range(nums[0], nums[0] + 8)))                        # unique and gap-free

    def test_list_filters_and_paging(self):
        req, p = self.issued()
        r = self.c.get(PI, params={"status": "ISSUED", "source_request_id": req["id"]}, headers=self.admin).json()
        self.assertEqual([x["id"] for x in r["items"]], [p["id"]])
        self.assertEqual(r["items"][0]["pdf"], {"status": "pending"})
        self.assertNotIn("items", r["items"][0])                                       # list rows carry no item lines
        by_number = self.c.get(PI, params={"search": p["pre_invoice_number"]}, headers=self.admin).json()["items"]
        self.assertIn(p["id"], [x["id"] for x in by_number])
        self.assertEqual(self.c.get(PI, params={"status": "WHATEVER"}, headers=self.admin).status_code, 422)
        self.assertEqual(self.c.get(PI, params={"source_request_id": "x"}, headers=self.admin).status_code, 422)
        self.assertEqual(len(self.c.get(PI, params={"page_size": 1}, headers=self.admin).json()["items"]), 1)


class Replacement(PreInvoiceBase):
    def test_replacement_flow(self):
        r1, p1 = self.issued()
        r2 = self.submitted()
        d2 = self.draft(r2["id"], body={"supersedes_id": p1["id"]})
        self.assertEqual((d2["supersedes_id"], d2["chain_id"], d2["status"], d2["pre_invoice_number"]), (p1["id"], p1["chain_id"], "DRAFT", None))
        self.assertEqual(self.detail(p1["id"])["status"], "ISSUED")                      # not superseded before the replacement is issued
        p2 = self.issue(d2["id"])
        self.assertEqual((p2["status"], p2["version"], p2["pre_invoice_number"]), ("ISSUED", 2, p1["pre_invoice_number"]))
        old = self.detail(p1["id"])
        self.assertEqual((old["status"], old["superseded_at"] is not None, old["version"]), ("SUPERSEDED", True, 1))
        self.assertEqual([(a["action"]) for a in self.audit(p1["id"])], ["CREATE", "ISSUE", "SUPERSEDE"])
        self.assertEqual([(a["action"]) for a in self.audit(p2["id"])], ["CREATE", "ISSUE"])
        # a superseded document is final and cannot be replaced again
        r3 = self.submitted()
        r = self.draft(r3["id"], body={"supersedes_id": p1["id"]}, expect=409)
        self.assertEqual((err(r)["code"], err(r)["details"]["reason"]), ("STATE_CONFLICT", "NOT_ISSUED"))
        r = self.c.post(f"{PI}/{p1['id']}/cancel", json={"reason": "x"}, headers=self.acct)
        self.assertEqual((r.status_code, err(r)["code"]), (409, "STATE_CONFLICT"))
        self.assertEqual(self.c.post(f"{PI}/{p2['id']}/cancel", json={"reason": "x"}, headers=self.acct).status_code, 200)

    def test_failed_replacement_keeps_the_old_document_issued(self):
        r1, p1 = self.issued()
        r2 = self.submitted()
        d2 = self.draft(r2["id"], body={"supersedes_id": p1["id"]})
        self.assertEqual(self.c.post(f"{R}/{r2['id']}/cancel", json={"reason": "x"}, headers=self.admin).status_code, 200)
        r = self.issue(d2["id"], expect=409)
        self.assertEqual(err(r)["code"], "STATE_CONFLICT")
        self.assertEqual(self.detail(p1["id"])["status"], "ISSUED")
        self.assertEqual(self.detail(d2["id"])["status"], "DRAFT")
        self.assertEqual([a["action"] for a in self.audit(p1["id"])], ["CREATE", "ISSUE"])        # no SUPERSEDE row

    def test_replacement_input_rules(self):
        r1, p1 = self.issued()
        r = self.draft(r1["id"], body={"supersedes_id": p1["id"]}, expect=409)                    # the request already has an ISSUED document
        self.assertEqual(err(r)["code"], "STATE_CONFLICT")
        r2 = self.submitted()
        r = self.draft(r2["id"], body={"supersedes_id": str(uuid.uuid4())}, expect=422)
        self.assertEqual(err(r)["code"], "REFERENCE_NOT_FOUND")
        draft_only = self.draft(self.submitted()["id"])
        r = self.draft(r2["id"], body={"supersedes_id": draft_only["id"]}, expect=409)            # only an ISSUED document can be replaced
        self.assertEqual((err(r)["code"], err(r)["details"]["reason"]), ("STATE_CONFLICT", "NOT_ISSUED"))
        mine = self.draft(r2["id"], body={"supersedes_id": p1["id"]})
        r = self.draft(self.submitted()["id"], body={"supersedes_id": p1["id"]}, expect=409)       # a document has one live successor
        self.assertEqual((err(r)["code"], err(r)["details"]["reason"]), ("DUPLICATE_RESOURCE", "ALREADY_REPLACED"))
        self.issue(mine["id"])

    def test_sales_cannot_replace_a_document_of_a_request_they_do_not_own(self):
        r1, p1 = self.issued(headers=self.sales)
        r2 = self.submitted(headers=self.sales2)
        r = self.draft(r2["id"], headers=self.sales2, body={"supersedes_id": p1["id"]}, expect=403)
        self.assertEqual(err(r)["code"], "FORBIDDEN_NOT_OWNER")


class Pdf(PreInvoiceBase):
    def test_generate_download_and_idempotence(self):
        _, p = self.issued()
        r = self.c.get(f"{PI}/{p['id']}/pdf", headers=self.admin)
        self.assertEqual((r.status_code, err(r)["code"], err(r)["details"]["reason"]), (409, "STATE_CONFLICT", "PDF_NOT_READY"))
        g = self.pdf_post(p["id"])
        self.assertEqual(g.status_code, 200, g.text)
        meta = g.json()["data"]
        self.assertEqual((meta["status"], meta["template_version"], meta["attempt_count"], meta["last_error_code"]), ("ready", pi.TEMPLATE_VERSION, 1, None))
        d = self.c.get(f"{PI}/{p['id']}/pdf", headers=self.admin)
        self.assertEqual((d.status_code, d.headers["content-type"]), (200, "application/pdf"))
        self.assertTrue(d.content.startswith(b"%PDF-"))
        sha = hashlib.sha256(d.content).hexdigest()
        self.assertEqual((meta["sha256"], meta["size"]), (sha, len(d.content)))
        self.assertEqual(d.headers["etag"], f'"{sha}"')
        self.assertIn("no-store", d.headers["cache-control"])
        self.assertIn(p["pre_invoice_number"], d.headers["content-disposition"])
        again = self.pdf_post(p["id"])                                                           # ready: returned as is, renderer not called
        self.assertEqual((again.status_code, again.json()["data"]["sha256"], self.renderer.calls), (200, sha, 1))
        self.renderer.mode = "raise"
        self.assertEqual(self.pdf_post(p["id"]).status_code, 200)                                # still no render
        self.assertEqual(self.c.get(f"{PI}/{p['id']}/pdf", headers=self.admin).content, d.content)
        full = self.detail(p["id"])
        self.assertEqual((full["status"], full["pdf"]["status"]), ("ISSUED", "ready"))
        self.assertNotIn("pdf_data", json.dumps(full))
        self.assertEqual([a["action"] for a in self.audit(p["id"])], ["CREATE", "ISSUE", "PDF_GENERATE"])

    def test_renderer_gets_the_snapshot_only(self):
        _, p = self.issued()
        self.pdf_post(p["id"])
        m = self.renderer.models[0]
        self.assertEqual((m["number"], m["version"], m["totals"]["grand_total"]), (p["pre_invoice_number"], 1, int(p["grand_total"])))
        self.assertNotIn("status", m)

    def test_pdf_requires_an_issued_document(self):
        d = self.draft(self.submitted()["id"])
        r = self.pdf_post(d["id"])
        self.assertEqual((r.status_code, err(r)["code"], err(r)["details"]["reason"]), (409, "STATE_CONFLICT", "NOT_ISSUED"))
        self.assertEqual(self.renderer.calls, 0)

    def test_failure_is_independent_of_the_commercial_state_and_never_leaks(self):
        _, p = self.issued()
        self.renderer.mode = "raise"
        r = self.pdf_post(p["id"])
        e = err(r)
        self.assertEqual((r.status_code, e["code"], e["details"]["error_code"]), (500, "PDF_GENERATION_FAILED", pi.PDF_RENDER_FAILED))
        self.assertNotIn(SECRET_TEXT, r.text)
        self.assertEqual(e["details"]["pdf"]["status"], "failed")
        full = self.detail(p["id"])
        self.assertEqual((full["status"], full["pre_invoice_number"], full["pdf"]["status"], full["pdf"]["last_error_code"]),
                         ("ISSUED", p["pre_invoice_number"], "failed", pi.PDF_RENDER_FAILED))
        self.assertEqual([a["action"] for a in self.audit(p["id"])], ["CREATE", "ISSUE", "PDF_FAIL"])
        self.assertNotIn(SECRET_TEXT, json.dumps(self.audit(p["id"])))
        r = self.c.get(f"{PI}/{p['id']}/pdf", headers=self.admin)
        self.assertEqual(err(r)["details"]["reason"], "PDF_NOT_READY")
        # the document can be cancelled although its PDF failed
        self.assertEqual(self.c.post(f"{PI}/{p['id']}/cancel", json={"reason": "x"}, headers=self.acct).status_code, 200)

    def test_closed_error_codes(self):
        for mode, code in (("invalid", pi.PDF_INVALID_OUTPUT), ("big", pi.PDF_TOO_LARGE), ("unavailable", pi.PDF_RENDERER_UNAVAILABLE)):
            _, p = self.issued()
            self.renderer.mode = mode
            r = self.pdf_post(p["id"])
            self.assertEqual((r.status_code, err(r)["code"], err(r)["details"]["error_code"]), (500, "PDF_GENERATION_FAILED", code), mode)
            self.assertEqual(self.detail(p["id"])["pdf"]["status"], "failed")

    def test_default_renderer_is_unavailable_and_visible(self):
        c = TestClient(support.make_app())                                                       # no renderer injected
        _, p = self.issued()
        r = c.post(f"{PI}/{p['id']}/pdf", headers=self.acct)
        self.assertEqual((r.status_code, err(r)["details"]["error_code"]), (500, pi.PDF_RENDERER_UNAVAILABLE))
        self.assertEqual(self.detail(p["id"])["status"], "ISSUED")

    def test_retry_policy(self):
        _, p = self.issued()
        self.renderer.mode = "raise"

        def attempt(offset_s):
            type(self).offset = timedelta(seconds=offset_s)
            return self.pdf_post(p["id"])
        self.assertEqual(attempt(0).status_code, 500)                                            # the initial attempt
        r = attempt(20)                                                                          # < 60 s after the last attempt
        self.assertEqual((r.status_code, err(r)["code"]), (429, "RATE_LIMITED"))
        self.assertTrue(1 <= err(r)["details"]["retry_after"] <= 60)
        self.assertEqual(r.headers["retry-after"], str(err(r)["details"]["retry_after"]))
        self.assertEqual(self.renderer.calls, 1)                                                 # a refused attempt does not render
        self.assertEqual(self.detail(p["id"])["pdf"]["attempt_count"], 1)                        # ... and is not counted
        for n, t in enumerate((70, 140, 210), start=2):                                          # retries 1..3 inside one 15-minute window
            self.assertEqual(attempt(t).status_code, 500, t)
            self.assertEqual(self.detail(p["id"])["pdf"]["attempt_count"], n)
        r = attempt(280)                                                                         # a 4th retry in the window
        self.assertEqual((r.status_code, err(r)["code"]), (429, "RATE_LIMITED"))
        self.assertGreater(err(r)["details"]["retry_after"], 60)                                 # the window, not the 60 s rule
        self.renderer.mode = "ok"
        r = attempt(70 + 905)                                                                    # the window (opened at the first retry) is over
        self.assertEqual((r.status_code, r.json()["data"]["status"]), (200, "ready"))
        self.assertEqual(self.detail(p["id"])["pdf"]["attempt_count"], 5)

    def test_a_ready_document_is_never_overwritten_even_by_sql(self):
        _, p = self.issued()
        self.pdf_post(p["id"])
        rc, _, e = pg.psql(support.DB, f"UPDATE pre_invoice_documents SET pdf_sha256 = repeat('0', 64) WHERE pre_invoice_id = '{p['id']}'")
        self.assertNotEqual(rc, 0)
        rc, _, e = pg.psql(support.DB, f"DELETE FROM pre_invoice_documents WHERE pre_invoice_id = '{p['id']}'")
        self.assertNotEqual(rc, 0)

    def test_parallel_generation_renders_the_final_document_once_stored(self):
        _, p = self.issued()
        out, bar = [], threading.Barrier(4)

        def go():
            c = TestClient(self.c.app)
            bar.wait()
            r = c.post(f"{PI}/{p['id']}/pdf", headers=self.acct)
            out.append((r.status_code, r.json().get("data", {}).get("status") if r.status_code == 200 else err(r)["code"]))
        ts = [threading.Thread(target=go) for _ in range(4)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertTrue(all(s in (200, 429) for s, _ in out), out)                               # never 500, never a half state
        self.assertIn((200, "ready"), out)
        got = self.c.get(f"{PI}/{p['id']}/pdf", headers=self.admin)
        self.assertEqual(hashlib.sha256(got.content).hexdigest(), self.detail(p["id"])["pdf"]["sha256"])


class AuditPayloads(PreInvoiceBase):
    def test_allowlist_and_no_customer_data(self):
        notes = "PRIVATE-NOTE-" + uuid.uuid4().hex[:6]
        req = self.submitted(notes=notes)
        d = self.draft(req["id"])
        p = self.issue(d["id"])
        self.c.post(f"{PI}/{p['id']}/cancel", json={"reason": "business reason"}, headers=self.acct)
        rows = self.audit(p["id"])
        self.assertEqual([(a["action"], a["entity_type"]) for a in rows], [("CREATE", "PRE_INVOICE"), ("ISSUE", "PRE_INVOICE"), ("CANCEL", "PRE_INVOICE")])
        blob = json.dumps(rows, ensure_ascii=False)
        for secret in (notes, d["customer"]["name"], str(d["customer"]["mobile"] or "-none-")):
            self.assertNotIn(secret, blob)
        for a in rows:
            for side in (a["old_data"], a["new_data"]):
                self.assertLessEqual(set(side or {}), pi.AUDIT_KEYS)
        self.assertEqual(rows[2]["description"], "business reason")
        self.assertEqual(rows[1]["new_data"]["pre_invoice_number"], p["pre_invoice_number"])

    def test_commercial_audit_is_in_the_same_transaction(self):
        """A failed issue leaves neither a number nor an ISSUE row."""
        req = self.submitted()
        d = self.draft(req["id"])
        self.c.post(f"{R}/{req['id']}/cancel", json={"reason": "x"}, headers=self.admin)
        self.issue(d["id"], expect=409)
        self.assertEqual([a["action"] for a in self.audit(d["id"])], ["CREATE"])


if __name__ == "__main__":
    unittest.main()
