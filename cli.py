from pathlib import Path

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
        console.print("[yellow]Not initialized.[/] Run [bold]incognito serve[/] and complete setup.")
        return

    from backend.db.session import init_db
    from backend.db.models import Request, RequestStatus

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
    auto: bool = typer.Option(False, "--auto", help="Automatically send follow-ups"),
):
    """Check deadlines and send follow-ups for overdue requests."""
    config = get_config()

    if not config.vault_path.exists():
        console.print("[yellow]Not initialized.[/]")
        return

    from backend.db.session import init_db
    from backend.core.request import RequestManager

    session_factory = init_db(config.db_path)
    session = session_factory()

    try:
        mgr = RequestManager(session, config.gdpr_deadline_days)
        overdue = mgr.find_overdue()

        if not overdue:
            console.print("[green]No overdue requests.[/]")
            return

        console.print(f"[yellow]{len(overdue)} overdue request(s) found.[/]")
        for req in overdue:
            console.print(f"  - {req.broker_id} ({req.request_type.value}) sent {req.sent_at}")
            if auto:
                mgr.mark_overdue(req.id)
                console.print(f"    [yellow]Marked as overdue[/]")
    finally:
        session.close()


if __name__ == "__main__":
    app()
