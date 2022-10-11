from datetime import datetime, timedelta
import re
from .db import Employee, db, ApplicationsHolidays, Holidays, Applications, Team, Attendance, DutySchedule, DutyShift
from flask import session, current_app
from sqlalchemy import extract


#Convert all team names of Fiber & Support to generic name
def convert_team_name():
    team_name = ''
    
    match = re.search('^Fiber', session['team'])
    if match:
        team_name = 'Fiber'

    match = re.search('^Support', session['team'])
    if match:
        team_name = 'Support'

    if team_name == '':
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
        
        start_date += timedelta(days=1)

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

def check_view_permission(show_type):
    if show_type == 'all' and session['access'] == 'Admin':
        return True
    
    if show_type == 'team' and session['role'] in ('Supervisor', 'Manager'):
        return True

    if show_type == 'department' and session['role'] == 'Head':
        return True
    
    return False

#Convert all team names of Fiber & Support to generic name
def convert_team_name2(team_name):    
    match = re.search('^Fiber', team_name)
    if match:
        team_name = 'Fiber'

    match = re.search('^Support', team_name)
    if match:
        team_name = 'Support'
    
    return team_name

#check whether session user is the team leader or department head of the employee
def check_data_access(employee_id):
    employee = Employee.query.join(Team).filter(Employee.id==employee_id).first()
    
    supervisor = Employee.query.join(Team).filter(Employee.id==session['empid'], Team.name==employee.teams[0].name, Employee.role=='Supervisor').first()
    if supervisor:
        return True

    manager = Employee.query.join(Team).filter(Employee.id==session['empid'], Team.name==employee.teams[0].name, Employee.role=='Manager').first()
    if manager:
        return True

    head = Employee.query.filter_by(id=session['empid'], department=employee.department, role='Head').first()
    if head:
        return True
    
    admin = Employee.query.filter_by(id=session['empid'], access='Admin').first()
    if admin:
        return True

    return False


def get_attendance_data(empid, month, year):
    
    attendances = Attendance.query.filter(Attendance.empid==empid, extract('month', Attendance.date)==month, extract('year', Attendance.date)==year).order_by(Attendance.date).all()
    
    return_values = {}
    if not attendances:
        return_values['returned'] = False
        return return_values

    attendances_list = []
    summary = {'NI': 0, 'L': 0, 'NO': 0, 'E': 0}
    for attendance in attendances:
        attendance_list = {'date': attendance.date, 'in_time':attendance.in_time, 'out_time':attendance.out_time}
        
        attendance_list['day'] = datetime.strftime(attendance.date, "%A")

        in_time = datetime.strptime(current_app.config['IN_TIME'], "%H:%M:%S") + timedelta(minutes=current_app.config['GRACE_PERIOD'])
        out_time = datetime.strptime(current_app.config['OUT_TIME'], "%H:%M:%S") - timedelta(minutes=current_app.config['GRACE_PERIOD'])

        duty_schedule = DutySchedule.query.join(DutyShift).with_entities(DutyShift.name, DutyShift.in_time, DutyShift.out_time, DutySchedule.date).filter(DutySchedule.date==attendance.date, DutySchedule.empid==empid).first()
        if duty_schedule:
            attendance_list['duty_shift'] = duty_schedule.name

            if duty_schedule.name not in ('O', 'HO'):
                in_time = datetime.combine(duty_schedule.date, duty_schedule.in_time) + timedelta(minutes=current_app.config['GRACE_PERIOD'])
                out_time = datetime.combine(duty_schedule.date, duty_schedule.out_time) - timedelta(minutes=current_app.config['GRACE_PERIOD'])
        else:
            attendance_list['duty_shift'] = None

        application = Applications.query.filter(Applications.empid==empid, Applications.start_date<=attendance.date, Applications.end_date>=attendance.date).first()
        application_type = ''
        if  application:
            application_type = application.type
            attendance_list['application_type'] = application.type
            attendance_list['application_id'] = application.id
        else:
            attendance_list['application_type'] = None
            attendance_list['application_id'] = None

        holiday = Holidays.query.filter(Holidays.start_date<=attendance.date, Holidays.end_date>=attendance.date).first()
        holiday_name = ''
        if  holiday:
            holiday_name = holiday.name
            attendance_list['holiday'] = holiday.name
        else:
            attendance_list['holiday'] = None

        no_attendance = datetime.strptime('00:00:00', "%H:%M:%S").time()

        if application_type in ('Casual', 'Medical', 'Both') or attendance_list['duty_shift'] in ('O', 'HO') or holiday_name != '' or attendance_list['day'] in ('Friday', 'Saturday'):
            attendance_list['in_flag'] = None
            attendance_list['out_flag'] = None
        else:
            if application_type == 'In':
                attendance_list['in_flag'] = None
            elif attendance_list['in_time'] == no_attendance:
                attendance_list['in_flag'] = 'NI'
                summary['NI'] += 1
            elif attendance_list['in_time'] > in_time.time():
                attendance_list['in_flag'] = 'L'
                summary['L'] += 1
            else:
                attendance_list['in_flag'] = None

            if application_type == 'Out':
                attendance_list['out_flag'] = None
            elif attendance_list['out_time'] == no_attendance:
                attendance_list['out_flag'] = 'NO'
                summary['NO'] += 1
            elif attendance_list['out_time'] < out_time.time():
                attendance_list['out_flag'] = 'E'
                summary['E'] += 1
            else:
                attendance_list['out_flag'] = None

        attendances_list.append(attendance_list)  

    attendances = attendances_list
    
    return_values['attendances'] = attendances
    return_values['summary'] = summary
    return_values['returned'] = True

    return return_values


def get_concern_emails2(empid):
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

    cc = []
    
    if emails['employee'] != '':
        cc.append(emails['employee'])
    
    if employee.role == 'Team':
        if emails['supervisor'] != '':
            cc.append(emails['supervisor'])
        if emails['manager'] != '':
            cc.append(emails['manager'])
        if emails['head'] != '':
            cc.append(emails['head'])

    if employee.role == 'Supervisor':
        if emails['manager'] != '':
            cc.append(emails['manager'])
        if emails['head'] != '':
            cc.append(emails['head'])

    if employee.role == 'Manager':
        if emails['head'] != '':
            cc.append(emails['head'])

    emails['cc'] = cc

    return emails