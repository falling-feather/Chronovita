"""Canonical authoring sources for the V0.10 flagship classroom lessons."""

from services.content.flagships.dayu_l101 import (
    COURSE_ID,
    DAYU_CORPUS_ID,
    DAYU_PRESENTATION_ID,
    DAYU_SCENARIO_ID,
    LESSON_ID,
    build_dayu_course_draft,
    build_dayu_evidence_draft,
    build_dayu_presentation,
    build_dayu_scenario_draft,
)
from services.content.flagships.shangyang_l103 import (
    COURSE_ID as SHANGYANG_COURSE_ID,
    LESSON_ID as SHANGYANG_LESSON_ID,
    SHANGYANG_CORPUS_ID,
    SHANGYANG_PRESENTATION_ID,
    SHANGYANG_SCENARIO_ID,
    build_shangyang_course_draft,
    build_shangyang_evidence_draft,
    build_shangyang_presentation,
    build_shangyang_scenario_draft,
)

__all__ = [
    "COURSE_ID",
    "DAYU_CORPUS_ID",
    "DAYU_PRESENTATION_ID",
    "DAYU_SCENARIO_ID",
    "LESSON_ID",
    "SHANGYANG_CORPUS_ID",
    "SHANGYANG_COURSE_ID",
    "SHANGYANG_LESSON_ID",
    "SHANGYANG_PRESENTATION_ID",
    "SHANGYANG_SCENARIO_ID",
    "build_dayu_course_draft",
    "build_dayu_evidence_draft",
    "build_dayu_presentation",
    "build_dayu_scenario_draft",
    "build_shangyang_course_draft",
    "build_shangyang_evidence_draft",
    "build_shangyang_presentation",
    "build_shangyang_scenario_draft",
]
