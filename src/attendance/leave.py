from threading import local
from flask import (Blueprint, current_app, redirect, render_template, request, send_from_directory, 
                    session, flash, url_for)
from sqlalchemy import and_, or_
from .check import check_access, date_check
from .db import (ApprLeaveAttn, AttnSummary, LeaveDeduction, db, Employee, Team, Applications, 
                    LeaveAvailable, AttnSummary)
from .mail import send_mail
from .auth import admin_required, login_required, manager_required, head_required
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timedelta
from .forms import (LeaveMedical, Leavecasual, Leavededuction, Leavefibercasual, Leavefibermedical)


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

#Checking and updating leave
def check_leave(empid, start_date, duration, type, update=None):
    
    leave = LeaveAvailable.query.filter(LeaveAvailable.empid==empid, 
                and_(LeaveAvailable.year_start < start_date, 
                LeaveAvailable.year_end > start_date)).first()
    if not leave:
        current_app.logger.warning('check_leave(): no data found in leave_available table for employee %s', empid)
        return False

    if type == 'Casual':
        if leave.casual > duration:
            if update:
                casual = leave.casual - duration
                leave.casual = casual
        else:
            total = leave.casual + leave.earned
            if total > duration:
                if update:
                    earned = total - duration
                    leave.casual = 0
                    leave.earned = earned
            else:
                return False

    if type == 'Medical':
        if leave.medical > duration:
            if update:
                medical = leave.medical - duration
                leave.medical = medical
        else:
            total = leave.medical + leave.casual
            
            if total > leave.duration:
                if update:
                    casual = total - duration
                    leave.medical = 0
                    leave.casual = casual
            else:
                total = total + leave.earned
                if total > duration:
                    if update:
                        earned = total - duration
                        leave.medical = 0
                        leave.casual = 0
                        leave.earned = earned
                else:
                    return False
                
    return True
 
