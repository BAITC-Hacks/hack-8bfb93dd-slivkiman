# Task Catalog MVP

A small Flask starter for a hackathon project. At this stage, a business user
can enter a rough task description and see it displayed back to them.

## Files

- `app.py` contains the Flask application and its two routes.
- `templates/base.html` provides the shared page layout.
- `templates/home.html` is the simple home page.
- `templates/create_task.html` contains the task-description form and submitted result.
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

Open `http://127.0.0.1:5000` in a browser.

## Test the current flow

1. On the home page, select **Describe a task**.
2. Enter a rough business need in the text area.
3. Select **Submit description**.
4. Confirm that the same text appears under **Submitted description**.
