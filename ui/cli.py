"""
ui/cli.py
Rich terminal interface for the Bank AI Agent.

Run:  python -m ui.cli
"""

import asyncio
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.spinner import Spinner
from rich.live import Live
from rich.text import Text
from rich import box

from agent.agent import BankAgent

console = Console()

BANNER = """
[bold cyan]╔══════════════════════════════════════════════════════╗[/]
[bold cyan]║[/]  [bold white]🏦  BANK AI AGENT[/]  [dim]│  Amazon Bedrock + MySQL MCP[/]  [bold cyan]║[/]
[bold cyan]╚══════════════════════════════════════════════════════╝[/]
"""

HELP_TEXT = """
[bold yellow]Commands:[/]
  [cyan]/reset[/]    — Clear conversation history
  [cyan]/stats[/]    — Quick portfolio stats
  [cyan]/pending[/]  — Show pending loan applications
  [cyan]/help[/]     — Show this help
  [cyan]/quit[/]     — Exit

[bold yellow]Example questions:[/]
  • Show me all under-review loan applications
  • What is the credit profile of customer CUST0013?
  • Approve loan LOAN-2024-0005 with amount 500000 at 11.5%
  • Give me a portfolio risk summary
  • Which customers have a credit score above 750?
  • Show loans rejected this year and the reasons
"""

QUICK_COMMANDS = {
    "/stats":   "Call get_portfolio_stats and give me a concise summary with key metrics.",
    "/pending": "Show all loan applications with status 'pending' in a table format.",
}


async def stream_response(agent: BankAgent, user_input: str):
    """Send user input to agent and stream the response with a spinner."""
    chunks: list[str] = []

    with Live(Spinner("dots", text="[dim]BankBot is thinking…[/dim]"), console=console, refresh_per_second=10):
        async def collect(chunk: str):
            chunks.append(chunk)

        response = await agent.chat(user_input, on_token=collect)

    # Render final markdown response
    console.print()
    console.print(
        Panel(
            Markdown(response),
            title="[bold green]🤖 BankBot[/]",
            border_style="green",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    return response


async def main():
    console.print(BANNER)
    console.print(
        "[dim]Type your question, a command (/help), or /quit to exit.[/dim]\n"
    )

    async with BankAgent() as agent:
        console.print("[bold green]✓ Connected to MCP server and database[/bold green]\n")

        while True:
            try:
                user_input = Prompt.ask("[bold blue]You[/bold blue]").strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Goodbye![/dim]")
                break

            if not user_input:
                continue

            # ── Built-in commands ──
            if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
                console.print("[dim]Goodbye![/dim]")
                break

            if user_input.lower() == "/help":
                console.print(Panel(HELP_TEXT, title="Help", border_style="yellow"))
                continue

            if user_input.lower() == "/reset":
                await agent.reset()
                console.print("[yellow]✓ Conversation reset.[/yellow]\n")
                continue

            # Expand quick commands
            prompt = QUICK_COMMANDS.get(user_input.lower(), user_input)

            console.print(Rule(style="dim"))
            await stream_response(agent, prompt)
            console.print()


if __name__ == "__main__":
    asyncio.run(main())
