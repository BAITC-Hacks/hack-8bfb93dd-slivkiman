from flask import Flask, render_template, request


app = Flask(__name__)


@app.route("/")
def home():
    """Show the application home page."""
    return render_template("home.html")


@app.route("/create-task", methods=["GET", "POST"])
def create_task():
    """Display a task form and show the submitted rough description."""
    description = None

    if request.method == "POST":
        description = request.form.get("description", "").strip()

    return render_template("create_task.html", description=description)


if __name__ == "__main__":
    app.run(debug=True)
