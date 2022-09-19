from datetime import datetime
import re
from urllib import request
from attendance.functions import convert_team_name
from flask import Blueprint, Flask, current_app, flash, render_template, session, request
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import validators, widgets
from wtforms.fields import (DateField, TextAreaField, IntegerField, StringField, PasswordField, 
                        EmailField, TelField, SelectField, RadioField, DateTimeField, TimeField, SelectMultipleField) 
from wtforms.validators import (InputRequired, ValidationError, EqualTo, InputRequired, Email, 
                                Optional, NumberRange)
from .auth import admin_required, login_required, manager_required, supervisor_required, team_leader_required
from .db import Employee, Team, DutyShift
from werkzeug.security import check_password_hash
from sqlalchemy import or_


departments = ['Accounts', 'Sales', 'Technical']

months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 
            'October', 'November', 'December']
attendance = ['In', 'Out', 'Both']
years = ['2022', '2023', '2024', '2025']
actions = ['Add', 'Delete']
designations = ['GM', 'DGM', 'AGM', 'Sr. Manager', 'Manager', 'Dy. Manager', 'Asst. Manager', 
                'Sr. Network Engineer', 'Sr. Executive', 'Network Engineer', 'Executive', 
                'Jr. Network Engineer', 'Jr. Executive', 'Sr. Asst. Engineer', 'Asst. Engineer', 
                'Jr. Asst. Engineer', 'Team Coordinator', 'Jr. Splice Tech', 'Jr. Cable Tech', 'Splice Tech', 'Cable Tech', 
                'Driver', 'Peon']
types = ['All', 'Username', 'Fullname', 'Department', 'Designation', 'Team', 'Access']
queries = ['Details', 'Summary']

#Common classes
class Monthyear(FlaskForm):
    month = IntegerField('Month', render_kw={'class': 'input-field'}, default=datetime.now().month, validators=[InputRequired(), NumberRange(min=1, max=12, message='Number must be between 1 to 12')])
    year = IntegerField('Year ', render_kw={'class': 'input-field'}, default=datetime.now().year, validators=[InputRequired(), NumberRange(min=2021, max=2030, message='Number must be between 2021 to 2030')])

#validator function to check file size
def file_length_check(form, field):
    max_bytes = 1 * 1024 * 1024
    if field.data:
        if len(field.data.read()) > max_bytes:
            raise ValidationError('File size can be max 1MB')
        field.data.seek(0)

class Dates(FlaskForm):
    start_date = DateField('Start Date', format='%Y-%m-%d', render_kw={'class': 'form-input'}, validators=[InputRequired()])
    end_date = DateField('End Date', format='%Y-%m-%d', render_kw={'class': 'form-input'}, validators=[Optional()])
    
    # extra validator added to check End date value with Start date value
    def validate_start_date(self, field):
        if self.end_date.data:
            if field.data > self.end_date.data:
                raise ValidationError('End date must be same or later than Start date')

#Attendance file upload
class Attndataupload(FlaskForm):
    file1 = FileField('Upload File 1', 
                        validators=[FileAllowed(['xls', 'xlsx'], '.xls & .xlsx only!'), FileRequired()])

#Attendance query for all 
class Attnqueryall(FlaskForm):
    month = SelectField('Month', render_kw={'class': 'input-field'}, choices=months)
    type = SelectField('Type', render_kw={'class': 'input-field'}, choices=['Summary', 'Details'])
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                                        validators=[validators.Optional()])
    
    # extra validator added to check username given if type is selected  'Details' by user
    def validate(self):
        rv = FlaskForm.validate(self)
        if not rv:
            return False

        if self.type.data == 'Details' and not self.username.data:
            self.type.errors.append('Must give "Username" if type is "Details"')
            return False
        return True

#Attendance query by admin datewise
class Attnquerydate(FlaskForm):
    date = DateField('Date', render_kw={'class': 'input-field'}, validators=[InputRequired()])

#Attendance summary create
class Attnsummary(FlaskForm):
    year = SelectField('Year', render_kw={'class': 'input-field'}, choices=years)
    month = SelectField('Month', render_kw={'class': 'input-field'}, choices=months)

#Attendance summary show
class Attnsummaryshow(Attnsummary):
    result = SelectField('Result', render_kw={'class': 'input-field'}, choices=['Show', 'Download'])
    
#Attendance summary
class Leavededuction(FlaskForm):
    year = SelectField('Year', render_kw={'class': 'input-field'}, choices=years)
    month = SelectField('Month', render_kw={'class': 'input-field'}, choices=months)

#Self password change
class Changeselfpass(FlaskForm):
    password = PasswordField('Password', 
                                render_kw={'class': 'input-field'}, 
                                validators=[InputRequired(), 
                                EqualTo('rpassword', message='Password must match')])
    rpassword = PasswordField('Retype Password', 
                                render_kw={'class': 'input-field'}, 
                                validators=[InputRequired()])

    #extra validators
    def validate(self):
        rv = FlaskForm.validate(self)
        if not rv:
            return False

        employee = Employee.query.filter_by(username=session['username']).first()
        match = check_password_hash(employee.password, self.password.data)
        
        if match:
            self.password.errors.append('old password and new password cannot be same')
            return False

        if len(self.password.data) < 8:
            self.password.errors.append('length must be at least 8 characters')
            return False
        
        #if not re.search('[A-Z0-9]', self.password.data):
        #    self.password.errors.append('password must contain at least one capital letter and one number')
        #    return False

        return True

#Update employee email 
class Updateemail(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])
    email = EmailField('Email', render_kw={'class': 'input-field'}, 
                        validators=[InputRequired(), Email(message='Email not correct')])

#Update employee fullname
class Updatefullname(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])
    fullname = StringField('Fullname', render_kw={'class': 'input-field'}, 
                        validators=[InputRequired()])

#Update employee designation
class Updatedesignation(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    designation = SelectField('Designation', render_kw={'class': 'input-field'}, 
                        validators=[InputRequired()], choices=designations)

#Update employee phone
class Updatephone(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])
    phone = TelField('Phone', render_kw={'class': 'input-field'}, 
                        validators=[InputRequired()])

#Update department
class Updatedept(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])
    dept = SelectField('Team', render_kw={'class': 'input-field'}, choices=departments)
    
#Reset password
class Resetpass(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])

#Employee search
class Employeesearch(FlaskForm):
    string = StringField('Search string', render_kw={'class': 'input-field'})
    type = SelectField('Search by', render_kw={'class': 'input-field'}, choices=types)

class Createleave(FlaskForm):
    year_start = IntegerField('Year Start', default=datetime.now().year, render_kw={'class': 'input-field'}, validators=[InputRequired()])
    year_end = IntegerField('Year End', default=datetime.now().year+1, render_kw={'class': 'input-field'}, validators=[InputRequired()])

    def validate_year_end(self, field):
        if self.year_start.data >= field.data:
            raise ValidationError('must be greater than year start')

forms = Blueprint('forms', __name__)

#Leave application
duty_types = ['No', 'On site', 'Off site']
class Leavecasual(Dates):
    remark = TextAreaField('Remark', render_kw={'class': 'textarea-field'})
    holiday_duty_type = SelectField('Adjust with holiday duty', render_kw={'class': 'form-input'}, choices=duty_types)
    holiday_duty_start_date = DateField('Holiday Start Date', format='%Y-%m-%d', render_kw={'class': 'form-input'}, validators=[Optional()])
    holiday_duty_end_date = DateField('Holiday End Date', format='%Y-%m-%d', render_kw={'class': 'form-input'}, validators=[Optional()])
    
    #Extra validator
    def validate_holiday_duty_type(self, field):
        if field.data != 'No':
            if not self.holiday_duty_start_date.data:
                raise ValidationError('Must give Holiday start date')

            if self.holiday_duty_end_date.data:
                if self.holiday_duty_start_date.data > self.holiday_duty_end_date.data:
                    raise ValidationError('Holiday end date must be same or later than Holiday start date')
    
            if not self.end_date.data:
                self.end_date.data = self.start_date.data
            leave_duration = (self.end_date.data - self.start_date.data).days

            if not self.holiday_duty_end_date.data:
                self.holiday_duty_end_date.data = self.holiday_duty_start_date.data    
            holiday_duty_duration = (self.holiday_duty_end_date.data - self.holiday_duty_start_date.data).days

            if leave_duration != holiday_duty_duration:
                raise ValidationError('Leave duration and holiday duty duration must be same')

class Leavemedical(Dates):
    remark = TextAreaField('Remark', render_kw={'class': 'textarea-field'}, validators=[InputRequired()])
    file1 = FileField('Upload File 1', validators=[FileAllowed(['jpeg', 'jpg', 'png', 'gif'], 'Images only!'),
                                FileRequired(), file_length_check])
    file2 = FileField('Upload File 2', validators=[FileAllowed(['jpeg', 'jpg', 'png', 'gif'], 'Images only!'),
                                                file_length_check])
    file3 = FileField('Upload File 3', validators=[FileAllowed(['jpeg', 'jpg', 'png', 'gif'], 'Images only!'),
                                                file_length_check])

