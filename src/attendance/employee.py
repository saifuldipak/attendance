import random
import secrets
import string
from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import generate_password_hash

import attendance.functions as fn
from attendance import schemas
from attendance.functions import (
    MailDeliveryError,
    calculate_annual_leave,
    get_fiscal_year,
)

from .auth import admin_required, login_required
from .db import Employee, LeaveAllocation, LeaveAvailable, Team, db
from .forms import (
    Changeselfpass,
    Employeecreate,
    Employeedelete,
    Employeesearch,
    Resetpass,
    Updateaccess,
    Updatedept,
    Updatedesignation,
    Updateemail,
    Updatefullname,
    Updatejoiningdate,
    Updatephone,
    Updaterole,
    Updateteam,
)

employee = Blueprint('employee', __name__)

# Generate random string for password
def random_string_generator():
    allowed_chars = string.ascii_letters
    str_size = 8
    return ''.join(random.choice(allowed_chars) for _ in range(str_size))

# Making string for fiscal year
def fiscalyear():
    currentyear = int(datetime.now().strftime('%Y'))  # noqa: DTZ005
    month = int(datetime.now().strftime('%m'))  # noqa: DTZ005
    if month >= 6:
        nextyear = currentyear + 1
        year = f"{currentyear}-{nextyear}"
    else:
        lastyear = currentyear - 1
        year = f"{lastyear}-{currentyear}"
    
    return year    

## Search employee record ##
@employee.route('/employee/search', methods=['GET', 'POST'])
@login_required
@admin_required
def search():
    form = Employeesearch()
    
    if form.validate_on_submit():
        string_val = f'{form.string.data}%' # type: ignore
        search_type = form.type.data.lower() if form.type.data else '' # type: ignore
        
        if search_type == 'username':
            employees = Employee.query.join(Team).filter(Employee.username.like(string_val)).all()
        elif search_type == 'fullname':
            string_val = f'%{form.string.data}%' # type: ignore
            employees = Employee.query.join(Team).filter(Employee.fullname.like(string_val)).all()
        elif search_type == 'department':
            employees = Employee.query.filter(Employee.department.like(string_val)).all()
        elif search_type == 'team':
            employees = Employee.query.join(Team).filter(Team.name.like(string_val)).all()
        elif search_type == 'designation':
            employees = Employee.query.join(Team).filter(Employee.designation.like(string_val)).all()
        elif search_type == 'access':
            employees = Employee.query.join(Team).filter(Employee.access.like(string_val)).all()
        else:
            employees = Employee.query.all()

        employee_data = [
            {
                'id': emp.id,
                'username': emp.username,
                'fullname': emp.fullname,
                'department': emp.department,
                'role': emp.role,
                'teams': [team.name for team in emp.teams]
            }
            for emp in employees
        ]

        return render_template('data.html', action='employee_search', form=form, employees=employee_data)
    
    return render_template('data.html', action='employee_search', form=form)

## Show detail employee record for every employee ##
@employee.route('/employee/details/<id>', methods=['GET', 'POST'])
@login_required
@admin_required
def details(id):
    employee_record = Employee.query.filter_by(id=id).first()
    return render_template('data.html', type='employee_details', employee=employee_record)
            