#update 'appr_leave_attn' table
def update_attn(empid, start_date, end_date, type):
    
    #start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
    #end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
    
    while start_date <= end_date:
        attendance = ApprLeaveAttn.query.filter(ApprLeaveAttn.date==start_date,
                        ApprLeaveAttn.empid==empid).first()

        if attendance:
            attendance.approved = type
        
        start_date += timedelta(days=1)

    db.session.commit()


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
        if not form.end_date.data:
            form.end_date.data = form.start_date.data
        
        duration = (form.end_date.data - form.start_date.data).days + 1
        
        date_exists = date_check(session['empid'], form.start_date.data, form.end_date.data)
        if date_exists:
            flash(date_exists, category='error')
            return redirect(url_for('forms.leave', type=type))
        
        available = check_leave(session['empid'], form.start_date.data, duration, type)
        if not available:
            flash('Leave not available, please check leave summary', category='error')
            return redirect(request.url)

        if type == 'Casual':
            leave = Applications(empid=session['empid'], type=type, start_date=form.start_date.data, 
                            end_date=form.end_date.data, duration=duration,
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
                            end_date=form.end_date.data, duration=duration,
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
            else:            
                receiver_email = manager.email

        if session['role'] == 'Manager':
            head = Employee.query.join(Team).filter(Employee.department==session['department'], 
                                                    Employee.role=='Head').first()
            if not head:
                current_app.logger.warning('Dept. Head email not found')
                rv = 'failed'
            else:
                receiver_email = head.email

        if 'rv' in locals():
            flash('Failed to send mail', category='warning')
            return redirect(request.url)

        employee = Employee.query.filter_by(id=session['empid']).first()
        
        host = current_app.config['SMTP_HOST']
        port = current_app.config['SMTP_PORT']
        rv = send_mail(host=host, port=port, sender=employee.email, receiver=receiver_email, 
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
    
    if type == 'Casual':
        form = Leavefibercasual()
    elif type == 'Medical':
        form = Leavefibermedical()

    if form.validate_on_submit():
        employee = Employee.query.filter_by(id=form.empid.data).first()
        if not employee:
            flash('Employee does not exists', category='error')
            return redirect(url_for('forms.leave', type=type))

        msg = date_check(employee.id, form.start_date.data, form.end_date.data)
        if msg:
            flash(msg, category='error')
            return redirect(url_for('forms.leave', type=type))
        
        if not form.end_date.data:
            form.end_date.data = form.start_date.data
        
        duration = (form.end_date.data - form.start_date.data).days + 1
        
        available = check_leave(employee.id, form.start_date.data, duration, type, 'update')
        if not available:
            flash('Leave not available, please check leave summary', category='error')
            return redirect(request.url)
        
        if type == 'Casual':
            leave = Applications(empid=employee.id, type=type, start_date=form.start_date.data, 
                            end_date=form.end_date.data, duration=duration,
                            remark=form.remark.data, submission_date=datetime.now(), 
                            status='Approved')
        
        if type == 'Medical':
            #creating a list of file names
            files = [form.file1.data]
            if form.file2.data is not None:
                files.append(form.file2.data)
            if form.file3.data is not None:
                files.append(form.file3.data)

            filenames = save_files(files, employee.username)

            leave = Applications(empid=employee.id, type=type, start_date=form.start_date.data, 
                            end_date=form.end_date.data, duration=duration,
                            remark=form.remark.data, submission_date=datetime.now(), 
                            file_url=filenames, status='Approved')
        
        db.session.add(leave)
        db.session.commit()
        flash('Leave approved', category='message')
        
        #Send mail to all concerned
        application = Applications.query.filter_by(start_date=form.start_date.data, 
                            end_date=form.end_date.data, empid=form.empid.data).first()
        
        
        manager = Employee.query.filter_by(id=session['empid']).first()
        if not manager:
            current_app.logger.warning('application_fiber(): Team Manager email not found')
            rv = 'failed'

        admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
        if not admin:
            current_app.logger.warning('application_fiber(): Admin email not found')
            rv = 'failed'

        head = Employee.query.join(Team).filter(Employee.department==session['department'], 
                    Employee.role=='Head').first()
        if not head:
            current_app.logger.warning('application_fiber(): Dept. Head email not found')
            rv = 'failed'
        
        if 'rv' in locals():
            flash('Failed to send mail', category='warning')
            return redirect(request.url)

        employee = Employee.query.filter_by(id=session['empid']).first()
        
        host = current_app.config['SMTP_HOST']
        port = current_app.config['SMTP_PORT']
        rv = send_mail(host=host, port=port, sender=manager.email, receiver=admin.email, 
                        cc1=head.email, type='leave', application=application, action='approved')
        
        if rv:
            current_app.logger.warning(rv)
            flash('Failed to send mail', category='warning')
            return redirect(request.url)
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
        team_applications = Applications.query.select_from(Applications).\
                            join(Team, Applications.empid==Team.empid).filter(Team.name==team.name, 
                            Applications.empid!=session['empid'], or_(Applications.type=='Casual', 
                            Applications.type=='Medical')).order_by(Applications.status, 
                            Applications.submission_date.desc()).all()

        applications += team_applications

    return render_template('data.html', type='leave_status', data='team', applications=applications)

#Leave application status for department
@leave.route('/leave/status/department')
@login_required
@head_required
def status_department():
    applications = Applications.query.join(Employee).\
                    filter(Employee.department==session['department'], or_(Applications.type=='Casual', 
                    Applications.type=='Medical'), Applications.empid!=session['empid']).\
                    order_by(Applications.status, Applications.submission_date.desc()).all()

    return render_template('data.html', type='leave_status', data='department', applications=applications)

#Leave application status for all
@leave.route('/leave/status/all')
@login_required
@admin_required
def status():
    applications  = Applications.query.join(Employee).filter(or_(Applications.type=='Casual', 
                    Applications.type=='Medical')).order_by(Applications.status).all()
    
    return render_template('data.html', type='leave_status', applications=applications)

## Query & show details of each leave application using application id ##
@leave.route('/leave/details/<application_id>')
@login_required
def details(application_id):
    rv = check_access(application_id)
    
    if not rv:
        flash('You are not authorized to see this record', category='error')
        return redirect(url_for('leave.status', type=type))

    details = Applications.query.join(Employee).filter(Applications.id==application_id).first()
    return render_template('data.html', data_type='leave_details', details=details)    


##Leave application cancel function##
@leave.route('/leave/cancel/<application_id>')
@login_required
def cancel(application_id):
    
    application = Applications.query.join(Employee).\
            filter(and_(Employee.id==session['empid'], Applications.id==application_id)).first()

    if not application:
        flash('Leave application not found', category='error')
    elif application.status == 'Approved':
        flash('Cancel request sent to Team Manager', category='message')
    else:
        error = ''
        # delete files attached with Medical leave
        if application.type == 'Medical':
            files = leave.file_url.split(';')
            
            if not files:
                error = 'File name not found in database'
            else:
                file_list = delete_files(files)
                if file_list != '':
                    error = 'Files not found in OS: ' + file_list
            
            if error != '':
                flash(error, category='error')
        
    #Send mail to all concerned
    if session['role'] == 'Team':
        manager = Employee.query.join(Team).filter(Team.name==session['team'], 
                                                Employee.role=='Manager').first()
        if not manager:
            current_app.logger.warning('Team Manager email not found')
        else:            
            receiver_email = manager.email

    if session['role'] == 'Manager' or not manager:
        head = Employee.query.join(Team).filter(Employee.department==session['department'], 
                                                Employee.role=='Head').first()
        if not head:
            current_app.logger.warning('Dept. Head email not found')
            rv = 'failed'
        else:
            receiver_email = head.email

    if 'rv' in locals():
        flash('Failed to send mail', category='warning')
        return redirect(request.url)

    employee = Employee.query.filter_by(id=session['empid']).first()
    
    host = current_app.config['SMTP_HOST']
    port = current_app.config['SMTP_PORT']
    rv = send_mail(host=host, port=port, sender=employee.email, receiver=receiver_email, 
                    type='leave', application=application, action='cancelled')
    
    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')
        return redirect(request.url)
    
    #delete Leave record from database        
    if error == '':
        db.session.delete(application)
        db.session.commit()
        flash('Leave cancelled', category='message')
    
    return redirect(url_for('leave.status_personal'))

##Leave summary personal##
@leave.route('/leave/summary/self')
@login_required     
def summary_self():
    leaves = LeaveAvailable.query.join(Employee).\
                filter(Employee.id==session['empid'], 
                or_(LeaveAvailable.year_start < datetime.now().date(), 
                LeaveAvailable.year_end > datetime.now().date())).all()
    if not leaves:
        current_app.logger.warning('summary_self(): No data found in leave_available table for %s', session['empid'])
        flash('No leave summary record found', category='warning')

    return render_template('data.html', data_type='leave_summary', leaves=leaves)

##Leave summary team##
@leave.route('/leave/summary/team')
@login_required
@manager_required     
def summary_team():
    teams = Team.query.filter_by(empid=session['empid']).all()
    team_leaves = []
   
    for team in teams:
        leaves = LeaveAvailable.query.join(Employee, Team).\
                filter(Team.name==team.name, Employee.id!=session['empid'], 
                or_(LeaveAvailable.year_start < datetime.now().date(), 
                LeaveAvailable.year_end > datetime.now().date())).all()
        team_leaves += leaves\
    
    leaves = team_leaves
    
    if not leaves:
        current_app.logger.warning('summary_team(): No data found in leave_available table')
        flash('No leave summary record found', category='warning')

    return render_template('data.html', data_type='leave_summary', leaves=leaves)

##Leave summary department##
@leave.route('/leave/summary/department')
@login_required
@head_required     
def summary_department():
    leaves = LeaveAvailable.query.join(Employee).\
                filter(Employee.department==session['department'], Employee.id!=session['empid'],  
                or_(LeaveAvailable.year_start < datetime.now().date(), 
                LeaveAvailable.year_end > datetime.now().date())).all()
    
    if not leaves:
        current_app.logger.warning('summary_department(): No data found in leave_available table')
        flash('No leave summary record found', category='warning')

    return render_template('data.html', data_type='leave_summary', leaves=leaves)

##Leave summary all##
@leave.route('/leave/summary/all')
@login_required     
def summary_all():
    leaves = LeaveAvailable.query.join(Employee).filter(or_(LeaveAvailable.year_start < datetime.now().date(), 
                LeaveAvailable.year_end > datetime.now().date())).all()
                
    if not leaves:
        current_app.logger.warning('summary_self(): No data found in leave_available table for %s', session['empid'])
        flash('No leave summary record found', category='warning')

    return render_template('data.html', data_type='leave_summary', leaves=leaves)

@leave.route('/leave/files/<name>')
@login_required
def files(name):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], name)

