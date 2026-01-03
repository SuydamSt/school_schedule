from __future__ import annotations

from pathlib import Path
from typing import Optional

from scheduler.models import InputData

DEFAULT_PATH = Path("data.json")


def save_data(data: InputData, path: Path = DEFAULT_PATH) -> None:
    path.write_text(data.model_dump_json(indent=2), encoding="utf-8")


def load_data(path: Path = DEFAULT_PATH) -> Optional[InputData]:
    if not path.exists():
        return None
    return InputData.model_validate_json(path.read_text(encoding="utf-8"))
