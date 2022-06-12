from threading import local
from flask import (Blueprint, current_app, redirect, render_template, request, send_from_directory, 
                    session, flash, url_for)
from sqlalchemy import and_, or_
from .check import date_check, user_check
from .db import (ApprLeaveAttn, AttnSummary, LeaveDeduction, db, Employee, Team, Applications, 
                    LeaveAvailable, AttnSummary)
from .mail import send_mail
from .auth import admin_required, login_required, manager_required
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timedelta
from .forms import (LeaveMedical, Leavecasual, Leavededuction, Leavefibercasual, Leavefibermedical)
from .employee import fiscalyear


# renaming original uploaded files and saving to disk, also creating a string 
# with all the file names for storing in database 
def save_files(files, username):
    file_names = ''
    file_id = datetime.now().strftime("%Y%m%d%H%M%S")
    file_count = 1
                
    for file in files:
        file_name = secure_filename(file.filename)
        ext = os.path.splitext(file_name)[1]
        file_name = username + "_" + file_id + str(file_count) + ext
        file_url = os.path.join(current_app.config['UPLOAD_FOLDER'], file_name)
        file.save(file_url)
        file_names += file_name + ';'
        file_count += 1
    
    file_names = file_names[:-1]
    return file_names

# delete files uploaded with Medical leave application
def delete_files(files):
    file_list = ''
    
    for file in files:
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file)

        if os.path.exists(file_path):
            os.remove(file_path)
        else:
            file_list += file_path
    
    return file_list
            
#checking leave availability in leave_available table
def leave_available(empid, applied):
    leave = LeaveAvailable.query.join(Employee).filter(Employee.id == empid).\
                    first()
    available = True
        
    if type == 'Casual':
        if leave.casual < applied:
            days = leave.casual + leave.earned
            if days < applied:
                available = False
    elif type == 'Medical':
        if leave.medical < applied:
            days = leave.medical + leave.casual + leave.earned
        if days < applied:
            available = False

    if not available:
        msg = 'You have applied ' + str(applied) + ' days ' + type + ' but' + ' leave available '\
                 + str(days) + ' days'
        return msg


leave = Blueprint('leave', __name__)

##Casual and Medical leave application submission##
@leave.route('/leave/application/<type>', methods=['GET', 'POST'])
@login_required
def application(type):

    if type == 'Casual':
        form = Leavecasual()
    elif type == 'Medical':
        form = LeaveMedical()

    if form.validate_on_submit():
        
        if form.end_date.data:
            applied = (form.end_date.data - form.start_date.data).days + 1
        else:
            applied = 1
        
        date_exists = date_check(session['empid'], form.start_date.data, form.end_date.data)
        if date_exists:
            flash(date_exists, category='error')
            return redirect(url_for('forms.leave', type=type))
        
        not_available = leave_available(session['empid'], applied)
        if not_available:
            flash(not_available, category='error')
            return render_template('forms.html', form_type='leave', leave_type='Casual', form=form)
        
        if not form.end_date.data:
            form.end_date.data == form.start_date.data

        if type == 'Casual':
            leave = Applications(empid=session['empid'], type=type, start_date=form.start_date.data, 
                            end_date=form.end_date.data, duration=applied,
                            remark=form.remark.data, submission_date=datetime.now(), 
                            status='Approval Pending')
        
        if type == 'Medical':
            #creating a list of file names
            files = [form.file1.data]
            if form.file2.data is not None:
                files.append(form.file2.data)
            if form.file3.data is not None:
                files.append(form.file3.data)

            filenames = save_files(files, session['username'])

            leave = Applications(empid=session['empid'], type=type, start_date=form.start_date.data, 
                            end_date=form.end_date.data, duration=applied,
                            remark=form.remark.data, submission_date=datetime.now(), 
                            file_url=filenames, status='Approval Pending')
        
        db.session.add(leave)
        db.session.commit()
        flash('Leave submitted', category='message')
        
        #Send mail to all concerned
        application = Applications.query.filter_by(start_date=form.start_date.data, 
                            end_date=form.end_date.data, empid=session['empid']).first()
        
        if session['role'] == 'Team':
            manager = Employee.query.join(Team).filter(Team.name==session['team'], 
                                                    Employee.role=='Manager').first()
            if not manager:
                current_app.logger.warning('Team Manager email not found')
                rv = 'failed'

        if session['role'] == 'Manager':
            head = Employee.query.join(Team).filter(Employee.department==session['department'], 
                                                    Employee.role=='Head').first()
            if not head:
                current_app.logger.warning('Dept. Head email not found')
                rv = 'failed'
        
        if 'rv' in locals():
            flash('Failed to send mail', category='warning')
            return redirect(request.url)

        employee = Employee.query.filter_by(id=session['empid']).first()
        
        host = current_app.config['SMTP_HOST']
        port = current_app.config['SMTP_PORT']
        rv = send_mail(host=host, port=port, sender=employee.email, receiver=manager.email, 
                        type='leave', application=application, action='submitted')
        
        if rv:
            current_app.logger.warning(rv)
            flash('Failed to send mail', category='warning')
            return redirect(request.url)
    else:
        return render_template('forms.html', type='leave', leave=type, form=form)
    
    return redirect(url_for('forms.leave', type=type))

