"""UMS Calendar -> Google Calendar (and others) converter.

Converts the UMS calendar data to either direct google calendar imports,
google-calendar valid CSV files, and google-calendar valid iCal files.
"""
import argparse
import csv
import json
import os
import sys

from abc import ABCMeta, abstractmethod
from datetime import datetime, date
from typing import List, Dict, Iterable, Any, Tuple, Optional

import icalendar
import requests

# these all come in with the google stuff
import pytz
import httplib2
from apiclient import discovery
import oauth2client
from oauth2client import client
from oauth2client import tools



def wait_for_response(question: str) -> bool: #  pragma: nocover
    while True:
        resp = input('{} (yes/no): '.format(question)).lower()
        if resp == 'yes':
            return True
        elif resp == 'no':
            return False


class Event:
    DATEFMT = '%Y-%m-%dT%H:%M:%S+0000'
    def __init__(self, src: Dict[str, str]) -> None:
        self.src = src
        self.end = datetime.strptime(self.src['end'], self.DATEFMT)
        self.start = datetime.strptime(self.src['start'], self.DATEFMT)

    def str_without_venue(self):
        return '({} - {}): {}'.format(self.start.strftime("%a %I:%M %p"), self.end.strftime("%I:%M %p"), self.artist)

    def str_with_venue(self):
        return '{} @ {}'.format(self.str_without_venue(), self.venue)

    @property
    def address(self):
        return self.src['description']

    @property
    def artist(self):
        return self.src['venue_artist'].strip()

    @property
    def artist_url(self):
        return self.src['url']

    @property
    def venue(self):
        return self.src['venue_name']

    @property
    def venue_url(self):
        return self.src['venue_url']


class Calendar(list):
    def __init__(self, name: str, *, items: Iterable[Event]=None) -> None:
        if items is None:
            items = []
        self.name = name
        super().__init__(items)


class DataSource:
    def __init__(self, filepath=None, url=None) -> None:
        self.filepath = os.path.realpath(filepath) if filepath else None
        self.url = url
        self._session = None  # type: requests.Session
        self.cache = None  # type: Dict[str, Any]

    @property
    def session(self) -> requests.Session:  # pragma: nocover
        if not self._session:
            self._session = requests.session()
            self._session.headers.update({
                'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:47.0) Gecko/20100101 Firefox/47.0',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Encoding': 'gzip, deflate',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'http://theums.com/calendar',
                'X-Requested-With': 'XMLHTTPRequest',
                'Connection': 'keep-alive',
            })
        return self._session

    def pull(self) -> List[Dict[str, str]]:
        if not self.url:
            raise ValueError('URL not set, cannot pull')
        datefmt = '%Y-%m-%d'
        now = int((datetime.utcnow() - datetime(1970, 1, 1)).total_seconds())
        start = date(2016, 7, 27)
        end = date(2016, 8, 1)
        resp = self.session.get('{url}?start={start}&end={end}&_={now}'.format(
            url=self.url,
            start=start.strftime(datefmt),
            end=end.strftime(datefmt),
            now=now
        ))
        self.cache = {
            'retrieved': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S'),
            'data': resp.json()
        }

    def writefile(self):
        if not self.cache or not self.filepath:  # pragma: nocover
            raise ValueError("Data and filepath must both be set")
        with open(self.filepath, 'w') as fp:
            json.dump(self.cache, fp, indent=4)

    def readfile(self):
        if not self.filepath:  # pragma: nocover
            raise ValueError("Filepath must be set")
        with open(self.filepath) as fp:
            self.cache = json.load(fp)
        return self.cache

    def get(self):
        try:
            self.readfile()
        except (ValueError, EnvironmentError):
            pass
        if not self.cache:
            self.pull()
            try:
                self.writefile()
            except (ValueError, EnvironmentError):  # pragma: no cover
                pass
        return self.cache

    def calendars(self, *, venue='all') -> Dict[str, Calendar]:
        self.get()
        events = [Event(e) for e in self.cache['data']]
        events.sort(key=lambda e: e.start)
        events_map = {}  # type: Dict[str, Calendar]
        for event in events:
            if venue == 'all' or venue == event.venue:
                events_map.setdefault(
                    event.venue,
                    Calendar(VENUE_FMT.format(event.venue))
                ).append(event)
        return events_map


