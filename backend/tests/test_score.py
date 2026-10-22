from app.score import RallyInput, ScoreRules, derive_score_timeline, expected_court, score_at_time


def rally(id_: str, start: float, winner: str | None, **kwargs) -> RallyInput:
    return RallyInput(
        id=id_,
        start_time=start,
        end_time=start + 5,
        winner=winner,  # type: ignore[arg-type]
        **kwargs,
    )


def test_server_keeps_serve_and_changes_court_after_winning_point():
    timeline = derive_score_timeline(
        ScoreRules(first_server="A"),
        [rally("1", 0, "A"), rally("2", 10, "A")],
    )
    assert timeline[0]["serve_court_before"] == "right"
    assert timeline[0]["serve_court_after"] == "left"
    assert timeline[1]["serve_court_before"] == "left"
    assert timeline[1]["score_after"] == {"A": 2, "B": 0}


def test_receiver_becomes_server_and_uses_own_score_parity():
    timeline = derive_score_timeline(
        ScoreRules(first_server="A"),
        [rally("1", 0, "B")],
    )
    assert timeline[0]["server_after"] == "B"
    assert timeline[0]["serve_court_after"] == "left"
    assert timeline[0]["score_after"] == {"A": 0, "B": 1}


def test_let_does_not_change_score_or_server_or_court():
    timeline = derive_score_timeline(
        ScoreRules(first_server="A"),
        [
            rally("1", 0, None, is_let=True, confidence=0.9),
            rally("2", 10, "A"),
        ],
    )
    assert timeline[0]["score_after"] == {"A": 0, "B": 0}
    assert timeline[0]["serve_court_after"] == "right"
    assert timeline[1]["serve_court_before"] == "right"
    assert timeline[1]["let_candidate"] is True


def test_history_edit_cascades_through_service_state():
    timeline = derive_score_timeline(
        ScoreRules(first_server="A", initial_a_score=4, initial_b_score=2),
        [rally("1", 0, "A"), rally("2", 10, "B")],
    )
    assert timeline[0]["serve_court_before"] == "right"
    assert timeline[1]["server_before"] == "A"
    assert timeline[1]["serve_court_before"] == "left"
    assert timeline[1]["score_after"] == {"A": 5, "B": 3}


def test_score_at_time_uses_pre_and_post_rally_score():
    timeline = derive_score_timeline(
        ScoreRules(first_server="A"),
        [rally("1", 0, "A")],
    )
    assert score_at_time(ScoreRules(first_server="A"), timeline, 2)["score"] == {
        "A": 0,
        "B": 0,
    }
    assert score_at_time(ScoreRules(first_server="A"), timeline, 5)["score"] == {
        "A": 1,
        "B": 0,
    }


def test_court_mapping_matches_badminton_rule():
    assert expected_court(0) == "right"
    assert expected_court(1) == "left"
    assert expected_court(2) == "right"

def test_repeated_service_is_automatically_marked_as_let_pending_confirmation():
    timeline = derive_score_timeline(
        ScoreRules(first_server="A", confidence_threshold=0.1),
        [
            rally("1", 0, None, is_let=True, let_confirmed=True, confidence=0.9, verified=True),
            rally("2", 10, "A", let_confirmed=False, confidence=0.9, verified=True),
        ],
    )
    assert timeline[1]["let_candidate"] is True
    assert timeline[1]["auto_let"] is True
    assert timeline[1]["is_let"] is True
    assert timeline[1]["unresolved"] is True
    assert timeline[1]["score_after"] == {"A": 0, "B": 0}
    assert timeline[1]["serve_court_after"] == "right"


def test_user_can_reject_automatic_let_and_count_the_point():
    timeline = derive_score_timeline(
        ScoreRules(first_server="A", confidence_threshold=0.1),
        [
            rally("1", 0, None, is_let=True, let_confirmed=True, confidence=0.9, verified=True),
            rally("2", 10, "A", is_let=False, let_confirmed=True, confidence=0.9, verified=True),
        ],
    )
    assert timeline[1]["auto_let"] is False
    assert timeline[1]["is_let"] is False
    assert timeline[1]["score_after"] == {"A": 1, "B": 0}
def test_invalid_rally_does_not_change_score_or_service_state():
    timeline = derive_score_timeline(
        ScoreRules(first_server="A", confidence_threshold=0.1),
        [
            rally("1", 0, "A", confidence=0.9, verified=True),
            rally("2", 10, "B", is_valid=False, confidence=1.0, verified=True),
            rally("3", 20, "A", confidence=0.9, verified=True),
        ],
    )
    invalid = timeline[1]
    assert invalid["is_valid"] is False
    assert invalid["winner"] is None
    assert invalid["score_after"] == {"A": 1, "B": 0}
    assert invalid["server_after"] == "A"
    assert invalid["serve_court_after"] == "left"
    assert invalid["unresolved"] is False
    assert timeline[2]["score_after"] == {"A": 2, "B": 0}
def test_auto_score_waits_until_next_valid_rally_before_updating():
    rules = ScoreRules(first_server="A")
    timeline = derive_score_timeline(
        rules,
        [rally("1", 0, "A"), rally("2", 10, "B")],
    )
    assert timeline[0]["score_update_time"] == 10.0
    assert score_at_time(rules, timeline, 6)["score"] == {"A": 0, "B": 0}
    assert score_at_time(rules, timeline, 10.0)["score"] == {"A": 1, "B": 0}
def test_confirmed_landing_updates_score_at_rally_end():
    rules = ScoreRules(first_server="A")
    timeline = derive_score_timeline(
        rules,
        [rally("1", 0, "A", verified=True), rally("2", 10, "B")],
    )
    assert timeline[0]["score_update_time"] == 5.0
    assert score_at_time(rules, timeline, 5.0)["score"] == {"A": 1, "B": 0}