@forms.route('/forms/leave/<type>', methods=['GET', 'POST'])
@login_required
def leave(type):

    if type == 'Casual':
        form = Leavecasual()
    elif type == 'Medical':
        form = Leavemedical()
    
    return render_template('forms.html', type='leave', leave=type, form=form)

#Leave application - Fiber
class Fiberteam(FlaskForm):
    empid = SelectField('Name', render_kw={'class' : 'input-field'}, choices=[], coerce=int, validate_choice=False)

class Leavefibercasual(Fiberteam, Leavecasual):
    pass

class Leavefibermedical(Fiberteam, Leavemedical):
    pass

@forms.route('/forms/leave/fiber/<type>', methods=['GET', 'POST'])
@login_required
def leave_fiber(type):

    if type == 'Casual':
        form = Leavefibercasual()
    elif type == 'Medical':
        form = Leavefibermedical()
    
    names = Employee.query.join(Team).filter(Team.name==session['team'], Employee.role=='Team').all()
    form.empid.choices = [(i.id, i.fullname) for i in names]
    
    return render_template('forms.html', type='leave', leave=type, team='fiber', form=form)


#Attendance application 
class Attnapplication(Dates):
    type = RadioField('Type', render_kw={'class': 'input-field'}, choices=attendance, validators=[InputRequired()])
    remark = TextAreaField('Remark', render_kw={'class' : 'input-field'}, validators=[InputRequired()])

@forms.route('/forms/attendance/application')
@login_required
def attn_application():
    form = Attnapplication()
    return render_template('forms.html', type='attn_application', form=form)


#Attendance application - Fiber
class Attnapplfiber(Attnapplication):
    empid = SelectField('Name', render_kw={'class' : 'input-field'}, choices=[], coerce=int, validate_choice=False)
    
@forms.route('/forms/attendance/fiber', methods=['GET', 'POST'])
@login_required
@supervisor_required
def attn_fiber():
    form = Attnapplfiber()
    
    names = Employee.query.join(Team).filter(Team.name==session['team'], Employee.role=='Team').all()
    form.empid.choices = [(i.id, i.fullname) for i in names]
    
    return render_template('forms.html', type='attn_application', team='fiber', form=form)

#Create, delete, update employee record
teams = ['Customer Care', 'Support-Dhanmondi', 'Support-Gulshan', 'Support-Motijheel', 
                'Support-Nationwide', 'Support-Uttara','Implementation', 'Fiber-Implementation', 
                'Fiber-Dhanmondi', 'Fiber-Gulshan', 'Fiber-Motijheel', 'NS', 'NOC', 'NTN', 'WAN', 'HR', 'Billing', 
                'Accounts', 'Sales']
roles = ['Team', 'Supervisor', 'Manager', 'Head']
access = ['User', 'Admin', 'None']

