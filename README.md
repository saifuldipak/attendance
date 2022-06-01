# Attendance
Employee attendance and leave record keeping app

## Description
This is an app to keep record of employee attendance data from attendance machines. Employees can also apply for leave and attendance approval. Team managers can approve those applications. It has option to send mail to concern persons for application submission and approval. It also calculates annual leave of each employee and update that data when application is approved. It can calculate late and absent days of each employee for each month. 

## Prerequisite software
1. Ubuntu-20.04
2. Python3

## Installation
1. First create a python virtual environment 
```bash
mkdir ~/attendance
cd ~/attendance
python3 -m venv attendance-venv
source attendance-venv/bin/activate
```
2. Copy attendance-x.x.x-py3-none-any.whl to directory created in step one and install
```bash
pip install attendnace-x.x.x-py3-none-any.whl
```
3. Edit the config file 'config.py' and 'logging.yaml' 
```bash
#generating secret key string
python -c 'import secrets; print(secrets.token_hex())'

#put the string in the 'config.py' file 'SECRET_KEY'
nano attendance-venv/config/config.py

#In "file:" section
#replace 'username' in 'filename' value with your linux account name  
#In "mail:" section
#replace appropriate values for mailhost, fromaddr, toaddrs
nano attendance-venv/config/logging.yaml 
```
4. Configuring systemd
```bash
#replace 'username' with your Linux username name
nano attendance-venv/config/attendance.service

#copy the file to systemd configuration folder
cp attendance-venv/config/attendance.service /etc/systemd/system/

#start attendance service
sudo systemctl start attendance
sudo systemctl enable attendance

#check the status, it should be showing status 'active(running)'
sudo systemctl status attendance
```
4. Installing and configuring Nginx server
```bash
sudo apt update
sudo apt install nginx

#check status, it should show status 'active(running)'
sudo systemctl status nginx

#replace your_domain and your_username with appropriate values
sudo attendance-venv/config/attendance

#copy to nginx config directory
cp attendance-venv/config/attendance /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/attendance /etc/nginx/sites-enabled

#check file syntax
sudo nginx -t

#restart Nginx
sudo systemctl restart nginx
```
5. Configure and check firewall
```bash
sudo ufw allow 'OpenSSH'
sudo ufw allow 'Nginx HTTP'
sudo ufw enable
sudo ufw status
```
6. Create database and admin user
```bash
flask initdb
```

## Usage
Login to Attendance app

http://yourdomain/login

user: admin
pass: admin123
