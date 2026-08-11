"""
Open Task Search
Turns the search box into a vault-wide list of unchecked tasks.

Trigger: search for "@task" or "@tasks" (case-insensitive)
Install: cp plugins/contrib/search_open_tasks.py plugins/
Author:  @LuBeDa
Caveats: One result per note, not per task — the sidebar keys results by path,
         so a note shows its first open task there and carries the rest in
         `matches` for API and MCP consumers. Opening a result highlights
         nothing, because "@tasks" is not text that appears in the note.
"""

import logging
import os
import re
from html import escape
from pathlib import Path

logger = logging.getLogger("uvicorn.error")

# Queries that hand the result set over to this plugin. Compared against the
# stripped, lowercased query, so "@Tasks " triggers too.
TRIGGERS = {"@task", "@tasks"}

# Unchecked checkboxes only, on any of the three bullet markers. "- [x]" is a
# finished task and deliberately never matches.
OPEN_TASK_PATTERN = re.compile(r'^[ \t]*[-*+] \[ \]\s+(\S.*?)\s*$', re.MULTILINE)

# A task longer than this is cut for display. Every task still gets its own
# entry — this trims a line, it never drops one.
MAX_TASK_CHARS = 200


class Plugin:
    def __init__(self):
        self.name = "Open Task Search"
        self.version = "1.0.0"
        self.enabled = True
        # Replaced in setup(). The loader always calls it, but a hook that
        # fired first would still see a usable vault path rather than None.
        self.notes_dir = Path(".")

    def setup(self, ctx):
        """Take the vault path from the host, and the per-plugin logger."""
        global logger
        logger = ctx.logger
        self.notes_dir = ctx.notes_dir

    def on_search(self, query: str, results: list) -> list | None:
        """Replace the results with the vault's open tasks, on trigger only.

        Any other query returns None, leaving core search untouched.
        """
        if query.strip().lower() not in TRIGGERS:
            return None

        notes = self._scan_vault()
        # This hook owns the ordering once it returns a list — core's sort is
        # skipped — and pagination needs one that holds still between requests.
        notes.sort(key=lambda note: note['path'].lower())

        total = sum(len(note['matches']) for note in notes)
        logger.info("search_open_tasks '%s' | %d open tasks in %d notes", query, total, len(notes))
        return notes

    def _scan_vault(self) -> list:
        """Every note holding at least one open task, in core's result shape."""
        notes = []

        for root, dirnames, filenames in os.walk(self.notes_dir):
            # Same exclusions as the core vault scan: dot-folders and dotfiles
            # hold app state, not notes.
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            root_path = Path(root)

            for filename in filenames:
                if filename.startswith('.') or not filename.endswith('.md'):
                    continue

                full_path = root_path / filename
                try:
                    content = full_path.read_text(encoding='utf-8')
                except Exception:
                    # An unreadable note skips itself rather than failing the
                    # whole search, the way core's own scan does.
                    continue

                matches = self._open_tasks(content)
                if not matches:
                    continue

                relative_path = full_path.relative_to(self.notes_dir)
                notes.append({
                    "name": full_path.stem,
                    "path": relative_path.as_posix(),
                    "folder": relative_path.parent.as_posix() if str(relative_path.parent) != "." else "",
                    "matches": matches,
                })

        return notes

    def _open_tasks(self, content: str) -> list:
        """One match entry per unchecked task, ordered as they appear."""
        matches = []

        for match in OPEN_TASK_PATTERN.finditer(content):
            text = match.group(1)
            if len(text) > MAX_TASK_CHARS:
                text = text[:MAX_TASK_CHARS].rstrip() + '…'

            matches.append({
                "line_number": content.count('\n', 0, match.start()) + 1,
                # Escaped before the mark goes on, so a task containing markup
                # renders as the text someone typed.
                "context": f'☐ <mark class="search-highlight">{escape(text)}</mark>',
            })

        return matches
