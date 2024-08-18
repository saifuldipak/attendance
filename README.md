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
Python3

## Installation 
There are two ways to install this sofware, 
1. From binary version (stable version)
2. From development version (current development version)

Note: Section which are exclusive for each version are specified, other sections are same for both types.

#### 1. Create the python virtual environment and install the app, 

For binary version   
first download the app from Github
Go to https://github.com/saifuldipak/attendance
Click on the release link in the "Realeases" secton on the right side to download
```bash
$ mkdir ~/attendance
$ cp ~Downloads/attendnace-x.x.x-py3-none-any.whl ~/attendance/
```

For development version  
```bash
$ cd ~
$ git clone https://github.com/saifuldipak/attendance.git
```

```bash
$ cd ~/attendance
$ python3 -m venv .venv --prompt=attendance
$ source .venv/bin/activate
```
For Binary version  
```bash
(attendance)$ pip install attendance-x.x.x-py3-none-any.whl
```
For Development version  
```bash
(attendance)$ pip install -e .
```

#### 2. Configure the app and create database, replace x with your python version, run command "$ python3 --version" to get the version

For binary version
```bash
(attendance)$ ln -s .venv/lib/pythonx.xx/site_packages/attendance src
(attendance)$ ln -s .venv/var/attendance-instance/ instance
```
For development version
```bash
(attendance)$ ln -s src/attendance src
(attendance)$ ln -s src/instance instance
```

```bash
(attendance)$ export FLASK_APP=attendance
(attendance)$ flask run
(attendance)$ ctrl+c
(attendance)$ flask initdb
(attendance)$ deactivate
```

```bash
$ cp src/config/config.py instance/
$ cp src/config/logging.yaml instance/
```

Generating secret key string
```bash
$ python -c 'import secrets; print(secrets.token_hex())'
```
Open config.py with your favorite text editor and replace the 'change_me' with the string generated above in the 'config.py' file 'SECRET_KEY'

Open logging.yaml with your favorite text editor and change following fields
In "file:" section replace 'username' in 'filename' value with your linux account name  
In "mail:" section replace appropriate values for mailhost, fromaddr, toaddrs

#### 3. Add attendance app to systemd
```bash
$ sudo cp src/config/attendance.service /etc/systemd/system/
```
Edit /etc/systemd/system/attendance.service and replace username with your Linux username, 
start attendance app from systemd, check status (message should show "Active: active (running)")
```bash
$ sudo systemctl enable --now attendance
$ systemctl status attendance
```

#### 4. Installing Nginx 
```bash
$ sudo apt update
$ sudo apt install nginx
$ sudo cp src/config/nginx-config /etc/nginx/sites-available/attendance
$ sudo ln -s /etc/nginx/sites-available/attendance /etc/nginx/sites-enabled/attendance
```
edit nginx config file and put your domain name in "server_name" section
check Nginx configuration, restart and check running status
```bash
$ sudo nginx -t
$ sudo systemctl restart nginx
$ systemctl status nginx
```

#### 5. Configure and check firewall
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

## Database backup
Create a cron task to take backup of attendance app sqlite3 database file to a remote linux machine using rsync, a bash script is run  
by cron to do the backup

Important:
1. backup bash script uses smtp client "msmtp", you need to install it and add ".msmtprc" config file in your user directory, 
you can find help online on how to create the config file, 
2. rsync uses ssh to login to the remote server, so you need to add your rsa public key to the remote server

copy the script and 
```bash
$ mkdir -p ~/scripts
$ cp ~/attendance/src/config/database-backup.sh ~/scripts/
$ chmod 744 ~/scripts/database-backup.sh
```
edit "~scripts/database-backup.sh" to set relevant values for your system

create a cron job
```bash
$ crontab -e
```
add following line to crontab file, replace username with your Linux username  
```
0 */6 * * * username /home/username/scripts/database-backup.sh
```
