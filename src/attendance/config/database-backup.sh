#!/bin/bash
#This is a bash script which will be run from cron to backup sqlite3 database file backup using rsync

# Important: rsync uses ssh to login to the remote server, so you need to add your rsa public key to the remote server

# Set the variables
DATABASE_FOLDER='/home/username/attendance/src/instance/'
REMOTE_USERNAME='root'
REMOTE_SERVER_NAME='backup-server-name'
REMOTE_DIRECTORY='/backup/directory'
SENDER="attendance@telnet.com.bd"
RECEIVER="syslog@telnet.com.bd"

# Run the rsync command and capture the output
OUTPUT=$(rsync -av --exclude "*.log" $DATABASE_FOLDER $REMOTE_USERNAME@$REMOTE_SERVER_NAME:$REMOTE_DIRECTORY --delete --delete-excluded 2>&1)

# Check the exit status of the rsync command
if [ $? -eq 0 ]; then
    SUBJECT="Attendance app backup successful"
else
    SUBJECT="Attendance app backup failed"
fi

# Send email with output in the body
echo -e "Subject: $SUBJECT\n\n$OUTPUT" | msmtp -f $SENDER $RECEIVER