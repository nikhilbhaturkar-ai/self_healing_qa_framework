from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import ROOT_DIR
from framework.scenario_generation.service import generate_feature, index_repository

app = FastAPI(title="RAG Cucumber Scenario Generator", version="0.1.0")
_ALLOWED_ROOT = Path(os.getenv("SCENARIO_GENERATOR_ALLOWED_ROOT", str(ROOT_DIR))).expanduser().resolve()


class IndexRequest(BaseModel):
    repo_path: str
    application: str | None = None
    module: str | None = None
    role: str | None = None


class GenerateRequest(BaseModel):
    repo_path: str
    requirement: str = Field(min_length=1, max_length=12000)
    application: str | None = None
    module: str | None = None
    role: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=30)
    output_name: str | None = None


def _allowed_repository(raw_path: str) -> Path:
    root = Path(raw_path).expanduser().resolve()
    if root != _ALLOWED_ROOT and _ALLOWED_ROOT not in root.parents:
        raise HTTPException(status_code=403, detail="Repository path is outside the configured allowed root")
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="Repository directory was not found")
    return root


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "allowed_root": _ALLOWED_ROOT.as_posix()}


@app.post("/index")
def index(request: IndexRequest) -> dict[str, Any]:
    root = _allowed_repository(request.repo_path)
    try:
        return index_repository(
            root,
            application=request.application,
            module=request.module,
            role=request.role,
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/generate")
def generate(request: GenerateRequest) -> dict[str, Any]:
    root = _allowed_repository(request.repo_path)
    try:
        return generate_feature(
            root,
            request.requirement,
            application=request.application,
            module=request.module,
            role=request.role,
            tags=request.tags,
            output_name=request.output_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc