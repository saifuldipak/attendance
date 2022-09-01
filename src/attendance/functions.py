import datetime
import re
from .db import db, ApplicationsHolidays, Holidays
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

def update_applications_holidays(empid, start_date, end_date, application_id):
    while start_date <= end_date:
        attendance = ApplicationsHolidays.query.filter(ApplicationsHolidays.date==start_date, ApplicationsHolidays.empid==empid).first()
        if attendance:
            attendance.application_id = application_id
        
        start_date += datetime.timedelta(days=1)
    
    db.session.commit()