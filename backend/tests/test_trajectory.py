from app.trajectory import ShuttlePoint, TrajectoryResult, infer_winner_from_landing


def trajectory(side: str | None, in_court: bool | None, confidence: float = 0.8) -> TrajectoryResult:
    points = (
        ShuttlePoint(1.0, 0.5, 0.3, 0.7),
        ShuttlePoint(1.5, 0.52, 0.4, 0.7),
    )
    return TrajectoryResult(points, 0.6, side, in_court, confidence)


def test_top_court_landing_means_bottom_player_wins():
    assert infer_winner_from_landing(trajectory("top", True), "bottom") == ("A", 0.8)


def test_bottom_court_landing_means_top_player_wins():
    assert infer_winner_from_landing(trajectory("bottom", True), "bottom") == ("B", 0.8)


def test_out_landing_on_top_side_means_top_player_wins():
    assert infer_winner_from_landing(trajectory("top", False), "bottom") == ("B", 0.8)


def test_missing_or_low_confidence_landing_falls_back():
    assert infer_winner_from_landing(trajectory(None, None), "bottom") is None
    assert infer_winner_from_landing(trajectory("top", True, 0.4), "bottom") is None