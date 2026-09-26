"""
src/identity_resolution/entity_resolution.py — Customer360 Navigator

SYNTHETIC MULTI-SOURCE CUSTOMER IDENTITY DEMONSTRATION.

This module exists to demonstrate what a real Customer 360 platform's identity-resolution /
golden-record layer looks like — a piece this project's own architecture review correctly
identified as missing. It is a **separate, clearly-labeled synthetic layer**, deliberately never
run against, joined onto, or blended with any real CFPB complaint data anywhere in this project.

WHY SYNTHETIC, EXPLICITLY: the real CFPB extract this whole suite is built on has no longitudinal
customer identifier at all — this project's own BP4 architecture doc states that plainly, and BP4
performs event/issue-cluster journey analytics specifically *because* no customer identifier
exists to resolve identities against. Building identity resolution against the real data would
mean either inventing a customer key the source data does not have, or leaving the resolution
untestable. Neither is acceptable under this project's zero-fabrication rule. Instead, this module
runs against three small, hand-authored, fictional CSVs
(`data/synthetic_identity_demo/customer_source_{a,b,c}.csv` — invented names, emails, phone
numbers and addresses; any resemblance to a real person is coincidental) that model three source
systems a real institution might have (a core-banking system, a CRM, and a web self-signup flow),
each describing overlapping fictional customers slightly differently — matching this project's own
disclosed convention (see BP1-8's architecture docs) of never fabricating a result over real data,
here applied to a *labeled* synthetic case instead.

METHOD — deterministic pass, then probabilistic pass, exactly as the architecture review specified:

1. Deterministic matching: two source records are the same customer if they share an identical
   normalized email OR an identical normalized (digits-only) phone number. Implemented as a
   union-find over these two exact keys — this is intentionally the cheapest, highest-confidence
   pass, and runs first so the probabilistic pass below only has to resolve what deterministic
   matching could not.
2. Probabilistic matching: every pair of records not already deterministically merged is scored on
   a weighted blend of four field similarities — name 0.35, address 0.35, phone 0.15, email 0.15 —
   each computed with Python's stdlib `difflib.SequenceMatcher.ratio()` (a real, if simplified,
   string-edit-distance-based similarity; disclosed here as a stand-in for a production system's
   Jaro-Winkler/phonetic-matching library, not a claim of using one). A pair merges only if its
   combined score clears `PROBABILISTIC_MATCH_THRESHOLD` — calibrated against this module's own
   real synthetic fixture (see `tests/identity_resolution/test_entity_resolution.py`), including a
   deliberate near-miss pair that must NOT merge, so the threshold is demonstrated to reject a
   false match, not just accept true ones.
3. Golden record: every connected component (cluster) of matched source records becomes one
   `customer_360_id`. Survivorship rule: `most_recently_updated_source_record_wins` — the field
   values from the source record with the latest `last_updated_utc` in each cluster become that
   golden record's values; every contributing source record is still listed in the match-pairs
   output, so no information is silently discarded, only which values "win" for display.

OUTPUT SCHEMA (`identity_match_pairs.csv`) — exactly as specified in the architecture review:
`customer_360_id, source_system, source_customer_id, match_score, match_method,
survivorship_rule, confidence`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

# Calibrated against this module's own real synthetic fixture (see the test module) — the
# deliberate near-miss pair (Michael Brown / Michelle Brown, different first name, different
# street, different city-neighborhood) scores below this threshold in a real run; the two
# deliberate true-positive probabilistic pairs (Robert/Rob Smith, Jennifer/Jen Lee) score above it.
# Not an arbitrary/guessed constant — see the test module's own assertions on the real numbers.
PROBABILISTIC_MATCH_THRESHOLD = 0.72

# Duplicate-detection review tier: a real MDM/identity-resolution pattern this module previously
# lacked - a pair scoring below the auto-merge threshold but clearly closer than the general
# population is not silently dropped, it is flagged for a human steward to review. Calibrated
# against this module's own real, computed score distribution (see resolve_identities' own
# pairwise diagnostics): the deliberate near-miss pair (Michael Brown / Michelle Brown) scores
# 0.6978 - the next-highest unrelated pair in this fixture scores 0.5921. 0.60 sits cleanly in
# that real gap, so it isolates exactly the one genuine near-miss without sweeping in the general
# population of unrelated pairs (all of which score well under 0.55 in this fixture).
REVIEW_THRESHOLD = 0.60

SIMILARITY_WEIGHTS = {"name": 0.35, "address": 0.35, "phone": 0.15, "email": 0.15}

DETERMINISTIC_EMAIL = "deterministic_email"
DETERMINISTIC_PHONE = "deterministic_phone"
PROBABILISTIC = "probabilistic"
SINGLE_SOURCE = "single_source_no_match"
FLAGGED_FOR_REVIEW = "flagged_for_review_possible_duplicate"

SURVIVORSHIP_RULE = "most_recently_updated_source_record_wins"


@dataclass
class SourceRecord:
    source_system: str
    source_customer_id: str
    full_name: str
    email: str
    phone: str
    address_line1: str
    city: str
    state: str
    zip: str
    last_updated_utc: str

    @property
    def row_key(self) -> tuple[str, str]:
        return (self.source_system, self.source_customer_id)


def _norm_email(email: str) -> str:
    return email.strip().lower()


def _norm_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _norm_address(rec: SourceRecord) -> str:
    parts = [rec.address_line1, rec.city, rec.state, rec.zip]
    return re.sub(r"\s+", " ", " ".join(p.strip().lower() for p in parts if p))


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def probabilistic_score(a: SourceRecord, b: SourceRecord) -> float:
    """Real, inspectable weighted blend — never a black box. Each component is independently
    testable (see the test module)."""
    name_sim = _similarity(_norm_name(a.full_name), _norm_name(b.full_name))
    addr_sim = _similarity(_norm_address(a), _norm_address(b))
    phone_sim = _similarity(_norm_phone(a.phone), _norm_phone(b.phone))
    email_sim = _similarity(_norm_email(a.email), _norm_email(b.email))
    return (
        SIMILARITY_WEIGHTS["name"] * name_sim
        + SIMILARITY_WEIGHTS["address"] * addr_sim
        + SIMILARITY_WEIGHTS["phone"] * phone_sim
        + SIMILARITY_WEIGHTS["email"] * email_sim
    )


class _UnionFind:
    def __init__(self, keys):
        self._parent = {k: k for k in keys}

    def find(self, k):
        while self._parent[k] != k:
            self._parent[k] = self._parent[self._parent[k]]
            k = self._parent[k]
        return k

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[rb] = ra


@dataclass
class MatchPair:
    customer_360_id: str
    source_system: str
    source_customer_id: str
    match_score: float
    match_method: str
    survivorship_rule: str
    confidence: str


@dataclass
class GoldenRecord:
    customer_360_id: str
    full_name: str
    email: str
    phone: str
    address_line1: str
    city: str
    state: str
    zip: str
    survived_from_source: str
    n_source_records: int
    source_systems: str


def _confidence_for(match_method: str, score: float) -> str:
    if match_method in (DETERMINISTIC_EMAIL, DETERMINISTIC_PHONE):
        return "HIGH"
    if match_method == PROBABILISTIC:
        return "MEDIUM" if score < 0.90 else "HIGH"
    return "N/A"  # single_source_no_match — nothing to have confidence about, not a low score


def resolve_identities(
    records: list[SourceRecord],
) -> tuple[list[MatchPair], list[GoldenRecord], dict]:
    """Runs the full deterministic -> probabilistic -> golden-record pipeline described in this
    module's own docstring. Returns (match_pairs, golden_records, diagnostics) — diagnostics
    includes every pairwise probabilistic score computed, so a caller (or a test) can audit
    exactly why a pair did or did not merge, never just trust a final label."""
    keys = [r.row_key for r in records]
    uf = _UnionFind(keys)

    edge_methods: dict[tuple, tuple[str, float]] = {}

    # Pass 1 — deterministic.
    by_email: dict[str, list[tuple]] = {}
    by_phone: dict[str, list[tuple]] = {}
    for r in records:
        e = _norm_email(r.email)
        p = _norm_phone(r.phone)
        if e:
            by_email.setdefault(e, []).append(r.row_key)
        if p:
            by_phone.setdefault(p, []).append(r.row_key)
    for group in by_email.values():
        for k in group[1:]:
            uf.union(group[0], k)
            edge_methods[frozenset((group[0], k))] = (DETERMINISTIC_EMAIL, 1.0)
    for group in by_phone.values():
        for k in group[1:]:
            uf.union(group[0], k)
            edge_methods.setdefault(frozenset((group[0], k)), (DETERMINISTIC_PHONE, 1.0))

    # Pass 2 — probabilistic, only over pairs not already deterministically merged. Small fixture
    # (real production would block by e.g. zip/state first) — full O(n^2) is fine at this scale and
    # disclosed as such rather than silently only ever demonstrating the cheap path.
    pairwise_scores: list[dict] = []
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            a, b = records[i], records[j]
            if uf.find(a.row_key) == uf.find(b.row_key):
                continue  # already merged deterministically
            score = probabilistic_score(a, b)
            merged = score >= PROBABILISTIC_MATCH_THRESHOLD
            flagged_for_review = (not merged) and score >= REVIEW_THRESHOLD
            pairwise_scores.append(
                {
                    "a": a.row_key,
                    "b": b.row_key,
                    "score": round(score, 4),
                    "merged": merged,
                    "flagged_for_review": flagged_for_review,
                }
            )
            if merged:
                uf.union(a.row_key, b.row_key)
                edge_methods[frozenset((a.row_key, b.row_key))] = (PROBABILISTIC, round(score, 4))

    # Pass 3 — cluster -> customer_360_id (deterministic, stable ordering by first-seen row).
    clusters: dict = {}
    for r in records:
        root = uf.find(r.row_key)
        clusters.setdefault(root, []).append(r)
    ordered_roots = sorted(clusters.keys(), key=lambda root: keys.index(root))
    root_to_id = {root: f"C360-{i+1:04d}" for i, root in enumerate(ordered_roots)}

    match_pairs: list[MatchPair] = []
    golden_records: list[GoldenRecord] = []
    for root, members in clusters.items():
        c360_id = root_to_id[root]
        for m in members:
            if len(members) == 1:
                method, score = SINGLE_SOURCE, 1.0
            else:
                # Report the strongest real edge touching this member within its cluster.
                candidates = [
                    edge_methods[fs]
                    for fs in edge_methods
                    if m.row_key in fs and uf.find(next(iter(fs))) == root
                ]
                method, score = max(candidates, key=lambda ms: ms[1]) if candidates else (PROBABILISTIC, 0.0)
            match_pairs.append(
                MatchPair(
                    customer_360_id=c360_id,
                    source_system=m.source_system,
                    source_customer_id=m.source_customer_id,
                    match_score=score,
                    match_method=method,
                    survivorship_rule=SURVIVORSHIP_RULE,
                    confidence=_confidence_for(method, score),
                )
            )
        survivor = max(members, key=lambda m: m.last_updated_utc)
        golden_records.append(
            GoldenRecord(
                customer_360_id=c360_id,
                full_name=survivor.full_name,
                email=survivor.email,
                phone=survivor.phone,
                address_line1=survivor.address_line1,
                city=survivor.city,
                state=survivor.state,
                zip=survivor.zip,
                survived_from_source=f"{survivor.source_system}:{survivor.source_customer_id}",
                n_source_records=len(members),
                source_systems=",".join(sorted({m.source_system for m in members})),
            )
        )

    match_pairs.sort(key=lambda mp: (mp.customer_360_id, mp.source_system, mp.source_customer_id))
    golden_records.sort(key=lambda g: g.customer_360_id)

    # Duplicate-detection review queue: every real pair this run scored as flagged_for_review,
    # NEVER auto-merged - a human steward decision, not this module's. Real, re-derivable from
    # pairwise_probabilistic_scores; kept as its own list so a caller never has to re-filter it.
    duplicate_review_queue = [s for s in pairwise_scores if s["flagged_for_review"]]

    diagnostics = {
        "pairwise_probabilistic_scores": pairwise_scores,
        "threshold": PROBABILISTIC_MATCH_THRESHOLD,
        "review_threshold": REVIEW_THRESHOLD,
        "duplicate_review_queue": duplicate_review_queue,
    }
    return match_pairs, golden_records, diagnostics
