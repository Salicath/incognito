
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


if __name__ == "__main__":
    app()