##Leave approval for Teams by Managers##
@leave.route('/leave/approval/team')
@login_required
@manager_required
def approval_team():
    application_id = request.args.get('application_id')

    leave = db.session.query(Applications, Team).join(Team, Applications.empid==Team.empid).\
                filter(Applications.id==application_id).one()
    
    manager = Employee.query.join(Team).filter(and_(Team.name==leave[1].name, 
                Employee.role=='Manager')).first_or_404()

    if manager.username != session['username']:
        flash('You are not authorized', category='error')
        return redirect(url_for('leave.status_team'))

    available = check_leave(leave[0].empid, leave[0].start_date, leave[0].duration, leave[0].type, 'update')
    if not available:
        flash('Leave not available, please check leave summary', category='error')
        return redirect(url_for('leave.status_team'))
    
    #update application status and appr_leave_attn table
    application = Applications.query.filter_by(id=application_id).one()
    application.status = 'Approved'

    update_attn(leave[0].empid, leave[0].start_date, leave[0].end_date, leave[0].type)
    flash('Leave approved', category='message')
    
    #Send mail to all concerned
    admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
    if not admin:
        current_app.logger.warning('approval(): Admin email not found for employee id: %s', application.employee.id)
        rv = 'failed'
    
    head = Employee.query.filter(Employee.department==manager.department, 
            Employee.role=='Head').first()
    if not head:
        current_app.logger.warning('approval(): Dept. head email not found for employee id: %s', application.employee.id)
        rv = 'failed'
    
    if 'rv' in locals():
        flash('Failed to send mail', category='warning')
        return redirect(url_for('leave.status_team'))

    host = current_app.config['SMTP_HOST']
    port = current_app.config['SMTP_PORT'] 
    rv = send_mail(host=host, port=port, sender=manager.email, receiver=admin.email, 
            cc1=application.employee.email, cc2=head.email, application=application, 
            type='leave', action='approved')
    
    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')
        return redirect(url_for('leave.status_team'))
    
    return redirect(url_for('leave.status_team'))

