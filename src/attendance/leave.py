from flask import Blueprint, current_app, redirect, render_template, session, flash, url_for
from sqlalchemy import and_, delete, or_
from attendance.db import db, Employee, Team, Applications, LeaveAvailable, AttendanceSummary, LeaveDeductionSummary, LeaveAllocation
from .auth import *
from attendance.forms import AnnualLeave, Monthyear
import datetime
from attendance.functions import calculate_annual_leave, get_fiscal_year_start_end, update_available_leave
from datetime import date
import attendance.schemas as schemas
import attendance.forms as forms
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, NoResultFound

leave = Blueprint('leave', __name__)

## Leave deduction function ##
@leave.route('/leave/deduction', methods=['GET', 'POST'])
@login_required
@admin_required
def deduction():
    form = Monthyear()
    if not form.validate_on_submit():
        return render_template('forms.html', type='leave_deduction', form=form)

    all_summary = AttendanceSummary.query.filter(AttendanceSummary.year==form.year.data, AttendanceSummary.month==form.month.data).all()
    if not all_summary:
        msg = f'No attendance summary found for {form.month.data}, {form.year.data}'
        flash(msg, category='error')
        return redirect(url_for('forms.leave_deduction'))
    
    deducted = LeaveDeductionSummary.query.filter_by(month=form.month.data, year=form.year.data).first()
    if deducted:
        msg = f'You have already deducted leave for {form.month.data}, {form.year.data}'
        flash(msg, category='error')
        return redirect(url_for('forms.leave_deduction'))
    
    date_object = date(form.year.data, form.month.data, 1)
    (year_start_date, year_end_date) = get_fiscal_year_start_end(date_object)

    for summary in all_summary:
        leave_deducted = 0
        salary_deducted = 0
                
        if summary.late > 2 or summary.early > 2 or summary.holiday_leave > 0:
            leave_available = LeaveAvailable.query.filter(LeaveAvailable.empid==summary.empid, LeaveAvailable.year_start==year_start_date, LeaveAvailable.year_end==year_end_date).first() # type: ignore
            leave_available_casual_earned = leave_available.casual + leave_available.earned # type: ignore
            leave_deducted = int(summary.late/3) + int(summary.early/3) + summary.holiday_leave
            
            if leave_available.casual >= leave_deducted: # type: ignore
                leave_available.casual = leave_available.casual - leave_deducted # type: ignore
            elif leave_available_casual_earned >= leave_deducted:
                leave_available.earned = leave_available_casual_earned - leave_deducted # type: ignore
                leave_available.casual = 0 # type: ignore
            else:    
                leave_available.casual = 0 # type: ignore
                leave_available.earned = 0 # type: ignore
                salary_deducted = (leave_deducted - leave_available_casual_earned)
                leave_deducted = leave_available_casual_earned

        if summary.absent > 0:
            salary_deducted += summary.absent

        deduction = LeaveDeductionSummary(attendance_summary=summary.id, empid=summary.empid, leave_deducted=leave_deducted, salary_deducted=salary_deducted, year=form.year.data, month=form.month.data) # type: ignore
        db.session.add(deduction)
    
    db.session.commit()
    flash('Leave deducted')
    
    return redirect(url_for('forms.leave_deduction'))

