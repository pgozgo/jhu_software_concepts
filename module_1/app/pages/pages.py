from flask import render_template, Blueprint
# Create a Blueprint for the pages
bp = Blueprint('pages', __name__, template_folder="app/templates", static_folder="app/static")

# the home page
@bp.route('/')
def home():
    return render_template('home.html')

# the projects page
@bp.route('/projects')
def projects():
    return render_template('projects.html')

# the contact page
@bp.route('/contact')
def contact():
    return render_template('contact.html')