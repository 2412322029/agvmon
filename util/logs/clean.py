import os
import re
from datetime import datetime


def _format_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _parse_indices(raw: str, max_n: int) -> list[int]:
    """Parse user input like '1,3,5-7,all' into a sorted list of indices."""
    raw = raw.strip().lower()
    if raw in ("all", "a", ""):
        return list(range(max_n))

    selected: set[int] = set()
    for part in re.split(r"[,\s]+", raw):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                selected.update(range(int(a), int(b) + 1))
            except ValueError:
                print(f"  [skip] invalid range: {part}")
        else:
            try:
                selected.add(int(part))
            except ValueError:
                print(f"  [skip] invalid index: {part}")

    return sorted(i for i in selected if 0 <= i < max_n)


def interactive_clean(directory: str, label: str = "files") -> int:
    """List files in *directory*, let user pick which to delete. Returns count deleted."""
    if not os.path.isdir(directory):
        print(f"Directory not found: {directory}")
        return 0

    entries = sorted(
        (
            (f, os.path.getsize(p), datetime.fromtimestamp(os.path.getmtime(p)))
            for f in os.listdir(directory)
            if os.path.isfile(p := os.path.join(directory, f))
        ),
        key=lambda x: x[2], reverse=True,  # newest first
    )

    if not entries:
        print(f"No files in {directory}")
        return 0

    total_size = sum(sz for _, sz, _ in entries)
    print(f"\n  [{label}] {directory}")
    print(f"  {'─' * 60}")
    print(f"  {'#':<4} {'size':>10}  {'modified':<20}  filename")
    print(f"  {'─' * 60}")
    for i, (name, size, mtime) in enumerate(entries):
        print(f"  {i:<4} {_format_size(size):>10}  {str(mtime):<20}  {name}")
    print(f"  {'─' * 60}")
    print(f"  {len(entries)} files  |  total {_format_size(total_size)}")
    print()
    while True:
        raw = input("  Delete which files? [numbers / 1,3 / 5-7 / all / q]: ").strip()
        if raw.lower() in ("q", "quit", "n", "no"):
            print("  Cancelled.")
            return 0

        indices = _parse_indices(raw, len(entries))
        if not indices:
            print("  No valid files selected.")

    targets = [entries[i] for i in indices]
    selected_size = sum(sz for _, sz, _ in targets)
    print(f"\n  Will delete {len(targets)} file(s) ({_format_size(selected_size)}):")
    for i in indices:
        print(f"    - {entries[i][0]}")

    confirm = input("\n  Confirm? [y/N]: ").strip().lower()
    if confirm not in ("y", "yes"):
        print("  Cancelled.")
        return 0

    deleted = 0
    for i in indices:
        name = entries[i][0]
        try:
            os.remove(os.path.join(directory, name))
            print(f"  Deleted: {name}")
            deleted += 1
        except OSError as e:
            print(f"  Failed: {name} ({e})")

    print(f"  Done ({deleted} deleted).\n")
    return deleted
