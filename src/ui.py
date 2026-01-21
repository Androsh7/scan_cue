"""Defines UI functions"""

# Standard libraries
from collections import deque
from datetime import datetime
from typing import Literal

# Third-party libraries
from attrs import define, field, validators
from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.rule import Rule
from rich.text import Text

# Project libraries
from src.config import LOG_COLOR_DICT, LOG_LEVEL_NUM_DICT, LOG_LEVELS


class LiveLog:
    def __init__(self, max_lines: int = 200):
        self._lines = deque(maxlen=max_lines)
        self._text = Text()

    def write(self, message: str) -> None:
        # Store actual lines only; no separate "\n" entries
        self._lines.append(message)

    def render(self, max_render_lines: int | None = None) -> Text:
        """
        Render only the last `max_render_lines` lines to simulate scrolling.
        If max_render_lines is None, render all buffered lines.
        """
        if max_render_lines is None or max_render_lines <= 0:
            lines = list(self._lines)
        else:
            lines = list(self._lines)[-max_render_lines:]

        self._text.plain = ""
        for line in lines:
            self._text.append(Text.from_markup(line))
            self._text.append("\n")

        return self._text


@define
class ScannerUI:
    log_level: Literal[LOG_LEVELS] = field(
        default="info", validator=validators.and_(validators.in_(LOG_LEVELS), validators.instance_of(str))
    )
    max_log_lines: int = field(default=50, validator=validators.instance_of(int))
    _progress: Progress = field(validator=validators.instance_of(Progress), init=False)
    _progress_task_id: int = field(validator=validators.instance_of(int), init=False)
    _log: LiveLog = field(validator=validators.instance_of(LiveLog), init=False)
    console: Console = field(validator=validators.instance_of(Console), init=False)

    def __attrs_post_init__(self):
        self.console = Console()
        self._progress = Progress(
            TextColumn("[bold]{task.description}[/bold]"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            expand=True,
        )
        self._progress_task_id = self._progress.add_task("Progress bar", total=0, start=True, visible=False)
        self._log = LiveLog(max_lines=self.max_log_lines)

    def log(self, log_level: Literal[LOG_LEVELS], message: str):
        """Writes a log to the queue

        Args:
            log_level: The log level
            message: The message
        """
        if LOG_LEVEL_NUM_DICT[log_level.lower()] < LOG_LEVEL_NUM_DICT[self.log_level]:
            return None
        timestamp = datetime.now().strftime(format=r"%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_color = LOG_COLOR_DICT[log_level.lower()]
        self._log.write(f"[green]{timestamp}[/green] [{log_color}]| {log_level.upper():8} | {message}[/{log_color}]")

    def show_progress_bar(self):
        """Shows the progress bar task"""
        self._progress.update(task_id=self._progress_task_id, visible=True)

    def hide_progress_bar(self):
        """Hides the progress bar task"""
        self._progress.update(task_id=self._progress_task_id, visible=False)

    def update_progress_bar(self, current_progress: float, total_progress: float = 100, description: str = ""):
        """Updates the progress bar

        Args:
            current_progress: The current progress, I.E: X/100
            total_progress: The total progress, I.E: 15/X
            description: The description for the progress bar
        """
        self._progress.update(
            task_id=self._progress_task_id,
            total=total_progress,
            completed=current_progress,
            description=description,
        )

    def advance_progress_bar(self, advance: float = 1):
        """Advances the progress bar"""
        self._progress.advance(task_id=self._progress_task_id, advance=advance)

    def render(self, console: Console):
        term_height = console.size.height
        reserved = 10
        log_height = max(3, term_height - reserved)

        return Group(
            Panel(
                Group(
                    self._progress,
                    Rule(title="[green]LOGS[/green]", characters="#"),
                    self._log.render(max_render_lines=log_height),
                ),
                title="Scan Cue",
                border_style="dim",
            )
        )

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield from self.render(console).__rich_console__(console, options)
