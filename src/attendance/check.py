from .db import Applications, Employee, Team, AttnSummary
from flask import current_app, session
from flask import flash

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

#Check attn_summary table
def check_attnsummary(start_date, end_date=None):
    start_date_in_summary = AttnSummary.query.filter(AttnSummary.year==start_date.year, 
                                AttnSummary.month==start_date.strftime("%B")).first()
    
    found = False
    if start_date_in_summary:
        month = start_date.strftime("%B")
        year = start_date.year
        found = True
        
    if end_date:
        end_date_in_summary = AttnSummary.query.filter(AttnSummary.year==end_date.year, 
                                AttnSummary.month==end_date.strftime("%B")).first()
        if end_date_in_summary:
            month = end_date.strftime("%B")
            year = end_date.year
            found = True
    
    if found:
        msg = f'Cannot add/delete holidays. Attendance summary already prepared for {month}, {year}'
        return msg
    
    return False