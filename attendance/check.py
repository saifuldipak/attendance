from .db import Applications, Employee, Team
from sqlalchemy import and_
from flask import session

#checking if dates in submitted application already exists in previously submitted 
#applications by this user
def date_check(empid, start_date, end_date):
    start = Applications.query.join(Employee).filter(and_(Applications.start_date<=start_date,
                                                    Applications.end_date>=start_date),
                                                Employee.id==empid).first()
        
    end = Applications.query.join(Employee).filter(and_(Applications.start_date<=end_date, 
                                                Applications.end_date>=end_date),
                                            Employee.id==empid).first()
        
    range = Applications.query.join(Employee).filter(and_(Applications.start_date>start_date, 
                                            Applications.end_date<end_date),
                                            Employee.id==empid).first()
        
    if start or end or range:
        return 'Start date or end date overlaps with another application'


#This function checks whether the user can see the details of an application by its id
#user can only see the application details if session user is the applicant or
#user is the manager of the applicant's team or
#user role is admin and user is a member of HR team
def user_check(id):
    employee = Employee.query.join(Applications).filter(Applications.id==id).first()
    team = Team.query.filter_by(empid=employee.id).first()
    #manager = Employee.query.join(Team).filter(Team.name==team.name, Employee.role=='Manager').first()

    if employee.username == session['username']:
        return True
    elif session['role'] == 'Manager' and session['team'] == team.name:
        return True
    elif session['role'] == 'Admin' and session['team'] == 'HR':
        return True
    else:
        return False