class Employeecreate(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    fullname = StringField('Full Name', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    password = PasswordField('Password', render_kw={'class': 'input-field'}, validators=[InputRequired(), 
                    EqualTo('rpassword', message='Password must match')])
    rpassword = PasswordField('Retype Password', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    email = EmailField('Email', render_kw={'class': 'input-field'})
    phone = StringField('Phone', render_kw={'class': 'input-field'})
    department = SelectField('Department', render_kw={'class': 'input-field'}, choices=departments)
    designation = SelectField('Designation', render_kw={'class': 'input-field'}, choices=designations)
    team = SelectField('Team', render_kw={'class': 'input-field'}, choices=teams)
    role = SelectField('Role', render_kw={'class': 'input-field'}, choices=roles)
    access = SelectField('Access', render_kw={'class': 'input-field'}, choices=access)

class Employeedelete(FlaskForm):
    empid = IntegerField('Employee ID', render_kw={'class': 'input-field'}, validators=[InputRequired()])

class Employeeupdate(FlaskForm):
    empid = StringField('Employee ID', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    team = SelectField('Team Add', 
                        render_kw={'class': 'input-field'},
                        choices=teams)

@forms.route('/forms/employee/<action>', methods=['GET', 'POST'])
@login_required
@admin_required
def employee(action):

    if action == 'create':
        form = Employeecreate()
        form_type = 'employee_create'
    elif action == 'delete':
        form = Employeedelete()
        form_type = 'employee_delete'
    elif action == 'update':
        form = Employeeupdate()
        form_type = 'employee_update'
    
    return render_template('forms.html', form_type=form_type, form=form)

#Attendance file upload 
@forms.route('/forms/attendance/upload', methods=['GET', 'POST'])
@login_required
def upload():
    form = Attndataupload()
    return render_template('forms.html', form_type='attendance_upload', form=form)

#Attendance query
class Attnquery(FlaskForm):
    month = IntegerField('Month', render_kw={'class': 'input-field'}, default=datetime.now().month, validators=[InputRequired(), NumberRange(min=1, max=12, message='Number must be between 1 to 12')])
    year = IntegerField('Year ', render_kw={'class': 'input-field'}, default=datetime.now().year, validators=[InputRequired(), NumberRange(min=2021, max=2030, message='Number must be between 2021 to 2030')])

class Attnqueryusername(Attnquery):
    username = StringField('Username', render_kw={'class': 'input-field'}, validators=[InputRequired()])

@forms.route('/forms/attendance/query/<query_type>', methods=['GET', 'POST'])
@login_required
def attendance_query(query_type):
    if query_type == 'date':
        form = Attnquerydate()
    elif query_type == 'username':
        if session['role'] == 'Team':
            form = Attnquery()
        else:
            form = Attnqueryusername()
    elif query_type == 'month':
        form = Attnsummaryshow()
    else:
        current_app.logger.error('attnquery_all(): unknown form type')
        flash('Could not create form', category='error')

    return render_template('forms.html', type='attendance_query', query_type=query_type, form=form)

#Attendance summary prepare
@forms.route('/forms/attendance/prepare_summary')
@login_required
@admin_required
def prepare_attendance_summary():
    form = Attnquery()
    return render_template('forms.html', type='attn_prepare_summary', form=form)


#Attendance summary show and prepare
class Attendancesummaryshow(Monthyear):
    action = SelectField('Action', render_kw={'class': 'input-field'}, choices=['show', 'download'], validators=[InputRequired()])

class Attendancesummaryprepare(Monthyear):
    pass

@forms.route('/forms/attendance/summary/<action>')
@login_required
def attendance_summary(action):
    summary_for = request.args.get('summary_for')
    
    if action == 'show':
        form = Attendancesummaryshow()
        return render_template('forms.html', type='show_attendance_summary', summary_for=summary_for, form=form)
    elif action == 'prepare':
        form = Attendancesummaryprepare()
        return render_template('forms.html', type='prepare_attendance_summary', form=form)
    else:
        current_app.logger.error(' summary(): Failed to create forms with argument %s', action)
        return render_template('base.html')
    

#Leave deduction
@forms.route('/forms/leave/deduction')
@login_required
@admin_required
def leave_deduction():
    form = Leavededuction()
    return render_template('forms.html', type='leave_deduction', form=form)

#Employee modify - email
@forms.route('/forms/employee/update_email')
@login_required
@admin_required
def update_email():
    form = Updateemail()
    return render_template('emp_update.html', type='email', form=form)

#Employee modify - fullname
@forms.route('/forms/employee/update_fullname')
@login_required
@admin_required
def update_fullname():
    form = Updatefullname()
    return render_template('emp_update.html', type='fullname', form=form)

#Employee modify - designation
@forms.route('/forms/employee/update_designation')
@login_required
@admin_required
def update_designation():
    form = Updatedesignation()
    return render_template('emp_update.html', type='designation', form=form)

#Employee modify - phone
@forms.route('/forms/employee/update_phone')
@login_required
@admin_required
def update_phone():
    form = Updatephone()
    return render_template('emp_update.html', type='phone', form=form)

#Employee modify - team
class Updateteam(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])
    team = SelectField('Team', render_kw={'class': 'input-field'}, choices=teams)
    action = SelectField('Action', render_kw={'class': 'input-field'}, choices=actions)

@forms.route('/forms/employee/update_team')
@login_required
@admin_required
def update_team():
    form = Updateteam()
    return render_template('emp_update.html', type='team', form=form)

#Employee modify - department
@forms.route('/forms/employee/update_dept')
@login_required
@admin_required
def update_dept():
    form = Updatedept()
    return render_template('emp_update.html', type='dept', form=form)

#Employee modify - password
@forms.route('/forms/employee/reset_pass')
@login_required
@admin_required
def reset_pass():
    form = Resetpass()
    return render_template('emp_update.html', type='pass', form=form)

#Employee modify - role
class Updaterole(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    role = SelectField('Role', render_kw={'class': 'input-field'}, choices=roles)

@forms.route('/forms/employee/update_role')
@login_required
@admin_required
def update_role():
    form = Updaterole()
    return render_template('emp_update.html', type='role', form=form)

#Employee modify - access
class Updateaccess(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])
    access = SelectField('Role', render_kw={'class': 'input-field'}, choices=access)

@forms.route('/forms/employee/update_access')
@login_required
@admin_required
def update_access():
    form = Updateaccess()
    return render_template('emp_update.html', type='access', form=form)

#Employee search 
@forms.route('/forms/employee/search')
@login_required
@admin_required
def employee_search():
    form = Employeesearch()
    return render_template('data.html', action='employee_search', form=form)

#Own password reset
@forms.route('/forms/employee/password/self')
@login_required
def password_self():
    form = Changeselfpass()
    return render_template('forms.html', type='change_pass', user='self', form=form)

@forms.route('/forms/leave/create')
@login_required
@admin_required
def create_leave():
    form = Createleave()
    return render_template('forms.html', type='create_leave', form=form)

class Addholidays(Dates):
    name = StringField('Name', render_kw={'class': 'input-field'}, validators=[InputRequired()])

@forms.route('/forms/holidays/add')
@login_required
@admin_required
def add_holiday():
    form = Addholidays()
    return render_template('forms.html', type='add_holiday', form=form)


#Duty schedule - Create, Query
fiber_teams = ['Fiber-Dhanmondi', 'Fiber-Gulshan', 'Fiber-Motijheel']

class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

class Dutyschedulecreate(FlaskForm):
    empid = MultiCheckboxField('Name', render_kw={'class' : 'input-field'}, choices=[], coerce=int, validate_choice=False)
    duty_shift = SelectField('Duty', render_kw={'class' : 'input-field'}, choices=[], coerce=int, validate_choice=False)
    start_date = DateField('Duty start date', render_kw={'class' : 'input-field'}, validators=[InputRequired()])
    end_date = DateField('Duty end date', render_kw={'class' : 'input-field'}, validators=[InputRequired()])

class Dutyschedulequery(FlaskForm):
    month = IntegerField('Month', render_kw={'class' : 'input-field'}, default=datetime.now().month, validators=[InputRequired()])
    year = IntegerField('Year', render_kw={'class' : 'input-field'}, default=datetime.now().year, validators=[InputRequired()])

@forms.route('/forms/duty_schedule/<action>', methods=['GET', 'POST'])
@login_required
@team_leader_required
def duty_schedule(action):
    if action == 'create':
        form = Dutyschedulecreate()
        team_name_string = convert_team_name() + '%'

        names = Employee.query.join(Team).filter(Team.name.like(team_name_string), Employee.role=='Team').all()
        form.empid.choices = [(i.id, i.fullname) for i in names]
    
        shifts = DutyShift.query.filter(DutyShift.team=='Fiber').all()
        form.duty_shift.choices = [(i.id, i.name) for i in shifts]

        return render_template('forms.html', type='duty_schedule', action='create', team='fiber', form=form)
    elif action == 'query':
        form = Dutyschedulequery()
        return render_template('forms.html', type='duty_schedule', action='query', form=form)
    else:
        current_app.logger.error(' duty_schedule(): <action> value not correct')
        flash('Cannot create duty schedule form', category='error')
        return render_template('base.html')
    
    
#Duty shift - create
shifts = ['Morning', 'Evening', 'Night', 'Regular']
class Dutyshiftcreate(FlaskForm):
    shift_name = SelectField('Shift name', render_kw={'class' : 'input-field'}, choices=shifts)
    in_time = TimeField('In time', render_kw={'class' : 'input-field'}, validators=[InputRequired()])
    out_time = TimeField('Out time', render_kw={'class' : 'input-field'}, validators=[InputRequired()])

class Dutyshiftquery(FlaskForm):
    month = IntegerField('Month', render_kw={'class' : 'input-field'}, default=datetime.now().month, validators=[InputRequired()])
    year = IntegerField('Year', render_kw={'class' : 'input-field'}, default=datetime.now().year, validators=[InputRequired()])

@forms.route('/forms/duty_shift/create', methods=['GET', 'POST'])
@login_required
@team_leader_required
def duty_shift_create():
    form = Dutyshiftcreate()
    return render_template('forms.html', type='duty_shift_create', form=form)
    
#Search applications
class Searchapplication(FlaskForm):
    month = IntegerField('Month', render_kw={'class': 'input-field'}, default=datetime.now().month, validators=[InputRequired(), NumberRange(min=1, max=12, message='Number must be between 1 to 12')])
    year = IntegerField('Year ', render_kw={'class': 'input-field'}, default=datetime.now().year, validators=[InputRequired(), NumberRange(min=2021, max=2030, message='Number must be between 2021 to 2030')])


@forms.route('/forms/application/search/<application_for>', methods=['GET', 'POST'])
@login_required
def search_application(application_for):
    form = Searchapplication()
    return render_template('forms.html', type='search_application', application_for=application_for, form=form)