##Leave approval for Department by Head##
@leave.route('/leave/approval/department')
@login_required
@head_required
def approval_department():
    application_id = request.args.get('application_id')

    leave = Applications.query.join(Employee).filter(Applications.id==application_id).first()

    #leave = db.session.query(Applications, Employee).join(Team, Applications.empid==Team.empid).\
    #            filter(Applications.id==application_id).first()
   
    department_head = Employee.query.filter(Employee.department==leave.employee.department, 
                        Employee.role=='Head').one()
    
    if department_head.id != int(session['empid']):
        flash('You are not authorized', category='error')
        return redirect(url_for('leave.status', type='team'))

    available = check_leave(leave.empid, leave.start_date, leave.duration, leave.type, 'update')
    if not available:
        flash('Leave not available, please check leave summary', category='error')
        return redirect(request.url)
    
    #update application status and appr_leave_attn table
    application = Applications.query.filter_by(id=application_id).one()
    application.status = 'Approved'

    update_attn(leave.empid, leave.start_date, leave.end_date, leave.type)
    flash('Application approved', category='message')
    
    #Send mail to all concerned
    admin = Employee.query.join(Team).filter(Employee.access=='Admin', Team.name=='HR').first()
    if not admin:
        current_app.logger.warning('approval(): Admin email not found for employee id: %s', application.employee.id)
        rv = 'failed'
    
    if 'rv' in locals():
        flash('Failed to send mail', category='warning')
        return redirect(url_for('leave.status_team'))

    host = current_app.config['SMTP_HOST']
    port = current_app.config['SMTP_PORT'] 
    rv = send_mail(host=host, port=port, sender=department_head.email, receiver=admin.email, 
            cc1=application.employee.email, application=application, type='leave', action='approved')
    
    if rv:
        current_app.logger.warning(rv)
        flash('Failed to send mail', category='warning')
        return redirect(url_for('leave.status_team'))
    
    return redirect(url_for('leave.status_department'))


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
