#!/usr/bin/env python3
"""Shared source-weight scoring. ONE definition, imported by build.py / rank.py / the dashboard.

Three distinct source classes, per Harbor guidance (points are per citing model per document):
  blog_headliner  = 3  # a chart or paragraph about a SINGLE benchmark in a release blog
  model_card      = 2  # a multi-benchmark comparison table (standalone card OR a table in a blog)
  system_card     = 1  # a row in the long-form system-card paper (NOT divided by table size)

There is NO table-size discount. A benchmark's weight in ONE document (for ONE model) is the
MAX over its mentions there, so a benchmark that is both a headline chart and a table row in the
same blog counts 3 (not 3+2); the same benchmark headlined in 3 different blogs counts 3+3+3=9.
This module intentionally does NOT compute any composite priority score (deferred project).
"""
from __future__ import annotations

WEIGHT_CLASS_POINTS = {"blog_headliner": 3, "model_card": 2, "system_card": 1}


def points(weight_class) -> int:
    return WEIGHT_CLASS_POINTS.get(weight_class, 0)
