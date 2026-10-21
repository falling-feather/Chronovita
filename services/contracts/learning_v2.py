"""Additive task and manual rubric snapshots; V1 records remain unchanged."""
from typing import Annotated, Literal
from pydantic import Field, TypeAdapter
from services.contracts.classroom_v1 import ClassroomTaskV1, LearningRubricV1
from services.contracts.learning_v1 import (LearningSubmissionRequestV1, LearningSubmissionV1,
    LearningFeedbackRequestV1, LearningFeedbackV1)


class LearningSubmissionRequestV2(LearningSubmissionRequestV1):
    schema_version: Literal['learning-submission-request/v2'] = 'learning-submission-request/v2'
    task: ClassroomTaskV1


class LearningSubmissionV2(LearningSubmissionV1):
    schema_version: Literal['learning-submission/v2'] = 'learning-submission/v2'
    task: ClassroomTaskV1


class LearningFeedbackRequestV2(LearningFeedbackRequestV1):
    schema_version: Literal['learning-feedback-request/v2'] = 'learning-feedback-request/v2'
    rubric: LearningRubricV1


class LearningFeedbackV2(LearningFeedbackV1):
    schema_version: Literal['learning-feedback/v2'] = 'learning-feedback/v2'
    rubric: LearningRubricV1


LearningSubmissionRequestAny = Annotated[LearningSubmissionRequestV1 | LearningSubmissionRequestV2, Field(discriminator='schema_version')]
LearningSubmissionAny = Annotated[LearningSubmissionV1 | LearningSubmissionV2, Field(discriminator='schema_version')]
LearningFeedbackRequestAny = Annotated[LearningFeedbackRequestV1 | LearningFeedbackRequestV2, Field(discriminator='schema_version')]
LearningFeedbackAny = Annotated[LearningFeedbackV1 | LearningFeedbackV2, Field(discriminator='schema_version')]
SUBMISSION_ADAPTER = TypeAdapter(LearningSubmissionAny)
FEEDBACK_ADAPTER = TypeAdapter(LearningFeedbackAny)
