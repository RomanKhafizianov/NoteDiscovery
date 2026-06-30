"""
NoteIndex — unified in-memory index of everything that's expensive to recompute
from disk: links, tags, full-text search, and per-note metadata.

  +---------------------------------------------------------------+
  |  ONE module, ONE singleton, ONE lock, ONE rollback switch.    |
  |  All call sites in utils.py / main.py are one-line shims.     |
  +---------------------------------------------------------------+

Why this exists
---------------
Without an index, every backlink lookup, every graph render, and every text
search re-walks the entire vault and re-reads every file. That's O(N) per
request and scales linearly with vault size — 4-second note loads on a 10K
vault, 5-10s graph renders, multi-second searches. With an index, those
endpoints become O(matches) — milliseconds regardless of vault size.

What's indexed
--------------
  * Note metadata     (path -> name, folder, mtime, size, type, tags)
  * Folders           (set of folder paths)
  * Tags forward      (path -> sorted tags)
  * Tags backward     (tag  -> set of paths)
  * Links forward     (source_path -> {target_path: "wikilink"|"markdown"})
  * Links backward    (target_path -> set of source paths)         strict
  * Wikilink tokens   (lowercased token -> set of source paths)    loose
  * Search inverted   (lowercased term  -> set of paths)

What's NOT cached
-----------------
File content. Reading file content for line-level context (backlinks, search
snippets) is done only for the small set of matched files, never for the
whole vault.

Threading model
---------------
Everything mutating goes through one RLock. Reads return snapshot copies, so
callers can iterate freely after they release the lock. The index is
designed to be called from FastAPI request handlers concurrently.

Lifetime
--------
Process-memory only. No persistence to disk — keeping the app lightweight
matters more than the ~500ms saved on cold restart for a 10K-note vault.
The index rebuilds on the first `/api/notes` request after every restart
(typically 1-3 seconds, dominated by reading every file once for tag/link
extraction). F5 / browser reload doesn't touch this — only Python process
restart does.

Rollback switch
---------------
USE_NOTE_INDEX (below) is the single, global on/off. Flip it to False and
every facade function becomes a no-op or returns None, and every call site
in utils.py / main.py falls through to the legacy file-scanning behavior.

  ROLLBACK RECIPE (decide the index isn't worth it)
  -------------------------------------------------
    Set USE_NOTE_INDEX = False below. That's it. Every try_* facade returns
    None, every on_* facade becomes a no-op, callers fall through to the
    legacy file-scanning paths that are preserved as the function bodies.

  COMMIT RECIPE (you're happy, drop the legacy paths)
  ---------------------------------------------------
    1. Here: delete USE_NOTE_INDEX and inline `if not USE_NOTE_INDEX` to True
       in every try_/on_ facade.
    2. In backend/utils.py:
         - get_backlinks: drop the `candidates is None` branch — the
           index always provides them.
         - search_notes: drop the `candidates is None` fallback.
         - get_all_tags / get_notes_by_tag: drop the legacy aggregation
           tail block.
    3. In backend/main.py:
         - /api/graph: drop the legacy fallback block at the bottom of
           the endpoint, keep only `try_graph_data`.
"""

from __future__ import annotations

import os
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


# ============================================================================
# Configuration
# ============================================================================

# Single global rollback switch. Flip to False to disable the index and every
# call site in utils.py / main.py falls back to the legacy code paths.
USE_NOTE_INDEX: bool = True

# Parallelism cutoff for full rescans. Below this many markdown files, threads
# add more overhead than they save (small vaults stay sequential).
_PARALLEL_CUTOFF = 50
_PARALLEL_WORKERS = min(8, (os.cpu_count() or 4))

# Search tokenization. Lowercase, split on anything that's not a word char.
# Min length 2 keeps single-letter noise out of the index without losing
# common short queries like "go", "ai".
_SEARCH_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]{2,}")
_SEARCH_MIN_QUERY_LEN = 2


# ============================================================================
# Shared regexes (same as legacy get_backlinks / /api/graph). Kept here so the
# index and the legacy paths are guaranteed to extract the same tokens.
# ============================================================================

WIKILINK_RE = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
MDLINK_RE = re.compile(r'\[([^\]]+)\]\((?!https?://|mailto:|#|data:)([^\)]+)\)')


# ============================================================================
# Public extraction helpers — used by the index AND by lifecycle hooks in
# utils.py (so a single save can update the index without re-reading the file).
# ============================================================================

def extract_links_from_content(content: str) -> Dict[str, List[str]]:
    """Pull raw wikilink targets and markdown-link paths out of note content."""
    wikilinks = [m.strip() for m in WIKILINK_RE.findall(content)]
    mdlinks = [link_path for _, link_path in MDLINK_RE.findall(content)]
    return {"wikilinks": wikilinks, "mdlinks": mdlinks}


def extract_search_terms(content: str) -> Set[str]:
    """Tokenize content for the inverted search index. Lowercased, deduped."""
    return {m.group(0).lower() for m in _SEARCH_TOKEN_RE.finditer(content)}


# ============================================================================
# Data record for one note's metadata snapshot
# ============================================================================

