import datetime
import re
from .db import Employee, db, ApplicationsHolidays, Holidays, Applications, Team
from flask import session


#Convert all team names of Fiber & Support to generic name
def convert_team_name():
    match = re.search('^Fiber', session['team'])
    if match:
        team_name = 'Fiber'

    match = re.search('^Support', session['team'])
    if match:
        team_name = 'Support'

    if team_name != 'Fiber' and team_name != 'Support':
        team_name = session['team']
    
    return team_name

#Check holiday in holidays table
def check_holidays(name, start_date, end_date=None):
    holiday_name_exists = Holidays.query.filter_by(name=name).all()
    if holiday_name_exists:
        return 'Holiday name exists'
        
    holiday_start_date_exists = Holidays.query.filter(Holidays.start_date<=start_date, Holidays.end_date>=start_date).first()
    if holiday_start_date_exists:
        return 'Holiday start date overlaps with another holiday'
    
    if end_date:
        if start_date != end_date:
            holiday_end_date_exists = Holidays.query.filter(Holidays.start_date<=end_date, Holidays.end_date>=end_date).first()
            if holiday_end_date_exists:
                return 'Holiday end date overlaps with another holiday'

            any_date_exists = Holidays.query.filter(Holidays.start_date>start_date, Holidays.end_date<end_date).first()
            if any_date_exists:
                return 'Holiday start and/or end dates overlaps with other holidays'

def update_applications_holidays(empid, start_date, end_date, application_id=None):
    while start_date <= end_date:
        attendance = ApplicationsHolidays.query.filter(ApplicationsHolidays.date==start_date, ApplicationsHolidays.empid==empid).first()
        
        if attendance:
            attendance.application_id = application_id
        
        start_date += datetime.timedelta(days=1)

#check whether session user is the team leader of the employee of the supplied application_id 
def check_team_access(application_id):
    employee = Employee.query.join(Applications, Team).filter(Applications.id==application_id).first()
    
    supervisor = Employee.query.join(Team).filter(Employee.username==session['username'], Team.name==employee.teams[0].name, Employee.role=='Supervisor').first()
    if supervisor:
        return True

    manager = Employee.query.join(Team).filter(Employee.username==session['username'], Team.name==employee.teams[0].name, Employee.role=='Manager').first()
    if manager:
        return True

    head = Employee.query.filter_by(username=session['username'], department=employee.department, role='Head').first()
    if head:
        return True

    return False

def check_edit_permission(application, employee):
    team = Team.query.filter_by(empid=employee.id).first()
    supervisor = Employee.query.join(Team).filter(Employee.username==session['username'], Team.name==team.name, Employee.role=='Supervisor').first()
    manager = Employee.query.join(Team).filter(Employee.username==session['username'], Team.name==team.name, Employee.role=='Manager').first()
    head = Employee.query.filter_by(username=session['username'], department=employee.department, role='Head').first()
    
    if application.status == 'Approval Pending':
        if session['username'] == employee.username:
            return True
    
    if employee.role == 'Team':
        if session['role'] == 'Supervisor' and supervisor:
            return True
        elif session['role'] == 'Manager' and manager:
            return True
        elif session['role'] == 'Head' and head:
            return True
    
    if employee.role == 'Supervisor':
        if session['role'] == 'Manager' and manager:
            return True
        elif session['role'] == 'Head' and head:
            return True

    if employee.role == 'Manager':
        if session['role'] == 'Head' and head:
            return True

    return False

def get_concern_emails(empid):
    employee = Employee.query.filter_by(id=empid).first()
    emails = {}

    if employee.email:
        employee_email = employee.email
    else:
        employee_email = ''

    emails['employee'] = employee_email

    supervisor = Employee.query.join(Team).filter(Employee.role=='Supervisor', Team.name==employee.teams[0].name).first()
    if supervisor:
        if supervisor.email:
            supervisor_email = supervisor.email
        else:
            supervisor_email = ''
    else:
        supervisor_email = ''
    
    emails['supervisor'] = supervisor_email

    manager = Employee.query.join(Team).filter(Employee.role=='Manager', Team.name==employee.teams[0].name).first()
    if manager:
        if manager.email:
            manager_email = manager.email
        else:
            manager_email = ''
    else:
        manager_email = ''
    
    emails['manager'] = manager_email

    head = Employee.query.join(Team).filter(Employee.department==employee.department, Employee.role=='Head').first()
    if head:
        if head.email:
            head_email = head.email
        else:
            head_email = ''
    else:
        head_email = ''
    
    emails['head'] = head_email
    
    admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
    if admin:
        if admin.email:
            admin_email = admin.email
        else:
            admin_email = ''
    else:
        admin_email = ''
    
    emails['admin'] = admin_email
    
    return emails 


def find_team_leader_email(emails):
    if session['role'] == 'Team' and emails['supervisor'] != '':
        team_leader_email = emails['supervisor']
    elif session['role'] == 'Team' and emails['manager'] != '':
        team_leader_email = emails['manager']
    elif session['role'] == 'Team' and emails['head'] != '':
        team_leader_email = emails['head']
    elif session['role'] == 'Supervisor' and emails['manager'] != '':
        team_leader_email = emails['manager']
    elif session['role'] == 'Supervisor' and emails['head'] != '':
        team_leader_email = emails['head']
    elif session['role'] == 'Manager' and emails['head'] != '':
        team_leader_email = emails['head']
    elif session['role'] == 'Head':
        team_leader_email = emails['manager']
    else:
        team_leader_email = False

    return team_leader_email


def check_edit_permission2(action, application, employee):
    team = Team.query.filter_by(empid=employee.id).first()
    supervisor = Employee.query.join(Team).filter(Employee.username==session['username'], Team.name==team.name, Employee.role=='Supervisor').first()
    manager = Employee.query.join(Team).filter(Employee.username==session['username'], Team.name==team.name, Employee.role=='Manager').first()
    head = Employee.query.filter_by(username=session['username'], department=employee.department, role='Head').first()
    
    if session['username'] == employee.username:
        if action == 'cancel' and application.status == 'Approval Pending': 
            return True
    
    if employee.role == 'Team':
        if session['role'] == 'Supervisor' and supervisor:
            return True
        elif session['role'] == 'Manager' and manager:
            return True
        elif session['role'] == 'Head' and head:
            return True
    
    if employee.role == 'Supervisor':
        if session['role'] == 'Manager' and manager:
            return True
        elif session['role'] == 'Head' and head:
            return True

    if employee.role == 'Manager':
        if session['role'] == 'Head' and head:
            return True

    return False