## Create employee record ##
@employee.route('/employee/create', methods=['GET', 'POST'])
@login_required
@admin_required 
def create():
    form = Employeecreate()
    if form.validate_on_submit():
        existing_user = Employee.query.filter_by(username=form.username.data).first()   # type: ignore
        if existing_user:
            flash('Username exists', category='error')
            return render_template('forms.html', form_type='employee_create', form=form)

        if form.email.data: # type: ignore
            existing_email = Employee.query.filter_by(email=form.email.data).first() # type: ignore
            if existing_email:
                flash('Email exists', category='error')
                return render_template('forms.html', form_type='employee_create', form=form)

        name = 'All' if form.role.data == 'Head' else form.team.data # type: ignore

        try:
            casual_leave, medical_leave, earned_leave = calculate_annual_leave(schemas.AnnualLeave(joining_date=form.joining_date.data)) # type: ignore
        except ValidationError as e:
            current_app.logger.error("create(): %s: %s", form.fullname.data, e) # type: ignore
            flash('Failed to calculate annual leave', category='error')
            return render_template('forms.html', form_type='employee_create', form=form)
        
        try:
            fiscal_year_start_date, fiscal_year_end_date = get_fiscal_year(form.joining_date.data) # type: ignore
        except TypeError as e:
            current_app.logger.error(e)
            flash('Failed to calculate joining fiscal year', category='error')
            return render_template('forms.html', form_type='employee_create', form=form)

        try:
            new_employee = Employee()
            new_employee.username=form.username.data, 
            new_employee.fullname=form.fullname.data, 
            new_employee.password=generate_password_hash(form.password.data), 
            new_employee.phone=form.phone.data, 
            new_employee.email=form.email.data, 
            new_employee.joining_date=form.joining_date.data, 
            new_employee.department=form.department.data, 
            new_employee.designation=form.designation.data, 
            new_employee.role=form.role.data, 
            new_employee.access=form.access.data            
            db.session.add(new_employee)
            db.session.flush()
        
            team = Team(empid=new_employee.id, name=name) # type: ignore
            db.session.add(team)
            leave_allocation = LeaveAllocation(empid=new_employee.id, fiscal_year_start_date=fiscal_year_start_date, fiscal_year_end_date=fiscal_year_end_date, casual=casual_leave, medical=medical_leave, earned=earned_leave) # type: ignore
            db.session.add(leave_allocation)
            leave_available = LeaveAvailable(empid=new_employee.id, fiscal_year_start_date=fiscal_year_start_date, fiscal_year_end_date=fiscal_year_end_date, casual=casual_leave, medical=medical_leave, earned=earned_leave) # type: ignore
            db.session.add(leave_available)
            db.session.commit()
        except (TypeError, IntegrityError, SQLAlchemyError) as e:
            db.session.rollback()
            current_app.logger.exception("create(): Error creating employee, session rolled back: %s", e)
            flash("Failed to create employee", category='error')
            return render_template('forms.html', form_type='employee_create', form=form)
        
        flash("Employee record created.", category='message')
        return redirect(url_for('forms.employee', action='create'))
    
    return render_template('forms.html', form_type='employee_create', form=form)

## Delete employee record ##
@employee.route('/employee/delete', methods=['GET', 'POST'])
@login_required
@admin_required    
def delete():     
    form = Employeedelete()

    if form.validate_on_submit():
        emp = Employee.query.filter_by(id=form.empid.data).first()
        error = ''

        if emp:
            if emp.role == 'Admin':
                admincount = Employee.query.filter_by(role='Admin').count()
                if admincount < 2:
                    error = 'You are trying to delete the last "Admin" user'
        else:
            error = 'Employee ID not found'

        if error:
            flash(error, category='error')
            return render_template('forms.html', form_type='employee_delete', form=form)
        
        db.session.delete(emp)
        db.session.commit()
        
        flash('Employee deleted', category='message')

    return redirect(url_for('forms.employee', action='delete'))

## Employee record update menu ##
@employee.route('/employee/update_menu')
@login_required
@admin_required
def update_menu():
    return render_template('emp_update.html')

