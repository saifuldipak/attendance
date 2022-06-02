
import csv
from werkzeug.security import generate_password_hash

try:
    with open('employee.csv', 'r') as f:
        content = csv.reader(f)
        for value in content:
            print(generate_password_hash(value[1]))

except FileNotFoundError as e:
    print(e)

