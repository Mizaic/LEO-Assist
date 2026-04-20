"""Game high-score endpoints — persisted to the patient graph.

Atlas trace:
  DO: DO-EC41233C
  DI: DI-9D0DF618
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EC41233C")
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.db.neo4j_client import PatientGraphClient
from libs.auth.org_scope import CallerScope, get_caller_scope

router = APIRouter(prefix="/games", tags=["games"])

GameName = Literal["snake", "invaders", "breakout"]


def _get_client() -> PatientGraphClient:
    client = PatientGraphClient()
    client.initialize_schema()
    return client


class ScoreSubmission(BaseModel):
    game: GameName
    player: str = Field(min_length=1, max_length=30)
    score: int = Field(ge=0)
    level: int = Field(default=1, ge=1)


class ScoreResponse(BaseModel):
    id: str
    game: str
    player: str
    score: int
    level: int
    created_at: str
    rank: int | None = None


@router.post("/scores", response_model=ScoreResponse)
def submit_score(
    body: ScoreSubmission,
    scope: CallerScope = Depends(get_caller_scope),
    client: PatientGraphClient = Depends(_get_client),
):
    _ = scope
    score_id = str(uuid.uuid4())
    rows = client.run(
        """
        CREATE (gs:GameScore {
            id: $id,
            game: $game,
            player: $player,
            score: $score,
            level: $level,
            created_at: datetime()
        })
        RETURN gs.id AS id, gs.game AS game, gs.player AS player,
               gs.score AS score, gs.level AS level,
               toString(gs.created_at) AS created_at
        """,
        id=score_id,
        game=body.game,
        player=body.player,
        score=body.score,
        level=body.level,
    )
    row = rows[0]
    rank_rows = client.run(
        """
        MATCH (gs:GameScore)
        WHERE gs.game = $game AND gs.score >= $score
        RETURN count(gs) AS rank
        """,
        game=body.game,
        score=body.score,
    )
    return ScoreResponse(**row, rank=rank_rows[0]["rank"] if rank_rows else None)


@router.get("/leaderboard", response_model=list[ScoreResponse])
def get_leaderboard(
    game: GameName = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    scope: CallerScope = Depends(get_caller_scope),
    client: PatientGraphClient = Depends(_get_client),
):
    _ = scope
    rows = client.run(
        """
        MATCH (gs:GameScore)
        WHERE gs.game = $game
        RETURN gs.id AS id, gs.game AS game, gs.player AS player,
               gs.score AS score, gs.level AS level,
               toString(gs.created_at) AS created_at
        ORDER BY gs.score DESC, gs.created_at ASC
        LIMIT $limit
        """,
        game=game,
        limit=limit,
    )
    return [ScoreResponse(**r, rank=i + 1) for i, r in enumerate(rows)]