#Writers, for outputting data.
class Writer(metaclass=ABCMeta):
    @classmethod
    def flatten(cls, calendars: Iterable[Calendar]) -> Calendar:
        flat = Calendar(FLAT_NAME)
        for cal in calendars:
            flat.extend(cal)
        flat.sort(key=lambda e: e.start)
        return flat

    @abstractmethod
    def write(self, calendars: List[Calendar], *, flatten=False):
        """Do whatever the output thing is."""


class FileWriter(Writer):
    """Write Calendars out to a filetype."""
    def __init__(self, output, *, silently_destroy_data=False) -> None:
        self.output = output
        self.silently_destroy_data = silently_destroy_data


    @abstractmethod
    def calendar_filename(self, calendar: Calendar):
        """Return a default filename creator for the given calendar."""

    @abstractmethod
    def write_file(self, filepath: str, calendar: Calendar):
        """Write a calendar out to fp in whatever the output format is."""

    def to_file(self, calendar: Calendar, *, path: str=None):
        if path is None:
            path = self.output

        if not self.silently_destroy_data and os.path.exists(path):
            question = 'Delete existing file at {}?'.format(path)
            if not wait_for_response(question):
                return

        self.write_file(path, calendar)

    def to_directory(self, calendars: Iterable[Calendar]):
        """Write out the calendars to a directory, one per calendar."""
        os.makedirs(self.output, exist_ok=True)
        for calendar in calendars:
            path = os.path.join(self.output, self.calendar_filename(calendar))
            self.to_file(calendar, path=path)

    def write(self, calendars: Iterable[Calendar], *, flatten=False):
        if flatten:
            self.to_file(self.flatten(calendars))
        else:
            self.to_directory(calendars)


class CSVWriter(FileWriter):
    """Write the calendar out to a csv file."""
    def to_csvdict(self, event: Event) -> Dict[str, str]:
        return {
            'Location': event.address,
            'Description': event.venue,
            'Start Date': event.start.strftime('%m/%d/%Y'),
            'Start Time': event.start.strftime('%I:%M %p'),
            'End Date': event.end.strftime('%m/%d/%Y'),
            'End Time': event.end.strftime('%I%M %p'),
            'All Day Event': 'False',
            'Subject': event.artist,
            'Private': 'False'
        }

    def calendar_filename(self, calendar: Calendar) -> str:
            return calendar.name.lower().replace('(', '').replace(')', '')\
                   .replace('@', 'at')+'.csv'

    def write_file(self, path: str, calendar: Calendar):
        caldicts = [self.to_csvdict(e) for e in calendar]
        fieldnames = list(caldicts[0])
        with open(path, 'w') as fp:
            writer = csv.DictWriter(fp, fieldnames)
            writer.writeheader()
            writer.writerows(caldicts)


class IcalWriter(FileWriter):
    """Write the calendar out to an ical file."""
    def calendar_filename(self, calendar: Calendar) -> str:
            return calendar.name.lower().replace('(', '').replace(')', '')\
                   .replace('@', 'at')+'.ical'

    def to_ical_event(self, event: Event) -> icalendar.Event:
        e = icalendar.Event()
        e.add('dtstart', event.start)
        e.add('dtend', event.end)
        e.add('summary', event.artist)
        e.add('location', icalendar.prop.vText('{}: {}'.format(
            event.venue, event.address))
        )
        e.add('description', '[{}]({}) @ [{}]({})'.format(
            event.artist, event.artist_url, event.venue, event.venue_url)
        )
        return e

    def to_ical_calendar(self, calendar: Calendar) -> icalendar.Calendar:
        c = icalendar.Calendar()
        c.add('prodid', "-//Jakes awesome ums converter//Jacob Beck//")
        c.add('version', '1.0')
        c.add('name', calendar.name)
        for event in calendar:
            c.add_component(self.to_ical_event(event))
        return c

    def write_file(self, path: str, calendar: Calendar):
        with open(path, 'wb') as fp:
            fp.write(self.to_ical_calendar(calendar).to_ical())


