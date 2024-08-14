from flask import Blueprint, render_template
from attendance.auth import admin_required, login_required

help = Blueprint('help', __name__)

@help.route('/help/admin/<help_section>', methods=['GET'])
@login_required
@admin_required
def show_admin_help(help_section):
    return render_template('help.html', help_section=help_section)