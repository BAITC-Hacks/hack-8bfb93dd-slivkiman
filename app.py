import json
import os
import sqlite3

from flask import Flask, abort, redirect, render_template, request, url_for
from openai import OpenAI


app = Flask(__name__)
DB_PATH = os.path.join(app.root_path, "task_catalog.db")

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


def get_connection():
    """Open the small SQLite database used by this MVP."""
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_database():
    """Create the two MVP storage tables when the application starts."""
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                topic TEXT NOT NULL,
                card_json TEXT NOT NULL,
                score INTEGER NOT NULL,
                level TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                team_name TEXT NOT NULL,
                solution_idea TEXT NOT NULL,
                implementation_plan TEXT NOT NULL,
                estimated_timeline TEXT NOT NULL,
                prototype_link TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        """)


def get_task(task_id):
    """Return a published task with its stored card, or stop with a 404."""
    with get_connection() as connection:
        task = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if task is None:
        abort(404)
    task = dict(task)
    task["card"] = json.loads(task.pop("card_json"))
    return task


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


@app.route("/publish", methods=["POST"])
def publish_task():
    """Store a confirmed task so students can find it in the public catalog."""
    card = card_from_form(request.form)
    readiness = calculate_readiness(card)
    topic = request.form.get("topic", "").strip()
    title = card["title"] or "Untitled task"

    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO tasks (title, topic, card_json, score, level)
               VALUES (?, ?, ?, ?, ?)""",
            (title, topic, json.dumps(card), readiness["score"], readiness["level"]),
        )
        task_id = cursor.lastrowid
    return redirect(url_for("task_detail", task_id=task_id))


@app.route("/catalog")
def catalog():
    """Show published tasks, with small topic and readiness filters."""
    selected_topic = request.args.get("topic", "")
    selected_level = request.args.get("level", "")
    query = "SELECT * FROM tasks WHERE 1 = 1"
    parameters = []
    if selected_topic:
        query += " AND topic = ?"
        parameters.append(selected_topic)
    if selected_level:
        query += " AND level = ?"
        parameters.append(selected_level)
    query += " ORDER BY score DESC, id DESC"

    with get_connection() as connection:
        tasks = [dict(row) for row in connection.execute(query, parameters).fetchall()]
        topics = [row[0] for row in connection.execute(
            "SELECT DISTINCT topic FROM tasks WHERE topic <> '' ORDER BY topic"
        ).fetchall()]
    for task in tasks:
        task["card"] = json.loads(task.pop("card_json"))
    return render_template("catalog.html", tasks=tasks, topics=topics,
                           selected_topic=selected_topic, selected_level=selected_level)


@app.route("/tasks/<int:task_id>")
def task_detail(task_id):
    """Show the full confirmed task card to a student or business user."""
    return render_template("task_detail.html", task=get_task(task_id), field_labels=TASK_FIELDS)


@app.route("/tasks/<int:task_id>/propose", methods=["GET", "POST"])
def submit_proposal(task_id):
    """Let a student team add a proposal without authentication."""
    task = get_task(task_id)
    if request.method == "POST":
        proposal = {
            "team_name": request.form.get("team_name", "").strip(),
            "solution_idea": request.form.get("solution_idea", "").strip(),
            "implementation_plan": request.form.get("implementation_plan", "").strip(),
            "estimated_timeline": request.form.get("estimated_timeline", "").strip(),
            "prototype_link": request.form.get("prototype_link", "").strip(),
        }
        required = ("team_name", "solution_idea", "implementation_plan", "estimated_timeline")
        if not all(proposal[field] for field in required):
            return render_template("proposal_form.html", task=task, proposal=proposal,
                                   error="Please complete the required proposal fields."), 400
        with get_connection() as connection:
            connection.execute("""
                INSERT INTO proposals (task_id, team_name, solution_idea, implementation_plan,
                                       estimated_timeline, prototype_link)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (task_id, *proposal.values()))
        return redirect(url_for("task_detail", task_id=task_id))
    return render_template("proposal_form.html", task=task, proposal={}, error=None)


@app.route("/tasks/<int:task_id>/proposals")
def business_proposals(task_id):
    """Show all team proposals for a task; no ranking is performed."""
    task = get_task(task_id)
    with get_connection() as connection:
        proposals = [dict(row) for row in connection.execute(
            "SELECT * FROM proposals WHERE task_id = ? ORDER BY id DESC", (task_id,)
        ).fetchall()]
    return render_template("proposals.html", task=task, proposals=proposals)


@app.route("/tasks/<int:task_id>/proposals/<int:proposal_id>/decision", methods=["POST"])
def decide_proposal(task_id, proposal_id):
    """Record the business's explicit Accept or Reject decision."""
    decision = request.form.get("decision")
    if decision not in ("Accepted", "Rejected"):
        abort(400)
    with get_connection() as connection:
        proposal = connection.execute(
            "SELECT id FROM proposals WHERE id = ? AND task_id = ?", (proposal_id, task_id)
        ).fetchone()
        if proposal is None:
            abort(404)
        connection.execute("UPDATE proposals SET status = ? WHERE id = ?", (decision, proposal_id))
    return redirect(url_for("business_proposals", task_id=task_id))


init_database()


if __name__ == "__main__":
    app.run(debug=True)