class GoogleCalendarWriter(Writer):
    """A little wrapper for a google calendar service to skip all the boring
    stuff.

    Warning: If you pass or set silently_destroy_data, you will not be
    prompted before calendars are deleted!
    """
    SCOPE = 'https://www.googleapis.com/auth/calendar'
    def __init__(self, secrets: str, *, silently_destroy_data=False) -> None:
        self.service = self.get_service(secrets, appname='UMS Calendar app')

        self.calsvc = self.service.calendars()
        self.esvc = self.service.events()
        self.calendar_list = self.service.calendarList()

        self._calendar_list_cache = None  #  type: Optional[Dict[str, dict]]
        self.silently_destroy_data = silently_destroy_data

    @classmethod
    def get_service(cls, secrets: str, appname: str):
        home_dir = os.path.expanduser('~')
        credential_dir = os.path.join(home_dir, '.credentials')
        if not os.path.exists(credential_dir):
            os.makedirs(credential_dir)
        credential_path = os.path.join(credential_dir,
                                       'calendar-python-quickstart.json')

        store = oauth2client.file.Storage(credential_path)
        credentials = store.get()
        if not credentials or credentials.invalid:
            flow = client.flow_from_clientsecrets(secrets, cls.SCOPE)
            flow.user_agent = appname
            credentials = tools.run_flow(flow, store, None)
        http = credentials.authorize(httplib2.Http())
        return discovery.build('calendar', 'v3', http=http)

    @staticmethod
    def to_gcal(event: Event) -> Dict[str, Any]:
        return {
            'start': {'dateTime': event.start.strftime('%Y-%m-%dT%H:%M:%S-06:00')},
            'end': {'dateTime': event.end.strftime('%Y-%m-%dT%H:%M:%S-06:00')},
            'location': event.address,
            'description': '[{}]({}) @ [{}]({})'.format(event.artist, event.artist_url, event.venue, event.venue_url),
            'summary': event.artist,
        }

    def _delete_name_if_necessary(self, name: str):
        if self._calendar_list_cache is None:
            resp = self.calendar_list.list().execute()
            self._calendar_list_cache = {c['summary']: c for c in resp['items']}
        try:
            to_delete = self._calendar_list_cache[name]
        except KeyError:
            return

        if not self.silently_destroy_data:
            question = 'About to delete existing google calendar "{}". Ok?'
            if not wait_for_response(question.format(to_delete['summary'])):
                return

        self.calsvc.delete(calendarId=to_delete['id']).execute()
        del self._calendar_list_cache[name]

    def _add_calendar(self, calendar: Calendar):
        """Add a calendar entry."""
        self._delete_name_if_necessary(calendar.name)
        print('Importing {} events into calendar {}'.format(len(calendar), calendar.name))
        created = self.calsvc.insert(body={'summary': calendar.name}).execute()
        for event in calendar:
            self.esvc.insert(calendarId=created['id'], body=self.to_gcal(event)).execute()

    def write(self, calendars: Iterable[Calendar], *, flatten=False):
        self._calendar_list_cache = None
        if flatten:
            calendars = [self.flatten(calendars)]
        for calendar in calendars:
            self._add_calendar(calendar)


