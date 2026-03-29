import logging

from fastapi import APIRouter, Cookie, HTTPException
from fastapi import Request as FastAPIRequest
from pydantic import BaseModel

from backend.api.deps import SessionStore
from backend.core.broker import BrokerRegistry
from backend.core.config import AppConfig
from backend.core.profile import ImapConfig, Profile, ProfileVault, SmtpConfig

log = logging.getLogger("incognito.settings")


def create_settings_router(
    vault: ProfileVault,
    session_store: SessionStore,
    broker_registry: BrokerRegistry,
    config: AppConfig,
) -> APIRouter:
    r = APIRouter(prefix="/api/settings", tags=["settings"])

    class UpdateProfileRequest(BaseModel):
        profile: Profile

    class UpdateSmtpRequest(BaseModel):
        smtp: SmtpConfig

    @r.get("/info")
    def get_info(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        from pathlib import Path

        from backend.core.dpa import DPA_REGISTRY

        templates_dir = Path(__file__).parent.parent.parent / "templates" / "locales"
        locale_count = len(list(templates_dir.iterdir())) + 1 if templates_dir.exists() else 1

        return {
            "broker_count": len(broker_registry.brokers),
            "dpa_count": len(DPA_REGISTRY),
            "locale_count": locale_count,
            "data_dir": str(config.data_dir),
            "version": "0.3.0",
            "notifications": bool(config.notify_url),
        }

    @r.get("/smtp")
    def get_smtp_status(session: str | None = Cookie(default=None)):
        key, _salt = session_store.validate(session)
        _, smtp, _ = vault.load_with_key(key)
        if smtp is None:
            return {"configured": False}
        return {
            "configured": True,
            "host": smtp.host,
            "port": smtp.port,
            "username": smtp.username,
            # Don't return the password
        }

    @r.post("/smtp")
    def update_smtp(body: UpdateSmtpRequest, session: str | None = Cookie(default=None)):
        key, salt = session_store.validate(session)
        profile, _, imap = vault.load_with_key(key)
        vault.save_with_key(profile, body.smtp, imap, key, salt)
        return {"status": "updated"}

    @r.post("/profile")
    def update_profile(body: UpdateProfileRequest, session: str | None = Cookie(default=None)):
        key, salt = session_store.validate(session)
        _, smtp, imap = vault.load_with_key(key)
        vault.save_with_key(body.profile, smtp, imap, key, salt)
        return {"status": "updated"}

    @r.get("/hibp")
    def get_hibp_status(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        key_path = config.data_dir / "hibp_key.txt"
        if key_path.exists():
            key = key_path.read_text().strip()
            preview = key[:4] + "..." + key[-4:] if len(key) > 8 else "***"
            return {"configured": True, "key_preview": preview}
        return {"configured": False}

    @r.post("/hibp")
    def update_hibp_key(body: dict, session: str | None = Cookie(default=None)):
        session_store.validate(session)
        key = body.get("api_key", "").strip()
        if not key:
            raise HTTPException(status_code=400, detail="API key required")
        import os
        key_path = config.data_dir / "hibp_key.txt"
        key_path.write_text(key)
        os.chmod(key_path, 0o600)
        return {"status": "saved"}

    @r.delete("/hibp")
    def delete_hibp_key(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        key_path = config.data_dir / "hibp_key.txt"
        if key_path.exists():
            key_path.unlink()
        return {"status": "deleted"}

    @r.post("/test-smtp")
    async def test_smtp(session: str | None = Cookie(default=None)):
        key, _salt = session_store.validate(session)
        _, smtp, _ = vault.load_with_key(key)
        if smtp is None:
            raise HTTPException(status_code=400, detail="SMTP not configured")

        from backend.senders.email import EmailSender
        sender = EmailSender(smtp)
        test_body = (
            "Subject: Incognito SMTP Test\n\n"
            "This is a test email from Incognito. "
            "If you received this, your SMTP configuration is working correctly."
        )
        result = await sender.send(
            to_email=smtp.username,
            rendered_text=test_body,
        )
        if result.status.value == "success":
            return {"status": "success", "message": f"Test email sent to {smtp.username}"}
        else:
            log.error("SMTP test failed: %s", result.message)
            raise HTTPException(
                status_code=400,
                detail="SMTP test failed. Check your server, port, and credentials.",
            )

    class UpdateImapRequest(BaseModel):
        imap: ImapConfig

    @r.get("/imap")
    def get_imap_status(session: str | None = Cookie(default=None)):
        key, _salt = session_store.validate(session)
        _, _, imap = vault.load_with_key(key)
        if imap is None:
            return {"configured": False}
        return {
            "configured": True,
            "host": imap.host,
            "port": imap.port,
            "username": imap.username,
            "folder": imap.folder,
            "poll_interval_minutes": imap.poll_interval_minutes,
            "starttls": imap.starttls,
            # Don't return the password
        }

    @r.post("/imap")
    async def update_imap(
        body: UpdateImapRequest, request: FastAPIRequest,
        session: str | None = Cookie(default=None),
    ):
        key, salt = session_store.validate(session)
        profile, smtp, _ = vault.load_with_key(key)
        vault.save_with_key(profile, smtp, body.imap, key, salt)

        # Start/restart the poller
        from backend.core.imap import ImapPoller

        old_poller = getattr(request.app.state, "imap_poller", None)
        if old_poller:
            old_poller.stop()

        broker_domains = getattr(request.app.state, "broker_domains", set())
        db_factory = getattr(request.app.state, "db_session_factory", None)
        if db_factory:
            poller = ImapPoller(body.imap, db_factory, broker_domains)
            request.app.state.imap_poller = poller
            poller.start()

        return {"status": "updated"}

    @r.delete("/imap")
    async def delete_imap(request: FastAPIRequest, session: str | None = Cookie(default=None)):
        key, salt = session_store.validate(session)
        profile, smtp, _ = vault.load_with_key(key)
        vault.save_with_key(profile, smtp, None, key, salt)

        # Stop the poller
        old_poller = getattr(request.app.state, "imap_poller", None)
        if old_poller:
            old_poller.stop()
        request.app.state.imap_poller = None

        return {"status": "deleted"}

    @r.post("/imap/test")
    async def test_imap(session: str | None = Cookie(default=None)):
        key, _salt = session_store.validate(session)
        _, _, imap = vault.load_with_key(key)
        if imap is None:
            raise HTTPException(status_code=400, detail="IMAP not configured")

        import ssl as ssl_mod
        try:
            from imap_tools import MailBox, MailBoxStartTls

            ssl_ctx = ssl_mod.create_default_context()
            if imap.host in ("127.0.0.1", "localhost", "::1"):
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl_mod.CERT_NONE

            if imap.starttls:
                mb = MailBoxStartTls(host=imap.host, port=imap.port, ssl_context=ssl_ctx)
            else:
                mb = MailBox(host=imap.host, port=imap.port, ssl_context=ssl_ctx)

            with mb.login(imap.username, imap.password, imap.folder) as mailbox:
                folders = [f.name for f in mailbox.folder.list()]
            return {"status": "success", "folders": folders}
        except Exception as exc:
            log.error("IMAP test failed: %s", exc)
            raise HTTPException(
                status_code=400,
                detail="IMAP connection failed. Check your server, port, and credentials.",
            ) from None

    @r.get("/imap/status")
    def get_imap_poller_status(request: FastAPIRequest, session: str | None = Cookie(default=None)):
        session_store.validate(session)
        poller = getattr(request.app.state, "imap_poller", None)
        if poller is None:
            return {
                "enabled": False,
                "last_check": None,
                "matched_count": 0,
                "unmatched_count": 0,
                "poll_interval_minutes": None,
            }
        return {
            "enabled": True,
            "last_check": poller.last_check.isoformat() if poller.last_check else None,
            "last_error": poller.last_error,
            "matched_count": poller.matched_count,
            "unmatched_count": poller.unmatched_count,
            "poll_interval_minutes": poller._config.poll_interval_minutes,
        }

    @r.get("/notifications")
    def get_notification_status(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        return {
            "configured": bool(config.notify_url),
            "url": config.notify_url if config.notify_url else None,
        }

    @r.post("/notifications/test")
    def test_notification(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        if not config.notify_url:
            raise HTTPException(
                status_code=400,
                detail="Notifications not configured. "
                "Set INCOGNITO_NOTIFY_URL environment variable.",
            )
        from backend.core.notifier import EventType, notify
        notify(
            EventType.BLAST_COMPLETE,
            "Incognito test notification",
            "If you see this, notifications are working correctly.",
        )
        return {"status": "sent"}

    @r.post("/import-csv")
    def import_csv(body: dict, session: str | None = Cookie(default=None)):
        """Import request history from CSV (e.g. exported from commercial tools)."""
        session_store.validate(session)

        import csv
        import io
        import uuid
        from datetime import UTC, datetime

        from backend.db.models import Request, RequestStatus, RequestType

        csv_text = body.get("csv", "")
        if not csv_text:
            raise HTTPException(status_code=400, detail="CSV data required")
        if len(csv_text) > 1_000_000:  # 1MB limit
            raise HTTPException(status_code=400, detail="CSV too large (max 1MB)")

        db_session = None
        try:
            from backend.db.session import init_db
            db_factory = init_db(config.db_path)
            db_session = db_factory()

            reader = csv.DictReader(io.StringIO(csv_text))
            imported = 0
            skipped = 0
            errors = []

            for row in reader:
                broker_name = row.get("broker") or row.get("broker_name") or row.get("name", "")
                status_str = (
                    row.get("status", "completed").lower().strip()
                )
                date_str = row.get("date") or row.get("date_requested") or row.get("sent_at", "")

                if not broker_name:
                    skipped += 1
                    continue

                # Find broker by name
                broker = None
                name_lower = broker_name.lower()
                for b in broker_registry.brokers:
                    if b.name.lower() == name_lower or b.domain.lower() == name_lower:
                        broker = b
                        break

                if broker is None:
                    errors.append(f"Broker not found: {broker_name}")
                    skipped += 1
                    continue

                # Map status
                status_map = {
                    "completed": RequestStatus.COMPLETED,
                    "removed": RequestStatus.COMPLETED,
                    "done": RequestStatus.COMPLETED,
                    "sent": RequestStatus.SENT,
                    "pending": RequestStatus.SENT,
                    "in progress": RequestStatus.SENT,
                    "in_progress": RequestStatus.SENT,
                    "acknowledged": RequestStatus.ACKNOWLEDGED,
                    "responded": RequestStatus.ACKNOWLEDGED,
                    "refused": RequestStatus.REFUSED,
                    "denied": RequestStatus.REFUSED,
                }
                req_status = status_map.get(status_str, RequestStatus.COMPLETED)

                # Check for existing request
                existing = (
                    db_session.query(Request)
                    .filter_by(broker_id=broker.id, request_type=RequestType.ERASURE)
                    .filter(Request.status.in_([
                        RequestStatus.SENT, RequestStatus.ACKNOWLEDGED,
                        RequestStatus.COMPLETED,
                    ]))
                    .first()
                )
                if existing:
                    skipped += 1
                    continue

                # Parse date
                sent_at = None
                if date_str:
                    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
                        try:
                            sent_at = datetime.strptime(date_str, fmt).replace(tzinfo=UTC)
                            break
                        except ValueError:
                            continue

                req = Request(
                    id=str(uuid.uuid4()),
                    broker_id=broker.id,
                    request_type=RequestType.ERASURE,
                    status=req_status,
                    sent_at=sent_at or datetime.now(UTC),
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                db_session.add(req)
                imported += 1

            db_session.commit()
            return {
                "imported": imported,
                "skipped": skipped,
                "errors": errors[:20],
            }
        except Exception as e:
            if db_session:
                db_session.rollback()
            log.error("CSV import failed: %s", e)
            raise HTTPException(
                status_code=400, detail="CSV import failed. Check file format.",
            ) from None
        finally:
            if db_session:
                db_session.close()

    class BackupRequest(BaseModel):
        password: str

    @r.post("/backup/export")
    def export_backup(body: BackupRequest, session: str | None = Cookie(default=None)):
        """Export encrypted backup of all data. Requires password confirmation."""
        import base64
        import json

        session_store.validate(session)

        # Verify password before allowing export
        try:
            vault.load(body.password)
        except Exception:
            raise HTTPException(
                status_code=401, detail="Password required to export backup",
            ) from None

        # Read the encrypted vault file
        vault_bytes = config.vault_path.read_bytes() if config.vault_path.exists() else b""

        # Read the database
        db_path = config.db_path
        db_bytes = db_path.read_bytes() if db_path.exists() else b""

        # Read HIBP key if exists
        hibp_key = ""
        hibp_path = config.data_dir / "hibp_key.txt"
        if hibp_path.exists():
            hibp_key = hibp_path.read_text().strip()

        backup = {
            "version": "0.3.0",
            "vault": base64.b64encode(vault_bytes).decode("ascii"),
            "database": base64.b64encode(db_bytes).decode("ascii"),
            "hibp_key": hibp_key,
        }

        log.info("Backup exported")
        from fastapi.responses import Response
        return Response(
            content=json.dumps(backup),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=incognito-backup.json"},
        )

    @r.post("/backup/import")
    async def import_backup(body: dict, session: str | None = Cookie(default=None)):
        """Import a backup file. Requires password confirmation."""
        import base64

        session_store.validate(session)

        # Verify password before allowing destructive import
        confirm_password = body.get("password", "")
        if not confirm_password:
            raise HTTPException(
                status_code=400, detail="Password required to import backup",
            )
        try:
            vault.load(confirm_password)
        except Exception:
            raise HTTPException(
                status_code=401, detail="Wrong password",
            ) from None

        version = body.get("version")
        if not version or not isinstance(version, str):
            raise HTTPException(status_code=400, detail="Invalid backup file")
        if not version.startswith("0."):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported backup version: {version}",
            )

        vault_b64 = body.get("vault", "")
        db_b64 = body.get("database", "")
        hibp_key = body.get("hibp_key", "")

        if vault_b64:
            vault_bytes = base64.b64decode(vault_b64)
            config.vault_path.write_bytes(vault_bytes)

        if db_b64:
            db_bytes = base64.b64decode(db_b64)
            config.db_path.write_bytes(db_bytes)

        if hibp_key:
            (config.data_dir / "hibp_key.txt").write_text(hibp_key)

        log.warning("Backup imported — application data overwritten")
        return {"status": "imported", "message": "Backup restored. Please restart the application."}

    return r
