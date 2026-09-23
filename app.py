import json
import os

from flask import Flask, render_template, request
from openai import OpenAI


app = Flask(__name__)

TASK_FIELDS = {
    "title": "Title", "context": "Context", "business_need": "Business need",
    "target_users": "Target users", "available_data_materials": "Available data/materials",
    "constraints": "Constraints", "expected_result": "Expected result",
    "success_criteria": "Success criteria", "business_contact": "Business contact",
    "interaction_format": "Interaction format",
}

SCORE_CATEGORIES = [
    ("Context + Business need", ("context", "business_need"), 20),
    ("Available data/materials", ("available_data_materials",), 20),
    ("Expected result", ("expected_result",), 15),
    ("Success criteria", ("success_criteria",), 15),
    ("Constraints", ("constraints",), 10),
    ("Target users", ("target_users",), 10),
    ("Business connection", ("business_contact", "interaction_format"), 10),
]

FALLBACK_QUESTIONS = [
    {"field": "target_users", "question": "Who will use the proposed solution?"},
    {"field": "expected_result", "question": "What result or deliverable would you like the student team to produce?"},
    {"field": "success_criteria", "question": "How will you know the task has been completed successfully?"},
]

QUESTION_SCHEMA = {
    "type": "object",
    "properties": {"questions": {"type": "array", "items": {
        "type": "object",
        "properties": {"field": {"type": "string", "enum": list(TASK_FIELDS)}, "question": {"type": "string"}},
        "required": ["field", "question"], "additionalProperties": False,
    }}},
    "required": ["questions"], "additionalProperties": False,
}


def validate_questions(data):
    """Return safe question dictionaries or raise ValueError for bad AI output."""
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        raise ValueError("The response does not contain a questions list.")

    questions = []
    seen_fields = set()
    for item in data["questions"]:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        question = item.get("question", "").strip()
        if field in TASK_FIELDS and question and field not in seen_fields:
            questions.append({"field": field, "question": question})
            seen_fields.add(field)
    if len(questions) < 3:
        raise ValueError("Fewer than three valid questions were returned.")
    return questions


def generate_questions(description):
    """Ask OpenAI for missing-information questions, with a safe fallback."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return FALLBACK_QUESTIONS, "OpenAI is not configured, so we are using starter questions."

    instructions = (
        "You help prepare a business task card. Return only clarification questions for "
        "information missing from the user's rough description. Do not state, assume, "
        "infer, summarize, or invent business facts. Each question must ask about one "
        "supplied field. Produce at least three concise, relevant questions. Do not ask "
        "about a field already covered by the description."
    )
    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model="gpt-4o-mini", instructions=instructions, input=description,
            text={"format": {"type": "json_schema", "name": "clarification_questions",
                              "strict": True, "schema": QUESTION_SCHEMA}},
        )
        return validate_questions(json.loads(response.output_text)), None
    except (Exception, json.JSONDecodeError, ValueError):
        return FALLBACK_QUESTIONS, "We could not generate AI questions right now. Starter questions are shown so you can continue."


def calculate_readiness(card):
    """Return a transparent, deterministic readiness rating for a task card."""
    breakdown = []
    missing_fields = []

    for category, fields, maximum in SCORE_CATEGORIES:
        completed = [field for field in fields if card.get(field, "").strip()]
        points_per_field = maximum // len(fields)
        points = points_per_field * len(completed)
        missing = [field for field in fields if field not in completed]
        missing_fields.extend(missing)
        breakdown.append({
            "category": category,
            "points": points,
            "maximum": maximum,
            "missing": [TASK_FIELDS[field] for field in missing],
        })

    score = sum(item["points"] for item in breakdown)
    if score <= 39:
        level = "Draft"
    elif score <= 69:
        level = "Working"
    elif score <= 89:
        level = "Ready"
    else:
        level = "Priority"

    return {
        "score": score,
        "level": level,
        "breakdown": breakdown,
        "missing_fields": [TASK_FIELDS[field] for field in missing_fields],
    }


def card_from_form(form):
    """Read only the known task-card fields from a submitted form."""
    return {field: form.get(field, "").strip() for field in TASK_FIELDS}


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/create-task")
def create_task():
    return render_template("create_task.html")


@app.route("/clarify", methods=["POST"])
def clarify_task():
    description = request.form.get("description", "").strip()
    if not description:
        return render_template("create_task.html", error="Please enter a rough task description."), 400
    questions, error = generate_questions(description)
    return render_template("clarify_task.html", description=description, questions=questions,
                           error=error, field_labels=TASK_FIELDS)


@app.route("/task-card", methods=["POST"])
def task_card():
    """Create an editable card from the user's description and answers only."""
    card = card_from_form(request.form)
    description = request.form.get("description", "").strip()
    if description:
        if card["business_need"]:
            card["business_need"] = f"{description}\n\n{card['business_need']}"
        else:
            card["business_need"] = description
    return render_template("task_card.html", card=card, field_labels=TASK_FIELDS)


@app.route("/rating", methods=["POST"])
def rating():
    """Calculate a deterministic readiness rating from the confirmed card."""
    card = card_from_form(request.form)
    return render_template("rating.html", card=card, rating=calculate_readiness(card),
                           field_labels=TASK_FIELDS)


@app.route("/edit-task-card", methods=["POST"])
def edit_task_card():
    """Return to the editable card without losing submitted values."""
    return render_template("task_card.html", card=card_from_form(request.form),
                           field_labels=TASK_FIELDS)


if __name__ == "__main__":
    app.run(debug=True)