class StdoutWriter(Writer):
    def print_calendar(self, calendar: Calendar, flattened: bool):
        print('{}:'.format(calendar.name))
        for event in calendar:
            if flattened:
                to_print = event.str_with_venue()
            else:
                to_print = event.str_without_venue()
            print('\t{}'.format(to_print))
        print('')

    def write(self, calendars: Iterable[Calendar], *, flatten=False):
        if flatten:
            calendars = [self.flatten(calendars)]
        for calendar in calendars:
            self.print_calendar(calendar, flatten)


def parse_args(args=None):
    if args is None:
        args = sys.argv[1:]
    parser = argparse.ArgumentParser()

    ds_group = parser.add_argument_group('data source arguments')
    ds_group.add_argument('--force-refresh', action='store_true',
        dest='force_refresh')
    ds_group.add_argument('--datasource', default='events.json',
        type=os.path.expanduser,
        help="""'The place on disk to look for the datasource. If you use
        --force-refresh, this file will be overwritten."""
    )
    ds_group.add_argument('--url', default='http://theums.com/myfeed/',
        help='The URL to use for refreshing.'
    )

    gcal_group = parser.add_argument_group('Google Calendar API arguments')
    gcal_group.add_argument('--gsecrets',
        default='~/.credentials/gcal_client_secret.json',
        help="""Your google secrets file. If you don't have one, follow the
        instructions here:
        https://developers.google.com/google-apps/calendar/quickstart/python

        In step 1. You'll want the "Other" kind since this is a local program.
        (Probably, anyway).
        """)
    gcal_group.add_argument('--gappname', default='UMS Calendar app',
        help="The name of the app in the Google API setup."
    )

    modifiers = parser.add_argument_group('output modifier arguments')

    modifiers.add_argument('--location', default='all',
        help='The venue to filter by (default: all venues)'
    )
    modifiers.add_argument('--flatten', action='store_true',
        help="""If set, don't convert UMS into one venue per calendar, but
            instead flatten it into one big calendar."""
    )

    output = parser.add_argument_group('output destination arguments')
    output.add_argument('--silently-destroy-data', action='store_true',
        dest='silently_destroy_data',
        help="""If set, conflicting data that exists in any chosen output
        method will be permanently deleted. Otherwise you'll be prompted."""
    )
    output.add_argument('--quiet', action='store_false', dest='print',
        help="If passed, don't print out the events found."
    )
    output.add_argument('--gcal', action='store_true',
        help="""If set, update google calendar, adding or replacing one
            calendar per UMS venue. (Requires API setup)"""
    )
    output.add_argument('--googlecsv', default=None,
        type=lambda x: os.path.expanduser(x) if x else None,
        help="""If provided, export each venue's calendar as a CSV file under
            the given directory that you can import into google calendar. If
            flatten is set, it will be a single CSV file."""
    )
    output.add_argument('--ical', default=None,
        type=lambda x: os.path.expanduser(x) if x else None,
        help="""If provided, export each venue's calendar as an iCal file
            under the given directory that you can import into google
            calendar. If flatten is set, it will be a single iCal file."""
    )

    parsed = parser.parse_args(args)
    return parsed


VENUE_FMT = 'UMS - {}'
FLAT_NAME = 'UMS'


def main():
    args = parse_args()

    ds = DataSource(args.datasource, args.url)
    if args.force_refresh:
        ds.pull()
        ds.writefile()

    events_map = ds.calendars(venue=args.location)
    if not events_map:
        print('No events')
        return

    writers = []
    if args.print:
        writers.append(StdoutWriter())

    if args.gcal:
        writers.append(GoogleCalendarWriter(
            secrets=args.gsecrets,
            silently_destroy_data=args.silently_destroy_data
        ))

    if args.googlecsv:
        writers.append(CSVWriter(
            output=args.googlecsv,
            silently_destroy_data=args.silently_destroy_data,
        ))

    if args.ical:
        writers.append(IcalWriter(
            output=args.ical,
            silently_destroy_data=args.silently_destroy_data,
        ))

    for writer in writers:
        writer.write(events_map.values(), flatten=args.flatten)



if __name__ == '__main__':
    main()

