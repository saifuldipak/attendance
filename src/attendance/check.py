from .db import Applications, Employee, Team
from flask import current_app, session

#checking if dates in submitted application already exists in previously submitted 
#applications by this user
def check_dates(empid, start_date, end_date):
    
    if not start_date and not end_date:
        current_app.logger.error('date_check(): start_date and/or end_date missing')
        return 'Start date and end date must be given'

    start_date_exists = Applications.query.filter(Applications.start_date<=start_date, Applications.end_date>=start_date, 
                            Applications.empid==empid).first()
    if start_date_exists:
        return 'Start date overlaps with another application'

    end_date_exists = Applications.query.filter(Applications.start_date<=end_date, Applications.end_date>=end_date, 
                        Applications.empid==empid).first()
    if end_date_exists:
        return 'End date overlaps with another application'

    any_date_exists = Applications.query.filter(Applications.start_date>start_date, Applications.end_date<end_date, 
                        Applications.empid==empid).first()
    if any_date_exists:
        return 'Start and/or end dates overlaps with other application'

#Check access to specific application id
def check_access(application_id):
    employee = Employee.query.join(Applications, Team).filter(Applications.id==application_id).first()
    manager = Employee.query.join(Team).filter(Team.name==employee.teams[0].name, 
                Employee.role=='Manager').first()
    head = Employee.query.filter_by(department=session['department'], role='Head').first()

    if employee.username == session['username']:
        return True
    elif manager:
        return True
    elif head:
        return True
    elif session['access'] == 'Admin':
        return True
    else:
        return False
