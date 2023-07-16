# Attendance
Employee attendance and leave record keeping app

## Description
This is an app to keep record of employee attendance data from attendance machines. Employees can also apply for leave and attendance approval. Team managers can approve those applications. It has option to send mail to concern persons for application submission and approval. It also calculates annual leave of each employee and update that data when application is approved. It can calculate late and absent days of each employee for each month.

### Features:
- Data (csv/excel) from the attendance machine can be uploaded directly to the app  
- Leave and attendance application submission and approval with auto email notification
- Attendance (in time, out time, late, early & absent etc) and leave status check
- Multiple access levels for different types of users. Admin, department head,  managers and team members etc.
- Option to set allowable Casual, Medical, Earned leave,in time, out time, in grace time etc as per need.
- Option to upload duty schedule for shifting duties. Office in time, out time and holidays are calculated based on that duty schedule
- Attendance summary preparation for all employees (Calculation of late, early, absent and leave around holidays etc) at the end of the month
- Leave deduction based on attendance summary.
- Option to reverse leave deduction and delete attendance summary by admin user if required due to some error in attendance data.
- Option to delete uploaded attendance data of specific date/s.


## Prerequisite software
1. Ubuntu-20.04
2. Python3

## Installation
1. First create and activate a python virtual environment 
```bash
$ mkdir ~/attendance
$ cd ~/attendance
$ python3 -m venv venv
$ source venv/bin/activate
```

2. Copy attendance-x.x.x-py3-none-any.whl to directory created in step one and install
```bash
(venv)$ python3 -m pip install attendnace-x.x.x-py3-none-any.whl
```

3. Run the app to create instance directory
```bash
(venv)$ export FLASK_APP=attendance
(venv)$ flask run
(venv)$ CTRL+c #exit app
```

4. Edit the config file 'config.py' and 'logging.yaml' 
```bash
#copy config files to instance folder, replace 'x' with your installed python 
#version number. run command "$ python3 --version" to get the version
(venv)$ cd ~/attendance/venv/lib/python3.x/site-packages/attendance/config
(venv)$ cp config.py logging.yaml ~/attendance/venv/var/attendance-instance/

#generating secret key string
(venv)$ cd ~/attendance/venv/var/attendance-instance
(venv)$ python -c 'import secrets; print(secrets.token_hex())'

#put the string in the 'config.py' file 'SECRET_KEY'
(venv)$ nano config.py

#In "file:" section
#replace 'username' in 'filename' value with your linux account name  
#In "mail:" section
#replace appropriate values for mailhost, fromaddr, toaddrs
(venv)$ nano logging.yaml 
```

5. Create database and admin user
```bash
(venv)$ flask initdb
```

6. Configuring systemd
```bash
(venv)$ deactivate
#copy systemd service file
$ cd ~/attendance/venv/lib/python3.x/site-packages/attendance/config/
$ sudo cp attendance.service /etc/systemd/system/

#replace 'username' with your Linux username name
$ sudo nano /etc/systemd/system/attendance.service

#start attendance service
$ sudo systemctl enable --now attendance

#check the status, it should be showing status 'active(running)'
$ systemctl status attendance
```

7. Installing and configuring Nginx server
```bash
$ sudo apt update
$ sudo apt install nginx

#check status, it should show status 'active(running)'
$ systemctl status nginx

#copy attendnace site config file to nginx config directory
$ sudo cp ~/attendance/venv/lib/python3.8/site-packages/attendance/config/attendance /etc/nginx/sites-available/

#edit site config file with appropriate domain name
$ sudo nano /etc/nginx/sites-vailable/attendance

#create symlink to activate attendance site
$ sudo ln -s /etc/nginx/sites-available/attendance /etc/nginx/sites-enabled

#check file syntax
$ sudo nginx -t

#restart Nginx
$ sudo systemctl restart nginx
```

8. Configure and check firewall
```bash
$ sudo ufw allow 'OpenSSH'
$ sudo ufw allow 'Nginx HTTP'
$ sudo ufw enable
$ sudo ufw status
```

## Usage
Login to Attendance app

http://yourdomain/login

user: admin
pass: admin123
