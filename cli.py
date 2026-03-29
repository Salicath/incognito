
import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from backend.core.config import AppConfig

app = typer.Typer(name="incognito", help="Self-hosted GDPR personal data removal tool.")
brokers_app = typer.Typer(help="Manage the broker registry.")
app.add_typer(brokers_app, name="brokers")
console = Console()


def get_config() -> AppConfig:
    return AppConfig()


def _load_broker_registry(config: AppConfig):
    from pathlib import Path

    from backend.core.broker import BrokerRegistry

    brokers_dir = config.brokers_dir
    if not brokers_dir.exists():
        brokers_dir = Path(__file__).parent / "brokers"
    return BrokerRegistry.load(brokers_dir)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    port: int = typer.Option(8080, help="Port to listen on"),
):
    """Start the Incognito web server."""
    from backend.main import create_app

    config = get_config()
    config.data_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold green]Incognito[/] starting on http://{host}:{port}")
    fastapi_app = create_app(config)
    uvicorn.run(fastapi_app, host=host, port=port)


@app.command()
def status():
    """Show request status summary."""
    config = get_config()

    if not config.vault_path.exists():
        console.print(
            "[yellow]Not initialized.[/] Run [bold]incognito serve[/] and complete setup."
        )
        return

    from backend.db.models import Request, RequestStatus
    from backend.db.session import init_db

    session_factory = init_db(config.db_path)
    session = session_factory()

    try:
        all_requests = session.query(Request).all()

        if not all_requests:
            console.print("No requests yet.")
            return

        table = Table(title="Request Status")
        table.add_column("Status", style="bold")
        table.add_column("Count", justify="right")

        for s in RequestStatus:
            count = sum(1 for r in all_requests if r.status == s)
            if count > 0:
                table.add_row(s.value, str(count))

        table.add_row("Total", str(len(all_requests)), style="bold")
        console.print(table)
    finally:
        session.close()


@app.command()
def report():
    """Generate a privacy exposure report with score and grade."""
    config = get_config()

    if not config.vault_path.exists():
        console.print("[yellow]Not initialized.[/]")
        return

    from backend.db.models import Request, ScanResult
    from backend.db.session import init_db

    session_factory = init_db(config.db_path)
    session = session_factory()

    try:
        all_requests = session.query(Request).all()
        scan_results = session.query(ScanResult).all()

        if not all_requests and not scan_results:
            console.print("No data yet. Run a scan and send requests first.")
            return

        # Calculate score
        broker_best: dict[str, str] = {}
        rank = {
            "completed": 6, "acknowledged": 5, "escalated": 4,
            "overdue": 3, "sent": 2, "created": 1,
            "refused": 0, "manual_action_needed": 0,
        }
        for req in all_requests:
            existing = broker_best.get(req.broker_id)
            if existing is None or rank.get(req.status.value, 0) > rank.get(existing, 0):
                broker_best[req.broker_id] = req.status.value

        total = len(broker_best)
        completed = sum(1 for s in broker_best.values() if s == "completed")
        in_progress = sum(
            1 for s in broker_best.values()
            if s in ("acknowledged", "sent", "overdue", "escalated")
        )

        score = min(round((completed * 100 + in_progress * 40) / total), 100) if total > 0 else 0

        if score >= 90:
            grade, color = "A", "green"
        elif score >= 70:
            grade, color = "B", "blue"
        elif score >= 50:
            grade, color = "C", "yellow"
        elif score >= 30:
            grade, color = "D", "dark_orange"
        else:
            grade, color = "F", "red"

        console.print()
        console.print(f"[bold]Privacy Score: [{color}]{grade}[/{color}] ({score}/100)[/]")
        console.print()

        table = Table(title="Summary")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")
        table.add_row("Brokers contacted", str(total))
        table.add_row("Completed", f"[green]{completed}[/]")
        table.add_row("In progress", f"[blue]{in_progress}[/]")
        table.add_row("Exposures found", str(len(scan_results)))
        console.print(table)

        # Show per-status breakdown
        from collections import Counter
        status_counts = Counter(broker_best.values())
        if status_counts:
            console.print()
            table = Table(title="By Status")
            table.add_column("Status", style="bold")
            table.add_column("Count", justify="right")
            for s, c in status_counts.most_common():
                table.add_row(s, str(c))
            console.print(table)
    finally:
        session.close()


