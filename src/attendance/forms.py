from datetime import datetime
from flask import Blueprint, Flask, current_app, flash, render_template, session
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import validators
from wtforms.fields import (DateField, TextAreaField, IntegerField, StringField, PasswordField, 
                        EmailField, TelField, SelectField, RadioField) 
from wtforms.validators import (InputRequired, ValidationError, EqualTo, InputRequired, Email, 
                                Optional, NumberRange)
from .auth import admin_required, login_required, manager_required
from .db import Employee, Team
from werkzeug.security import check_password_hash


departments = ['Accounts', 'Sales', 'Technical']
teams = ['Customer Care', 'Support-Dhanmondi', 'Support-Gulshan', 'Support-Motijheel', 
                'Support-Nationwide', 'Support-Uttara','Implementation', 'Fiber-Implementation', 
                'Fiber-Dhanmondi', 'Fiber-Gulshan', 'Fiber-Motijheel', 'NS', 'NOC', 'NTN', 'WAN', 'HR', 'Billing', 
                'Accounts']
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
roles = ['Team', 'Manager', 'Head']
access = ['User', 'Admin', 'None']
types = ['All', 'Username', 'Fullname', 'Department', 'Designation', 'Team', 'Access']
queries = ['Details', 'Summary']

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

#Create employee record
class Employeecreate(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    fullname = StringField('Full Name', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    password = PasswordField('Password', 
                                render_kw={'class': 'input-field'}, 
                                validators=[InputRequired(), 
                                EqualTo('rpassword', message='Password must match')])
    rpassword = PasswordField('Retype Password', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    email = EmailField('Email', render_kw={'class': 'input-field'})
    phone = StringField('Phone', render_kw={'class': 'input-field'})
    department = SelectField('Department', render_kw={'class': 'input-field'},
                            choices=departments)
    designation = SelectField('Designation', render_kw={'class': 'input-field'}, 
                            choices=designations)
    team = SelectField('Team',      
                        render_kw={'class': 'input-field'},
                        choices=teams)
    role = SelectField('Role',
                            render_kw={'class': 'input-field'},
                            choices=roles)
    access = SelectField('Access',
                        render_kw={'class': 'input-field'},
                        choices=access)

#Delete employee record
class Employeedelete(FlaskForm):
    empid = IntegerField('Employee ID', render_kw={'class': 'input-field'}, validators=[InputRequired()])

#Update employee record
class Employeeupdate(FlaskForm):
    empid = StringField('Employee ID', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    team = SelectField('Team Add', 
                        render_kw={'class': 'input-field'},
                        choices=teams)

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
    
#Attendance query by admin userwise 
class Attnqueryusername(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, validators=[InputRequired()])
    month = SelectField('Month', render_kw={'class': 'input-field'}, choices=months)

#Attendance query for self
class Attnqueryself(FlaskForm):
    month = IntegerField('Month', render_kw={'class': 'input-field'}, 
            default=datetime.now().month, validators=[InputRequired(), 
            NumberRange(min=1, max=12, message='Number must be between 1 to 12')])
    year = IntegerField('Year ', render_kw={'class': 'input-field'}, default=datetime.now().year, 
            validators=[InputRequired(), NumberRange(min=2021, max=2030, message='Number must be between 2021 to 2030')])
    query = SelectField('Query', render_kw={'class': 'input-field'}, choices=queries)

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

#Update team
class Updateteam(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])
    team = SelectField('Team', render_kw={'class': 'input-field'}, choices=teams)
    action = SelectField('Action', render_kw={'class': 'input-field'}, choices=actions)

#Update department
class Updatedept(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])
    dept = SelectField('Team', render_kw={'class': 'input-field'}, choices=departments)
    
#Reset password
class Resetpass(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])

#Update role
class Updaterole(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])
    role = SelectField('Role', render_kw={'class': 'input-field'}, choices=roles)