@leave.route('/leave/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_annual_leave():
    form = forms.AnnualLeave()
    if not form.validate_on_submit():
        return render_template('forms.html', type='annual_leave', action='add', form=form)
    
    #check any data already exists for fiscal_year_start_date and fiscal_year_end_date
    try:
        leave_available = LeaveAvailable.query.filter(or_(LeaveAvailable.fiscal_year_start_date == form.fiscal_year_start_date.data, LeaveAvailable.fiscal_year_end_date == form.fiscal_year_end_date.data)).first()
        leave_allocation = LeaveAllocation.query.filter(or_(LeaveAllocation.fiscal_year_start_date == form.fiscal_year_start_date.data, LeaveAllocation.fiscal_year_end_date == form.fiscal_year_end_date.data)).first()
    except SQLAlchemyError as e:
        current_app.logger.error('add_leave(): %s', e)
        flash('Failed to add leave (Internal server error)', category='error')
        return render_template('forms.html', type='annual_leave', action='add', form=form)

    if leave_available or leave_allocation:
        flash(f'Leave exists for {form.fiscal_year_start_date.data} - {form.fiscal_year_end_date.data}', category='error')
        return render_template('forms.html', type='annual_leave', action='add', form=form)  

    #add annual leave for each employee
    employees = Employee.query.all()
    count = 0
    failed_message = 'Failed to calculate annual leave'
    for employee in employees:        
        try:
            (casual, medical, earned) = calculate_annual_leave(schemas.AnnualLeave(joining_date=employee.joining_date, new_fiscal_year_start_date=form.fiscal_year_start_date.data))
        except ValidationError as e:
            current_app.logger.error('add_annual_leave() - ValidationError - %s - %s', employee.fullname, e)
            flash("Internel server error", category='error')
            break
        except NameError as e:
            current_app.logger.error('add_annual_leave() - NameError - %s - %s', employee.fullname, e)
            flash('Internal server error', category='error')
            break

        try:
            leave_available = LeaveAvailable(empid=employee.id, fiscal_year_start_date=form.fiscal_year_start_date.data, fiscal_year_end_date=form.fiscal_year_end_date.data, casual=casual, medical=medical, earned=earned) # type: ignore
            leave_allocation = LeaveAllocation(empid=employee.id, fiscal_year_start_date=form.fiscal_year_start_date.data, fiscal_year_end_date=form.fiscal_year_end_date.data, casual=casual, medical=medical, earned=earned) # type: ignore
            db.session.add(leave_available)
            db.session.add(leave_allocation)
            count += 1
        except SQLAlchemyError as e:
            current_app.logger.error('add_annual_leave() - SQLAlchemyError - %s - %s', employee.fullname, e)
            flash(f"{failed_message} for {employee.fullname}", category='warning')
    
    if count:
        db.session.commit()
        message = f'Leave added for {count} employees from {form.fiscal_year_start_date.data} to {form.fiscal_year_end_date.data}' # type: ignore
        flash(message, category='info')
    else:
        flash('No leave added', category='error')

    return render_template('base.html')   
    

@leave.route('/leave/approval/batch')
@login_required
@admin_required
def approval_batch():
    employees = Employee.query.all()
    
    for employee in employees:
        leave_available = LeaveAvailable.query.filter_by(empid=employee.id).first()
        casual_approved = Applications.query.with_entities(db.func.sum(Applications.duration).label('days')).filter_by(empid=employee.id, type='Casual', status='Approved').first() 
        medical_approved = Applications.query.with_entities(db.func.sum(Applications.duration).label('days')).filter_by(empid=employee.id, type='Medical', status='Approved').first() 

        leave_available.casual = current_app.config['CASUAL'] # type: ignore
        leave_available.medical = current_app.config['MEDICAL'] # type: ignore
        leave_available.earned = current_app.config['EARNED'] # type: ignore
        leave_available_casual_earned = leave_available.casual + leave_available.earned # type: ignore
        
        if casual_approved.days: # type: ignore
            if casual_approved.days <= leave_available.casual: # type: ignore
                leave_available.casual = leave_available.casual - casual_approved.days # type: ignore
            elif casual_approved.days > leave_available.casual and casual_approved.days <= leave_available_casual_earned: # type: ignore
                leave_available.earned = leave_available_casual_earned - casual_approved.days # type: ignore
                leave_available.casual = 0 # type: ignore
            else:
                current_app.logger.error('Failed to update leave_available table for %s (casual)', employee.username)
                msg = f'Batch casual leave approval failed for {employee.fullname}'
                flash(msg, category='warning')

        leave_available_medical_casual = leave_available.medical + leave_available.casual # type: ignore
        leave_available_all = leave_available_medical_casual + leave_available.earned # type: ignore
        
        if medical_approved.days: # type: ignore
            if medical_approved.days <= leave_available.medical: # type: ignore
                leave_available.medical = leave_available.medical - medical_approved.days # type: ignore
            elif medical_approved.days > leave_available.medical and medical_approved.days <= leave_available_medical_casual: # type: ignore
                leave_available.medical = 0 # type: ignore
                leave_available.casual = leave_available_medical_casual - medical_approved.days # type: ignore
            elif medical_approved.days > leave_available_medical_casual and medical_approved.days <= leave_available_all: # type: ignore
                leave_available.earned = leave_available_all - medical_approved.days # type: ignore
                leave_available.medical = 0 # type: ignore
                leave_available.casual = 0 # type: ignore
            else:
                current_app.logger.error('Failed to update leave_available table for of %s (medical)', employee.username)
                msg = f'Batch medical leave approval failed for {employee.fullname}'
                flash(msg, category='warning')

    db.session.commit()
    flash('Leave approved in batch', category='message')
    return render_template('base.html')


@leave.route('/leave/reverse_deduction', methods=['GET', 'POST'])
@login_required
@admin_required
def reverse_deduction():
    form = Monthyear()
    if not form.validate_on_submit():
        return render_template('forms.html', type='leave_deduction', action='reverse', form=form)
    
    all_deducted = LeaveDeductionSummary.query.filter_by(month=form.month.data, year=form.year.data).all()
    if not all_deducted:
        msg = f'No leave deduction record found for {form.month.data}, {form.year.data}'
        flash(msg, category='error')
        return redirect(url_for('forms.reverse_leave_deduction'))
        
    for deducted in all_deducted:
        db.session.delete(deducted)
    
    db.session.commit()

    deduction_date = date(form.year.data, form.month.data, 1)
    (fiscal_year_start_date, fiscal_year_end_date) = get_fiscal_year_start_end(deduction_date)
    
    employees = Employee.query.all()
    number_of_employees = len(employees)
    leave_updated_employees = 0
    for employee in employees:
        try:
            update_available_leave(schemas.EmployeeFiscalYear(employee=employee, fiscal_year_start_date=fiscal_year_start_date, fiscal_year_end_date=fiscal_year_end_date))
            leave_updated_employees += 1
        except ValidationError as e:
            current_app.logger.error('reverse_deduction() - ValidationError - %s - %s', employee.fullname, e)
            break
        except NoResultFound as e:
            current_app.logger.warning('Leave not found for %s - from %s to %s', employee.username, fiscal_year_start_date, fiscal_year_end_date)
        except SQLAlchemyError as e:
            current_app.logger.error('reverse_deduction(): SQLAlchemyError - %s', e)
            break

    if leave_updated_employees == number_of_employees:
        flash('Leave deduction reversed', category='info')
    else:
        flash('Failed to reverse deduction (Internal server error)', category='error')

    return redirect(url_for('forms.reverse_leave_deduction'))

@leave.route('/leave/summary/<type>', methods=['GET', 'POST'])
@login_required     
def summary(type):
    if type not in ('self', 'team', 'department', 'all'):
        current_app.logger.error(' summary(): unknown type "%s" for user "%s"', type, session['username'])
        flash('Failed to show summary', category='error')
        return render_template('base.html')
    
    if type == 'team' and session['role'] not in ('Supervisor', 'Manager'):
        current_app.logger.error(' summary(): "%s" is trying to access team leave summary', session['username'])
        flash('You are not authorized to see leave summary of team', category='error')
        return render_template('base.html')
    
    if type == 'department' and session['role'] != 'Head':
        current_app.logger.error(' summary(): "%s" is trying to access department leave summary', session['username'])
        flash('You are not authorized to see leave summary of department', category='error')
        return render_template('base.html')
    
    if type == 'all' and session['access'] != 'Admin':
        current_app.logger.error(' summary(): "%s" is trying to access all leave summary', session['username'])
        flash('You are not authorized to see leave summary of all', category='error')
        return render_template('base.html')

    form = AnnualLeave()
    if type == 'self':
        try:
            leave_summary = LeaveAvailable.query.join(Employee).filter(Employee.id==session['empid'], and_(LeaveAvailable.fiscal_year_start_date == form.fiscal_year_start_date.data)).one()
        except NoResultFound as e:
            flash('No leave summary record found', category='warning')
            return render_template('base.html')
        except IntegrityError as e:
            current_app.logger.error(' summary(): IntegrityError: %s', e)
            flash('Failed to show summary', category='error')
            return render_template('base.html')

    if type == 'team':
        teams = Team.query.filter_by(empid=session['empid']).all()
        team_summary = []
        for team in teams:
            try:
                summary = LeaveAvailable.query.join(Employee, Team).filter(Team.name==team.name, Employee.id!=session['empid'], and_(LeaveAvailable.fiscal_year_start_date == form.fiscal_year_start_date.data)).all() # type: ignore
            except IntegrityError as e:
                current_app.logger.error(' summary(): IntegrityError: %s', e)
                flash('Failed to show summary', category='error')
                return render_template('base.html')
            team_summary += summary
        leave_summary = team_summary
    
        if not leave_summary:
            current_app.logger.warning(' summary(): No data found in leave_available table for team user "%s"', session['username'])
            flash('No leave summary record found for team', category='warning')
            return render_template('base.html')
    
    if type == 'department':
        try:
            leave_summary = LeaveAvailable.query.join(Employee).filter(Employee.department==session['department'], Employee.id!=session['empid'],  and_(LeaveAvailable.fiscal_year_start_date == form.fiscal_year_start_date)).all()
        except IntegrityError as e:
            current_app.logger.error(' summary(): IntegrityError: %s', e)
            flash('Failed to show summary', category='error')
            return render_template('base.html')
        
    if type == 'all':
        try:
            leave_summary = LeaveAvailable.query.join(Employee).filter(LeaveAvailable.fiscal_year_start_date == form.fiscal_year_start_date.data).all()
        except IntegrityError as e:
            current_app.logger.error(' summary(): IntegrityError: %s', e)
            flash('Failed to show summary', category='error')
            return render_template('base.html')

    if not leave_summary:
        flash(f'No leave summary record found for {form.fiscal_year_start_date.data} to {form.fiscal_year_end_date.data}', category='warning')

    return render_template('data.html', data_type='leave_summary', type=type, leave_summary=leave_summary, form=form)   

@leave.route('/leave/update', methods=['GET', 'POST'])
@login_required
@admin_required
def update_leave():
    form = AnnualLeave()
    if not form.validate_on_submit():
        return render_template('forms.html', type='update_leave', form=form)

    employees = Employee.query.all()
    for employee in employees:
        internal_error = f'Failed to update leave for {employee.fullname} (internal error)'
        no_leave_found = f'Failed to update leave for {employee.fullname} (no leave found)'
        try:
            return_message = update_available_leave(schemas.EmployeeFiscalYear(employee=employee, fiscal_year_start_date=form.fiscal_year_start_date.data, fiscal_year_end_date=form.fiscal_year_end_date.data))
        except ValidationError as e:
            current_app.logger.error(' %s', e)
            flash(internal_error, category='warning')
        except NoResultFound as e:
            flash(no_leave_found, category='warning')
        except SQLAlchemyError as e:
            flash(internal_error, category='warning')
        else:
            flash(return_message, category='info')

    return render_template('base.html')

@leave.route('/leave/delete', methods=['GET', 'POST'])
@login_required
@admin_required
def delete_annual_leave():
    (fiscal_year_start_date, fiscal_year_end_date) = get_fiscal_year_start_end()

    function_name = 'delete_annual_leave()'
    no_leave_found_message = f"No leave found for {fiscal_year_start_date} to {fiscal_year_end_date}"
    internal_error_message = f'Failed to delete leave for {fiscal_year_start_date} - {fiscal_year_end_date}'

    try:
        leave_available = LeaveAvailable.query.filter(LeaveAvailable.fiscal_year_start_date == fiscal_year_start_date).first()
        leave_allocation = LeaveAllocation.query.filter(LeaveAllocation.fiscal_year_start_date == fiscal_year_start_date).first()
        if not leave_available and not leave_allocation:
            flash(no_leave_found_message, category='warning')
            return render_template('base.html')
        
        if leave_available:
            stmt = delete(LeaveAvailable).where(LeaveAvailable.fiscal_year_start_date == fiscal_year_start_date)
            db.session.execute(stmt)

        if leave_allocation:    
            stmt = delete(LeaveAllocation).where(LeaveAllocation.fiscal_year_start_date == fiscal_year_start_date)
            db.session.execute(stmt)
        
        db.session.commit()
    except SQLAlchemyError as e:
        current_app.logger.error('%s %s', function_name, e)
        flash(internal_error_message, category='error')
    else:
        flash('Leave deleted successfully', category='info')

    return render_template('base.html')