@app.command(name="follow-up")
def follow_up(
    auto: bool = typer.Option(
        False, "--auto", help="Automatically send follow-ups and escalations",
    ),
):
    """Check deadlines and send follow-ups for overdue requests."""
    import asyncio

    config = get_config()

    if not config.vault_path.exists():
        console.print("[yellow]Not initialized.[/]")
        return

    from backend.core.profile import ProfileVault
    from backend.core.request import RequestManager
    from backend.db.session import init_db

    session_factory = init_db(config.db_path)
    session = session_factory()

    try:
        mgr = RequestManager(session, config.gdpr_deadline_days)
        overdue = mgr.find_overdue()

        if not overdue and not auto:
            console.print("[green]No overdue requests.[/]")
            return

        if overdue:
            console.print(f"[yellow]{len(overdue)} request(s) past their 30-day deadline.[/]")
            for req in overdue:
                console.print(
                    f"  - {req.broker_id} ({req.request_type.value}) sent {req.sent_at}"
                )

        if auto:
            from pathlib import Path

            from backend.core.scheduler import run_follow_ups
            from backend.core.template import TemplateRenderer

            vault = ProfileVault(config.vault_path)

            import os
            import sys
            password = os.environ.get("INCOGNITO_PASSWORD")
            if not password:
                if sys.stdin.isatty():
                    import getpass
                    password = getpass.getpass("Master password: ")
                else:
                    msg = "Error: INCOGNITO_PASSWORD required for non-interactive use."
                    print(msg, file=sys.stderr)
                    raise typer.Exit(code=1)

            profile, smtp, _ = vault.load(password)

            from backend.core.notifier import init_notifier
            init_notifier(config.notify_url)

            templates_dir = Path(__file__).parent / "templates"
            if not templates_dir.exists():
                templates_dir = config.data_dir / "templates"
            renderer = TemplateRenderer(templates_dir)

            broker_registry = _load_broker_registry(config)

            result = asyncio.run(run_follow_ups(
                session=session,
                profile=profile,
                smtp=smtp,
                broker_registry=broker_registry,
                renderer=renderer,
                gdpr_deadline_days=config.gdpr_deadline_days,
            ))

            if result.newly_overdue:
                console.print(
                    f"[yellow]Marked {result.newly_overdue} request(s) as overdue.[/]"
                )
            if result.follow_ups_sent:
                console.print(
                    f"[blue]Sent {result.follow_ups_sent} follow-up email(s).[/]"
                )
            if result.escalations_sent:
                console.print(
                    f"[red]Sent {result.escalations_sent} escalation warning(s).[/]"
                )
            if result.errors:
                for err in result.errors:
                    console.print(f"[red]Error: {err}[/]")
            no_actions = (
                not result.newly_overdue
                and not result.follow_ups_sent
                and not result.escalations_sent
            )
            if no_actions:
                console.print("[green]Nothing to do.[/]")
        else:
            for req in overdue:
                mgr.mark_overdue(req.id)
            if overdue:
                console.print(
                    f"[yellow]Marked {len(overdue)} as overdue. "
                    "Run with --auto to send follow-ups.[/]"
                )
    finally:
        session.close()


@brokers_app.command("list")
def brokers_list(
    country: str = typer.Option(None, help="Filter by country code (e.g. DE, US)"),
    method: str = typer.Option(None, help="Filter by removal method (email, web_form, api)"),
):
    """List all brokers in the registry."""
    config = get_config()
    registry = _load_broker_registry(config)

    brokers = registry.brokers
    if country:
        brokers = [b for b in brokers if b.country.upper() == country.upper()]
    if method:
        brokers = [b for b in brokers if b.removal_method.value == method]

    table = Table(title=f"Broker Registry ({len(brokers)} brokers)")
    table.add_column("Name", style="bold")
    table.add_column("Domain")
    table.add_column("Country")
    table.add_column("Method")
    table.add_column("DPO Email", style="dim")

    for b in brokers:
        table.add_row(b.name, b.domain, b.country, b.removal_method.value, b.dpo_email)

    console.print(table)


@brokers_app.command("stats")
def brokers_stats():
    """Show broker registry statistics."""
    from collections import Counter

    config = get_config()
    registry = _load_broker_registry(config)

    countries = Counter(b.country for b in registry.brokers)
    methods = Counter(b.removal_method.value for b in registry.brokers)
    categories = Counter(b.category for b in registry.brokers)

    console.print(f"\n[bold]Total brokers:[/] {len(registry.brokers)}\n")

    table = Table(title="By Country")
    table.add_column("Country")
    table.add_column("Count", justify="right")
    for country, count in countries.most_common():
        table.add_row(country, str(count))
    console.print(table)

    table = Table(title="By Removal Method")
    table.add_column("Method")
    table.add_column("Count", justify="right")
    for method_name, count in methods.most_common():
        table.add_row(method_name, str(count))
    console.print(table)

    table = Table(title="By Category")
    table.add_column("Category")
    table.add_column("Count", justify="right")
    for cat, count in categories.most_common():
        table.add_row(cat, str(count))
    console.print(table)


