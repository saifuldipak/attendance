import re
from flask import session

#Convert all team names of Fiber & Support to generic name
def convert_team_name():
    match = re.search('^Fiber', session['team'])
    if match:
        team_name = 'Fiber'

    match = re.search('^Support', session['team'])
    if match:
        team_name = 'Support'

    if team_name != 'Fiber' and team_name != 'Support':
        team_name = session['team']
    
    return team_name