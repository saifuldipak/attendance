from flask import Blueprint, current_app, redirect, render_template, session, flash, url_for
from sqlalchemy import and_, or_
from .db import db, Employee, Team, Applications, LeaveAvailable, AttendanceSummary, LeaveDeductionSummary
from .auth import *
from .forms import Createleave, Monthyear
import datetime
from .functions import get_fiscal_year_start_end_2, update_leave_summary
from datetime import date

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

    for summary in all_summary:
        total_deduct = 0
        salary_deduct = 0
                
        if summary.late > 2 or summary.early > 2:
            leave_available = LeaveAvailable.query.filter(LeaveAvailable.empid==summary.empid).first()
            leave_available_casual_earned = leave_available.casual + leave_available.earned
            total_deduct = int(summary.late/3) + int(summary.early/3)
            
            if leave_available.casual >= total_deduct:
                leave_available.casual = leave_available.casual - total_deduct
            elif leave_available_casual_earned >= total_deduct:
                leave_available.earned = leave_available_casual_earned - total_deduct
                leave_available.casual = 0
            else:    
                leave_available.casual = 0
                leave_available.earned = 0
                salary_deduct = (total_deduct - leave_available_casual_earned)

        if summary.absent > 0:
            salary_deduct += summary.absent

        deduction = LeaveDeductionSummary(attendance_summary=summary.id, empid=summary.empid, late_early=total_deduct, salary_deduct=salary_deduct, year=form.year.data, month=form.month.data)
        db.session.add(deduction)
    
    db.session.commit()
    flash('Leave deducted')
    
    return redirect(url_for('forms.leave_deduction'))

