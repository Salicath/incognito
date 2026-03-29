
import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from backend.core.config import AppConfig

app = typer.Typer(name="incognito", help="Self-hosted GDPR personal data removal tool.")
console = Console()


def get_config() -> AppConfig:
    return AppConfig()


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
                console.print(f"  - {req.broker_id} ({req.request_type.value}) sent {req.sent_at}")

        if auto:
            from pathlib import Path

            from backend.core.broker import BrokerRegistry
            from backend.core.scheduler import run_follow_ups
            from backend.core.template import TemplateRenderer

            vault = ProfileVault(config.vault_path)

            # Need password from environment or prompt
            import os
            password = os.environ.get("INCOGNITO_PASSWORD", "")
            if not password:
                import getpass
                password = getpass.getpass("Master password: ")

            profile, smtp = vault.load(password)

            templates_dir = Path(__file__).parent / "templates"
            if not templates_dir.exists():
                templates_dir = config.data_dir / "templates"
            renderer = TemplateRenderer(templates_dir)

            brokers_dir = config.brokers_dir
            if not brokers_dir.exists():
                brokers_dir = Path(__file__).parent / "brokers"
            broker_registry = BrokerRegistry.load(brokers_dir)

            result = asyncio.run(run_follow_ups(
                session=session,
                profile=profile,
                smtp=smtp,
                broker_registry=broker_registry,
                renderer=renderer,
                gdpr_deadline_days=config.gdpr_deadline_days,
            ))

            if result.newly_overdue:
                console.print(f"[yellow]Marked {result.newly_overdue} request(s) as overdue.[/]")
            if result.follow_ups_sent:
                console.print(f"[blue]Sent {result.follow_ups_sent} follow-up email(s).[/]")
            if result.escalations_sent:
                console.print(f"[red]Sent {result.escalations_sent} escalation warning(s).[/]")
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
            # Just mark overdue without sending
            for req in overdue:
                mgr.mark_overdue(req.id)
            if overdue:
                console.print(
                    f"[yellow]Marked {len(overdue)} as overdue. "
                    "Run with --auto to send follow-ups.[/]"
                )
    finally:
        session.close()


if __name__ == "__main__":
    app()
