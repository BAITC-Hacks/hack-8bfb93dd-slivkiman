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
    card = {field: "" for field in TASK_FIELDS}
    card["business_need"] = request.form.get("description", "").strip()
    for field in TASK_FIELDS:
        answer = request.form.get(field, "").strip()
        if answer:
            if field == "business_need" and card[field]:
                card[field] = f"{card[field]}\n\n{answer}"
            else:
                card[field] = answer
    return render_template("task_card.html", card=card, field_labels=TASK_FIELDS)


if __name__ == "__main__":
    app.run(debug=True)
