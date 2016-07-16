UMSCal: A tool for collecting and using data for the 2016 UMS
=============================================================

This is just a little helper module/cli tool for generating calendar data from
the UMS's calendar online. The regular calendar is a bit slow and doesn't seem
to cache anything.

This tool pulls data once (or more often if you choose to refresh) and
generates calendar output. Supported formats are:

    - csv (google-calendar format)
    - ical (google-calendar compatible)
    - google calendar directly (requires an API key set up)
    - stdout


Usage
-----
Use the `--help` flag for parameter information. There are many.

By default ums.py will only attempt to pull down data if none exists in
`events.json`, and print out a calendar with the contents of `events.json`.

You can pass `--quiet` to skip printing.

If you don't want to get prompted about overwriting, use the
`--silently-destroy-data` flag. Note that it will result in silently destroying
your data.

Setting up an API key
---------------------
The below is modified from the google python calendar quickstart
[guide](https://developers.google.com/google-apps/calendar/quickstart/python)
first step.

Use this
[wizard](https://console.developers.google.com/flows/enableapi?apiid=calendar)
to create or select a project in the Google Developers Console and
automatically turn on the API. Click Continue, then Go to credentials.

At the top of the page, select the OAuth consent screen tab. Select an Email
address, enter a Product name if not already set, and click the Save button.

Select the Credentials tab, click the Create credentials button and select
OAuth client ID.

Select the application type Other, enter the name "UMS Calendar app". (You can
really pick anything, it doesn't matter).

Click "OK" to dismiss the resulting dialog.

Click the "Download JSON" button to the right of the client ID and save that to
`~/credentials/gcal_client_secret.json` (On Windows, I think you'd want to
replace "~" with your home directory) If you save it anywhere else, you'll
want to tell ums.py where using the `--gsecrets` flag.

Requires
--------
Python 3.5
Previous versions of Python (3.3+?) should work.

`pip install -r requirements.txt`

I've tested this on Linux, it should probably work on OSX and Windows.


License
-------
MIT