#Casual and Medical leave application submission for Fiber
@leave.route('/leave/application/fiber/<type>', methods=['GET', 'POST'])
@login_required
@manager_required
def application_fiber(type):
    status = 'Approved'
    submission_date = datetime.now()
    
    if type == 'Casual':
        form = Leavefibercasual()
    elif type == 'Medical':
        form = Leavefibermedical()

    if form.validate_on_submit():
        employee = Employee.query.filter_by(id=form.empid.data).first()
        if not employee:
            flash('Employee does not exists', category='error')
            return redirect(url_for('forms.leave', type=type))

        #checking dates with date_check() function
        msg = date_check(employee.id, form.start_date.data, form.end_date.data)
        if msg:
            flash(msg, category='error')
            return redirect(url_for('forms.leave', type=type))
        
        #checking leave availablity with leave_available() function
        applied = (form.end_date.data - form.start_date.data).days + 1
        msg = leave_available(employee.id, applied)
        if msg:
            flash(msg, category='error')
            return render_template('forms.html', form_type='leave', leave_type='Casual', form=form)
        
        if type == 'Casual':
            leave = Applications(empid=employee.id, type=type, start_date=form.start_date.data, 
                            end_date=form.end_date.data, duration=applied,
                            remark=form.remark.data, submission_date=submission_date, status=status)
        
        if type == 'Medical':
            #creating a list of file names
            files = [form.file1.data]
            if form.file2.data is not None:
                files.append(form.file2.data)
            if form.file3.data is not None:
                files.append(form.file3.data)

            filenames = save_files(files, employee.username)

            leave = Applications(empid=employee.id, type=type, start_date=form.start_date.data, 
                            end_date=form.end_date.data, duration=applied,
                            remark=form.remark.data, submission_date=submission_date, 
                            file_url=filenames, status=status)
        
        db.session.add(leave)
        db.session.commit()
        flash('Leave submitted', category='message')
        
        #getting leave application data from database for the above submitted leave
        application = Applications.query.filter_by(start_date=form.start_date.data, 
                                                    end_date=form.end_date.data).first()
       
        #Getting manager email address of the above employee
        manager = Employee.query.join(Team).filter(Team.name==session['team'], 
                                                    Employee.role=='Manager').first()

        #Getting admin email
        admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()

        if not admin:
            flash('Failed to send mail (HR email not found)', category='error')
            return redirect(request.url)

        #Getting department head email
        head = Employee.query.filter(Employee.department==manager.department, 
                                        Employee.role=='Head').first()
        if not head:
            flash('Failed to send mail (Department head email not found)', category='error')
            return redirect(request.url)
        
        host = current_app.config['SMTP_HOST']
        port = current_app.config['SMTP_PORT']
        rv = send_mail(host=host, port=port, sender=manager.email, receiver=admin.email, cc1=head.email, 
                        application=application, type=leave, action='approved')
        
        if rv:
            msg = 'Mail sending failed (' + str(rv) + ')' 
            flash(msg, category='error')
    else:
        return render_template('forms.html', type='leave', leave=type, team='fiber', form=form)

    return redirect(request.url)

#Leave application status for individual 
@leave.route('/leave/status/personal')
@login_required
def status_personal():
    applications = Applications.query.join(Employee).filter(Employee.id==session['empid'], 
                    or_(Applications.type=='Casual', Applications.type=='Medical')).\
                    order_by(Applications.submission_date.desc()).all()

    return render_template('data.html', type='leave_status', data='personal', applications=applications)

