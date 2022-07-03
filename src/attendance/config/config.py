#generate a new SECRET_KEY value with the following command when app installed in a new server
# $ python -c 'import secrets; print(secrets.token_hex())'
SECRET_KEY='change_me'

#SMTP server details
SMTP_HOST='120.50.31.12'
SMTP_PORT='25'

#Yearly leave
CASUAL = 10
MEDICAL = 14
EARNED = 14