#Update access
class Updateaccess(FlaskForm):
    username = StringField('Username', render_kw={'class': 'input-field'}, 
                            validators=[InputRequired()])
    access = SelectField('Role', render_kw={'class': 'input-field'}, choices=access)

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
duty_types = [('', 'No'), ('Casual adjust - On site', 'On site'), ('Casual adjust - Off site', 'Off site')]
class Leavecasual(Dates):
    remark = TextAreaField('Remark', render_kw={'class': 'textarea-field'}, validators=[InputRequired()])
    holiday_duty = SelectField('Adjust with holiday duty', render_kw={'class': 'form-input'}, choices=duty_types)
    holiday_start_date = DateField('Holiday Start Date', format='%Y-%m-%d', render_kw={'class': 'form-input'}, validators=[Optional()])
    holiday_end_date = DateField('Holiday End Date', format='%Y-%m-%d', render_kw={'class': 'form-input'}, validators=[Optional()])
    
    #Extra validator
    def validate_holiday_duty(self, field):
        if field.data != 'No':
            if not self.holiday_start_date.data:
                raise ValidationError('Must give Holiday start date')

            if self.holiday_end_date.data:
                if self.holiday_start_date.data > self.holiday_end_date.data:
                    raise ValidationError('Holiday end date must be same or later than Holiday start date')

class LeaveMedical(Leavecasual):
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
        form = LeaveMedical()
    
    return render_template('forms.html', type='leave', leave=type, form=form)

#Leave application - Fiber
class Leavefibercasual(Leavecasual):
    empid = SelectField('Name', render_kw={'class' : 'input-field'}, choices=[], coerce=int, validate_choice=False)

class Leavefibermedical(LeaveMedical, Leavefibercasual):
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
class Attnapplication(Leavecasual):
    type = RadioField('Type', render_kw={'class': 'input-field'}, choices=attendance, validators=[InputRequired()])

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
def attn_fiber():
    form = Attnapplfiber()
    
    names = Employee.query.join(Team).filter(Team.name==session['team'], Employee.role=='Team').all()
    form.empid.choices = [(i.id, i.fullname) for i in names]
    
    return render_template('forms.html', type='attn_application', team='fiber', form=form)

#Attendance file upload 
@forms.route('/forms/attendance/upload', methods=['GET', 'POST'])
@login_required
def upload():
    form = Attndataupload()
    return render_template('forms.html', form_type='attendance_upload', form=form)

#Attendance query
@forms.route('/forms/attendance/query/<query_type>', methods=['GET', 'POST'])
@login_required
def attendance_query(query_type):
    
    if session['role'] == 'User' and session['access'] != 'Admin':
        flash('You are not authorized to access this page', category='error')
        return render_template('base.html')

    if query_type == 'date':
        form = Attnquerydate()
    elif query_type == 'username':
        form = Attnqueryusername()
    elif query_type == 'month':
        form = Attnsummaryshow()
    else:
        current_app.logger.error('attnquery_all(): unknown form type')
        flash('Could not create form', category='error')
    
    if session['role'] == 'Manager':
        query_for = 'Team'
    elif session['role'] == 'Head':
        query_for = 'Department'
    elif session['access'] == 'Admin':
        query_for = 'All'
    else:
        current_app.logger.error('attendance_query(): Unknow user type %s, %s', session['role'], session['access'])
        flash('Failed to create form', category='error')
        return render_template('base.html')

    return render_template('attn_query.html', query_for=query_for, query_type=query_type, form=form)

#Attendance query - Team
@forms.route('/forms/attendance/query/team', methods=['GET', 'POST'])
@login_required
@manager_required
def attnquery_team():
    form = Attnqueryall()
    return render_template('forms.html', type='attnquery', user='team', form=form)

#Attendance query - Self
@forms.route('/forms/attendance/query/self', methods=['GET', 'POST'])
@login_required
def attnquery_self():
    form = Attnqueryself()
    return render_template('forms.html', type='attnquery_self', form=form)

#Attendance summary prepare
@forms.route('/forms/attendance/prepare_summary')
@login_required
@admin_required
def attn_prepare_summary():
    form = Attnsummary()
    return render_template('forms.html', type='attn_prepare_summary', form=form)

#Leave deduction
@forms.route('/forms/leave/deduction')
@login_required
@admin_required
def leave_deduction():
    form = Leavededuction()
    return render_template('forms.html', type='leave_deduction', form=form)

#Employee create
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
@forms.route('/forms/employee/update_role')
@login_required
@admin_required
def update_role():
    form = Updaterole()
    return render_template('emp_update.html', type='role', form=form)

#Employee modify - access
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