#Leave application status for team 
@leave.route('/leave/status/team')
@login_required
@manager_required
def status_team():
    teams = Team.query.join(Employee).filter_by(id=session['empid']).all()
    applications = []
    
    for team in teams:
        applist = Applications.query.select_from(Applications).\
                    join(Team, Applications.empid==Team.empid).\
                        filter(Team.name == team.name).order_by(Applications.status).all()
        applications += applist

    return render_template('data.html', type='leave_status', data='team', applications=applications)

#Leave application status for all
@leave.route('/leave/status/all')
@login_required
@admin_required
def status():
    applications  = Applications.query.join(Employee).order_by(Applications.status).all()
    return render_template('data.html', type='leave_status', applications=applications)

## Query & show details of each leave application using application id ##
@leave.route('/leave/details/<id>')
@login_required
def details(id):
    rv = user_check(id)
    
    if not rv:
        flash('You are not authorized to see this record', category='error')
        return redirect(url_for('leave.status', type=type))

    details = Applications.query.join(Employee).filter(Applications.id==id).first()
    return render_template('data.html', data_type='leave_details', details=details)    


## Leave application cancel function ##
@leave.route('/leave/cancel/<leave_id>')
@login_required
def cancel(leave_id):
    username = session['username']

    leave = Applications.query.join(Employee).\
            filter(and_(Employee.username == username, Applications.id == leave_id)).first()

    if not leave:
        flash('Leave not found', category='error')
    elif leave.status == 'Approved':
        flash('Cancel request sent to Team Manager', category='message')
    else:
        error = ''
        # delete files attached with Medical leave
        if leave.type == 'Medical':
            files = leave.file_url.split(';')
            
            if not files:
                error = 'File name not found in database'
            else:
                file_list = delete_files(files)
                if file_list != '':
                    error = 'Files not found in OS: ' + file_list
            
            if error != '':
                flash(error, category='error')
        
        # delete Leave record from database        
        if error == '':
            db.session.delete(leave)
            db.session.commit()
            flash('Leave cancelled', category='message')
    
    return redirect(url_for('leave.status', type='personal'))

## Showing leave summary ##
@leave.route('/leave/summary/<type>')
@login_required     
def summary(type):
    year = fiscalyear()
    
    if type == 'personal':
        leaves = LeaveAvailable.query.join(Employee).filter(and_(Employee.username == \
                        session['username'], year == year)).all()
    elif type == 'team' and session['role'] == 'Manager':
        leaves = LeaveAvailable.query.join(Employee).filter(and_(Employee.role == 'Team', 
                        Employee.team == session['team'], year == year)).all()
    elif type == 'all' and session['role'] == 'Admin':
        leaves = LeaveAvailable.query.join(Employee).all()
    else:
        flash('Your are not authorized', category='error')
        return render_template('base.html')  

    return render_template('data.html', data_type='leave_summary', leaves=leaves)

@leave.route('/leave/files/<name>')
@login_required
def files(name):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], name)

