from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Player = Literal["A", "B"]
CourtSide = Literal["left", "right"]
VideoSide = Literal["top", "bottom"]
RallySource = Literal["ai", "manual", "split", "merged"]


class ProjectImport(BaseModel):
    path: str
    title: str | None = None
    player_a_name: str = "球员 A"
    player_b_name: str = "球员 B"
    initial_a_score: int = Field(default=0, ge=0)
    initial_b_score: int = Field(default=0, ge=0)
    first_server: Player = "A"
    first_server_court: CourtSide | None = None
    initial_a_side: VideoSide = "bottom"


class ProjectUpdate(BaseModel):
    title: str | None = None
    player_a_name: str | None = None
    player_b_name: str | None = None
    initial_a_score: int | None = Field(default=None, ge=0)
    initial_b_score: int | None = Field(default=None, ge=0)
    first_server: Player | None = None
    first_server_court: CourtSide | None = None
    initial_a_side: VideoSide | None = None
    court_points: list[list[float]] | None = None


class RallyUpdate(BaseModel):
    start_time: float | None = Field(default=None, ge=0)
    end_time: float | None = Field(default=None, ge=0)
    winner: Player | None = None
    is_valid: bool | None = None
    is_let: bool | None = None
    let_confirmed: bool | None = None
    verified: bool | None = None
    note: str | None = None


class RallyCreate(BaseModel):
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    winner: Player | None = None
    is_valid: bool = True
    is_let: bool = False
    note: str | None = None


class RallySplit(BaseModel):
    time: float = Field(gt=0)


class RallyMerge(BaseModel):
    first_id: str
    second_id: str


class SideSwapCreate(BaseModel):
    time: float = Field(ge=0)


class ExportCreate(BaseModel):
    kind: Literal["full", "highlights"] = "highlights"
    rally_ids: list[str] | None = None
