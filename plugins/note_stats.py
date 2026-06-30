"""
Note Statistics Plugin for NoteDiscovery

Computes per-note metrics (words, sentences, reading time, links, tasks, …)
returned via /api/plugins/note_stats/calculate and consumed by the frontend
stats panel. On save we also emit a one-line INFO summary for quick
visibility in the server logs.
"""

import logging
import re

logger = logging.getLogger("uvicorn.error")

# Average reading speed used to derive `reading_time_minutes`.
WORDS_PER_MINUTE = 200


class Plugin:
    def __init__(self):
        self.name = "Note Statistics"
        self.version = "1.0.0"
        self.enabled = True

    def calculate_stats(self, content: str) -> dict:
        """Compute the full metric set returned to the frontend / API."""
        words = len(re.findall(r'\S+', content))
        chars = len(re.sub(r'\s', '', content))
        total_chars = len(content)
        reading_time = max(1, round(words / WORDS_PER_MINUTE))
        lines = len(content.split('\n'))
        paragraphs = len([p for p in content.split('\n\n') if p.strip()])
        sentences = len(re.findall(r'[.!?]+(?:\s|$)', content))

        # Bullet/numbered list items, excluding task checkboxes like "- [ ]".
        list_items = len(re.findall(r'^\s*(?:[-*+]|\d+\.)\s+(?!\[)', content, re.MULTILINE))
        # Markdown table separator rows: | --- | :--: |
        tables = len(re.findall(r'^\s*\|(?:\s*:?-+:?\s*\|){1,}\s*$', content, re.MULTILINE))

        markdown_links = len(re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', content))
        markdown_internal_links = len(re.findall(r'\[([^\]]+)\]\(([^\)]+\.md)\)', content))
        wikilinks = len(re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', content))
        links = markdown_links + wikilinks
        internal_links = markdown_internal_links + wikilinks  # wikilinks are always internal

        code_blocks = len(re.findall(r'```[\s\S]*?```', content))
        inline_code = len(re.findall(r'`[^`]+`', content))

        h1_count = len(re.findall(r'^# ', content, re.MULTILINE))
        h2_count = len(re.findall(r'^## ', content, re.MULTILINE))
        h3_count = len(re.findall(r'^### ', content, re.MULTILINE))

        total_tasks = len(re.findall(r'- \[[ x]\]', content))
        completed_tasks = len(re.findall(r'- \[x\]', content, re.IGNORECASE))

        images = len(re.findall(r'!\[([^\]]*)\]\(([^\)]+)\)', content))
        blockquotes = len(re.findall(r'^> ', content, re.MULTILINE))

        return {
            'words': words,
            'sentences': sentences,
            'characters': chars,
            'total_characters': total_chars,
            'reading_time_minutes': reading_time,
            'lines': lines,
            'paragraphs': paragraphs,
            'list_items': list_items,
            'tables': tables,
            'links': links,
            'internal_links': internal_links,
            'external_links': links - internal_links,
            'wikilinks': wikilinks,
            'code_blocks': code_blocks,
            'inline_code': inline_code,
            'headings': {
                'h1': h1_count,
                'h2': h2_count,
                'h3': h3_count,
                'total': h1_count + h2_count + h3_count,
            },
            'tasks': {
                'total': total_tasks,
                'completed': completed_tasks,
                'pending': total_tasks - completed_tasks,
                'completion_rate': round(completed_tasks / total_tasks * 100) if total_tasks else 0,
            },
            'images': images,
            'blockquotes': blockquotes,
        }

    def on_note_save(self, note_path: str, content: str) -> str | None:
        """Emit a one-line summary on save. Doesn't modify content."""
        s = self.calculate_stats(content)
        parts = [
            f"{s['words']:,} words",
            f"{s['sentences']:,} sentences",
            f"~{s['reading_time_minutes']}m read",
            f"{s['lines']:,} lines",
        ]
        if s['list_items']:
            parts.append(f"{s['list_items']:,} lists")
        if s['tables']:
            parts.append(f"{s['tables']:,} tables")
        if s['links']:
            parts.append(f"{s['links']} links ({s['internal_links']} internal)")
        if s['tasks']['total']:
            parts.append(f"{s['tasks']['completed']}/{s['tasks']['total']} tasks")
        logger.info("note_stats %s | %s", note_path, " | ".join(parts))
        return None