## Leave approval function ##
@leave.route('/leave/approval')
@login_required
@manager_required
def approval():
    # leave_id from url
    leave_id = request.args.get('leave_id')

    # Getting different application data and team name of a single leave application 
    leave = Applications.query.select_from(Applications).join(Team, Applications.empid==Team.empid).\
                with_entities(Applications.empid, Applications.type, Applications.duration, 
                                Team.name.label('team')).\
                filter(Applications.id==leave_id).first()

    # Getting manager username from employee table of team name(which retrived from above query)
    manager = Employee.query.join(Team).filter(and_(Team.name==leave.team, 
                                                    Employee.role=='Manager')).first_or_404()

    if manager.username != session['username']:
        flash('You are not authorized', category='error')
        return redirect(url_for('leave.status', type='team'))

    #Getting leave summary record
    summary = LeaveAvailable.query.filter_by(empid=leave.empid).first()
    if not summary:
        flash('Leave summary not found', category='error')
        current_app.logger.warning('Leave summary not found, leave id: %s', leave_id)

    # if casual leave not available, add earned with casual, 
    # if still not available print error
    if leave.type == 'Casual':
        if summary.casual > leave.duration:
            casual = summary.casual - leave.duration
            summary.casual = casual
        else:
            total = summary.casual + summary.earned
            if total > leave.duration:
                earned = total - leave.duration
                summary.casual = 0
                summary.earned = earned
            else:
                flash('Leave not available, check leave summary', category='error')
                return redirect(url_for('leave.status', type='team'))

    # if medical leave not available, add casual with medical, 
    # if still not available, add earned with medical & casual
    # if still not available print error 
    if leave.type == 'Medical':

        if summary.medical > leave.duration:
            medical = summary.medical - leave.duration
            summary.medical = medical
        else:
            total = summary.medical + summary.casual
            if total > leave.duration:
                casual = total - leave.duration
                summary.medical = 0
                summary.casual = casual
            else:
                total = total + summary.earned
                if total > leave.duration:
                    earned = total - leave.duration
                    summary.medical = 0
                    summary.casual = 0
                    summary.earned = earned
                else:
                    flash('Leave not available, check leave summary', category='error')
                    return redirect(url_for('leave.status', type='team'))

    # Application table queried again to update status column,
    # this is done because previous Application table query result was a tuple not an object 
    leave = Applications.query.filter_by(id=leave_id).one()
    leave.status = 'Approved'
    
    # For each date between leave start_date and end_date from 'application' table, 
    # update 'appr_leave_attn' table 'approved' column.
    start_date = leave.start_date
    end_date = leave.end_date

    while start_date <= end_date:
        datestr = datetime.strftime(start_date, '%Y-%m-%d')
        attendance = ApprLeaveAttn.query.filter(ApprLeaveAttn.date==datestr).\
                                    filter(ApprLeaveAttn.empid==leave.empid).first()

        if attendance:
            attendance.approved = leave.type
        
        start_date += timedelta(days=1)

    db.session.commit()

    #Getting HR email 
    admin = Employee.query.filter(Employee.role=='Admin', Employee.username!='admin').first()

    #Getting application details
    application = Applications.query.filter_by(id=leave_id).first()

    #Getting department head's email
    head = Employee.query.filter(Employee.department==application.employee.department, 
                                Employee.role=='Head').first()

    #send mail to concern parties
    host = current_app.config['SMTP_HOST']
    port = current_app.config['SMTP_PORT'] 
    rv = send_mail(host=host, port=port, sender=manager.email, receiver=admin.email, cc1=application.employee.email, 
                    cc2=head.email, application=application, type='leave', action='approved')
    if rv:
        msg = 'Mail sending failed (' + str(rv) + ')' 
        flash(msg, category='error')

    return redirect(url_for('leave.status', type='team'))


## Leave deduction function ##
@leave.route('/leave/deduction', methods=['GET', 'POST'])
@login_required
@admin_required
def deduction():
    form = Leavededuction()

    month = datetime.strptime(form.month.data, '%B').month
    cur_month = datetime.now().month
    cur_year = datetime.now().year

    #checking given month number is equal or greater than current month number
    #leave deduction is only permitted for previous month or months before that
    if month >= cur_month and int(form.year.data) >= cur_year:
        flash('You can only deduct leave for attendance of previous month or before previous month', category='error')    
        return redirect(url_for('forms.leave_deduction'))
    
    #checking given month name exists in 'leave_deduction' table or not
    #if exists, it means leave deduction already performed for this month
    deducted = LeaveDeduction.query.filter_by(month=form.month.data).\
                                    filter_by(year=form.year.data).first()

    if deducted:
        flash('You have already deducted leave for this month', category='error')
        return redirect(url_for('forms.leave_deduction'))

    summary = AttnSummary.query.filter(AttnSummary.year==form.year.data).\
                                filter(AttnSummary.month==form.month.data).all()
    if summary:
        for employee in summary:
            if employee.late >= 3:
                leave = LeaveAvailable.query.filter(LeaveAvailable.empid==employee.empid).first()

                #if late count is more than or equal to 3 in a month, 1 casual leave will be
                #deducted for 3 late attendance.if sufficient casual leave not available for
                #deduction, 1 absent will be counted for 3 late. deducted leave days and absent 
                #due to late is recorded in attn_summary table
                days = round(employee.late/3)

                if leave.casual > days:
                    leave.casual = leave.casual - days
                    deducted = days
                    absent = 0
                else:
                    leave.casual = 0
                    absent = days - leave.casual
                    deducted = days - absent
                
                employee.late_absent = absent
                employee.deducted = deducted
        
        #add entry in 'leave_deduction' table 
        deduction = LeaveDeduction(year=form.year.data, month=form.month.data, 
                                date=datetime.now())
        
        db.session.add(deduction)
        db.session.commit()
        flash('Leave deducted')
    else:
        flash('No record found in attendance summary', category='warning')
    
    return redirect(url_for('forms.leave_deduction'))