@brokers_app.command("update")
def brokers_update(
    repo: str = typer.Option(
        "Salicath/incognito",
        help="GitHub repo to fetch brokers from (owner/repo)",
    ),
    branch: str = typer.Option("main", help="Git branch to fetch from"),
):
    """Update the broker registry from a remote GitHub repository."""
    import shutil
    import tempfile
    from pathlib import Path

    import httpx

    config = get_config()
    target_dir = config.brokers_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    base_url = f"https://api.github.com/repos/{repo}/contents/brokers"
    params = {"ref": branch}

    console.print(f"[blue]Fetching broker list from {repo}@{branch}...[/]")

    try:
        resp = httpx.get(base_url, params=params, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        console.print(f"[red]Failed to fetch broker list: {e}[/]")
        raise typer.Exit(code=1) from None

    files = resp.json()
    yaml_files = [
        f for f in files
        if isinstance(f, dict)
        and f.get("name", "").endswith(".yaml")
        and f.get("name") != "schema.yaml"
    ]

    if not yaml_files:
        console.print("[yellow]No broker files found in remote repository.[/]")
        return

    # Count existing brokers
    existing = set(p.name for p in target_dir.glob("*.yaml"))
    added = 0
    updated = 0

    with tempfile.TemporaryDirectory() as tmp:
        for file_info in yaml_files:
            name = file_info["name"]
            download_url = file_info.get("download_url")
            if not download_url:
                continue

            try:
                file_resp = httpx.get(download_url, timeout=15)
                file_resp.raise_for_status()
            except httpx.HTTPError:
                console.print(f"  [yellow]Skipped {name} (download failed)[/]")
                continue

            # Validate YAML before saving
            import yaml
            try:
                data = yaml.safe_load(file_resp.text)
                if not isinstance(data, dict) or "name" not in data:
                    continue
            except yaml.YAMLError:
                continue

            tmp_path = Path(tmp) / name
            tmp_path.write_text(file_resp.text)

            dest = target_dir / name
            if name in existing:
                # Only update if content changed
                if dest.read_text() != file_resp.text:
                    shutil.copy2(tmp_path, dest)
                    updated += 1
            else:
                shutil.copy2(tmp_path, dest)
                added += 1

    total = len(list(target_dir.glob("*.yaml")))
    console.print("\n[bold green]Broker registry updated:[/]")
    console.print(f"  {added} new, {updated} updated, {total} total")
    if added > 0:
        console.print(
            "[dim]Restart the server to load new brokers.[/]"
        )


@app.command()
def send(
    dry_run: bool = typer.Option(
        True, help="Preview what would be sent without actually sending",
    ),
    request_type: str = typer.Option(
        "erasure", help="Request type: access or erasure",
    ),
):
    """Create and optionally send GDPR requests to all brokers."""

    config = get_config()

    if not config.vault_path.exists():
        console.print("[yellow]Not initialized.[/]")
        return

    from backend.core.request import RequestManager
    from backend.db.models import Request, RequestStatus, RequestType
    from backend.db.session import init_db

    session_factory = init_db(config.db_path)
    session = session_factory()
    registry = _load_broker_registry(config)

    try:
        rtype = RequestType.ACCESS if request_type == "access" else RequestType.ERASURE
        mgr = RequestManager(session, config.gdpr_deadline_days)

        existing = session.query(Request).filter(
            Request.request_type == rtype,
            Request.status.in_([
                RequestStatus.CREATED, RequestStatus.SENT, RequestStatus.ACKNOWLEDGED,
            ]),
        ).all()
        existing_ids = {r.broker_id for r in existing}

        created = 0
        skipped = 0
        for broker in registry.brokers:
            if broker.id in existing_ids:
                skipped += 1
                continue
            if not dry_run:
                mgr.create(broker.id, rtype)
            created += 1

        action = "Would create" if dry_run else "Created"
        console.print(f"[green]{action} {created} {request_type} requests[/]")
        if skipped:
            console.print(f"[dim]Skipped {skipped} (already have active requests)[/]")
        if dry_run and created > 0:
            console.print("[yellow]Run with --no-dry-run to actually create them.[/]")

        if not dry_run and created > 0:
            pending = session.query(Request).filter(
                Request.status == RequestStatus.CREATED,
            ).count()
            console.print(
                f"\n{pending} requests ready to send. "
                "Use the web UI or configure SMTP to send them."
            )
    finally:
        session.close()


@app.command()
def rescan():
    """Run a scan and check for data that reappeared after removal."""
    import asyncio
    import os
    import sys

    config = get_config()

    if not config.vault_path.exists():
        console.print("[yellow]Not initialized.[/]")
        return

    from backend.core.profile import ProfileVault
    from backend.core.rescan import check_for_reappearances, save_scan_results
    from backend.db.session import init_db
    from backend.scanner.duckduckgo import scan_profile

    password = os.environ.get("INCOGNITO_PASSWORD")
    if not password:
        if sys.stdin.isatty():
            import getpass
            password = getpass.getpass("Master password: ")
        else:
            msg = "Error: INCOGNITO_PASSWORD required for non-interactive use."
            print(msg, file=sys.stderr)
            raise typer.Exit(code=1)

    vault = ProfileVault(config.vault_path)
    profile, _, _ = vault.load(password)

    from backend.core.notifier import init_notifier
    init_notifier(config.notify_url)

    registry = _load_broker_registry(config)

    console.print("[blue]Scanning for your data across broker sites...[/]")
    broker_domains = [(b.domain, b.name) for b in registry.brokers]

    def on_progress(checked, total):
        if checked % 10 == 0 or checked == total:
            console.print(f"  {checked}/{total} searches completed")

    report = asyncio.run(scan_profile(profile, broker_domains, on_progress))
    console.print(
        f"\n[bold]Scan complete:[/] {len(report.hits)} hits "
        f"from {report.checked} searches"
    )

    if not report.hits:
        console.print("[green]No data found in search results.[/]")
        return

    session_factory = init_db(config.db_path)
    db = session_factory()

    try:
        # Save results
        hits = [
            {
                "broker_domain": h.broker_domain,
                "broker_name": h.broker_name,
                "snippet": h.snippet,
                "url": h.url,
            }
            for h in report.hits
        ]
        save_scan_results(db, hits, source="duckduckgo")

        # Check for reappearances
        rescan = check_for_reappearances(db, hits)

        if rescan.reappeared:
            console.print(
                f"\n[bold red]WARNING: {len(rescan.reappeared)} broker(s) "
                "re-listed your data after confirmed deletion![/]"
            )
            for alert in rescan.reappeared:
                console.print(
                    f"  [red]- {alert.broker_name} ({alert.broker_domain})"
                    f" — removed {alert.previous_removal_date}[/]"
                )

        if rescan.new_exposures:
            console.print(
                f"\n[yellow]{len(rescan.new_exposures)} new exposure(s) "
                "not seen in previous scans:[/]"
            )
            for alert in rescan.new_exposures:
                console.print(f"  - {alert.broker_name} ({alert.broker_domain})")
    finally:
        db.close()


@app.command("check-replies")
def check_replies():
    """Check IMAP inbox for broker replies and update request statuses."""
    import asyncio
    import os
    import sys

    config = get_config()

    if not config.vault_path.exists():
        console.print("[yellow]Not initialized.[/]")
        return

    from backend.core.imap import ImapPoller
    from backend.core.profile import ProfileVault
    from backend.db.session import init_db

    password = os.environ.get("INCOGNITO_PASSWORD")
    if not password:
        if sys.stdin.isatty():
            import getpass
            password = getpass.getpass("Master password: ")
        else:
            msg = "Error: INCOGNITO_PASSWORD required for non-interactive use."
            print(msg, file=sys.stderr)
            raise typer.Exit(code=1)

    vault = ProfileVault(config.vault_path)
    _, _, imap = vault.load(password)

    from backend.core.notifier import init_notifier
    init_notifier(config.notify_url)

    if imap is None:
        console.print(
            "[yellow]IMAP not configured. "
            "Add IMAP settings in the web UI first.[/]"
        )
        return

    session_factory = init_db(config.db_path)
    registry = _load_broker_registry(config)
    broker_domains = {b.domain.lower() for b in registry.brokers}

    poller = ImapPoller(
        imap_config=imap,
        db_session_factory=session_factory,
        broker_domains=broker_domains,
    )

    console.print(
        f"[blue]Checking {imap.host}:{imap.port} "
        f"({imap.folder})...[/]"
    )
    processed = asyncio.run(poller.poll_once())

    if poller.last_error:
        console.print(f"[red]Error: {poller.last_error}[/]")
        raise typer.Exit(code=1)

    console.print(
        f"[bold]Done:[/] {processed} emails checked, "
        f"{poller.matched_count} matched, "
        f"{poller.unmatched_count} unmatched"
    )
    if poller.matched_count:
        console.print(
            "[green]Matched replies have been linked to requests "
            "and statuses updated.[/]"
        )


if __name__ == "__main__":
    app()