@dataclass
class NoteRecord:
    """Snapshot of one note's metadata. Kept tiny — no content, no resolved
    links (those live in the inverted indexes)."""
    path: str                       # vault-relative POSIX
    name: str                       # stem (no extension)
    folder: str                     # vault-relative POSIX, "" for root
    modified: str                   # ISO timestamp
    size: int                       # bytes
    type: str                       # "note" | "image" | "audio" | ...
    mtime: float                    # raw stat mtime, for staleness checks
    tags: Tuple[str, ...] = field(default_factory=tuple)  # sorted, deduped


# ============================================================================
# The index itself
# ============================================================================

class NoteIndex:
    """Thread-safe in-memory index of vault state. Every read returns a
    snapshot copy so callers don't have to hold the lock."""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        self._lock = threading.RLock()

        # Note metadata
        self._notes: Dict[str, NoteRecord] = {}  # path -> record
        self._folders: Set[str] = set()

        # Tag indexes
        self._tags_forward: Dict[str, Tuple[str, ...]] = {}  # path -> tags
        self._tags_backward: Dict[str, Set[str]] = {}        # tag -> paths

        # Link indexes
        self._raw_links: Dict[str, Dict[str, List[str]]] = {}    # path -> {"wikilinks":[], "mdlinks":[]}
        self._links_forward: Dict[str, Dict[str, str]] = {}      # src -> {tgt: type}
        self._links_backward: Dict[str, Set[str]] = {}           # tgt -> {srcs}
        self._wikilink_tokens: Dict[str, Set[str]] = {}          # token -> {srcs} (loose)

        # Full-text inverted index
        self._search_terms: Dict[str, Set[str]] = {}             # term -> {paths}

        # Build state. _built tracks the cheap part (notes/tags/links).
        # _search_built tracks the expensive search index separately — that
        # one is built lazily on first search request to keep startup fast.
        self._built = False
        self._search_built = False
        self._raw_fingerprint: Optional[int] = None  # short-circuits no-op rebuilds

        # Observability counters (lock-free reads OK; rough is fine)
        self._stats = {
            "build_count": 0,
            "last_build_ms": 0.0,
            "last_built_at": None,
            "incremental_updates": 0,
            "fingerprint_short_circuits": 0,
            "search_build_count": 0,
            "last_search_build_ms": 0.0,
        }

    # ------------------------------------------------------------------
    # Status / lifecycle gates
    # ------------------------------------------------------------------

    def is_built(self) -> bool:
        with self._lock:
            return self._built

    def invalidate(self) -> None:
        """Mark as needing rebuild on next scan. Used as a safety net when
        an operation's incremental update is too fiddly to track precisely."""
        with self._lock:
            self._built = False
            self._raw_fingerprint = None

    def reset(self) -> None:
        with self._lock:
            self._notes.clear()
            self._folders.clear()
            self._tags_forward.clear()
            self._tags_backward.clear()
            self._raw_links.clear()
            self._links_forward.clear()
            self._links_backward.clear()
            self._wikilink_tokens.clear()
            self._search_terms.clear()
            self._built = False
            self._search_built = False
            self._raw_fingerprint = None

    def is_search_built(self) -> bool:
        with self._lock:
            return self._search_built

    def ensure_search_index_built(self, notes_dir: str) -> bool:
        """Build the full-text search index by reading every markdown file.

        Cheap if already built (instant return). Called lazily by search_notes
        on the first search request so app startup stays fast. Subsequent
        searches reuse the built index.

        Concurrency: while one thread is building, others can still read the
        (still-cold) index — they'll just take the legacy path until the
        build completes. Returns True if the index is built (now or already).
        """
        # Cheap pre-check without lock.
        if self._search_built:
            return True

        # Slow path: do the read+tokenize OUTSIDE the lock so other reads
        # aren't blocked. Snapshot the paths we need to read under the lock,
        # release, do I/O, then re-acquire to install the result.
        with self._lock:
            if self._search_built:  # raced with another builder
                return True
            if not self._built:
                return False
            paths_to_read = [p for p, r in self._notes.items() if r.type == "note"]

        t0 = time.perf_counter()
        base = Path(notes_dir)
        terms_per_path: Dict[str, Set[str]] = {}
        for rel in paths_to_read:
            try:
                full = base / rel
                with open(full, "r", encoding="utf-8") as f:
                    terms_per_path[rel] = extract_search_terms(f.read())
            except Exception:
                terms_per_path[rel] = set()

        # Re-acquire and install. If state changed under us (vault was
        # heavily mutated during the build), still install — the index
        # will be slightly stale until the next note save, which is the
        # same liveness guarantee as the per-save update path.
        with self._lock:
            if self._search_built:
                return True
            self._search_terms.clear()
            for path, terms in terms_per_path.items():
                for term in terms:
                    self._search_terms.setdefault(term, set()).add(path)
            self._search_built = True
            self._stats["search_build_count"] += 1
            self._stats["last_search_build_ms"] = (time.perf_counter() - t0) * 1000
        return True

    # ------------------------------------------------------------------
    # Bulk population — called from a full scan_notes_fast_walk
    # ------------------------------------------------------------------

    def bulk_set(
        self,
        notes_meta: List[NoteRecord],
        folders: Iterable[str],
        sources_raw: Dict[str, Dict[str, List[str]]],
    ) -> None:
        """Replace the entire index atomically. Builds notes/tags/links
        (cheap on top of an already-completed scan). The search index is
        NOT touched here — it's built lazily on the first search request
        (see ensure_search_index_built) so app startup stays fast.

        Fast-paths when the input fingerprints to the same state we already
        hold (typical warm scan where nothing changed in the vault).
        """
        new_fp = _fingerprint(notes_meta, sources_raw)
        with self._lock:
            if self._built and self._raw_fingerprint == new_fp:
                self._stats["fingerprint_short_circuits"] += 1
                return

            t0 = time.perf_counter()

            self._notes = {n.path: n for n in notes_meta}
            self._folders = set(folders)
            self._raw_links = {k: v for k, v in sources_raw.items()}

            self._rebuild_tags_unlocked()
            self._rebuild_links_unlocked()
            # Search index: if it was built and still references known notes,
            # prune stale entries; full rebuild is deferred until a search.
            if self._search_built:
                self._prune_search_unlocked()

            self._raw_fingerprint = new_fp
            self._built = True

            self._stats["build_count"] += 1
            self._stats["last_build_ms"] = (time.perf_counter() - t0) * 1000
            self._stats["last_built_at"] = datetime.now(tz=timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Incremental updates — called from save/delete/rename handlers
    # ------------------------------------------------------------------

    def update_note(
        self,
        record: NoteRecord,
        raw_links: Dict[str, List[str]],
        content: Optional[str] = None,
    ) -> None:
        """A single note's content changed (or was just created). Patches the
        index in place: re-extracts its links, updates the tag indexes, and
        if `content` is provided, refreshes its search-term entries."""
        with self._lock:
            old_record = self._notes.get(record.path)
            old_tags = old_record.tags if old_record else ()

            self._notes[record.path] = record
            if record.folder:
                self._folders.add(record.folder)

            # Tags: diff old vs new and patch the backward index.
            new_tags = record.tags
            if old_tags != new_tags:
                for t in set(old_tags) - set(new_tags):
                    bucket = self._tags_backward.get(t)
                    if bucket is not None:
                        bucket.discard(record.path)
                        if not bucket:
                            del self._tags_backward[t]
                for t in set(new_tags) - set(old_tags):
                    self._tags_backward.setdefault(t, set()).add(record.path)
                self._tags_forward[record.path] = new_tags

            # Links: re-resolve this one source against the current vault.
            self._raw_links[record.path] = raw_links
            self._resolve_single_source_unlocked(record.path)

            # Search: only patch the search index if it's already been built.
            # Otherwise we'd be doing work for an index nobody is using yet
            # (the first /api/search call will build it from disk).
            if content is not None and self._search_built:
                self._update_search_for_note_unlocked(record.path, content)

            self._raw_fingerprint = None
            self._stats["incremental_updates"] += 1

    def remove_note(self, path: str) -> None:
        """A note was deleted. Drop everything that mentions it."""
        with self._lock:
            old_record = self._notes.pop(path, None)
            if old_record is None:
                return

            # Tags
            for t in old_record.tags:
                bucket = self._tags_backward.get(t)
                if bucket is not None:
                    bucket.discard(path)
                    if not bucket:
                        del self._tags_backward[t]
            self._tags_forward.pop(path, None)

            # Links: drop as source.
            self._raw_links.pop(path, None)
            old_targets = self._links_forward.pop(path, {})
            for t in old_targets:
                bucket = self._links_backward.get(t)
                if bucket is not None:
                    bucket.discard(path)
                    if not bucket:
                        del self._links_backward[t]

            # Links: drop as loose wikilink source.
            empty_keys = []
            for key, sources in self._wikilink_tokens.items():
                sources.discard(path)
                if not sources:
                    empty_keys.append(key)
            for k in empty_keys:
                del self._wikilink_tokens[k]

            # Links: drop as target from every other source's forward dict.
            sources_pointing_here = self._links_backward.pop(path, set())
            for src in sources_pointing_here:
                fwd = self._links_forward.get(src)
                if fwd is not None and path in fwd:
                    del fwd[path]
                    if not fwd:
                        del self._links_forward[src]

            # Search: drop from every term bucket. Linear in distinct terms
            # this note contributed to, which is bounded by note size.
            empty_terms = []
            for term, paths in self._search_terms.items():
                if path in paths:
                    paths.discard(path)
                    if not paths:
                        empty_terms.append(term)
            for term in empty_terms:
                del self._search_terms[term]

            self._raw_fingerprint = None
            self._stats["incremental_updates"] += 1

    def rename_note(self, old_path: str, new_path: str) -> None:
        """A note was renamed/moved. Move all references from old_path to
        new_path in every index. Because the new path can change the source's
        own relative-folder resolution AND can change how other notes resolve
        their wikilinks to it (different parent folder, different stem),
        the simplest correct path is to migrate raw state then re-resolve."""
        if old_path == new_path:
            return
        with self._lock:
            old_record = self._notes.pop(old_path, None)
            if old_record is None:
                return
            new_record = NoteRecord(
                path=new_path,
                name=Path(new_path).stem,
                folder=str(Path(new_path).parent).replace("\\", "/").lstrip(".").lstrip("/") or "",
                modified=old_record.modified,
                size=old_record.size,
                type=old_record.type,
                mtime=old_record.mtime,
                tags=old_record.tags,
            )
            # Re-derive folder cleanly (the above lstrip dance is brittle).
            folder = str(Path(new_path).parent).replace("\\", "/")
            new_record.folder = "" if folder == "." else folder
            self._notes[new_path] = new_record
            if new_record.folder:
                self._folders.add(new_record.folder)

            # Tags forward + backward — swap the key.
            if old_path in self._tags_forward:
                tags = self._tags_forward.pop(old_path)
                self._tags_forward[new_path] = tags
                for t in tags:
                    bucket = self._tags_backward.get(t)
                    if bucket is not None:
                        bucket.discard(old_path)
                        bucket.add(new_path)

            # Search: swap path in every term bucket. Bounded by terms-per-note.
            for paths in self._search_terms.values():
                if old_path in paths:
                    paths.discard(old_path)
                    paths.add(new_path)

            # Raw links: migrate.
            if old_path in self._raw_links:
                self._raw_links[new_path] = self._raw_links.pop(old_path)

            # Strict link indexes: drop both old src and old target everywhere,
            # then re-resolve. Other sources that linked TO old_path by name
            # may now resolve to new_path (or not), so we need a re-resolve.
            #
            # Implementation: drop forward/backward for old_path, drop old
            # entries in other sources' forwards that pointed to old_path,
            # invalidate the index. The next scan rebuilds (which we trigger
            # implicitly because the caller flips _built = False below).
            self._links_forward.pop(old_path, None)
            for bucket in self._links_backward.values():
                bucket.discard(old_path)
            old_backlinks = self._links_backward.pop(old_path, set())
            for src in old_backlinks:
                fwd = self._links_forward.get(src)
                if fwd is not None and old_path in fwd:
                    del fwd[old_path]
                    if not fwd:
                        del self._links_forward[src]

            # Loose wikilink index: replace path values.
            empty_keys = []
            for key, sources in self._wikilink_tokens.items():
                if old_path in sources:
                    sources.discard(old_path)
                    sources.add(new_path)
                if not sources:
                    empty_keys.append(key)
            for k in empty_keys:
                del self._wikilink_tokens[k]

            self._raw_fingerprint = None
            self._built = False  # force re-resolve on next bulk_set/scan
            self._stats["incremental_updates"] += 1

    def rename_folder_prefix(self, old_prefix: str, new_prefix: str) -> None:
        """A folder was renamed/moved. Migrate every entry whose path starts
        with `old_prefix/` to `new_prefix/`. Much cheaper than a full rebuild:
        for a 1000-note folder rename, this is microseconds of key swaps
        vs ~400ms of disk re-scan.

        Both prefixes are normalized to forward slashes, no trailing slash.
        """
        old_prefix = old_prefix.rstrip("/")
        new_prefix = new_prefix.rstrip("/")
        if old_prefix == new_prefix:
            return
        with self._lock:
            affected_paths = [p for p in self._notes if p == old_prefix or p.startswith(old_prefix + "/")]
            for old_path in affected_paths:
                suffix = old_path[len(old_prefix):]  # includes leading "/" or nothing
                new_path = new_prefix + suffix
                # Reuse rename_note's heavy lifting — already correct, just
                # called many times. Acceptable for folder operations.
                # (Inlining would be a perf gain but multiplies bug surface.)
                self._rename_note_unlocked(old_path, new_path)

            # Migrate the folder set too.
            folders_to_rename = [
                f for f in self._folders if f == old_prefix or f.startswith(old_prefix + "/")
            ]
            for f in folders_to_rename:
                self._folders.discard(f)
                suffix = f[len(old_prefix):]
                self._folders.add(new_prefix + suffix)

            self._raw_fingerprint = None
            self._built = False

    def remove_folder_prefix(self, prefix: str) -> None:
        """A folder was deleted. Drop everything under it."""
        prefix = prefix.rstrip("/")
        with self._lock:
            affected = [p for p in self._notes if p == prefix or p.startswith(prefix + "/")]
            for path in affected:
                self._remove_note_unlocked(path)
            folders_to_drop = [
                f for f in self._folders if f == prefix or f.startswith(prefix + "/")
            ]
            for f in folders_to_drop:
                self._folders.discard(f)
            self._raw_fingerprint = None

    # ------------------------------------------------------------------
    # Read API — every method returns a snapshot copy
    # ------------------------------------------------------------------

    def get_backlink_candidate_sources(self, target_path: str) -> Set[str]:
        """Superset of true backlink sources. Combines strict resolved
        backward links with the loose wikilink-token reverse index. Caller
        runs the per-line matcher against each candidate to filter."""
        target_lower = target_path.lower()
        target_no_ext_lower = target_lower[:-3] if target_lower.endswith(".md") else target_lower
        target_name = Path(target_path).stem.lower()

        with self._lock:
            candidates: Set[str] = set(self._links_backward.get(target_path, set()))
            for key in (target_lower, target_no_ext_lower, target_name):
                candidates.update(self._wikilink_tokens.get(key, set()))
            candidates.discard(target_path)
            return candidates

    def get_graph_data(self) -> Tuple[List[str], List[Tuple[str, str, str]]]:
        """Snapshot of (sorted note paths, (source, target, type) edges)."""
        with self._lock:
            nodes = sorted(p for p, r in self._notes.items() if r.type == "note")
            edges: List[Tuple[str, str, str]] = []
            for src, targets in self._links_forward.items():
                for target, edge_type in targets.items():
                    edges.append((src, target, edge_type))
            return nodes, edges

    def get_all_tags(self) -> Dict[str, int]:
        """Snapshot: {tag: count}, sorted by tag name."""
        with self._lock:
            return {tag: len(paths) for tag, paths in sorted(self._tags_backward.items())}

    def get_paths_for_tag(self, tag: str) -> Set[str]:
        """Snapshot set of paths tagged with `tag` (case-insensitive)."""
        with self._lock:
            return set(self._tags_backward.get(tag.lower(), set()))

    def get_note_record(self, path: str) -> Optional[NoteRecord]:
        with self._lock:
            return self._notes.get(path)

    def try_get_extraction(
        self,
        rel_path: str,
        mtime: float,
    ) -> Optional[Tuple[List[str], Dict[str, List[str]]]]:
        """Return (tags, raw_links) from the index when fresh.

        The caller passes the file's current mtime; we hand back the cached
        extraction only when the recorded mtime matches exactly. Lets
        scan_notes_fast_walk skip the per-file read on a snapshot-warm
        startup — the bulk of cold-load latency on large vaults.

        Returns None when:
          - The note isn't in the index (new file)
          - mtime differs (file changed since snapshot)
          - We've somehow lost the raw_links entry (defensive)
        """
        with self._lock:
            rec = self._notes.get(rel_path)
            if rec is None or rec.mtime != mtime:
                return None
            raw = self._raw_links.get(rel_path)
            if raw is None:
                return None
            return (
                list(rec.tags),
                {
                    "wikilinks": list(raw.get("wikilinks", [])),
                    "mdlinks": list(raw.get("mdlinks", [])),
                },
            )

    def get_search_candidates(self, query: str) -> Optional[Set[str]]:
        # Index can only narrow candidates if it's been built.
        if not self._search_built:
            return None
        """Return the set of paths that COULD contain `query` as a substring,
        based on the inverted term index.

        Returns None when the query is too short to use the index (caller
        should fall through to the legacy full-scan). When the query
        tokenizes to nothing useful (all stopword-like noise), returns the
        set of every indexed path so the caller still does a substring
        check on each (no false negatives).

        IMPORTANT: this is a SUPERSET — the caller must still run the
        substring match per candidate to confirm and extract context.
        Token-AND can include docs that have both tokens but not as the
        adjacent substring the user searched for.
        """
        if len(query) < _SEARCH_MIN_QUERY_LEN:
            return None
        tokens = [m.group(0).lower() for m in _SEARCH_TOKEN_RE.finditer(query)]
        if not tokens:
            # Query has no tokenizable parts (pure punctuation, single char,
            # etc.). Index can't help; fall through.
            return None
        with self._lock:
            # Intersection of all token buckets. Empty set means no doc
            # contains ALL of the tokens (and therefore none contain the
            # query as substring either).
            candidate = self._search_terms.get(tokens[0])
            if candidate is None:
                return set()
            result: Set[str] = set(candidate)
            for tok in tokens[1:]:
                bucket = self._search_terms.get(tok)
                if bucket is None:
                    return set()
                result &= bucket
                if not result:
                    break
            return result

    def stats(self) -> Dict[str, Any]:
        """Snapshot of internal counters + size metrics. Cheap to call —
        no traversal beyond `len()` on the top-level dicts."""
        with self._lock:
            return {
                "enabled": USE_NOTE_INDEX,
                "built": self._built,
                "search_built": self._search_built,
                "notes": len(self._notes),
                "folders": len(self._folders),
                "tags": len(self._tags_backward),
                "links_forward_entries": len(self._links_forward),
                "links_backward_entries": len(self._links_backward),
                "wikilink_tokens": len(self._wikilink_tokens),
                "search_terms": len(self._search_terms),
                "counters": dict(self._stats),
            }

    # ==================================================================
    # Internal — must hold _lock when called
    # ==================================================================

    def _rebuild_tags_unlocked(self) -> None:
        self._tags_forward.clear()
        self._tags_backward.clear()
        for path, record in self._notes.items():
            if record.type != "note":
                continue
            tags = record.tags
            if not tags:
                continue
            self._tags_forward[path] = tags
            for tag in tags:
                self._tags_backward.setdefault(tag, set()).add(path)

    def _rebuild_links_unlocked(self) -> None:
        """Full link re-resolution. Builds a shared Resolver lookup once
        (O(N)) and reuses it for every source (O(K) each) — total O(N+K*L)
        rather than the O(N*K) you'd get by building a fresh Resolver per
        source.
        """
        self._links_forward.clear()
        self._links_backward.clear()
        self._wikilink_tokens.clear()
        note_paths = {p for p, r in self._notes.items() if r.type == "note"}
        resolver = _Resolver(note_paths)
        for source_path in self._raw_links:
            self._resolve_single_source_unlocked(source_path, resolver=resolver, skip_cleanup=True)

    def _prune_search_unlocked(self) -> None:
        """Drop search-term entries for paths no longer in the index. Cheap
        compared to a full rebuild — only touches terms whose bucket still
        references a now-deleted path."""
        live_paths = set(self._notes.keys())
        empty_terms = []
        for term, paths in self._search_terms.items():
            stale = paths - live_paths
            if stale:
                paths -= stale
                if not paths:
                    empty_terms.append(term)
        for term in empty_terms:
            del self._search_terms[term]

    def _update_search_for_note_unlocked(self, path: str, content: str) -> None:
        """Replace one note's terms in the inverted index."""
        # Drop old entries for this path.
        empty_terms = []
        for term, paths in self._search_terms.items():
            if path in paths:
                paths.discard(path)
                if not paths:
                    empty_terms.append(term)
        for term in empty_terms:
            del self._search_terms[term]
        # Add new entries.
        for term in extract_search_terms(content):
            self._search_terms.setdefault(term, set()).add(path)

    def _resolve_single_source_unlocked(
        self,
        source_path: str,
        resolver: Optional["_Resolver"] = None,
        skip_cleanup: bool = False,
    ) -> None:
        if not skip_cleanup:
            old_targets = self._links_forward.pop(source_path, {})
            for t in old_targets:
                bucket = self._links_backward.get(t)
                if bucket is not None:
                    bucket.discard(source_path)
                    if not bucket:
                        del self._links_backward[t]
            empty_keys = []
            for key, sources in self._wikilink_tokens.items():
                sources.discard(source_path)
                if not sources:
                    empty_keys.append(key)
            for k in empty_keys:
                del self._wikilink_tokens[k]

        raw = self._raw_links.get(source_path)
        if not raw:
            return

        if resolver is None:
            note_paths = {p for p, r in self._notes.items() if r.type == "note"}
            resolver = _Resolver(note_paths)

        source_folder = str(Path(source_path).parent).replace("\\", "/")
        if source_folder == ".":
            source_folder = ""

        targets: Dict[str, str] = {}

        # Wikilinks first so they win the "first wins" dedup that legacy
        # /api/graph also implements.
        for target in raw.get("wikilinks", []):
            resolved = resolver.resolve_wikilink(target, source_folder)
            if resolved and resolved != source_path and resolved not in targets:
                targets[resolved] = "wikilink"
            # Loose wikilink reverse index — populated regardless of strict
            # resolution success, because the legacy get_backlinks uses
            # token-stem matching independent of where the link actually
            # navigates.
            t_lower = target.strip().lower()
            if t_lower:
                self._wikilink_tokens.setdefault(t_lower, set()).add(source_path)
                t_no_ext = t_lower[:-3] if t_lower.endswith(".md") else t_lower
                if t_no_ext != t_lower:
                    self._wikilink_tokens.setdefault(t_no_ext, set()).add(source_path)

        for link_path in raw.get("mdlinks", []):
            resolved = resolver.resolve_mdlink(link_path, source_folder)
            if resolved and resolved != source_path and resolved not in targets:
                targets[resolved] = "markdown"

        if targets:
            self._links_forward[source_path] = targets
            for t in targets:
                self._links_backward.setdefault(t, set()).add(source_path)

    def _rename_note_unlocked(self, old_path: str, new_path: str) -> None:
        """Same as rename_note() but assumes the caller already holds the lock.
        Used by folder-prefix rename to avoid re-acquiring the lock per file."""
        if old_path == new_path:
            return
        old_record = self._notes.pop(old_path, None)
        if old_record is None:
            return
        folder = str(Path(new_path).parent).replace("\\", "/")
        new_record = NoteRecord(
            path=new_path,
            name=Path(new_path).stem,
            folder="" if folder == "." else folder,
            modified=old_record.modified,
            size=old_record.size,
            type=old_record.type,
            mtime=old_record.mtime,
            tags=old_record.tags,
        )
        self._notes[new_path] = new_record
        if new_record.folder:
            self._folders.add(new_record.folder)

        if old_path in self._tags_forward:
            tags = self._tags_forward.pop(old_path)
            self._tags_forward[new_path] = tags
            for t in tags:
                bucket = self._tags_backward.get(t)
                if bucket is not None:
                    bucket.discard(old_path)
                    bucket.add(new_path)

        for paths in self._search_terms.values():
            if old_path in paths:
                paths.discard(old_path)
                paths.add(new_path)

        if old_path in self._raw_links:
            self._raw_links[new_path] = self._raw_links.pop(old_path)

        self._links_forward.pop(old_path, None)
        for bucket in self._links_backward.values():
            bucket.discard(old_path)
        old_backlinks = self._links_backward.pop(old_path, set())
        for src in old_backlinks:
            fwd = self._links_forward.get(src)
            if fwd is not None and old_path in fwd:
                del fwd[old_path]
                if not fwd:
                    del self._links_forward[src]

        empty_keys = []
        for key, sources in self._wikilink_tokens.items():
            if old_path in sources:
                sources.discard(old_path)
                sources.add(new_path)
            if not sources:
                empty_keys.append(key)
        for k in empty_keys:
            del self._wikilink_tokens[k]

    def _remove_note_unlocked(self, path: str) -> None:
        """Same as remove_note() but assumes the caller already holds the lock."""
        old_record = self._notes.pop(path, None)
        if old_record is None:
            return
        for t in old_record.tags:
            bucket = self._tags_backward.get(t)
            if bucket is not None:
                bucket.discard(path)
                if not bucket:
                    del self._tags_backward[t]
        self._tags_forward.pop(path, None)
        self._raw_links.pop(path, None)
        old_targets = self._links_forward.pop(path, {})
        for t in old_targets:
            bucket = self._links_backward.get(t)
            if bucket is not None:
                bucket.discard(path)
                if not bucket:
                    del self._links_backward[t]
        empty_keys = []
        for key, sources in self._wikilink_tokens.items():
            sources.discard(path)
            if not sources:
                empty_keys.append(key)
        for k in empty_keys:
            del self._wikilink_tokens[k]
        sources_pointing_here = self._links_backward.pop(path, set())
        for src in sources_pointing_here:
            fwd = self._links_forward.get(src)
            if fwd is not None and path in fwd:
                del fwd[path]
                if not fwd:
                    del self._links_forward[src]
        empty_terms = []
        for term, paths in self._search_terms.items():
            if path in paths:
                paths.discard(path)
                if not paths:
                    empty_terms.append(term)
        for term in empty_terms:
            del self._search_terms[term]


# ============================================================================
# Resolver — link-target matching (mirrors legacy /api/graph rules exactly)
# ============================================================================

class _Resolver:
    """Build the lookup tables once per resolution batch, then call
    resolve_* repeatedly. Reused across sources within a single rebuild so
    we don't pay O(N) to construct it on every source."""

    def __init__(self, all_notes: Set[str]) -> None:
        self.note_paths: Set[str] = set(all_notes)
        self.note_paths_lower: Dict[str, str] = {}
        self.note_names: Dict[str, str] = {}
        for p in all_notes:
            self.note_paths_lower[p.lower()] = p
            if p.endswith(".md"):
                self.note_paths_lower[p[:-3].lower()] = p
            stem = Path(p).stem
            self.note_names[stem.lower()] = p
            self.note_names[Path(p).name.lower()] = p

    def resolve_wikilink(self, target: str, source_folder: str) -> Optional[str]:
        target = target.strip()
        if not target:
            return None
        target_lower = target.lower()

        # 1. Relative to source folder (only for bare names with no slash).
        if source_folder and "/" not in target:
            relative_path = f"{source_folder}/{target}"
            relative_path_lower = relative_path.lower()
            if relative_path in self.note_paths:
                return relative_path if relative_path.endswith(".md") else relative_path + ".md"
            if relative_path + ".md" in self.note_paths:
                return relative_path + ".md"
            if relative_path_lower in self.note_paths_lower:
                return self.note_paths_lower[relative_path_lower]
            if (relative_path_lower + ".md") in self.note_paths_lower:
                return self.note_paths_lower[relative_path_lower + ".md"]

        if target in self.note_paths:
            return target if target.endswith(".md") else target + ".md"
        if (target + ".md") in self.note_paths:
            return target + ".md"
        if target_lower in self.note_paths_lower:
            return self.note_paths_lower[target_lower]
        if (target_lower + ".md") in self.note_paths_lower:
            return self.note_paths_lower[target_lower + ".md"]
        if target_lower in self.note_names:
            return self.note_names[target_lower]
        return None

    def resolve_mdlink(self, link_path: str, source_folder: str) -> Optional[str]:
        if not link_path:
            return None
        link_path = link_path.split("#")[0]
        if not link_path:
            return None
        link_path = urllib.parse.unquote(link_path)
        if link_path.startswith("./"):
            link_path = link_path[2:]
        link_path_with_md = link_path if link_path.endswith(".md") else link_path + ".md"

        if source_folder and not link_path.startswith("/"):
            relative_path = f"{source_folder}/{link_path}"
            relative_path_with_md = f"{source_folder}/{link_path_with_md}"
            relative_path_lower = relative_path.lower()
            relative_path_with_md_lower = relative_path_with_md.lower()
            if relative_path in self.note_paths:
                return relative_path if relative_path.endswith(".md") else relative_path + ".md"
            if relative_path_with_md in self.note_paths:
                return relative_path_with_md
            if relative_path_lower in self.note_paths_lower:
                return self.note_paths_lower[relative_path_lower]
            if relative_path_with_md_lower in self.note_paths_lower:
                return self.note_paths_lower[relative_path_with_md_lower]

        link_path_lower = link_path.lower()
        link_path_with_md_lower = link_path_with_md.lower()
        if link_path in self.note_paths:
            return link_path if link_path.endswith(".md") else link_path + ".md"
        if link_path_with_md in self.note_paths:
            return link_path_with_md
        if link_path_lower in self.note_paths_lower:
            return self.note_paths_lower[link_path_lower]
        if link_path_with_md_lower in self.note_paths_lower:
            return self.note_paths_lower[link_path_with_md_lower]
        return None


# ============================================================================
# Internal helpers
# ============================================================================

def _fingerprint(
    notes_meta: List[NoteRecord],
    sources_raw: Dict[str, Dict[str, List[str]]],
) -> int:
    """Cheap content hash of a scan result. Used to short-circuit bulk_set
    when nothing has changed in the vault."""
    notes_fp = hash(frozenset((n.path, n.mtime) for n in notes_meta))
    raw_items = (
        (src, tuple(raw.get("wikilinks", [])), tuple(raw.get("mdlinks", [])))
        for src, raw in sources_raw.items()
    )
    return hash((notes_fp, hash(frozenset(raw_items))))


# ============================================================================
# Module-level singleton + facade
#
# Every utils.py / main.py call site uses these — never instantiates its own
# index. The facade functions are no-ops (or return None) when
# USE_NOTE_INDEX is False, so call sites don't have to repeat the flag check.
# ============================================================================

_index = NoteIndex()


def get_index() -> NoteIndex:
    return _index


# --- Lifecycle facade (one-line calls from utils.py mutators) ----------------

def on_note_saved(notes_dir: str, full_path: Path, content: str) -> None:
    """A note was created or updated on disk. Patch the index in place."""
    if not USE_NOTE_INDEX:
        return
    try:
        rel_path = full_path.relative_to(Path(notes_dir)).as_posix()
        st = full_path.stat()
        folder = str(Path(rel_path).parent).replace("\\", "/")
        record = NoteRecord(
            path=rel_path,
            name=Path(rel_path).stem,
            folder="" if folder == "." else folder,
            modified=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            size=st.st_size,
            type="note",
            mtime=st.st_mtime,
            tags=tuple(_parse_tags_for_record(content)),
        )
        raw_links = extract_links_from_content(content)
        _index.update_note(record, raw_links, content=content)
    except Exception as e:
        print(f"note_index: on_note_saved failed for {full_path}: {e}")


def on_note_deleted(notes_dir: str, full_path: Path) -> None:
    if not USE_NOTE_INDEX:
        return
    try:
        rel_path = full_path.relative_to(Path(notes_dir)).as_posix()
        _index.remove_note(rel_path)
    except Exception as e:
        print(f"note_index: on_note_deleted failed for {full_path}: {e}")


def on_note_renamed(notes_dir: str, old_full_path: Path, new_full_path: Path) -> None:
    if not USE_NOTE_INDEX:
        return
    try:
        base = Path(notes_dir)
        _index.rename_note(
            old_full_path.relative_to(base).as_posix(),
            new_full_path.relative_to(base).as_posix(),
        )
    except Exception as e:
        print(f"note_index: on_note_renamed failed: {e}")


def on_folder_renamed(notes_dir: str, old_full_path: Path, new_full_path: Path) -> None:
    """A folder was moved/renamed. Re-keys every entry under it (cheap,
    no disk reads) rather than invalidating the whole index."""
    if not USE_NOTE_INDEX:
        return
    try:
        base = Path(notes_dir)
        _index.rename_folder_prefix(
            old_full_path.relative_to(base).as_posix(),
            new_full_path.relative_to(base).as_posix(),
        )
    except Exception as e:
        print(f"note_index: on_folder_renamed failed: {e}")
        _index.invalidate()  # fail-safe


def on_folder_deleted(notes_dir: str, full_path: Path) -> None:
    if not USE_NOTE_INDEX:
        return
    try:
        rel_prefix = full_path.relative_to(Path(notes_dir)).as_posix()
        _index.remove_folder_prefix(rel_prefix)
    except Exception as e:
        print(f"note_index: on_folder_deleted failed: {e}")
        _index.invalidate()


def populate_from_scan(
    notes_meta: List[NoteRecord],
    folders: Iterable[str],
    sources_raw: Dict[str, Dict[str, List[str]]],
) -> None:
    """Bulk-replace the index from a fresh scan. No-op when off."""
    if not USE_NOTE_INDEX:
        return
    try:
        _index.bulk_set(notes_meta, folders, sources_raw)
    except Exception as e:
        print(f"note_index: populate_from_scan failed: {e}")


def ensure_search_index(notes_dir: str) -> bool:
    """Lazily build the full-text search index on first /api/search request.
    Cheap after the first call. Returns True if the index is now usable."""
    if not USE_NOTE_INDEX:
        return False
    if not _index.is_built():
        return False
    return _index.ensure_search_index_built(notes_dir)


# --- Read facade (returns None when off — callers fall through to legacy) ----

def try_backlink_candidates(target_path: str) -> Optional[Set[str]]:
    if not USE_NOTE_INDEX or not _index.is_built():
        return None
    return _index.get_backlink_candidate_sources(target_path)


def try_graph_data() -> Optional[Tuple[List[str], List[Tuple[str, str, str]]]]:
    if not USE_NOTE_INDEX or not _index.is_built():
        return None
    return _index.get_graph_data()


def try_search_candidates(query: str) -> Optional[Set[str]]:
    if not USE_NOTE_INDEX or not _index.is_built():
        return None
    return _index.get_search_candidates(query)


def try_all_tags() -> Optional[Dict[str, int]]:
    if not USE_NOTE_INDEX or not _index.is_built():
        return None
    return _index.get_all_tags()


def try_notes_by_tag(tag: str) -> Optional[Set[str]]:
    if not USE_NOTE_INDEX or not _index.is_built():
        return None
    return _index.get_paths_for_tag(tag)


def try_get_extraction(
    rel_path: str,
    mtime: float,
) -> Optional[Tuple[List[str], Dict[str, List[str]]]]:
    """Serve (tags, raw_links) from the index for a single file, when fresh.

    Used by scan_notes_fast_walk to skip the cold per-file read after a
    snapshot load. Returns None when the index can't help (off, not built,
    file unknown, mtime mismatch) — caller falls back to reading the file.
    """
    if not USE_NOTE_INDEX or not _index.is_built():
        return None
    return _index.try_get_extraction(rel_path, mtime)


# --- Observability -----------------------------------------------------------

def stats() -> Dict[str, Any]:
    return _index.stats()


# ============================================================================
# Late import to avoid a circular dependency with utils.parse_tags.
# We need tag parsing inside on_note_saved but utils.py imports this module.
# ============================================================================

def _parse_tags_for_record(content: str) -> List[str]:
    """Thin shim to utils.parse_tags. Late-bound so this module imports cleanly
    before utils.py is loaded."""
    from .utils import parse_tags
    return parse_tags(content)
