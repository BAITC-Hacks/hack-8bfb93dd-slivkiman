# Task Catalog MVP

A small Flask starter for a hackathon project. A business user can enter a
rough task description, answer clarification questions, and edit a task card.

## Files

- `app.py` contains the Flask application, OpenAI clarification step, fallback
  questions, and editable task-card flow.
- `templates/base.html` provides the shared page layout.
- `templates/home.html` is the simple home page.
- `templates/create_task.html` contains the rough task-description form.
- `templates/clarify_task.html` displays clarification questions.
- `templates/task_card.html` displays the editable task card.
- `static/style.css` contains the page styling.
- `requirements.txt` lists the Python dependency.
- `.env.example` documents the environment-file convention for later stages.

## Install

Create and activate a virtual environment (recommended):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the dependency:

```powershell
pip install -r requirements.txt
```

## Run

```powershell
python app.py
```

Set your API key in the current PowerShell session before starting the app:

```powershell
$env:OPENAI_API_KEY = "your_api_key"
```

Open `http://127.0.0.1:5000` in a browser. If the API key is absent or the API
call fails, the app shows fallback questions so the flow still works.

## Test the current flow

1. On the home page, select **Describe a task**.
2. Enter a rough business need in the text area and select **Submit description**.
3. Confirm that at least three clarification questions are displayed.
4. Answer one or more questions and select **Create editable task card**.
5. Confirm the supplied rough description and answers appear in editable fields.
