"""Search and evidence selection for the optimized agent."""
from collections import Counter
from math import log1p
import re

from .store import terms, windows


def passage_candidates(text, query, question):
    query_words = set(terms(query))
    question_words = set(terms(question))
    vocabulary = query_words | question_words
    spans = []
    frequencies = Counter()
    for left, right in windows(text, size=74, overlap=24):
        present = set(terms(text[left:right])) & vocabulary
        frequencies.update(present)
        spans.append((left, right, present))
    weighted = {w: (2.0 if w in query_words else 0.65) *
                (1 + log1p(len(spans) / (1 + count))) for w, count in frequencies.items()}
    ranked = sorted(spans, key=lambda p: (-sum(weighted[w] for w in sorted(p[2])), p[0]))
    chosen = []
    for left, right, _ in ranked:
        if any(left < b and a < right for a,b in chosen):
            continue
        chosen.append((left, right))
        if len(chosen) == 2:
            break
    return [{"start": a, "end": b, "quote": text[a:b]} for a,b in chosen]


def search_with_clues(retrieval, question, query, intent, first):
    if not isinstance(query, str) or not query.strip() or not isinstance(intent, str):
        raise ValueError("Supply a nonempty query and a text intent.")
    probes = [query.strip()]
    if first and question.strip().casefold() != probes[0].casefold():
        probes.append(question.strip())
    ranks = Counter()
    found = {}
    for index, probe in enumerate(probes):
        hits = retrieval.search(probe, intent if index == 0 else "", top=8)
        for rank, hit in enumerate(hits, 1):
            docid = hit["doc_id"]
            found[docid] = hit
            ranks[docid] += (1.0 if index == 0 else 0.85) / (4 + rank)
    rows = []
    for docid in sorted(ranks, key=lambda d: (-ranks[d], d))[:6]:
        text, url = retrieval.store.get(docid)
        passages = passage_candidates(text, " ".join((query, intent)), question)
        if first:
            for original in found[docid]["passages"]:
                left = original["start"]
                right = min(original["end"], left + 470)
                covered = any(max(0, min(right, p["end"]) - max(left, p["start"])) >
                              0.65 * (right-left) for p in passages)
                if not covered:
                    passages.append({"start": left, "end": right, "quote": text[left:right]})
                    break
        rows.append({**found[docid], "url": url, "score": round(ranks[docid], 6), "passages": passages})
    return probes, rows


def retained_evidence(state, question):
    clues = set(terms(question))
    anchors = set(terms(" ".join([state["candidate"], *state["unresolved"]])))
    selected = set(state["selected"])
    evidence = list(state["evidence"].values())
    def priority(entry):
        words = set(terms(entry["quote"]))
        return (entry["id"] in selected, entry["source"] == "read",
                len(words & anchors) * 2 + len(words & clues))
    ordered = sorted(reversed(evidence), key=priority, reverse=True)
    result = []
    seen = Counter()
    for entry in ordered:
        doc = entry["doc_id"]
        if seen[doc] >= 2 or any(item["doc_id"] == doc and
                entry["start"] < item["end"] and item["start"] < entry["end"] for item in result):
            continue
        result.append(entry)
        seen[doc] += 1
        if len(result) == 7:
            break
    return [{"id": e["id"], "url": e["url"][:240], "quote": e["quote"][:660]} for e in result]


def needs_extraction(answer):
    if len(answer.split()) > 26 or "\n\n" in answer or "**" in answer:
        return True
    return bool(re.match(r"(?i)^(?:based on\b|according to\b|the (?:answer|evidence) (?:is|was|shows)\b|the .{1,42}? (?:is|was) (?:called |named )?|i (?:think|believe|could not)\b)", answer))
