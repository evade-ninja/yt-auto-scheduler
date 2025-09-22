# yt-auto-scheduler

Auto schedule youtube live streams for multiple congregations as specified in the config.json.

Usage:

Copy sample.config.json to config.json and add your information. You can get stream key IDs by using the list_streams.py script. Create a secrets.json file for each channel.

You'll need to run schedule.py manually once to obtain the refresh tokens. After that - it should be able to run automagically on its own.

Depends on: google-auth, google-auth-oauthlib, google-api-python-client, pytz
