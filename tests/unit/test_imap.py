from backend.core.profile import ImapConfig, Profile, ProfileVault, SmtpConfig


def test_imap_config_defaults():
    cfg = ImapConfig(host="imap.example.com", username="user@example.com", password="secret")
    assert cfg.port == 993
    assert cfg.folder == "INBOX"
    assert cfg.poll_interval_minutes == 5
    assert cfg.starttls is False


def test_imap_config_proton_bridge():
    cfg = ImapConfig(
        host="127.0.0.1",
        port=1143,
        username="user@proton.me",
        password="bridge-password",
        folder="INBOX",
        poll_interval_minutes=10,
        starttls=True,
    )
    assert cfg.port == 1143
    assert cfg.starttls is True


def test_vault_roundtrip_with_imap(tmp_path):
    vault = ProfileVault(tmp_path / "profile.enc")
    profile = Profile(full_name="Test", emails=["t@example.com"])
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="u", password="p")
    imap = ImapConfig(host="imap.test.com", username="u", password="p")

    vault.save(profile, smtp=smtp, imap=imap, password="pw")
    loaded_profile, loaded_smtp, loaded_imap = vault.load("pw")

    assert loaded_profile.full_name == "Test"
    assert loaded_smtp is not None
    assert loaded_smtp.host == "smtp.test.com"
    assert loaded_imap is not None
    assert loaded_imap.host == "imap.test.com"
    assert loaded_imap.port == 993


def test_vault_roundtrip_without_imap(tmp_path):
    vault = ProfileVault(tmp_path / "profile.enc")
    profile = Profile(full_name="Test", emails=["t@example.com"])
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="u", password="p")

    vault.save(profile, smtp=smtp, password="pw")
    loaded_profile, loaded_smtp, loaded_imap = vault.load("pw")

    assert loaded_profile.full_name == "Test"
    assert loaded_smtp is not None
    assert loaded_imap is None


from backend.db.models import EmailDirection, EmailMessage, Request, RequestStatus, RequestType
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from backend.db.models import Base


def test_email_message_model():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    req = Request(
        id="test-req-001",
        broker_id="example-com",
        request_type=RequestType.ERASURE,
        status=RequestStatus.SENT,
        message_id="<test-req-001@incognito.local>",
    )
    db.add(req)
    db.commit()

    email = EmailMessage(
        request_id="test-req-001",
        message_id="<reply-001@broker.com>",
        in_reply_to="<test-req-001@incognito.local>",
        direction=EmailDirection.INBOUND,
        from_address="dpo@broker.com",
        to_address="user@proton.me",
        subject="Re: Data Erasure Request [REF-TEST0001]",
        body_text="Your data has been deleted.",
    )
    db.add(email)
    db.commit()

    loaded = db.query(EmailMessage).filter_by(request_id="test-req-001").first()
    assert loaded is not None
    assert loaded.direction == EmailDirection.INBOUND
    assert loaded.from_address == "dpo@broker.com"
    assert loaded.in_reply_to == "<test-req-001@incognito.local>"

    loaded_req = db.get(Request, "test-req-001")
    assert loaded_req.message_id == "<test-req-001@incognito.local>"
    assert loaded_req.reply_read_at is None

    db.close()


def test_email_sender_sets_message_id_and_ref():
    """Verify the EmailMessage object has Message-ID and [REF-...] in subject."""
    from backend.core.profile import SmtpConfig
    from backend.senders.email import EmailSender

    smtp_config = SmtpConfig(
        host="smtp.test.com", port=587, username="user@test.com", password="pw",
    )
    sender = EmailSender(smtp_config)

    request_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    rendered = "Subject: Data Erasure Request pursuant to Article 17 GDPR\n\nPlease delete my data."

    msg = sender.build_message(
        to_email="dpo@broker.com",
        rendered_text=rendered,
        request_id=request_id,
    )

    assert msg["Message-ID"] == f"<{request_id}@incognito.local>"
    assert "[REF-A1B2C3D4]" in msg["Subject"]
    assert msg["To"] == "dpo@broker.com"
    assert msg["From"] == "user@test.com"


from backend.core.imap import match_reply, MatchResult, MatchTier


def test_match_by_message_id_threading():
    """Tier 1: In-Reply-To matches a stored outbound Message-ID."""
    outbound_ids = {"<req-001@incognito.local>": "req-001"}
    result = match_reply(
        in_reply_to="<req-001@incognito.local>",
        references="",
        subject="Re: Data Erasure Request [REF-REQ00001]",
        from_address="dpo@broker.com",
        outbound_message_ids=outbound_ids,
        broker_domains={"broker.com"},
    )
    assert result is not None
    assert result.request_id == "req-001"
    assert result.tier == MatchTier.MESSAGE_ID


def test_match_by_references_header():
    """Tier 1: References header contains a stored outbound Message-ID."""
    outbound_ids = {"<req-002@incognito.local>": "req-002"}
    result = match_reply(
        in_reply_to="<some-other-id@broker.com>",
        references="<some-other-id@broker.com> <req-002@incognito.local>",
        subject="Re: Something",
        from_address="dpo@broker.com",
        outbound_message_ids=outbound_ids,
        broker_domains={"broker.com"},
    )
    assert result is not None
    assert result.request_id == "req-002"
    assert result.tier == MatchTier.MESSAGE_ID


def test_match_by_subject_ref_code():
    """Tier 2: Subject contains [REF-XXXXXXXX] and sender domain matches a broker."""
    ref_code_map = {"A1B2C3D4": "req-003"}
    result = match_reply(
        in_reply_to="",
        references="",
        subject="Re: Data Erasure Request [REF-A1B2C3D4]",
        from_address="privacy@databroker.eu",
        outbound_message_ids={},
        broker_domains={"databroker.eu"},
        ref_code_map=ref_code_map,
    )
    assert result is not None
    assert result.request_id == "req-003"
    assert result.tier == MatchTier.REFERENCE_CODE


def test_match_by_subject_ref_code_wrong_domain():
    """Tier 2: Subject matches but sender domain is not a known broker — no match."""
    ref_code_map = {"A1B2C3D4": "req-003"}
    result = match_reply(
        in_reply_to="",
        references="",
        subject="Re: Data Erasure Request [REF-A1B2C3D4]",
        from_address="random@unknown.com",
        outbound_message_ids={},
        broker_domains={"databroker.eu"},
        ref_code_map=ref_code_map,
    )
    assert result is None


def test_match_by_sender_domain():
    """Tier 3: Sender domain matches a broker with active request — low confidence."""
    domain_request_map = {"broker.com": "req-004"}
    result = match_reply(
        in_reply_to="",
        references="",
        subject="Your privacy request",
        from_address="noreply@broker.com",
        outbound_message_ids={},
        broker_domains={"broker.com"},
        domain_request_map=domain_request_map,
    )
    assert result is not None
    assert result.request_id == "req-004"
    assert result.tier == MatchTier.DOMAIN_ONLY


def test_no_match():
    """No matching strategy succeeds — returns None."""
    result = match_reply(
        in_reply_to="",
        references="",
        subject="Unrelated email",
        from_address="someone@random.com",
        outbound_message_ids={},
        broker_domains=set(),
    )
    assert result is None
