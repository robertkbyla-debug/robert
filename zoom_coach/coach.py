"""The coaching engine: sends the live transcript + project context to Claude."""

from __future__ import annotations

import json
import logging
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class Tip(BaseModel):
    kind: Literal["ask", "steer", "clarify", "listen", "warn", "close"] = Field(
        description="ask = question to pose, steer = redirect the topic, clarify = pin down something vague, "
        "listen = hold back and let them talk, warn = a risk or mistake to avoid, close = lock in a commitment"
    )
    text: str = Field(description="What to say or do, short enough to glance at mid-call")
    why: str = Field(description="One short clause on why this helps reach the goals")
    priority: Literal["high", "medium", "low"]


class GoalStatus(BaseModel):
    goal: str
    status: Literal["not_started", "in_progress", "achieved", "at_risk"]
    evidence: str = Field(description="What in the conversation supports this status, or what is still missing")


class CoachingUpdate(BaseModel):
    read: str = Field(description="One sentence: where the conversation stands right now and its mood")
    say_next: str = Field(description="The single best thing to say next, phrased so it can be said verbatim")
    tips: list[Tip]
    goals: list[GoalStatus]
    risks: list[str] = Field(description="Objections, concerns or red flags raised and not yet handled")
    open_questions: list[str] = Field(description="Questions or topics raised but left unresolved")
    running_summary: str = Field(description="Compact summary of the whole call so far, including facts learned")


class ActionItem(BaseModel):
    owner: str
    item: str
    due: str = Field(description="Due date or timing if mentioned, otherwise an empty string")


class Debrief(BaseModel):
    summary: str
    outcome: str = Field(description="What was actually achieved relative to the goals, stated plainly")
    decisions: list[str]
    action_items: list[ActionItem]
    goals: list[GoalStatus]
    missed_opportunities: list[str]
    follow_up_email: str = Field(description="A ready-to-send follow-up email in plain text")


COACH_INSTRUCTIONS = """\
You are a live conversation coach. The user is in a video call right now and glances at your \
advice in a side panel while talking. You receive the call transcript as it is produced, the \
user's project context, their goals for the call and quick notes they type during it.

Your job is to help them steer the conversation toward useful, concrete outcomes for their project.

How to coach:
- Ground every tip in something specific: a line from the transcript, a fact from the project \
context, or a stated goal. Use names, numbers and details from the context when they help.
- Focus on what should happen in the next minute or two. Prioritise: unanswered objections, \
goals not yet touched, moments to ask for a commitment, and facts worth verifying.
- Suggest questions that uncover needs, constraints, decision makers, timelines and budget \
when those serve the goals; suggest steering back when the call drifts.
- `say_next` is the single most valuable next line. Make it natural and speakable, not a \
script-like pitch. If the best move is to let the other person keep talking, say so.
- Give 2 to 5 tips, highest value first. Do not repeat advice from the previous update unless \
it is still the top priority and has not been acted on; if the user already did it, move on.
- Treat the user's live notes as the most recent and most authoritative signal of their intent.
- Transcripts come from speech recognition: expect wrong words, missing punctuation and \
mislabelled or missing speakers. Infer sensibly and never quote a garbled phrase as fact.
- If the transcript is too short to judge, give brief opening advice based on the goals and context.
- Be direct and concise. The user reads this in a few seconds while someone is talking to them.
"""

DEBRIEF_INSTRUCTIONS = """\
You are a conversation coach writing a post-call debrief. Using the transcript, the project \
context, the user's goals and notes, produce an honest assessment of the call: what was achieved, \
what was decided, who owes what, which opportunities were missed, and a follow-up email the user \
can send. Only include decisions and action items that the transcript supports; the transcript \
comes from speech recognition, so read past recognition errors.
"""


class CoachError(RuntimeError):
    pass


