"""Loads the stored OPSIN traces written by backend/scripts/dump_traces.py."""

import json
from functools import lru_cache
from pathlib import Path

from app.opsin_trace import Trace, trace_from_dict

PATH = Path(__file__).with_name("explain_traces.json")


@lru_cache(maxsize=1)
def load_traces() -> dict[str, Trace]:
    data = json.loads(PATH.read_text())
    return {name: trace_from_dict(d) for name, d in data["traces"].items()}
