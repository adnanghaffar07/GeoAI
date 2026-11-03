# ruff: noqa: E501  (plain-English answer sentences and the model prompt)
"""CR-006 "Ask about road risk" (cr-006-ask-road-risk-proposal.md, approved 2026-11-02, free only).

How an answer is made, so it stays correct with a small free model:
1. Plain rules recognise what is asked (top roads, one road, weather, roads without an inspection,
   what changed, alerts). Anything else: "I don't know" with example questions.
2. Ordinary code collects the facts from the app's own data, only what this person may see, and the
   links to the pages they come from.
3. A built-in answer is written from the facts. If the free local model (Ollama) answers in time, it
   rewrites the facts as a short reply; that reply is checked (no percentage, no new numbers) and the
   built-in answer is used if the check fails.
Never a percentage, never an action; each question and answer is kept in the project history.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from typing import Any

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import ProjectContext
from app.core.config import get_settings
from app.core.errors import ConflictError, TooManyRequestsError
from app.core.permissions import Perm
from app.models import Alert, AuditEvent, Inspection
from app.models.priority import ACTIVE_INSPECTION_STATES
from app.schemas.road_risk import AssistantAnswer, SourceLink
from app.services import road_risk
from app.services.audit import record_event

log = logging.getLogger(__name__)

ACTION = "assistant.asked"
TOP = 5
EXAMPLES = [
    "Which roads should we inspect first, and why?",
    "Why is <road name> high risk?",
    "Will the weather this week affect our roads?",
    "Which high-risk roads have no inspection planned?",
]
INTENTS: list[tuple[str, tuple[str, ...]]] = [
    (
        "no_inspection",
        ("no inspection", "not inspected", "without inspection", "not planned", "unplanned"),
    ),
    ("weather", ("weather", "freeze", "frost", "thaw", "rain", "snow", "cold", "forecast")),
    ("changes", ("changed", "change", "since last", "new this week", "turned")),
    ("alerts", ("alert", "warning", "notification")),
    ("top", ("first", "inspect", "top", "worst", "riskiest", "highest", "which roads", "priority")),
]


@dataclass
class Facts:
    lines: list[str] = field(default_factory=list)
    sources: list[SourceLink] = field(default_factory=list)


def _level_word(level: str | None) -> str:
    return f"{level} risk" if level else "no level yet"


def _road_line(item: Any) -> str:
    reasons = [r.label if r.value is None else f"{r.label}: {r.value:g}" for r in item.reasons]
    if not reasons:
        reasons = [
            f"{f.label} ({f.level})"
            for f in item.factors
            if f.kind == "risk" and f.level in ("high", "medium")
        ]
    because = f" because of: {'; '.join(reasons)}" if reasons else ""
    return f"{item.name or 'Unnamed road'} is {_level_word(item.level)} (number {item.position} on the list){because}."


def _road_link(ctx: ProjectContext, item: Any) -> SourceLink:
    return SourceLink(
        label=item.name or "Unnamed road",
        path=f"/projects/{ctx.project.id}/road-risk/{item.section_id}",
    )


def intent_of(question: str, road_names: list[str]) -> tuple[str, str | None]:
    text = question.lower()
    named = next(
        (
            name
            for name in sorted(road_names, key=len, reverse=True)
            if name and name.lower() in text
        ),
        None,
    )
    for intent, words in INTENTS:
        if any(word in text for word in words):
            if intent == "top" and named and "why" in text:
                return "road", named
            return intent, named
    if named:
        return "road", named
    return "unknown", None


def collect(db: Session, ctx: ProjectContext, intent: str, named: str | None) -> Facts:
    risk = road_risk.project_risk_for(db, ctx.project.id)
    facts = Facts()
    risk_page = SourceLink(label="Road risk", path=f"/projects/{ctx.project.id}/road-risk")
    if risk.levels_run:
        facts.lines.append(
            f"The levels are from Monday {risk.levels_run.as_of} (model {risk.levels_run.model_version})."
        )
    elif risk.factors_run:
        facts.lines.append(
            f"Only risk factors are available here (updated {risk.factors_run.as_of}); there is no tested forecast."
        )
    if not risk.items:
        facts.lines.append("There are no road levels or risk factors for this project yet.")
        facts.sources.append(risk_page)
        return facts

    if intent == "top":
        top = [i for i in risk.items if i.level in ("high", "medium")][:TOP] or risk.items[:TOP]
        facts.lines += [_road_line(i) for i in top]
        facts.sources += [_road_link(ctx, i) for i in top] + [risk_page]
    elif intent == "road":
        matches = [i for i in risk.items if (i.name or "").lower() == (named or "").lower()][:3]
        facts.lines += [_road_line(i) for i in matches]
        facts.lines += [
            f"Missing inputs for it: {', '.join(i.missing_inputs)}."
            for i in matches
            if i.missing_inputs
        ]
        facts.sources += [_road_link(ctx, i) for i in matches]
    elif intent == "weather":
        outlook = road_risk.outlook(db, ctx.project.id)
        if outlook is None:
            facts.lines.append("The 7-day weather outlook is not available yet.")
        else:
            facts.lines.append(
                f"Next 7 days (National Weather Service, {outlook.source}): {outlook.freeze_thaw_days} freeze-thaw days, "
                f"{outlook.frost_days} frost days, {outlook.heavy_rain_days} heavy-rain days, snow {outlook.snow_mm:g} mm."
            )
            exposed = [i for i in risk.items if i.level in ("high", "medium")][:TOP]
            if exposed and (outlook.freeze_thaw_days or outlook.heavy_rain_days):
                facts.lines.append(
                    "Roads already at high or medium risk that this weather may affect most:"
                )
                facts.lines += [_road_line(i) for i in exposed]
                facts.sources += [_road_link(ctx, i) for i in exposed]
        facts.sources.append(risk_page)
    elif intent == "no_inspection":
        planned = set(
            db.scalars(
                select(Inspection.section_id).where(
                    Inspection.project_id == ctx.project.id,
                    Inspection.status.in_(ACTIVE_INSPECTION_STATES),
                )
            )
        )
        waiting = [i for i in risk.items if i.level == "high" and i.section_id not in planned][:TOP]
        if waiting:
            facts.lines.append("High-risk roads with no open inspection:")
            facts.lines += [_road_line(i) for i in waiting]
            facts.sources += [_road_link(ctx, i) for i in waiting]
        else:
            facts.lines.append(
                "Every high-risk road has an open inspection, or there are no high-risk roads now."
            )
        facts.sources.append(risk_page)
    elif intent == "changes":
        turned = db.scalar(
            select(Alert)
            .where(Alert.project_id == ctx.project.id, Alert.type == "turned_high")
            .order_by(Alert.created_at.desc())
            .limit(1)
        )
        if turned and ctx.has(Perm.ALERT_VIEW):
            facts.lines.append(f"{turned.title}:")
            facts.lines += [
                f"{r['name']} (was {r.get('previous_level', 'not listed')})."
                for r in turned.details.get("roads", [])
            ]
        else:
            high = [i for i in risk.items if i.level == "high"]
            facts.lines.append(
                f"This week {len(high)} road(s) in the project are high risk. Week-by-week changes are on each road's page."
            )
        facts.sources.append(risk_page)
    elif intent == "alerts":
        if not ctx.has(Perm.ALERT_VIEW):
            facts.lines.append("Alerts go to project managers only.")
        else:
            open_alerts = list(
                db.scalars(
                    select(Alert).where(
                        Alert.project_id == ctx.project.id, Alert.closed_at.is_(None)
                    )
                )
            )
            facts.lines.append(f"There are {len(open_alerts)} open alert(s).")
            facts.lines += [f"{a.title}." for a in open_alerts[:TOP]]
            facts.sources += [
                SourceLink(label=a.title, path=f"/notifications/{a.id}") for a in open_alerts[:TOP]
            ]
    return facts


def built_in_answer(intent: str, named: str | None, facts: Facts) -> str:
    if intent == "unknown":
        return (
            "I don't know how to answer that from the road-risk data. You can ask, for example: "
            + " / ".join(EXAMPLES)
        )
    if intent == "road" and not facts.sources:
        return f"I don't know: I could not find a road called \"{named}\" in this project's road-risk list."
    return " ".join(facts.lines)


PERCENT = re.compile(r"\d\s*%|percent|per cent|probability|likelihood of", re.IGNORECASE)


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def check_reply(reply: str, facts_text: str) -> bool:
    """The model's reply may only rephrase: no percentage and no number that is not in the facts."""
    reply = reply.strip()
    return (
        bool(reply)
        and len(reply) < 2000
        and not PERCENT.search(reply)
        and _numbers(reply) <= _numbers(facts_text)
    )