@leave.route('/leave/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_leave():
    form = Createleave()
    
    if form.validate_on_submit():
        year_start = datetime.date(form.year_start.data, 7, 1)
        year_end = datetime.date(form.year_start.data + 1, 6, 30)

        employees = Employee.query.all()
        count = 0
        for employee in employees:
            leave_available = LeaveAvailable.query.filter(LeaveAvailable.year_start <= year_start, 
                                LeaveAvailable.year_end >= year_end, LeaveAvailable.empid==employee.id).first()
            if leave_available:
                message = f'Leave exists for {employee.fullname} year: {leave_available.year_start} - {leave_available.year_end}'
                flash(message, category='warning')
            else:
                leave_available = LeaveAvailable(empid=employee.id, year_start=year_start, year_end=year_end, 
                                    casual=current_app.config['CASUAL'], medical=current_app.config['MEDICAL'], 
                                    earned=current_app.config['EARNED'])
                db.session.add(leave_available)
                count += 1
        
        if count:
            db.session.commit()
            form.year_end.data = form.year_start.data + 1
            message = f'Leave added for {count} employees for {form.year_start.data}-{form.year_end.data}'
            flash(message, category='message')
        else:
            flash('No leave added', category='error')

        return render_template('base.html')
    else:
        return render_template('forms.html', type='create_leave', form=form)
    

@leave.route('/leave/approval/batch')
@login_required
@admin_required
def approval_batch():
    employees = Employee.query.all()
    
    for employee in employees:
        leave_available = LeaveAvailable.query.filter_by(empid=employee.id).first()
        casual_approved = Applications.query.with_entities(db.func.sum(Applications.duration).label('days')).filter_by(empid=employee.id, type='Casual', status='Approved').first() 
        medical_approved = Applications.query.with_entities(db.func.sum(Applications.duration).label('days')).filter_by(empid=employee.id, type='Medical', status='Approved').first() 

        leave_available.casual = current_app.config['CASUAL']
        leave_available.medical = current_app.config['MEDICAL']
        leave_available.earned = current_app.config['EARNED']
        leave_available_casual_earned = leave_available.casual + leave_available.earned
        
        if casual_approved.days:
            if casual_approved.days <= leave_available.casual:
                leave_available.casual = leave_available.casual - casual_approved.days
            elif casual_approved.days > leave_available.casual and casual_approved.days <= leave_available_casual_earned:
                leave_available.earned = leave_available_casual_earned - casual_approved.days
                leave_available.casual = 0
            else:
                current_app.logger.error('Failed to update leave_available table for %s (casual)', employee.username)
                msg = f'Batch casual leave approval failed for {employee.fullname}'
                flash(msg, category='warning')

        leave_available_medical_casual = leave_available.medical + leave_available.casual
        leave_available_all = leave_available_medical_casual + leave_available.earned
        
        if medical_approved.days:
            if medical_approved.days <= leave_available.medical:
                leave_available.medical = leave_available.medical - medical_approved.days
            elif medical_approved.days > leave_available.medical and medical_approved.days <= leave_available_medical_casual:
                leave_available.medical = 0
                leave_available.casual = leave_available_medical_casual - medical_approved.days
            elif medical_approved.days > leave_available_medical_casual and medical_approved.days <= leave_available_all:
                leave_available.earned = leave_available_all - medical_approved.days
                leave_available.medical = 0
                leave_available.casual = 0
            else:
                current_app.logger.error('Failed to update leave_available table for of %s (medical)', employee.username)
                msg = f'Batch medical leave approval failed for {employee.fullname}'
                flash(msg, category='warning')

    db.session.commit()
    flash('Leave approved in batch', category='message')
    return render_template('base.html')


""" @leave.route('/leave/summary')
@login_required     
def summary():
    (year_start_date, year_end_date) = get_fiscal_year_start_end()

    approved_casual = Applications.query.filte(Applications.empid==session['empid'], Applications.start_date >= year_start_date, Applications.start_date <= year_end_date, Applications.type == 'Casual').first()
    approved_medical = Applications.query.filte(Applications.empid==session['empid'], Applications.start_date >= year_start_date, Applications.start_date <= year_end_date, Applications.type == 'Medical').first()

    yearly_casual = current_app.config['CASUAL']
    yearly_earned = current_app.config['EARNED']
    yearly_medical = current_app.config['MEDICAL']
    yearly_casual_earned = yearly_casual + yearly_earned
    yearly_all = yearly_medical + yearly_casual + yearly_earned

    if yearly_casual > approved_casual:
        leave_available_casual = yearly_casual - approved_casual
    elif approved_casual > yearly_casual and approved_casual < yearly_casual_earned:
        leave_available_casual = 0
        leave_available_earned = yearly_casual_earned - approved_casual
    elif approved_casual > yearly_casual_earned:
        current_app.logger.error(' summary(): approved casual leave is greater than yearly casual+earned leave')
        flash('Failed to get leave summary', category='error')
        return render_template('base.html')

    yearly_medical_casual = yearly_medical + leave_available_casual

    if yearly_medical > approved_medical:
        leave_available_medical = yearly_medical - approved_medical
    elif approved_medical > yearly_medical and approved_medical < yearly_medical_casual:
        leave_available_medical = 0
        leave_available_casual = yearly_medical_casual - approved_medical
    elif approved_medical > yearly_medical_casual and approved_medical < yearly_all:
        leave_available = yearly_all - approved_medical
    elif approved_medical > yearly_all:
        current_app.logger.error(' summary(): approved medical leave is greater than yearly medical+casual+earned leave')
        flash('Failed to get leave summary', category='error')
        return render_template('base.html')

    leaves = LeaveAvailable.query.join(Employee).filter(Employee.id==session['empid'], and_(LeaveAvailable.year_start < datetime.datetime.now().date(), LeaveAvailable.year_end > datetime.datetime.now().date())).all()
    if not leaves:
        current_app.logger.warning('summary_self(): No data found in leave_available table for %s', session['empid'])
        flash('No leave summary record found', category='warning')

    return render_template('data.html', data_type='leave_summary', leaves=leaves) """


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
    (year_start_date, year_end_date) = get_fiscal_year_start_end_2(deduction_date)
    employees = Employee.query.all()
   
    rv = update_leave_summary(employees, year_start_date, year_end_date)
    if rv:
        flash('Leave summary update failed, Please check log', category='error')
    else:
        flash('Leave deduction reversed')
   
    return redirect(url_for('forms.reverse_leave_deduction'))


@leave.route('/leave/summary/<type>')
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

    if type == 'self':
        leave_summary = LeaveAvailable.query.join(Employee).filter(Employee.id==session['empid'], and_(LeaveAvailable.year_start < datetime.datetime.now().date(), LeaveAvailable.year_end > datetime.datetime.now().date())).all()
        if not leave_summary:
            current_app.logger.warning(' summary(): No data found in leave_available table for %s', session['empid'])
            flash('No leave summary record found', category='warning')
            return render_template('base.html')

    if type == 'team':
        teams = Team.query.filter_by(empid=session['empid']).all()
        team_summary = []
    
        for team in teams:
            summary = LeaveAvailable.query.join(Employee, Team).filter(Team.name==team.name, Employee.id!=session['empid'], and_(LeaveAvailable.year_start < datetime.datetime.now().date(), LeaveAvailable.year_end > datetime.datetime.now().date())).all()
            team_summary += summary
        
        leave_summary = team_summary
    
        if not leave_summary:
            current_app.logger.warning(' summary(): No data found in leave_available table for team user "%s"', session['username'])
            flash('No leave summary record found for team', category='warning')
            return render_template('base.html')
    
    if type == 'department':
        leave_summary = LeaveAvailable.query.join(Employee).filter(Employee.department==session['department'], Employee.id!=session['empid'],  and_(LeaveAvailable.year_start < datetime.datetime.now().date(), LeaveAvailable.year_end > datetime.datetime.now().date())).all()

    if type == 'all':
        leave_summary = LeaveAvailable.query.join(Employee).filter(or_(LeaveAvailable.year_start < datetime.datetime.now().date(), LeaveAvailable.year_end > datetime.datetime.now().date())).all()

    return render_template('data.html', data_type='leave_summary', leave_summary=leave_summary)


@leave.route('/leave/update')
@login_required
@admin_required
def update_leave():
    employees = Employee.query.all()
    (year_start_date, year_end_date) = get_fiscal_year_start_end_2(date.today())
    
    rv = update_leave_summary(employees, year_start_date, year_end_date)
    if rv:
        flash('Failed to update leave', category='error')
    else:
        flash('Leave updated successfully')

    return render_template('base.html')

