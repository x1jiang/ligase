"""Tests for the Comments, Screenshots & Uploaded Figures Feedback Tab + Email Delivery Engine."""

from __future__ import annotations

from email import message_from_string
from pathlib import Path
from typing import Any, List, Tuple
from unittest.mock import patch

from fastapi.testclient import TestClient

from ligase.webapp.server import create_webapp

# Minimal valid 1x1 PNG bytes
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc`\x00\x00"
    b"\x00\x02\x00\x01\xe5'\xde\xfc\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _FakeSMTP:
    sent_messages: List[Tuple[str, List[str], str]] = []

    def __init__(self, host: str, port: int, timeout: int = 30) -> None:
        self.host = host
        self.port = port
        self.started_tls = False
        self.logged_in = False

    def __enter__(self) -> "_FakeSMTP":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, user: str, password: str) -> None:
        assert user
        assert password
        self.logged_in = True

    def sendmail(self, sender: str, recipients: List[str], raw_msg: str) -> None:
        assert self.started_tls and self.logged_in
        _FakeSMTP.sent_messages.append((sender, recipients, raw_msg))


def test_feedback_tab_routes_multipart_persistence_and_inline_screenshot_email(tmp_path: Path) -> None:
    _FakeSMTP.sent_messages.clear()
    persist_root = tmp_path / "gcs_mount"
    state_a = tmp_path / "ephemeral_a"
    runs_a = tmp_path / "runs_a"

    app = create_webapp(state_dir=state_a, runs_root=runs_a, persistent_dir=persist_root)
    app.state.feedback_manager._smtp_password = "unit-test-app-password"

    with patch("ligase.webapp.feedback.smtplib.SMTP", _FakeSMTP), patch.object(
        app.state.feedback_manager,
        "synthesize_improvement_brief",
        wraps=lambda items, allow_ai=True: app.state.feedback_manager._fallback_improvement_brief(items),
    ):
        client = TestClient(app)

        # 1. Verify /feedback and /comments render the accessible Comments & Feedback tab
        for route in ("/feedback", "/comments"):
            r = client.get(route)
            assert r.status_code == 200
            assert 'id="tab-feedback"' in r.text
            assert 'id="panel-feedback"' in r.text

        # 2. Verify shipped fixes endpoint
        res_fixed = client.get("/api/feedback/resolved")
        assert res_fixed.status_code == 200
        assert len(res_fixed.json()["items"]) >= 3

        # 3. Submit multipart feedback with PNG screenshot + CSV figure data + captions
        svg_figure = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 40"><text y="20">BIN1 Locus</text></svg>'
        post_res = client.post(
            "/api/feedback?wait_email=1",
            headers={"X-Ligase-Client-Id": "cli_feedback_tester01"},
            data={
                "name": "Dr. Test Researcher",
                "email": "researcher@uth.tmc.edu",
                "category": "ui_figures",
                "target_area": "mindmap",
                "comment": "Please add a zoom-to-fit button and exportable locus plot on the Capabilities Mindmap.",
                "captions_json": '["Annotated screenshot of Mindmap zoom bar", "Sample BIN1 locus SVG figure"]',
            },
            files=[
                ("files", ("mindmap_screenshot.png", TINY_PNG, "image/png")),
                ("files", ("bin1_locus_figure.svg", svg_figure, "image/svg+xml")),
            ],
        )
        assert post_res.status_code == 200, post_res.text
        body = post_res.json()
        assert body["ok"] is True
        assert body["attachment_count"] == 2
        assert body["persistent"] is True
        assert body["email_delivery"]["sent"] is True
        fid = body["feedback_id"]

        # 4. Verify durable files exist on the persistent GCS-style mount
        assert (persist_root / "feedback" / "events" / f"{fid}.json").is_file()
        att_files = list((persist_root / "feedback" / "attachments" / fid).iterdir())
        assert len(att_files) == 2

        # 5. Verify MIME email contains HTML engineering spec, Reply-To, inline CID screenshot, and 2 file attachments
        assert len(_FakeSMTP.sent_messages) == 1
        sender, recipients, raw_mime = _FakeSMTP.sent_messages[0]
        parsed_mail = message_from_string(raw_mime)
        assert "Ligase Improvement" in parsed_mail["Subject"]
        assert parsed_mail["Reply-To"] == "researcher@uth.tmc.edu"
        decoded_html = "".join(
            part.get_payload(decode=True).decode("utf-8", errors="replace")
            for part in parsed_mail.walk()
            if part.get_content_type() == "text/html"
        )
        assert "cid:ligase_fig_" in decoded_html
        assert "Content-ID: <ligase_fig_" in raw_mime
        assert "Annotated screenshot of Mindmap zoom bar" in decoded_html
        assert "Future Improvement Engineering Spec" in decoded_html
        assert "bin1_locus_figure.svg" in raw_mime

        # 6. Simulate ephemeral container wipe — new container mounts same persist_root
        app_b = create_webapp(
            state_dir=tmp_path / "ephemeral_b",
            runs_root=tmp_path / "runs_b",
            persistent_dir=persist_root,
        )
        client_b = TestClient(app_b)
        recent = client_b.get(
            "/api/feedback/recent",
            headers={"X-Ligase-Client-Id": "cli_feedback_tester01"},
        )
        assert recent.status_code == 200
        items = recent.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == fid
        assert items[0]["emailed"] is True
        assert items[0]["attachment_count"] == 2
        # Ensure PII (email/IP) is never leaked in workspace listing
        assert "researcher@uth.tmc.edu" not in recent.text

        # Owner can fetch attachment; different workspace gets 403
        fname = items[0]["attachments"][0]["filename"]
        ok_att = client_b.get(
            f"/api/feedback/{fid}/attachments/{fname}",
            headers={"X-Ligase-Client-Id": "cli_feedback_tester01"},
        )
        assert ok_att.status_code == 200
        denied_att = client_b.get(
            f"/api/feedback/{fid}/attachments/{fname}",
            headers={"X-Ligase-Client-Id": "cli_other_workspace99"},
        )
        assert denied_att.status_code == 403

        # Also verify feedback event was persisted into Usage & Volume Ledger
        usage = client_b.get("/api/usage?days=all").json()
        assert any(r["event_type"] == "feedback" for r in usage["ledger"])


def test_cron_digest_token_enforcement_and_delivery(tmp_path: Path, monkeypatch: Any) -> None:
    _FakeSMTP.sent_messages.clear()
    monkeypatch.setenv("LIGASE_CRON_TOKEN", "secret-cron-token-xyz")
    persist_root = tmp_path / "gcs_mount"
    app = create_webapp(
        state_dir=tmp_path / "state",
        runs_root=tmp_path / "runs",
        persistent_dir=persist_root,
    )
    app.state.feedback_manager._smtp_password = "unit-test-app-password"

    with patch("ligase.webapp.feedback.smtplib.SMTP", _FakeSMTP), patch.object(
        app.state.feedback_manager,
        "synthesize_improvement_brief",
        wraps=lambda items, allow_ai=True: app.state.feedback_manager._fallback_improvement_brief(items),
    ):
        client = TestClient(app)
        # Save one feedback record without immediate send (simulate queued digest item)
        rec = app.state.feedback_manager.save_feedback(
            comment="Add FILER cell-type filter pills on NIAGADS v2.0 tab.",
            category="niagads_data",
            target_area="niagads-api",
            client_id="cli_digest_user01",
            attachments=[{"filename": "filer_mock.png", "content": TINY_PNG, "content_type": "image/png", "caption": "Mockup"}],
        )
        assert rec["digested"] is False

        # Missing / wrong cron token -> 403
        assert client.post("/api/cron/digest").status_code == 403
        assert client.post("/api/cron/digest", headers={"X-Cron-Token": "wrong"}).status_code == 403

        # Valid cron token -> 200 and sends digest email with inline screenshot
        ok = client.post("/api/cron/digest", headers={"X-Cron-Token": "secret-cron-token-xyz"})
        assert ok.status_code == 200
        res = ok.json()
        assert res["sent"] is True
        assert res["item_count"] == 1
        assert len(_FakeSMTP.sent_messages) == 1


def test_deferred_hydration_fast_cold_boot_still_recovers_persistent_state(tmp_path: Path) -> None:
    """Verify scale-from-zero deferred GCS hydration skips init blocking yet serves all persisted data."""
    from ligase.webapp.feedback import FeedbackManager
    from ligase.webapp.store import ThreadStore
    from ligase.webapp.usage_tracker import UsageTracker

    persist_root = tmp_path / "gcs_fuse_sim"
    db_a = tmp_path / "inst_a" / "ligase.sqlite3"
    store_a = ThreadStore(db_a, persistent_root=persist_root)
    th = store_a.create_thread("cli_coldboot_01", title="Cold Boot Persistence Check")
    tracker_a = UsageTracker(db_a, persistent_dir=persist_root / "usage_events")
    tracker_a.record_niagads_api_call(
        client_id="cli_coldboot_01",
        action="gene",
        target="APOE",
        endpoint="/service/gene/APOE",
        ok=True,
        elapsed_ms=95,
        payload_bytes=2048,
    )

    # New instance boots with defer_hydration=True (zero FUSE scandir/mkdir during __init__)
    db_b = tmp_path / "inst_b" / "ligase.sqlite3"
    store_b = ThreadStore(db_b, persistent_root=persist_root, defer_hydration=True)
    tracker_b = UsageTracker(db_b, persistent_dir=persist_root / "usage_events", defer_hydration=True)
    fb_b = FeedbackManager(persist_root, defer_dirs=True)
    assert store_b._last_sync_m == 0.0
    assert tracker_b._last_sync_monotonic == 0.0

    # Even if queried immediately before background hydration runs, on-demand sync recovers everything
    threads = store_b.list_threads("cli_coldboot_01")
    assert any(t["id"] == th["id"] for t in threads)
    summary = tracker_b.get_dashboard_summary(days="all")
    assert len(summary["ledger"]) == 1
    assert summary["ledger"][0]["event_type"] == "niagads_api"
    rec = fb_b.save_feedback(comment="Fast cold boot comment check", client_id="cli_coldboot_01")
    assert (persist_root / "feedback" / "events" / f"{rec['id']}.json").is_file()


