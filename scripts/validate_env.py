# @module: ENV_VALIDATION
# @deps: None
# @status: INITIALIZED
# @last_update: 2026-04-06
# @summary: Sanity check do ambiente Aevra - importa todas as libs core e valida disponibilidade

import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.align import Align

console = Console()

REQUIRED_LIBS = {
    "pydantic": "Schema Validation / Data Sovereign (Phi2)",
    "numpy": "Matrix Computation / Signal Engine (Phi4)",
    "ccxt": "Exchange Connector / Multi-Exchange (Phi1)",
    "pandas": "Data Structuring / Feature Pipeline (Phi2)",
    "sklearn": "Clustering / Regression / Feature Selection (Phi3)",
    "pytest": "Institutional Testing / Unit Framework (Phi6)",
    "hypothesis": "Property-Based Testing / Edge Discovery (Phi6)",
    "httpx": "Async HTTP / API Client (Phi1)",
    "rich": "Terminal UI / Rich Logging (Phi9)",
    "yaml": "State Serialization / Config (Infra)",
    "coincurve": "Crypto Primitives / Secure Comms (ZeroTrust)",
    "aiohttp": "Async I/O / WebSocket Handler (Phi1)",
    "cryptography": "Encryption / Credential Protection (ZeroTrust)",
}


def validate_environment():
    table = Table(title="[bold blue]AEVRA ENVIRONMENT GATE: LIB INTEGRATION CHECK")
    table.add_column("Library", style="cyan", width=18)
    table.add_column("Version", style="green", width=15)
    table.add_column("Status", style="bold", width=10)
    table.add_column("Purpose", style="magenta")

    results = []
    all_pass = True

    for lib, purpose in REQUIRED_LIBS.items():
        try:
            module = __import__(lib)
            version = getattr(module, "__version__", getattr(module, "VERSION", "N/A"))
            if isinstance(version, tuple):
                version = ".".join(str(v) for v in version)
            table.add_row(lib, version, "[green]PASS[/green]", purpose)
            results.append(True)
        except ImportError as e:
            table.add_row(lib, "MISSING", "[red]FAIL[/red]", f"[red]{e}[/red]")
            results.append(False)
            all_pass = False

    console.print(table)
    console.print("")

    if all_pass:
        console.print(
            Panel(
                Align.center(
                    "[bold green]" + "="*50 + "\n"
                    "[bold green][green][bold][green] AEVRA ENVIRONMENT: SOVEREIGN & ONLINE [/][bold green]\n"
                    f"[bold cyan]Python:  {sys.version}[/]\n"
                    f"[bold cyan]Passed:  {sum(results)}/{len(results)} libs[/]\n"
                    f"[bold cyan]Failed:  {len(results) - sum(results)}/{len(results)} libs[/]\n"
                    "[bold green]" + "="*50
                ),
                title="[bold white]INTEGRITY CONFIRMED",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                Align.center(
                    f"[bold red]AEVRA ENVIRONMENT: DEGRADED\n"
                    f"Failed: {len(results) - sum(results)}/{len(results)}[/]"
                ),
                title="[bold red]GATE FAILURE",
                border_style="red",
            )
        )

    return all_pass


if __name__ == "__main__":
    success = validate_environment()
    sys.exit(0 if success else 1)
