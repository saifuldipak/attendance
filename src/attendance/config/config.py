#generate a new SECRET_KEY value with the following command when app installed in a new server
# $ python -c 'import secrets; print(secrets.token_hex())'
SECRET_KEY='change_me'

#SMTP server details
SMTP_HOST='127.0.0.1'
SMTP_PORT='1025'

#Yearly leave
CASUAL=10
MEDICAL=14
EARNED=14

#Office timing
IN_TIME='09:00:00'
OUT_TIME='18:00:00'
GRACE_PERIOD=15