class Coach:
    def __init__(
        self,
        context: str,
        *,
        me: str | None = None,
        model: str = DEFAULT_MODEL,
        effort: str = "low",
        debrief_effort: str = "high",
        use_fallbacks: bool = True,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self.client = client or anthropic.AsyncAnthropic()
        self.context = context
        self.me = me
        self.model = model
        self.effort = effort
        self.debrief_effort = debrief_effort
        self.use_fallbacks = use_fallbacks

    def _system(self, instructions: str) -> list[dict]:
        # Stable across the whole call, so it is cached after the first request.
        context = self.context or "(No project context was provided.)"
        return [
            {"type": "text", "text": instructions},
            {
                "type": "text",
                "text": f"<project_context>\n{context}\n</project_context>",
                "cache_control": {"type": "ephemeral"},
            },
        ]

    def _situation(
        self,
        *,
        title: str,
        goals: list[str],
        notes: list[str],
        transcript: str,
        truncated: bool,
        summary: str | None,
        elapsed_min: float,
    ) -> str:
        parts = [f"<call title={json.dumps(title)} elapsed_minutes=\"{elapsed_min:.0f}\">"]
        if self.me:
            parts.append(f"The user appears in the transcript as: {self.me}")
        goal_lines = "\n".join(f"- {g}" for g in goals) or "- (none stated; infer sensible goals from the context)"
        parts.append(f"<goals>\n{goal_lines}\n</goals>")
        if notes:
            parts.append("<live_notes>\n" + "\n".join(f"- {n}" for n in notes) + "\n</live_notes>")
        if truncated and summary:
            parts.append(f"<summary_of_earlier_call>\n{summary}\n</summary_of_earlier_call>")
        parts.append(f"<transcript>\n{transcript or '(nothing transcribed yet)'}\n</transcript>")
        parts.append("</call>")
        return "\n\n".join(parts)

    async def _parse(self, *, instructions: str, user: str, output: type[BaseModel], effort: str):
        extra: dict = {}
        if self.use_fallbacks:
            extra = {"extra_headers": {"anthropic-beta": FALLBACK_BETA}, "extra_body": {"fallbacks": "default"}}
        response = await self.client.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=self._system(instructions),
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort},
            output_format=output,
            **extra,
        )
        log.debug(
            "usage: in=%s cache_read=%s out=%s",
            response.usage.input_tokens,
            response.usage.cache_read_input_tokens,
            response.usage.output_tokens,
        )
        if response.stop_reason == "refusal":
            raise CoachError("Claude declined to analyse this part of the call.")
        if response.stop_reason == "max_tokens":
            raise CoachError("The response was cut off; try again.")
        if response.parsed_output is None:
            raise CoachError("Claude returned no usable coaching output.")
        return response.parsed_output

    async def analyze(
        self,
        *,
        title: str,
        goals: list[str],
        notes: list[str],
        transcript: str,
        truncated: bool,
        previous: CoachingUpdate | None,
        elapsed_min: float,
    ) -> CoachingUpdate:
        user = self._situation(
            title=title,
            goals=goals,
            notes=notes,
            transcript=transcript,
            truncated=truncated,
            summary=previous.running_summary if previous else None,
            elapsed_min=elapsed_min,
        )
        if previous:
            shown = previous.model_dump(include={"say_next", "tips"})
            user += f"\n\n<previous_update>\n{json.dumps(shown, indent=1)}\n</previous_update>"
        user += "\n\nGive your coaching update for this moment of the call."
        return await self._parse(instructions=COACH_INSTRUCTIONS, user=user, output=CoachingUpdate, effort=self.effort)

    async def debrief(
        self,
        *,
        title: str,
        goals: list[str],
        notes: list[str],
        transcript: str,
        truncated: bool,
        summary: str | None,
        elapsed_min: float,
    ) -> Debrief:
        user = self._situation(
            title=title,
            goals=goals,
            notes=notes,
            transcript=transcript,
            truncated=truncated,
            summary=summary,
            elapsed_min=elapsed_min,
        )
        user += "\n\nThe call has ended. Write the debrief."
        return await self._parse(
            instructions=DEBRIEF_INSTRUCTIONS, user=user, output=Debrief, effort=self.debrief_effort
        )
