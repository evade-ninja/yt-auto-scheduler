# yt-auto-scheduler

Auto schedule youtube live streams for multiple congregations as specified in the config.json.

Usage:

Copy sample.config.json to config.json and add your information. You can get stream key IDs by using the list_streams.py script. Create a secrets.json file for each channel.

You'll need to run schedule.py manually once to obtain the refresh tokens. After that - it should be able to run automagically on its own.

Depends on: google-auth, google-auth-oauthlib, google-api-python-client, pytz

`schedule.py`, `hide_videos.py`, and `remove_videos.py` email a status report
after each run using the top-level `smtp` object in the configuration passed
with `--config`. Copy the SMTP settings from `sample.config.json` and set
`server`, `username`, `password`, and `destination` for your mail server.
The sender defaults to `username`; set `fromAddress` if a different sender is needed.
The default connection uses STARTTLS on port 587. For implicit TLS, set
`useSsl` to `true` and `port` to 465.
`useSsl: false` still encrypts the connection using STARTTLS. Setting
`useSsl: true` while leaving `port: 587` causes a TLS protocol mismatch;
the reporter rejects this combination with instructions to correct it.

Reports distinguish successful actions, skipped videos, retry warnings, and
failures. A retry that eventually succeeds is still included as an issue.
Scheduling reports include the title, date/time in America/Boise with its UTC
offset, video link, and which of the three scheduling steps completed.
If a scheduling step fails five times, dependent steps stop and the partial
report is sent. Unexpected errors (including authentication and video-list
file errors) also trigger a report once the configuration has been loaded.
An unreadable or invalid configuration cannot supply SMTP settings, so those
errors are reported in the console only. Email delivery failures are printed
to stderr and cause a nonzero exit without replacing an existing script error.