## Update employee record ##
@employee.route('/employee/update/<action>', methods=['GET', 'POST'])
@login_required
@admin_required     
def update(action):
    action_form_map = {
        'team': Updateteam,
        'dept': Updatedept,
        'designation': Updatedesignation,
        'joining_date': Updatejoiningdate,
        'email': Updateemail,
        'fullname': Updatefullname,
        'phone': Updatephone,
        'role': Updaterole,
        'access': Updateaccess,
        'pass': Resetpass,
    }

    form_class = action_form_map.get(action)
    if not form_class:
        flash('Function not found', category='error')
        return redirect(url_for('employee.update_menu'))

    form = form_class()

    if form.validate_on_submit():
        emp = Employee.query.filter_by(username=form.username.data).first()
        
        if not emp:
            flash('Username not found.', category='error')
            return redirect(request.url)
        
        # Add or delete team
        if action == 'team':
            team = Team.query.filter_by(empid=emp.id, name=form.team.data).first()  # type: ignore

            if form.action.data == 'Add':  # type: ignore
                if not team:
                    team = Team(empid=emp.id, name=form.team.data)  # type: ignore
                    db.session.add(team)
                    flash('Team added', category='info')
                else:
                    flash('Team name already exists', category='error')
                    return redirect(url_for('forms.update_team'))
            
            elif form.action.data == 'Delete':  # type: ignore
                if team:
                    db.session.delete(team)
                    flash('Team deleted', category='info')
                else:
                    flash('Team name not found', category='error')
        
        # Update department
        elif action == 'dept':
            if emp.department == form.dept.data:  # type: ignore
                flash('Current and new department is the same', category='warning')
            else:
                emp.department = form.dept.data  # type: ignore
                flash('Department updated', category='info')
        
        # Update designation
        elif action == 'designation':
            if emp.designation == form.designation.data:  # type: ignore
                flash('Current and new designation is the same', category='warning')
            else:
                emp.designation = form.designation.data  # type: ignore
                flash('Designation updated', category='info')
        
        # Update joining date
        elif action == 'joining_date':
            if emp.joining_date == form.joining_date.data:  # type: ignore
                flash('Current and new joining date is the same', category='warning')
            else:
                emp.joining_date = form.joining_date.data  # type: ignore
                flash('Joining date updated', category='info')

        # Update email
        elif action == 'email':
            if emp.email == form.email.data:  # type: ignore
                flash('Current and new email is the same', category='warning')
            else:
                emp.email = form.email.data  # type: ignore
                flash('Email updated', category='info')
        
        # Update fullname
        elif action == 'fullname':
            if emp.fullname == form.fullname.data:  # type: ignore
                flash('Current and new fullname is the same', category='warning')
            else:
                emp.fullname = form.fullname.data  # type: ignore
                flash('Fullname updated', category='info')

        # Update phone
        elif action == 'phone':
            if emp.phone == form.phone.data:  # type: ignore
                flash('Current and new phone is the same', category='warning')
            else:
                emp.phone = form.phone.data  # type: ignore
                flash('Phone updated', category='info')

        # Update role
        elif action == 'role':
            if emp.role != form.role.data:  # type: ignore
                emp.role = form.role.data  # type: ignore
                flash('Role updated', category='info')
            else:
                flash('Current and new role is the same', category='warning')
        
        # Update access
        elif action == 'access':
            if emp.access != form.access.data:  # type: ignore
                emp.access = form.access.data  # type: ignore
                flash('Access updated', category='info')
            else:
                flash('Current and new access is the same', category='warning')

        # Reset password
        elif action == 'pass':
            admin_email = session.get('email')
            if not admin_email:
                flash('Admin email not found in session', category='error')
                return redirect(url_for('employee.update_menu'))
            
            if not emp.email:
                flash('Employee email not found', category='error')
                return redirect(url_for('employee.update_menu'))

            # Generate random password
            # ✅ Yields individual characters sequentially to .join()
            new_password = ''.join(
            char 
            for _ in range(3) 
            for char in (
                secrets.choice(string.ascii_lowercase),
                secrets.choice(string.ascii_uppercase),
                secrets.choice(string.digits)
            )
)
            
            # Dispatch password reset email
            try:
                fn.send_mail(
                    sender=admin_email, 
                    receiver=emp.email, 
                    mail_type='reset', 
                    extra=new_password
                )
            except MailDeliveryError as e:
                current_app.logger.warning(
                    "Failed to send password reset email to employee '%s' (ID %s): %s", 
                    emp.username, 
                    emp.id, 
                    e
                )
                flash('Failed to send password reset email. Password was not changed.', category='error')
                return redirect(url_for('employee.update_menu'))

            emp.password = generate_password_hash(new_password)
            flash('Password reset and sent via email', category='info')

        try:
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.exception("Database commit failed during employee update for '%s': %s", emp.username, e)
            flash('Failed to commit employee update to database', category='error')

    return redirect(url_for('employee.update_menu'))


## Change password for self ##
@employee.route('/employee/password/self', methods=['GET', 'POST'])
@login_required    
def password_self():
    form = Changeselfpass()

    if form.validate_on_submit():
        emp = Employee.query.filter_by(username=session['username']).first()
        if emp and form.password.data:  # type: ignore
            try:
                emp.password = generate_password_hash(form.password.data)  # type: ignore
                db.session.commit()
                flash('Password changed', category='message')
            except SQLAlchemyError as e:
                db.session.rollback()
                current_app.logger.exception("Failed to change password for user '%s': %s", session.get('username'), e)
                flash('Error updating password in database', category='error')
        else:
            flash('Error updating password', category='error')

    return render_template('forms.html', type='change_pass', form=form)

## Show detail employee record for self ##
@employee.route('/employee/details/self', methods=['GET', 'POST'])
@login_required
def details_self():
    emp = Employee.query.filter_by(username=session['username']).first()
    return render_template('data.html', type='employee_details', employee=emp)