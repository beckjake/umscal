import ums

import json
import os
import shutil
import tempfile

from unittest import mock

import pytest

TEST_DATA = b"""{
    "retrieved": "2016-07-16T18:32:13",
    "data": [
        {
            "start": "2016-07-28T21:00:00+0000",
            "end": "2016-07-28T21:40:00+0000",
            "venue_artist": "artist1",
            "url": "http://example.com/artists/artist1",
            "venue_name": "venue1",
            "venue_url": "http://example.com/venues/venue1",
            "description": "123 Fake Lane, Denver, CO"
        },
        {
            "start": "2016-07-28T22:00:00+0000",
            "end": "2016-07-28T22:40:00+0000",
            "venue_artist": "artist2",
            "url": "http://example.com/artists/artist2",
            "venue_name": "venue1",
            "venue_url": "http://example.com/venues/venue1",
            "description": "123 Fake Lane, Denver, CO"
        },
        {
            "start": "2016-07-28T23:00:00+0000",
            "end": "2016-07-28T23:40:00+0000",
            "venue_artist": "artist3",
            "url": "http://example.com/artists/artist3",
            "venue_name": "venue1",
            "venue_url": "http://example.com/venues/venue1",
            "description": "123 Fake Lane, Denver, CO"
        },
        {
            "start": "2016-07-28T21:00:00+0000",
            "end": "2016-07-28T21:40:00+0000",
            "venue_artist": "artist4",
            "url": "http://example.com/artists/artist4",
            "venue_name": "venue2",
            "venue_url": "http://example.com/venues/venue2",
            "description": "321 Fake Lane, Denver, CO"
        },
        {
            "start": "2016-07-28T22:00:00+0000",
            "end": "2016-07-28T22:40:00+0000",
            "venue_artist": "artist5",
            "url": "http://example.com/artists/artist5",
            "venue_name": "venue2",
            "venue_url": "http://example.com/venues/venue2",
            "description": "321 Fake Lane, Denver, CO"
        },
        {
            "start": "2016-07-28T23:00:00+0000",
            "end": "2016-07-28T23:40:00+0000",
            "venue_artist": "artist6",
            "url": "http://example.com/artists/artist6",
            "venue_name": "venue2",
            "venue_url": "http://example.com/venues/venue2",
            "description": "321 Fake Lane, Denver, CO"
        }
    ]
}
"""

@pytest.yield_fixture
def jsondata():
    with tempfile.NamedTemporaryFile(suffix='.json') as fp:
        fp.write(TEST_DATA)
        fp.flush()
        yield fp.name


@pytest.yield_fixture
def calendars(jsondata):
    ds = ums.DataSource(filepath=jsondata, url=None)
    ds.readfile()
    calendars = ds.calendars()
    yield calendars


@pytest.yield_fixture
def tempdir():
    try:
        dirname = tempfile.mkdtemp()
        yield dirname
    finally:
        shutil.rmtree(dirname)


def test_ds_get_nodata():
    with tempfile.NamedTemporaryFile(suffix='.json') as fp:
        with mock.patch('ums.requests.session') as mock_session_get:
            session = mock_session_get.return_value
            data = json.loads(TEST_DATA.decode('ascii'))['data']
            session.get.return_value.json.return_value = data

            ds = ums.DataSource(fp.name, 'http://example.com/')
            ds.get()

            assert session.get.call_count == 1
            assert ds.cache['data'] == data
        assert len(fp.read()) > 0

def test_ds_get_nowrite():
    with mock.patch('ums.requests.session') as mock_session_get:
        session = mock_session_get.return_value
        data = json.loads(TEST_DATA.decode('ascii'))['data']
        session.get.return_value.json.return_value = data

        ds = ums.DataSource(url='http://example.com/')
        ds.get()

        assert session.get.call_count == 1
        assert ds.cache['data'] == data

def test_event_read(calendars):
    assert len(calendars) == 2
    assert len(calendars['venue1']) == 3
    assert len(calendars['venue2']) == 3
    assert(all(isinstance(cal, ums.Calendar) for cal in calendars.values()))
    assert all(isinstance(e, ums.Event) for cal in calendars.values() for e in cal)


def test_event_write(jsondata):
    name = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as fp:
            name = fp.name
            ds = ums.DataSource(filepath=fp.name)
            ds.cache = json.loads(TEST_DATA.decode('ascii'))
            ds.writefile()
        with open(name) as fp:
            data = json.load(fp)
        with open(jsondata) as fp:
            assert json.load(fp) == data
    finally:
        if name:
            os.remove(name)


def test_csv_dir(calendars, tempdir):
    writer = ums.CSVWriter(output=tempdir)
    writer.write(calendars.values(), flatten=False)
    files = os.listdir(tempdir)
    assert len(files) == 2
    assert 'ums - venue1.csv' in files
    assert 'ums - venue2.csv' in files
    for file in files:
        with open(os.path.join(tempdir, file)) as fp:
            lines = fp.readlines()
            assert len(lines) == 4 # header + 3 entries


def test_csv_file(calendars, tempdir):
    filepath = os.path.join(tempdir, 'test.csv')
    writer = ums.CSVWriter(output=filepath)
    writer.write(calendars.values(), flatten=True)
    files = os.listdir(tempdir)
    assert len(files) == 1
    assert files[0] == 'test.csv'
    with open(filepath) as fp:
        lines = fp.readlines()
    assert len(lines) == 7 # header + 6 entries


def test_csv_file_silent_ovewrite(calendars, tempdir):
    filepath = os.path.join(tempdir, 'test.csv')
    # touch it.
    with open(filepath, 'w') as fp:
        pass
    writer = ums.CSVWriter(output=filepath, silently_destroy_data=True)
    writer.write(calendars.values(), flatten=True)
    files = os.listdir(tempdir)
    assert len(files) == 1
    assert files[0] == 'test.csv'
    with open(filepath) as fp:
        lines = fp.readlines()
    assert len(lines) == 7 # header + 6 entries


def test_csv_file_overwrite(calendars, tempdir):
    filepath = os.path.join(tempdir, 'test.csv')
    # touch it.
    with open(filepath, 'w') as fp:
        pass
    writer = ums.CSVWriter(output=filepath, silently_destroy_data=False)
    with mock.patch('ums.wait_for_response') as mock_wait:
        mock_wait.return_value = False
        writer.write(calendars.values(), flatten=True)
    files = os.listdir(tempdir)
    assert len(files) == 1
    assert files[0] == 'test.csv'
    with open(filepath) as fp:
        assert len(fp.read()) == 0



# Just make sure we don't crash, no correctness checks
def test_stdout(calendars):
    writer = ums.StdoutWriter()
    writer.write(calendars.values(), flatten=True)
    writer.write(calendars.values(), flatten=False)


def test_gcal_events(calendars):
    event = calendars['venue1'][0]
    event = ums.GoogleCalendarWriter.to_gcal(event)
    assert event == {
        'start': {'dateTime': "2016-07-28T21:00:00-06:00"},
        'end': {'dateTime': "2016-07-28T21:40:00-06:00"},
        'location': "123 Fake Lane, Denver, CO",
        'description': '[artist1](http://example.com/artists/artist1) @ [venue1](http://example.com/venues/venue1)',
        'summary': 'artist1',
    }
