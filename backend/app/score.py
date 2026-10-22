from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Player = Literal["A", "B"]
CourtSide = Literal["left", "right"]


@dataclass(frozen=True)
class ScoreRules:
    initial_a_score: int = 0
    initial_b_score: int = 0
    first_server: Player = "A"
    first_server_court: CourtSide | None = None
    confidence_threshold: float = 0.55


@dataclass(frozen=True)
class RallyInput:
    id: str
    start_time: float
    end_time: float
    winner: Player | None
    is_valid: bool = True
    is_let: bool = False
    let_confirmed: bool = False
    confidence: float = 0.0
    verified: bool = False
    source: str = "ai"
    note: str | None = None


def expected_court(server_score: int) -> CourtSide:
    return "right" if server_score % 2 == 0 else "left"


def derive_score_timeline(rules: ScoreRules, rallies: list[RallyInput]) -> list[dict]:
    ordered = sorted(rallies, key=lambda rally: (rally.start_time, rally.end_time))
    scores: dict[Player, int] = {
        "A": rules.initial_a_score,
        "B": rules.initial_b_score,
    }
    server: Player = rules.first_server
    serve_court: CourtSide = rules.first_server_court or expected_court(scores[server])
    previous: dict | None = None
    output: list[dict] = []

    for index, rally in enumerate(ordered):
        score_before = {"A": scores["A"], "B": scores["B"]}
        repeated_service = bool(
            rally.is_valid
            and previous
            and previous["is_valid"]
            and previous["server_before"] == server
            and previous["serve_court_before"] == serve_court
            and previous["score_before"] == score_before
        )

        auto_let = repeated_service and not rally.let_confirmed
        effective_let = rally.is_valid and (rally.is_let or auto_let)
        winner = None if (not rally.is_valid or effective_let) else rally.winner
        if winner is not None:
            scores[winner] += 1

        score_after = {"A": scores["A"], "B": scores["B"]}
        if not rally.is_valid or effective_let:
            server_after = server
        elif winner is not None:
            server_after = winner
        else:
            server_after = server

        if not rally.is_valid or (effective_let and previous is not None):
            court_after = serve_court
        else:
            court_after = expected_court(scores[server_after])

        unresolved = False if not rally.is_valid else (
            (winner is None and not effective_let)
            or (auto_let and not rally.let_confirmed)
            or (not rally.verified and rally.confidence < rules.confidence_threshold)
        )

        next_valid_start = next(
            (
                candidate.start_time
                for candidate in ordered[index + 1 :]
                if candidate.is_valid and candidate.start_time >= rally.end_time - 0.001
            ),
            None,
        )
        score_update_time = rally.end_time
        landing_confirmed = rally.verified or bool(
            rally.note and "轨迹落点判断" in rally.note
        )
        if next_valid_start is not None and not landing_confirmed:
            score_update_time = max(rally.end_time, next_valid_start)

        item = {
            "id": rally.id,
            "order_index": index,
            "start_time": round(rally.start_time, 3),
            "end_time": round(rally.end_time, 3),
            "score_update_time": round(score_update_time, 3),
            "winner": winner,
            "is_valid": rally.is_valid,
            "is_let": effective_let,
            "auto_let": auto_let,
            "let_confirmed": rally.let_confirmed,
            "let_candidate": repeated_service,
            "confidence": round(rally.confidence, 3),
            "verified": rally.verified,
            "unresolved": unresolved,
            "source": rally.source,
            "note": rally.note,
            "score_before": score_before,
            "score_after": score_after,
            "server_before": server,
            "server_after": server_after,
            "serve_court_before": serve_court,
            "serve_court_after": court_after,
        }
        output.append(item)
        previous = item
        server = server_after
        serve_court = court_after

    return output


def score_at_time(
    rules: ScoreRules, timeline: list[dict], time_seconds: float
) -> dict:
    score = {"A": rules.initial_a_score, "B": rules.initial_b_score}
    server = rules.first_server
    serve_court = rules.first_server_court or expected_court(score[server])

    for item in timeline:
        if time_seconds >= item["score_update_time"]:
            score = item["score_after"]
            server = item["server_after"]
            serve_court = item["serve_court_after"]
            continue
        if time_seconds >= item["start_time"]:
            score = item["score_before"]
            server = item["server_before"]
            serve_court = item["serve_court_before"]
        break

    return {
        "score": score,
        "server": server,
        "serve_court": serve_court,
    }


def public_rally(item: dict) -> dict:
    return dict(item)


def timeline_as_dicts(timeline: list[dict]) -> list[dict]:
    return [dict(item) for item in timeline]


def dataclass_to_dict(value: object) -> dict:
    return asdict(value)