def call_model(question: str, facts_text: str) -> str | None:
    """Ask the free local model (Ollama) to rephrase the facts. None when it is off or too slow."""
    cfg = get_settings()
    if not cfg.assistant_url:
        return None
    prompt = (
        "You help a city road department. Answer the question in 2-5 short, plain sentences using ONLY the facts "
        "below. Do not add numbers, percentages, chances, costs or advice beyond the facts. If the facts do not "
        "answer the question, say you don't know.\n\nFACTS:\n"
        + facts_text
        + "\n\nQUESTION: "
        + question
    )
    try:
        response = requests.post(
            f"{cfg.assistant_url.rstrip('/')}/api/chat",
            json={
                "model": cfg.assistant_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.1},
            },
            timeout=cfg.assistant_timeout_seconds,
        )
        response.raise_for_status()
        return str(response.json()["message"]["content"])
    except (requests.RequestException, KeyError, ValueError) as error:
        log.info("Assistant model not used: %s", error)
        return None


def asked_today(db: Session, ctx: ProjectContext) -> int:
    start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    return int(
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action == ACTION,
                AuditEvent.actor_user_id == ctx.user.id,
                AuditEvent.created_at >= start,
            )
        )
        or 0
    )


def ask(db: Session, ctx: ProjectContext, question: str) -> AssistantAnswer:
    row = road_risk._settings(db, ctx.project.id)
    if row is None or not row.enabled or row.status != "ready" or not row.assistant_enabled:
        raise ConflictError('"Ask about road risk" is not switched on for this project.')
    limit = get_settings().assistant_daily_limit
    used = asked_today(db, ctx)
    if used >= limit:
        raise TooManyRequestsError(
            f"You have asked {limit} questions today. Please try again tomorrow."
        )
    risk_names = [i.name or "" for i in road_risk.project_risk_for(db, ctx.project.id).items]
    intent, named = intent_of(question, risk_names)
    facts = collect(db, ctx, intent, named) if intent != "unknown" else Facts()
    answer = built_in_answer(intent, named, facts)
    used_model = False
    if intent != "unknown" and facts.sources:
        reply = call_model(question, "\n".join(facts.lines))
        if reply and check_reply(reply, "\n".join(facts.lines)):
            answer, used_model = reply.strip(), True
    seen: set[str] = set()
    sources = [s for s in facts.sources if not (s.path in seen or seen.add(s.path))]
    record_event(
        db,
        action=ACTION,
        organization_id=ctx.project.organization_id,
        project_id=ctx.project.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="project",
        target_id=ctx.project.id,
        details={
            "question": question,
            "answer": answer[:2000],
            "intent": intent,
            "used_model": used_model,
            "sources": [s.path for s in sources],
        },
    )
    db.commit()
    return AssistantAnswer(
        answer=answer, sources=sources, used_model=used_model, questions_left_today=limit - used - 1
    )
