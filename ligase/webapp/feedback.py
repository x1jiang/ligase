"""Persistent Comments, Screenshots & Uploaded Figures Feedback + Email Delivery Engine for Ligase.

Stores every user comment, pasted screenshot, uploaded scientific figure, and supporting document
durably on Google Cloud Storage FUSE (in-place JSON writes — never temp-then-rename on gcsfuse)
or local persistent disk, synthesizes concrete engineering instructions for future improvements,
and emails rich HTML + inline CID image previews + file attachments via SMTP STARTTLS.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import smtplib
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("ligase.webapp.feedback")

PKG_DIR = Path(__file__).resolve().parent
REPO_DIR = PKG_DIR.parent.parent

ALLOWED_EXTENSIONS = {
    # Screenshots & scientific figures
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".svg",
    # Scientific & office documents
    ".pdf",
    ".docx",
    ".doc",
    ".pptx",
    ".xlsx",
    ".csv",
    ".tsv",
    ".txt",
    ".rtf",
    ".md",
    ".json",
    ".vcf",
    ".bed",
    ".fasta",
    ".fa",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}
INLINE_RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024        # 25 MB per file
MAX_TOTAL_ATTACHMENTS_BYTES = 50 * 1024 * 1024  # 50 MB per submission
MAX_EMAIL_ATTACHMENT_BYTES = 18 * 1024 * 1024   # 18 MB cumulative MIME cap

SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9_.-]")
UUID_RE = re.compile(r"^[a-f0-9-]{36}$")

DEFAULT_FROM_EMAIL = "xiaoqian.jiang@gmail.com"
DEFAULT_TO_EMAIL = "xiaoqian.jiang@uth.tmc.edu"
DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587
DEFAULT_SUMMARY_MODEL = "gpt-5.4-mini"

CATEGORY_LABELS: Dict[str, str] = {
    "feature_request": "Feature Request / New Capability",
    "niagads_data": "NIAGADS / Genomics API Enhancement",
    "ui_figures": "Figures, Mindmap, or UI Polish",
    "agent_quality": "Agent Speed, Grounding, or Accuracy",
    "bug_report": "Bug or Error Report",
    "general": "General Instruction for Future Improvements",
}

TARGET_AREA_LABELS: Dict[str, str] = {
    "studio": "Research Studio (gpt-6-luna)",
    "mindmap": "Capabilities Mindmap",
    "niagads-api": "NIAGADS Open Access v2.0 Explorer",
    "usage": "Usage & Volume Ledger",
    "portal": "Whole Web Portal / CLI / SDK",
}

TARGET_MODULE_HINTS: Dict[str, str] = {
    "studio": "ligase/agent.py, ligase/webapp/server.py, ligase/webapp/static/app.js",
    "mindmap": "ligase/webapp/mindmap.py, ligase/webapp/static/app.js, ligase/webapp/static/styles.css",
    "niagads-api": "ligase/niagads_api.py, ligase/gemma_tools.py, ligase/webapp/server.py",
    "usage": "ligase/webapp/usage_tracker.py, ligase/webapp/static/app.js, ligase/webapp/static/styles.css",
    "portal": "ligase/webapp/server.py, ligase/webapp/static/index.html, ligase/webapp/static/app.js",
}


def _read_env_key(path: Path, key: str) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(f"{key}=") and not stripped.startswith("#"):
                val = stripped.split("=", 1)[1].strip()
                return val.strip("\"'")
    except Exception:
        pass
    return None


def resolve_credential(key: str, default: str = "", explicit: Optional[str] = None) -> str:
    """Resolve SMTP/email credential across explicit value, .env, os.environ, and sibling workspace .env files."""
    if explicit and explicit.strip():
        return explicit.strip()

    val = _read_env_key(REPO_DIR / ".env", key)
    if val:
        return val.strip()

    env_val = os.environ.get(key)
    if env_val and env_val.strip():
        return env_val.strip()

    for fallback_env in (
        REPO_DIR.parent / "pptx_accessibility_agent" / ".env",
        REPO_DIR.parent / "mcp_grant_search" / ".env",
    ):
        val = _read_env_key(fallback_env, key)
        if val:
            return val.strip()

    return default


def sanitize_filename(filename: str, fallback_ext: str = ".png") -> str:
    """Sanitize filename to prevent path traversal and shell injection."""
    name = Path(filename or "").name
    name = SAFE_FILENAME_RE.sub("_", name)
    if not name or name.startswith("."):
        name = f"attachment_{uuid4().hex[:8]}{fallback_ext}"
    if len(name) > 120:
        stem = Path(name).stem[:96]
        ext = Path(name).suffix[:20]
        name = f"{stem}{ext}"
    return name


def validate_file_extension(filename: str) -> str:
    """Verify that the uploaded file extension is permitted."""
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext or 'unknown'}'. Allowed: "
            f"{', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    return ext


def _cap_list(values: Any, limit: int = 5) -> List[Any]:
    if not isinstance(values, list):
        return [values] if values else []
    return values[:limit]


class FeedbackManager:
    """Durable feedback storage + AI improvement synthesizer + SMTP email dispatcher."""

    def __init__(
        self,
        base_dir: Path,
        *,
        openai_api_key: Optional[str] = None,
        smtp_password: Optional[str] = None,
    ) -> None:
        self.root = (Path(base_dir).resolve() / "feedback").resolve()
        self.events_dir = self.root / "events"
        self.attachments_root = self.root / "attachments"
        self.raw_dir = self.root / "raw"
        self.digests_dir = self.root / "digests"
        for d in (self.root, self.events_dir, self.attachments_root, self.raw_dir, self.digests_dir):
            d.mkdir(parents=True, exist_ok=True)
        self._openai_api_key = (openai_api_key or "").strip() or None
        self._smtp_password = (smtp_password or "").strip() or None

    def get_smtp_config(self) -> Dict[str, Any]:
        raw_pw = resolve_credential("SMTP_PASSWORD", "", explicit=self._smtp_password)
        clean_pw = raw_pw.replace(" ", "") if raw_pw else ""
        port_raw = resolve_credential("SMTP_PORT", str(DEFAULT_SMTP_PORT))
        try:
            port = int(port_raw)
        except ValueError:
            port = DEFAULT_SMTP_PORT
        to_addr = (
            resolve_credential("FEEDBACK_TO_EMAIL", "")
            or resolve_credential("DIGEST_TO_EMAIL", DEFAULT_TO_EMAIL)
        )
        from_addr = (
            resolve_credential("FEEDBACK_FROM_EMAIL", "")
            or resolve_credential("DIGEST_FROM_EMAIL", DEFAULT_FROM_EMAIL)
        )
        return {
            "host": resolve_credential("SMTP_HOST", DEFAULT_SMTP_HOST),
            "port": port,
            "user": resolve_credential("SMTP_USER", from_addr),
            "password": clean_pw,
            "from_email": from_addr,
            "to_email": to_addr,
            "configured": bool(clean_pw),
        }

    def save_feedback(
        self,
        *,
        comment: str,
        name: str = "",
        email: str = "",
        category: str = "feature_request",
        target_area: str = "portal",
        client_id: str = "local_default",
        page_url: str = "",
        attachments: Optional[List[Dict[str, Any]]] = None,
        client_ip: str = "unknown",
    ) -> Dict[str, Any]:
        """Persist a feedback submission + screenshots/figures in-place (GCS FUSE safe)."""
        cleaned_comment = (comment or "").strip()
        if not cleaned_comment:
            raise ValueError("Comment or improvement instruction cannot be empty.")

        feedback_id = str(uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        sub_att_dir = self.attachments_root / feedback_id
        sub_att_dir.mkdir(parents=True, exist_ok=True)

        processed_attachments: List[Dict[str, Any]] = []
        total_bytes = 0

        for idx, item in enumerate(attachments or [], start=1):
            raw_name = str(item.get("filename") or f"attachment_{idx}.png")
            content = item.get("content")
            content_type = str(item.get("content_type") or "").strip()
            caption = str(item.get("caption") or "").strip()[:300]

            if not isinstance(content, (bytes, bytearray)) or len(content) == 0:
                continue

            size_bytes = len(content)
            if size_bytes > MAX_ATTACHMENT_BYTES:
                raise ValueError(
                    f"File '{raw_name}' ({size_bytes / (1024 * 1024):.1f} MB) exceeds the 25 MB per-file limit."
                )
            total_bytes += size_bytes
            if total_bytes > MAX_TOTAL_ATTACHMENTS_BYTES:
                raise ValueError("Total attachment size exceeds the 50 MB per-submission limit.")

            ext = validate_file_extension(raw_name)
            safe_name = sanitize_filename(raw_name, fallback_ext=ext)
            dest_file = sub_att_dir / safe_name
            if dest_file.exists():
                safe_name = f"{Path(safe_name).stem}_{uuid4().hex[:4]}{ext}"
                dest_file = sub_att_dir / safe_name

            dest_file.write_bytes(bytes(content))
            guessed_mime, _ = mimetypes.guess_type(safe_name)
            final_mime = content_type or guessed_mime or "application/octet-stream"

            processed_attachments.append(
                {
                    "id": str(uuid4()),
                    "filename": safe_name,
                    "original_name": Path(raw_name).name[:140],
                    "size_bytes": size_bytes,
                    "content_type": final_mime,
                    "is_image": ext in IMAGE_EXTENSIONS,
                    "is_inline_raster": ext in INLINE_RASTER_EXTENSIONS,
                    "caption": caption,
                }
            )

        norm_cat = (category or "feature_request").strip().lower()
        if norm_cat not in CATEGORY_LABELS:
            norm_cat = "general"
        norm_area = (target_area or "portal").strip().lower()
        if norm_area not in TARGET_AREA_LABELS:
            norm_area = "portal"

        record: Dict[str, Any] = {
            "schema": 1,
            "id": feedback_id,
            "created_at": now_iso,
            "client_id": (client_id or "local_default").strip(),
            "name": (name or "").strip()[:120],
            "email": (email or "").strip()[:160],
            "category": norm_cat,
            "category_label": CATEGORY_LABELS[norm_cat],
            "target_area": norm_area,
            "target_area_label": TARGET_AREA_LABELS[norm_area],
            "page_url": (page_url or "").strip()[:240],
            "comment": cleaned_comment,
            "raw_comment": comment,
            "attachments": processed_attachments,
            "total_attachment_bytes": total_bytes,
            "emailed": False,
            "emailed_at": None,
            "email_recipient": None,
            "email_error": None,
            "digested": False,
            "digest_sent_at": None,
            "digest_id": None,
            "resolved": False,
            "resolved_at": None,
            "resolution": None,
            "client_ip": client_ip,
        }

        try:
            (self.raw_dir / f"{feedback_id}.txt").write_text(comment, encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not write raw comment text %s: %s", feedback_id, exc)

        try:
            ledger_line = json.dumps(
                {
                    "id": feedback_id,
                    "created_at": now_iso,
                    "client_id": record["client_id"],
                    "category": norm_cat,
                    "target_area": norm_area,
                    "comment": cleaned_comment[:500],
                    "attachments": [a["original_name"] for a in processed_attachments],
                },
                ensure_ascii=False,
            )
            with open(self.root / "raw_comments.jsonl", "a", encoding="utf-8") as fh:
                fh.write(ledger_line + "\n")
        except Exception as exc:
            logger.warning("Could not append raw_comments.jsonl: %s", exc)

        # In-place write (never temp-then-rename on GCS FUSE)
        (self.events_dir / f"{feedback_id}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return record

    def get_feedback(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        if not UUID_RE.match(feedback_id or ""):
            return None
        path = self.events_dir / f"{feedback_id}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _save_record_in_place(self, record: Dict[str, Any]) -> None:
        fid = str(record.get("id") or "")
        if not UUID_RE.match(fid):
            return
        (self.events_dir / f"{fid}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def get_attachment_path(self, feedback_id: str, filename: str) -> Optional[Path]:
        if not UUID_RE.match(feedback_id or ""):
            return None
        safe_name = Path(filename or "").name
        if not safe_name or safe_name != filename:
            return None
        target = (self.attachments_root / feedback_id / safe_name).resolve()
        if not str(target).startswith(str(self.attachments_root.resolve())) or not target.is_file():
            return None
        return target

    def list_feedback(
        self,
        *,
        undigested_only: bool = False,
        client_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        if not self.events_dir.is_dir():
            return items
        try:
            with os.scandir(self.events_dir) as it:
                for entry in it:
                    if not entry.name.endswith(".json") or entry.name.startswith("."):
                        continue
                    try:
                        data = json.loads(Path(entry.path).read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    if not isinstance(data, dict) or not data.get("id"):
                        continue
                    if undigested_only and data.get("digested"):
                        continue
                    if client_id and data.get("client_id") != client_id:
                        continue
                    items.append(data)
        except OSError:
            pass
        items.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return items[: max(1, int(limit))]

    def list_workspace_submissions(self, client_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Return safe, PII-scrubbed submission summaries for the active browser workspace."""
        rows = self.list_feedback(client_id=client_id, limit=limit)
        out: List[Dict[str, Any]] = []
        for r in rows:
            atts = r.get("attachments") or []
            out.append(
                {
                    "id": r["id"],
                    "created_at": r.get("created_at"),
                    "category": r.get("category") or "general",
                    "category_label": r.get("category_label") or CATEGORY_LABELS.get(r.get("category", ""), "General"),
                    "target_area": r.get("target_area") or "portal",
                    "target_area_label": r.get("target_area_label") or TARGET_AREA_LABELS.get(r.get("target_area", ""), "Portal"),
                    "comment_preview": str(r.get("comment") or "")[:220],
                    "attachment_count": len(atts),
                    "image_count": sum(1 for a in atts if a.get("is_image")),
                    "attachments": [
                        {
                            "filename": a.get("filename"),
                            "original_name": a.get("original_name"),
                            "size_bytes": a.get("size_bytes", 0),
                            "is_image": bool(a.get("is_image")),
                            "caption": a.get("caption") or "",
                        }
                        for a in atts
                    ],
                    "emailed": bool(r.get("emailed")),
                    "emailed_at": r.get("emailed_at"),
                    "resolved": bool(r.get("resolved")),
                }
            )
        return out

    def _load_shipped_fixes(self) -> List[Dict[str, Any]]:
        path = PKG_DIR / "shipped_fixes.json"
        if not path.is_file():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return [x for x in raw if isinstance(x, dict) and x.get("id") and x.get("problem")] if isinstance(raw, list) else []
        except Exception:
            return []

    def list_resolved_feedback(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Public 'What We've Shipped & Fixed' list — never includes submitter names, emails, or IPs."""
        entries: List[Dict[str, Any]] = [
            {
                "id": str(item["id"]),
                "category": str(item.get("category") or "general"),
                "problem": str(item["problem"]),
                "resolution": str(item.get("resolution") or ""),
                "raised_at": item.get("raised_at"),
                "resolved_at": item.get("resolved_at"),
            }
            for item in self._load_shipped_fixes()
        ]
        seen = {e["id"] for e in entries}
        for item in self.list_feedback(limit=500):
            if not item.get("resolved") or item["id"] in seen:
                continue
            res = item.get("resolution") or {}
            entries.append(
                {
                    "id": item["id"],
                    "category": item.get("category") or "general",
                    "problem": str(res.get("problem") or ""),
                    "resolution": str(res.get("resolution") or ""),
                    "raised_at": item.get("created_at"),
                    "resolved_at": item.get("resolved_at"),
                }
            )
        entries.sort(key=lambda e: str(e.get("resolved_at") or ""), reverse=True)
        return entries[: max(1, int(limit))]

    def resolve_feedback(self, feedback_id: str, *, problem: str, resolution: str = "") -> Optional[Dict[str, Any]]:
        cleaned_problem = " ".join((problem or "").split())
        if not cleaned_problem:
            raise ValueError("Problem description is required.")
        item = self.get_feedback(feedback_id)
        if not item:
            return None
        item["resolved"] = True
        item["resolved_at"] = datetime.now(timezone.utc).isoformat()
        item["resolution"] = {
            "problem": cleaned_problem[:500],
            "resolution": " ".join((resolution or "").split())[:1000],
        }
        self._save_record_in_place(item)
        return item

    # ── AI Synthesis to Instruct Future Improvements ──────────────────────────
    def _fallback_improvement_brief(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not items:
            return {
                "next_action": "Nothing to do: no pending feedback submissions.",
                "status": "Zero new feedback submissions in this window.",
                "engineering_spec": "No code changes queued.",
                "action_items": [],
                "reported_issues": ["No bugs or errors reported."],
                "what_people_want": ["No new feature requests submitted."],
            }
        first = items[0]
        area = str(first.get("target_area") or "portal")
        mod_hint = TARGET_MODULE_HINTS.get(area, TARGET_MODULE_HINTS["portal"])
        who = first.get("name") or first.get("email") or "Researcher"
        short_comment = str(first.get("comment") or "").strip()
        if len(short_comment) > 130:
            short_comment = short_comment[:127] + "..."

        att_count = sum(len(i.get("attachments") or []) for i in items)
        cat_counts: Dict[str, int] = {}
        requests: List[str] = []
        issues: List[str] = []
        for it in items:
            cl = CATEGORY_LABELS.get(str(it.get("category") or ""), "General")
            cat_counts[cl] = cat_counts.get(cl, 0) + 1
            txt = str(it.get("comment") or "").strip()
            line = f"[{TARGET_AREA_LABELS.get(str(it.get('target_area') or 'portal'), 'Portal')}] {txt[:135]}"
            if "bug" in str(it.get("category") or ""):
                issues.append(line)
            else:
                requests.append(line)

        breakdown = ", ".join(f"{n} {k}" for k, n in cat_counts.items())
        return {
            "next_action": f"Review {who}'s {CATEGORY_LABELS.get(first.get('category', ''), 'feedback')} and attached visuals, then queue edit in {mod_hint.split(',')[0]}.",
            "status": f"Received {len(items)} Ligase improvement submission(s) ({breakdown}) with {att_count} screenshot/figure attachment(s).",
            "engineering_spec": f"Target modules: {mod_hint}. Primary instruction: {short_comment}",
            "action_items": [
                {
                    "task": f"Inspect attached screenshots/figures and apply requested update in {mod_hint.split(',')[0]}",
                    "time_estimate": "20 minutes",
                    "why": "Directly addresses user-submitted Ligase improvement instruction.",
                },
                {
                    "task": "Add regression test in tests/ and redeploy Cloud Run service ligase",
                    "time_estimate": "10 minutes",
                    "why": "Verifies improvement without regressing fast SSR or GCS persistence.",
                },
            ],
            "reported_issues": issues[:5] if issues else ["No bugs or errors reported."],
            "what_people_want": requests[:5] if requests else ["See verbatim comment below."],
        }

    def synthesize_improvement_brief(self, items: List[Dict[str, Any]], *, allow_ai: bool = True) -> Dict[str, Any]:
        """Use OpenAI to turn user comments + figure metadata into concrete future-improvement instructions."""
        fallback = self._fallback_improvement_brief(items)
        if not items or not allow_ai:
            return fallback

        api_key = resolve_credential("OPENAI_API_KEY", "", explicit=self._openai_api_key)
        if not api_key:
            return fallback

        model = (
            resolve_credential("FEEDBACK_SUMMARY_MODEL", "")
            or resolve_credential("LIGASE_WEB_MODEL", DEFAULT_SUMMARY_MODEL)
        )
        prompt_items = []
        for idx, it in enumerate(items, start=1):
            area = str(it.get("target_area") or "portal")
            prompt_items.append(
                {
                    "index": idx,
                    "author": it.get("name") or "Anonymous Researcher",
                    "category": it.get("category_label") or it.get("category"),
                    "target_area": it.get("target_area_label") or area,
                    "candidate_repo_files": TARGET_MODULE_HINTS.get(area, TARGET_MODULE_HINTS["portal"]),
                    "comment": it.get("comment"),
                    "attachments": [
                        {
                            "name": a.get("original_name"),
                            "is_image": a.get("is_image"),
                            "size_kb": max(1, int((a.get("size_bytes") or 0) // 1024)),
                            "caption": a.get("caption") or "",
                        }
                        for a in (it.get("attachments") or [])
                    ],
                    "created_at": it.get("created_at"),
                }
            )

        system_prompt = (
            "You write concise engineering improvement briefs for Ligase (Biomedical & NIAGADS Co-Scientist Web Portal, "
            "UTHealth Houston McWilliams School of Biomedical Informatics).\n"
            "Turn researcher comments, screenshot captions, and uploaded figure notes into concrete instructions for future improvements.\n"
            "Return JSON with exact keys:\n"
            "1. 'next_action': ONE concrete action under 2 minutes in imperative mood.\n"
            "2. 'status': ONE sentence (<25 words) summarizing what arrived and its priority.\n"
            "3. 'engineering_spec': 1-2 crisp sentences naming exact Ligase files/modules to update and the acceptance check.\n"
            "4. 'action_items': max 5 ranked objects {'task': imperative step, 'time_estimate': e.g. '15 minutes', 'why': <15 words}.\n"
            "5. 'reported_issues': max 5 objects {'issue': <15 words, 'severity': 'High'|'Medium'|'Low', 'details': 1 sentence}.\n"
            "6. 'what_people_want': max 5 objects {'request': <15 words, 'urgency_impact': 'High'|'Medium'|'Low'}.\n"
            "Lead with action, zero fluff."
        )

        try:
            import openai

            client = openai.OpenAI(api_key=api_key, timeout=15.0)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(prompt_items, indent=2, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=1200,
            )
            raw = resp.choices[0].message.content or "{}"
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                return fallback
            for k in ("next_action", "status", "engineering_spec"):
                if not parsed.get(k):
                    parsed[k] = fallback[k]
            return parsed
        except Exception as exc:
            logger.warning("OpenAI feedback synthesis fell back to deterministic brief: %s", exc)
            return fallback

    # ── HTML Email Rendering with Inline Screenshot / Figure Previews ─────────
    @staticmethod
    def _format_bullet(val: Any) -> str:
        if isinstance(val, str):
            return escape(val)
        if isinstance(val, dict):
            badges: List[str] = []
            if val.get("urgency_impact"):
                badges.append(
                    f"<span style='background:#0f766e;color:#fff;font-size:11px;padding:2px 6px;border-radius:4px;margin-right:5px;'>{escape(str(val['urgency_impact']))} Impact</span>"
                )
            if val.get("severity"):
                badges.append(
                    f"<span style='background:#b91c1c;color:#fff;font-size:11px;padding:2px 6px;border-radius:4px;margin-right:5px;'>{escape(str(val['severity']))}</span>"
                )
            if val.get("time_estimate"):
                badges.append(
                    f"<span style='background:#e6f4ea;color:#166534;font-size:11px;padding:2px 6px;border-radius:4px;margin-right:5px;'>{escape(str(val['time_estimate']))}</span>"
                )
            main_txt = escape(
                str(val.get("task") or val.get("request") or val.get("issue") or val.get("title") or "")
            )
            sub_txt = escape(str(val.get("why") or val.get("details") or ""))
            note = f" <span style='color:#475569;font-size:13px;'>— {sub_txt}</span>" if sub_txt else ""
            return "".join(badges) + f"<strong>{main_txt}</strong>" + note
        return escape(str(val))

    def render_feedback_email_html(
        self,
        summary: Dict[str, Any],
        items: List[Dict[str, Any]],
        *,
        heading: str,
        subtitle: str,
        cid_map: Optional[Dict[str, str]] = None,
    ) -> str:
        """Render responsive scientific HTML email with inline screenshot/figure previews."""
        cid_lookup = cid_map or {}
        total_items = len(items)
        total_atts = sum(len(i.get("attachments") or []) for i in items)
        total_imgs = sum(
            sum(1 for a in (i.get("attachments") or []) if a.get("is_image"))
            for i in items
        )

        next_action = escape(str(summary.get("next_action") or "Review submission #1 below."))
        status_line = escape(str(summary.get("status") or ""))
        eng_spec = escape(str(summary.get("engineering_spec") or ""))

        actions = _cap_list(summary.get("action_items", []))
        issues = _cap_list(summary.get("reported_issues", []))
        wants = _cap_list(summary.get("what_people_want", []))

        def render_list(vals: List[Any]) -> str:
            if not vals:
                return "<li>None</li>"
            return "".join(f"<li style='margin-bottom:8px;'>{self._format_bullet(v)}</li>" for v in vals)

        cards_html = ""
        for idx, item in enumerate(items, start=1):
            cat_badge = escape(str(item.get("category_label") or item.get("category") or "Feedback"))
            area_badge = escape(str(item.get("target_area_label") or item.get("target_area") or "Portal"))
            author = escape(str(item.get("name") or "Anonymous Researcher"))
            em = escape(str(item.get("email") or ""))
            author_html = f"<strong>{author}</strong>" + (f" &lt;{em}&gt;" if em else "")
            ts_str = escape(str(item.get("created_at") or "")[:19].replace("T", " "))
            comment_html = escape(str(item.get("comment") or "")).replace("\n", "<br>")

            atts = item.get("attachments") or []
            pills_html = ""
            inline_gallery_html = ""
            if atts:
                pills = []
                inline_cards = []
                for att in atts:
                    att_key = f"{item['id']}:{att.get('filename')}"
                    orig = escape(str(att.get("original_name") or att.get("filename") or "file"))
                    kb = max(1, int((att.get("size_bytes") or 0) // 1024))
                    icon = "🖼️" if att.get("is_image") else "📎"
                    cap = escape(str(att.get("caption") or ""))
                    cap_note = f" — <em>{cap}</em>" if cap else ""
                    pills.append(
                        f"<span style='display:inline-block;background:#f0fdfa;border:1px solid #99f6e4;border-radius:5px;padding:4px 9px;margin:3px 5px 3px 0;font-size:12px;color:#0f766e;'>{icon} {orig} ({kb} KB){cap_note}</span>"
                    )
                    if att_key in cid_lookup:
                        cid_ref = cid_lookup[att_key]
                        inline_cards.append(
                            f"""
                            <div style="margin-top:12px;border:1px solid #cbd5e1;border-radius:8px;overflow:hidden;background:#f8fafc;">
                              <div style="padding:7px 12px;background:#f1f5f9;border-bottom:1px solid #cbd5e1;font-size:12px;color:#334155;">
                                🖼️ <strong>{orig}</strong> ({kb} KB){cap_note}
                              </div>
                              <div style="padding:10px;text-align:center;">
                                <img src="cid:{escape(cid_ref)}" alt="{orig}" style="max-width:100%;max-height:460px;border-radius:6px;border:1px solid #e2e8f0;">
                              </div>
                            </div>
                            """
                        )
                pills_html = f"<div style='margin-top:12px;font-size:13px;'><strong>Attached Screenshots, Figures &amp; Files ({len(atts)}):</strong><div style='margin-top:5px;'>{''.join(pills)}</div></div>"
                inline_gallery_html = "".join(inline_cards)

            cards_html += f"""
            <div style="background:#ffffff;border:1px solid #cbd5e1;border-radius:10px;padding:16px;margin-bottom:16px;">
              <div style="border-bottom:1px solid #e2e8f0;padding-bottom:10px;margin-bottom:12px;">
                <span style="background:#0f766e;color:#ffffff;font-size:11px;font-weight:700;text-transform:uppercase;padding:3px 8px;border-radius:4px;">#{idx} · {cat_badge}</span>
                <span style="background:#e0f2fe;color:#0369a1;font-size:11px;font-weight:600;padding:3px 8px;border-radius:4px;margin-left:6px;">{area_badge}</span>
                <div style="margin-top:7px;font-size:13px;color:#334155;">From {author_html} · <span style="color:#64748b;">{ts_str} UTC · ID <code>{escape(str(item.get('id', ''))[:8])}</code></span></div>
              </div>
              <div style="color:#0f172a;font-size:14px;line-height:1.62;">{comment_html}</div>
              {pills_html}
              {inline_gallery_html}
            </div>
            """

        spec_block = (
            f"""
            <div style="background:#f0fdfa;border-left:4px solid #0f766e;border-radius:0 8px 8px 0;padding:12px 16px;margin-bottom:18px;font-size:13.5px;color:#134e4a;">
              <strong>Future Improvement Engineering Spec:</strong> {eng_spec}
            </div>
            """
            if eng_spec
            else ""
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(heading)}</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
  <div style="max-width:740px;margin:22px auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #cbd5e1;box-shadow:0 4px 14px rgba(15,23,42,0.06);">
    <div style="background:linear-gradient(135deg,#0f766e 0%,#115e59 100%);padding:20px 24px;color:#ffffff;">
      <div style="font-size:11px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;opacity:0.92;margin-bottom:4px;">UTHealth Houston · Ligase Biomedical &amp; NIAGADS Co-Scientist</div>
      <h1 style="margin:0;font-size:21px;font-weight:700;">{escape(heading)}</h1>
      <div style="font-size:13px;opacity:0.92;margin-top:6px;">{escape(subtitle)}</div>
    </div>

    <div style="background:#0f172a;color:#ffffff;padding:12px 24px;text-align:center;">
      <span style="display:inline-block;margin:0 18px;"><strong style="font-size:18px;color:#5eead4;">{total_items}</strong> <span style="font-size:11px;text-transform:uppercase;opacity:0.82;">Submission(s)</span></span>
      <span style="display:inline-block;margin:0 18px;"><strong style="font-size:18px;color:#5eead4;">{total_imgs}</strong> <span style="font-size:11px;text-transform:uppercase;opacity:0.82;">Screenshots / Figures</span></span>
      <span style="display:inline-block;margin:0 18px;"><strong style="font-size:18px;color:#5eead4;">{total_atts}</strong> <span style="font-size:11px;text-transform:uppercase;opacity:0.82;">Total Files</span></span>
    </div>

    <div style="padding:24px;">
      <div style="background:#166534;color:#ffffff;border-radius:8px;padding:15px 18px;margin-bottom:16px;">
        <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.6px;opacity:0.88;margin-bottom:4px;">Do First (Under 2 Minutes)</div>
        <div style="font-size:16px;font-weight:700;line-height:1.4;">{next_action}</div>
      </div>

      <div style="background:#f8fafc;border-left:4px solid #334155;border-radius:0 8px 8px 0;padding:11px 16px;margin-bottom:14px;font-size:13.5px;color:#1e293b;">
        <strong>Status:</strong> {status_line}
      </div>

      {spec_block}

      <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:15px 18px;margin-bottom:18px;">
        <h2 style="margin:0 0 10px 0;font-size:15px;color:#166534;">Recommended Future Improvement Steps (Ranked)</h2>
        <ol style="margin:0;padding-left:20px;font-size:13.5px;line-height:1.52;color:#14532d;">
          {render_list(actions)}
        </ol>
      </div>

      <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:14px 18px;margin-bottom:18px;">
        <h2 style="margin:0 0 8px 0;font-size:15px;color:#991b1b;">Reported Issues / Friction</h2>
        <ol style="margin:0;padding-left:20px;font-size:13.5px;line-height:1.5;color:#7f1d1d;">
          {render_list(issues)}
        </ol>
      </div>

      <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:14px 18px;margin-bottom:22px;">
        <h2 style="margin:0 0 8px 0;font-size:15px;color:#92400e;">Requested Capabilities &amp; Polish</h2>
        <ol style="margin:0;padding-left:20px;font-size:13.5px;line-height:1.5;color:#78350f;">
          {render_list(wants)}
        </ol>
      </div>

      <h2 style="font-size:16px;color:#0f172a;margin:24px 0 12px 0;border-bottom:2px solid #e2e8f0;padding-bottom:6px;">
        Verbatim Comments, Inline Screenshots &amp; Uploaded Figures ({total_items})
      </h2>
      {cards_html}

      <div style="background:#f0fdf4;border-radius:8px;padding:12px 16px;margin-top:10px;font-size:13.5px;color:#166534;">
        <strong>Next:</strong> {next_action}
      </div>
    </div>

    <div style="background:#f8fafc;border-top:1px solid #e2e8f0;padding:14px 24px;font-size:12px;color:#64748b;text-align:center;">
      Ligase Biomedical &amp; NIAGADS Co-Scientist · Durable GCS Feedback Ledger · <a href="https://ligase-765428358644.us-central1.run.app/feedback" style="color:#0f766e;">Open Portal Feedback Tab</a>
    </div>
  </div>
</body>
</html>
"""

    def send_email_with_attachments(
        self,
        *,
        subject: str,
        summary: Dict[str, Any],
        items: List[Dict[str, Any]],
        heading: str,
        subtitle: str,
        to_email: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Deliver HTML email with BOTH inline CID screenshots/figures AND file attachments."""
        cfg = self.get_smtp_config()
        recipient = (to_email or cfg["to_email"]).strip()
        sender = cfg["from_email"]

        if not cfg["host"] or not cfg["user"] or not cfg["password"]:
            raise RuntimeError(
                "SMTP credentials not configured (set SMTP_HOST, SMTP_USER, and SMTP_PASSWORD)."
            )

        # Prepare inline raster CID map + file attachments within 18 MB cap
        cid_map: Dict[str, str] = {}
        inline_parts: List[MIMEImage] = []
        file_parts: List[Any] = []
        cum_bytes = 0
        attached_count = 0

        for item in items:
            fid = str(item.get("id") or "")
            for idx, att in enumerate(item.get("attachments") or [], start=1):
                fname = str(att.get("filename") or "")
                orig_name = str(att.get("original_name") or fname or f"file_{idx}")
                fpath = self.get_attachment_path(fid, fname)
                if not fpath or not fpath.is_file():
                    continue
                fsize = fpath.stat().st_size
                if cum_bytes + fsize > MAX_EMAIL_ATTACHMENT_BYTES:
                    logger.info("Reached 18 MB email attachment cap; remaining files stay on GCS.")
                    break

                data = fpath.read_bytes()
                ext = fpath.suffix.lower()
                cum_bytes += fsize
                attached_count += 1

                if ext in INLINE_RASTER_EXTENSIONS:
                    cid_token = f"ligase_fig_{fid[:8]}_{idx}"
                    cid_map[f"{fid}:{fname}"] = cid_token
                    try:
                        inline_img = MIMEImage(data, name=orig_name)
                    except TypeError:
                        inline_img = MIMEImage(data, _subtype=ext.lstrip("."), name=orig_name)
                    inline_img.add_header("Content-ID", f"<{cid_token}>")
                    inline_img.add_header("Content-Disposition", "inline", filename=orig_name)
                    inline_parts.append(inline_img)

                    # Also attach as standard downloadable attachment so email clients list it in attachments bar
                    try:
                        dl_img = MIMEImage(data, name=orig_name)
                    except TypeError:
                        dl_img = MIMEImage(data, _subtype=ext.lstrip("."), name=orig_name)
                    dl_img.add_header("Content-Disposition", "attachment", filename=orig_name)
                    file_parts.append(dl_img)
                else:
                    part = MIMEApplication(data, Name=orig_name)
                    part.add_header("Content-Disposition", "attachment", filename=orig_name)
                    file_parts.append(part)

        html_body = self.render_feedback_email_html(
            summary,
            items,
            heading=heading,
            subtitle=subtitle,
            cid_map=cid_map,
        )
        plain_lines = [
            f"{heading}",
            f"{subtitle}",
            "",
            f"DO FIRST: {summary.get('next_action', '')}",
            f"STATUS: {summary.get('status', '')}",
            f"ENGINEERING SPEC: {summary.get('engineering_spec', '')}",
            "",
        ]
        for idx, it in enumerate(items, start=1):
            plain_lines.append(
                f"#{idx} [{it.get('category_label', it.get('category'))}] ({it.get('target_area_label', it.get('target_area'))}) "
                f"from {it.get('name') or 'Anonymous'}:"
            )
            plain_lines.append(str(it.get("comment") or ""))
            for a in it.get("attachments") or []:
                plain_lines.append(f"  - Attachment: {a.get('original_name')} ({a.get('size_bytes', 0) // 1024} KB) {a.get('caption', '')}")
            plain_lines.append("")

        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = f"Ligase Co-Scientist Feedback <{sender}>"
        msg["To"] = recipient
        if reply_to and "@" in reply_to:
            msg["Reply-To"] = reply_to
        msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

        related = MIMEMultipart("related")
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText("\n".join(plain_lines), "plain", "utf-8"))
        alt.attach(MIMEText(html_body, "html", "utf-8"))
        related.attach(alt)
        for inl in inline_parts:
            related.attach(inl)
        msg.attach(related)

        for fp in file_parts:
            msg.attach(fp)

        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as smtp:
            smtp.starttls()
            smtp.login(cfg["user"], cfg["password"])
            smtp.sendmail(sender, [recipient], msg.as_string())

        return {
            "sent": True,
            "recipient": recipient,
            "sender": sender,
            "attached_count": attached_count,
            "inline_images": len(inline_parts),
            "attached_bytes": cum_bytes,
        }

    def deliver_single_feedback_email(
        self,
        feedback_id: str,
        *,
        to_email: Optional[str] = None,
        allow_ai: bool = True,
    ) -> Dict[str, Any]:
        """Synthesize improvement instructions and immediately email a newly submitted feedback item."""
        record = self.get_feedback(feedback_id)
        if not record:
            return {"sent": False, "reason": "Feedback record not found."}

        cfg = self.get_smtp_config()
        if not cfg["configured"]:
            record["email_error"] = "SMTP_PASSWORD not configured"
            self._save_record_in_place(record)
            return {"sent": False, "reason": "SMTP credentials not configured; saved durably to storage."}

        try:
            summary = self.synthesize_improvement_brief([record], allow_ai=allow_ai)
            cat_lbl = record.get("category_label") or "Feedback"
            area_lbl = record.get("target_area_label") or "Portal"
            att_n = len(record.get("attachments") or [])
            att_tag = f" + {att_n} visual/file(s)" if att_n else ""
            subject = f"[Ligase Improvement] {cat_lbl} ({area_lbl}){att_tag}"
            res = self.send_email_with_attachments(
                subject=subject,
                summary=summary,
                items=[record],
                heading="Ligase Future Improvement Brief",
                subtitle=f"{cat_lbl} · {area_lbl} · Submitted {str(record.get('created_at', ''))[:19].replace('T', ' ')} UTC",
                to_email=to_email,
                reply_to=record.get("email") or None,
            )
            now_iso = datetime.now(timezone.utc).isoformat()
            record["emailed"] = True
            record["emailed_at"] = now_iso
            record["email_recipient"] = res["recipient"]
            record["email_error"] = None
            record["digested"] = True
            record["digest_sent_at"] = now_iso
            self._save_record_in_place(record)
            return {**res, "feedback_id": feedback_id, "summary": summary}
        except Exception as exc:
            logger.warning("Immediate feedback email failed for %s: %s", feedback_id, exc)
            record["email_error"] = str(exc)[:300]
            self._save_record_in_place(record)
            return {"sent": False, "reason": str(exc), "feedback_id": feedback_id}

    def generate_and_send_digest(
        self,
        *,
        force: bool = False,
        to_email: Optional[str] = None,
        allow_ai: bool = True,
    ) -> Dict[str, Any]:
        """Compile any undigested feedback items (or all recent if force=True) and email a digest."""
        items = self.list_feedback(undigested_only=not force, limit=50)
        if not items and not force:
            return {"sent": False, "reason": "No new undigested feedback items.", "item_count": 0}

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%B %d, %Y")
        digest_id = str(uuid4())
        summary = self.synthesize_improvement_brief(items, allow_ai=allow_ai)
        mail_res = self.send_email_with_attachments(
            subject=f"[Ligase Co-Scientist] Feedback & Improvement Digest — {date_str} ({len(items)} items)",
            summary=summary,
            items=items,
            heading="Ligase Feedback & Future Improvements Digest",
            subtitle=f"Reporting date: {date_str} · {len(items)} submission(s)",
            to_email=to_email,
        )

        now_iso = now.isoformat()
        for item in items:
            rec = self.get_feedback(item["id"])
            if rec:
                rec["digested"] = True
                rec["digest_sent_at"] = now_iso
                rec["digest_id"] = digest_id
                if not rec.get("emailed"):
                    rec["emailed"] = True
                    rec["emailed_at"] = now_iso
                    rec["email_recipient"] = mail_res.get("recipient")
                self._save_record_in_place(rec)

        digest_rec = {
            "digest_id": digest_id,
            "sent_at": now_iso,
            "recipient": mail_res.get("recipient"),
            "item_count": len(items),
            "item_ids": [i["id"] for i in items],
            "summary": summary,
            "delivery": mail_res,
        }
        (self.digests_dir / f"{now.strftime('%Y-%m-%d')}-{digest_id}.json").write_text(
            json.dumps(digest_rec, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return {
            "sent": True,
            "digest_id": digest_id,
            "item_count": len(items),
            "recipient": mail_res.get("recipient"),
            "summary": summary,
            "sent_at": now_iso,
        }
