#!/usr/bin/env python3
"""
Quasar snippet-loss report — the most certain number in the whole study.

For every indexed RAG document it computes:

    lost = find_critical(content) - find_critical(content[:SNIPPET_LEN])

Every value in `lost` is a critical value (IBAN, CUI, total, invoice number,
date, ...) that RAGService._create_snippet() cuts off at char 300, making it
INVISIBLE to the LLM on EVERY query — before any budget or ranking logic runs.

This needs NO Quasar, NO embeddings, NO torch, NO budget assumptions. Just regex
over text. It is deterministic and query-independent.

If the total is large, that is a bug worth fixing on its own (raise the snippet
length, or feed full content to the LLM) — independent of the Quasar work.
If the total is ~0, that is reported plainly: the 300-char snippet is not losing
critical values on this corpus.

Usage:
    # Against a database (READ-ONLY: a single SELECT; never writes):
    python scripts/quasar_snippet_report.py --database-url "$STAGING_DATABASE_URL"

    # Against a folder of .txt files (offline validation):
    python scripts/quasar_snippet_report.py --from-dir /path/to/txts

    # Options: --snippet-len 300  --examples 15  --json out.json
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

# Load the pure-regex pattern module DIRECTLY by path, bypassing the ai_agent
# package __init__ (which imports the whole app and needs DATABASE_URL). This
# keeps the "most certain number" dependency-free: psycopg2 only if --database-url.
import importlib.util  # noqa: E402
_pat_path = os.path.join(os.path.dirname(__file__), "..", "jarvis",
                         "ai_agent", "services", "quasar_patterns.py")
_spec = importlib.util.spec_from_file_location("quasar_patterns", _pat_path)
_qp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_qp)
find_critical, find_critical_kinds = _qp.find_critical, _qp.find_critical_kinds

SNIPPET_LEN_DEFAULT = 300  # must match RAGService._create_snippet(max_length=300)


def snippet_loss(content: str, snippet_len: int):
    """Return (lost_values, lost_kinds) for one document."""
    full = set(find_critical(content))
    kept = set(find_critical(content[:snippet_len]))
    lost = full - kept
    kinds = {v: k for v, k in find_critical_kinds(content)}
    return sorted(lost), Counter(kinds[v] for v in lost)


def iter_db_documents(database_url: str):
    import psycopg2
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(database_url)
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # READ-ONLY. Order for stable, repeatable output.
        cur.execute("""
            SELECT id, source_type, source_id, content
            FROM ai_agent.rag_documents
            WHERE content IS NOT NULL AND content <> ''
            ORDER BY id
        """)
        for row in cur:
            yield {
                "id": row["id"],
                "label": f"{row['source_type']}#{row['source_id']}",
                "source_type": row["source_type"],
                "content": row["content"],
            }
    finally:
        conn.close()


def iter_dir_documents(path: str):
    import glob
    for fp in sorted(glob.glob(os.path.join(path, "*.txt"))):
        with open(fp, encoding="utf-8", errors="replace") as f:
            yield {
                "id": os.path.basename(fp),
                "label": os.path.basename(fp)[:48],
                "source_type": "file",
                "content": f.read(),
            }


def main():
    ap = argparse.ArgumentParser(description="Quasar snippet-loss report (query-independent).")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--database-url", help="Postgres URL; reads ai_agent.rag_documents (READ-ONLY).")
    src.add_argument("--from-dir", help="Folder of .txt files (offline validation).")
    ap.add_argument("--snippet-len", type=int, default=SNIPPET_LEN_DEFAULT)
    ap.add_argument("--examples", type=int, default=15, help="How many example lost values to show.")
    ap.add_argument("--json", help="Write full per-document results to this JSON file.")
    args = ap.parse_args()

    docs = iter_db_documents(args.database_url) if args.database_url else iter_dir_documents(args.from_dir)

    total_docs = 0
    docs_with_loss = 0
    total_lost_values = 0
    kind_counter = Counter()
    by_source_type = defaultdict(lambda: {"docs": 0, "docs_with_loss": 0, "values_lost": 0})
    examples = []
    per_doc = []

    for d in docs:
        total_docs += 1
        by_source_type[d["source_type"]]["docs"] += 1
        lost, kinds = snippet_loss(d["content"], args.snippet_len)
        if lost:
            docs_with_loss += 1
            total_lost_values += len(lost)
            kind_counter.update(kinds)
            by_source_type[d["source_type"]]["docs_with_loss"] += 1
            by_source_type[d["source_type"]]["values_lost"] += len(lost)
            if len(examples) < args.examples:
                examples.append((d["label"], lost[:6], dict(kinds)))
        per_doc.append({"id": d["id"], "label": d["label"],
                        "source_type": d["source_type"],
                        "content_len": len(d["content"]),
                        "lost": lost, "lost_kinds": dict(kinds)})

    print("=" * 78)
    print("QUASAR SNIPPET-LOSS REPORT  (find_critical(content) - find_critical(content[:%d]))" % args.snippet_len)
    print("=" * 78)
    print(f"  indexed documents scanned .............. {total_docs}")
    print(f"  documents losing >=1 critical value .... {docs_with_loss}"
          f"  ({(100.0*docs_with_loss/total_docs if total_docs else 0):.1f}%)")
    print(f"  TOTAL critical values dropped .......... {total_lost_values}")
    print()

    if total_lost_values == 0:
        print("  RESULT: ZERO snippet loss. The 300-char snippet is NOT dropping critical")
        print("          values on this corpus. This part of the case study is a NULL result")
        print("          — report it plainly; do not massage it.")
    else:
        print("  RESULT: the 300-char snippet silently drops the above values from EVERY")
        print("          query. This is a query-independent bug, independent of Quasar.")
        print()
        print("  By kind:")
        for kind, n in kind_counter.most_common():
            print(f"    {kind:15} {n}")
        print()
        print("  By source_type:")
        for st, s in sorted(by_source_type.items(), key=lambda kv: -kv[1]["values_lost"]):
            print(f"    {st:15} {s['values_lost']:5} values lost across "
                  f"{s['docs_with_loss']}/{s['docs']} docs")
        print()
        print(f"  Examples (up to {args.examples}):")
        for label, vals, kinds in examples:
            print(f"    {label}: would DROP {vals}")

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"total_docs": total_docs, "docs_with_loss": docs_with_loss,
                       "total_lost_values": total_lost_values,
                       "by_kind": dict(kind_counter),
                       "by_source_type": {k: v for k, v in by_source_type.items()},
                       "documents": per_doc}, f, indent=2, default=str)
        print(f"\n  full results -> {args.json}")


if __name__ == "__main__":
    main()
