# SPDX-License-Identifier: MIT
"""Real GJS + GStreamer + D-Bus tests with local MP3/ICY streams, no internet."""
import http.server
import struct
import zlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

ROOT = Path(__file__).resolve().parents[2]
BUS = 'org.mpris.MediaPlayer2.GnomeRadio'
APP = '/org/gnome/Radio'
MPRIS = '/org/mpris/MediaPlayer2'
IFACE = 'org.gnome.Radio1'
PLAYER = 'org.mpris.MediaPlayer2.Player'


def pump():
    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)


def fixture_favicon():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(b'\x00\x40\x90\xe0\xff')) + chunk(b'IEND', b''))


class Streams(http.server.BaseHTTPRequestHandler):
    title = 'First song'
    audio = b''
    slow_started = threading.Event()
    favicon_requests = 0
    favicon_mode = 'png'
    favicon = fixture_favicon()

    def log_message(self, *_args):
        pass

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/favicon.ico':
            Streams.favicon_requests += 1
            mode = Streams.favicon_mode
            if mode == 'slow': time.sleep(1)
            body = Streams.favicon if mode in ('png', 'slow') else b'<html>no icon</html>'
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(256 * 1024 + 1 if mode == 'huge' else len(body)))
            self.end_headers()
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass
            return
        playlists = {
            '/station.m3u': ('audio/x-mpegurl', '#EXTM3U\nfile:///etc/passwd\n/plain.mp3\n'),
            '/station.xspf': ('application/xspf+xml', '<playlist xmlns="http://xspf.org/ns/0/"><trackList><track><location>/icy</location></track></trackList></playlist>'),
            '/playlist': ('audio/x-mpegurl', '#EXTM3U\n/plain.mp3\n'),
            '/loop.m3u': ('audio/x-mpegurl', '/loop.m3u\n'),
            '/empty.m3u': ('audio/x-mpegurl', '#EXTM3U\n'),
            '/huge.m3u': ('audio/x-mpegurl', 'x' * (256 * 1024 + 1)),
            '/bad.xspf': ('application/xspf+xml', '<playlist><bad></playlist>'),
            '/slow.m3u': ('audio/x-mpegurl', '/icy\n'),
        }
        if path == '/redirect.m3u':
            self.send_response(302)
            self.send_header('Location', '/station.m3u')
            self.end_headers()
            return
        if path in playlists:
            if path == '/slow.m3u':
                Streams.slow_started.set()
                time.sleep(1)
            content_type, text = playlists[path]
            body = text.encode()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if self.path == '/missing':
            self.send_error(404)
            return
        icy = self.path == '/icy'
        self.send_response(200)
        self.send_header('Content-Type', 'audio/mpeg')
        if icy:
            self.send_header('icy-metaint', '4096')
            self.send_header('icy-name', 'Local test radio')
        self.end_headers()
        if self.path == '/tagged.mp3':
            self.wfile.write(Streams.tags)
        position = 0
        try:
            while True:
                audio = (self.audio * 2)[position:position + 4096]
                if len(audio) < 4096:
                    audio += self.audio[:4096 - len(audio)]
                position = (position + 4096) % len(self.audio)
                self.wfile.write(audio)
                if icy:
                    text = f"StreamTitle='{Streams.title}';".encode()
                    blocks = (len(text) + 15) // 16
                    self.wfile.write(bytes([blocks]) + text.ljust(blocks * 16, b'\0'))
                self.wfile.flush()
                time.sleep(0.25)
        except (BrokenPipeError, ConnectionResetError):
            pass


class ServiceE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix='gnome-radio-fixture-')
        audio = Path(cls.fixture.name) / 'tone.mp3'
        subprocess.run(['gst-launch-1.0', '-q', 'audiotestsrc', 'num-buffers=200',
                        '!', 'audioconvert', '!', 'lamemp3enc', 'target=bitrate',
                        'bitrate=64', 'cbr=true', '!', 'filesink', f'location={audio}'], check=True)
        Streams.audio = audio.read_bytes()
        def size(value):
            return bytes((value >> shift) & 127 for shift in (21, 14, 7, 0))
        def frame(name, text):
            data = b'\x03' + text.encode('utf-8')
            return name.encode() + size(len(data)) + b'\0\0' + data
        tags = frame('TIT2', 'Tagged song') + frame('TPE1', 'Tagged artist')
        Streams.tags = b'ID3\x04\x00\x00' + size(len(tags)) + tags
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Streams)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.fixture.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='gnome-radio-e2e-')
        self.env = dict(os.environ, XDG_CONFIG_HOME=self.directory.name, XDG_CACHE_HOME=self.directory.name, GIO_USE_VFS='local')
        Streams.title = 'First song'
        Streams.slow_started.clear()
        Streams.favicon_requests = 0
        Streams.favicon_mode = 'png'
        self.tracks = []
        self.subscription = self.bus.signal_subscribe(
            BUS, IFACE, 'TrackChanged', APP, None, Gio.DBusSignalFlags.NONE,
            lambda _connection, _sender, _path, _interface, _signal, args:
            self.tracks.append(args.unpack()))
        self.log = tempfile.TemporaryFile(mode='w+')
        self.start()

    def start(self, extra=()):
        self.process = subprocess.Popen(['gjs', '-m', str(ROOT / 'src/service/main.js'), '--test-audio', *extra],
                                        env=self.env, stdout=self.log, stderr=self.log)
        self.wait(lambda: self.state(), 'service startup')

    def tearDown(self):
        self.bus.signal_unsubscribe(self.subscription)
        self.shutdown()
        self.log.seek(0)
        log = self.log.read()
        self.log.close()
        self.directory.cleanup()
        self.assertNotIn('JS ERROR', log)
        self.assertNotIn('CRITICAL', log)

    def shutdown(self):
        if self.process.poll() is None:
            self.call('Quit')
            self.process.wait(timeout=5)
        self.assertEqual(self.process.returncode, 0)
        self.wait(lambda: not self.has_owner(), 'bus name released')

    def has_owner(self):
        return self.bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                  'org.freedesktop.DBus', 'NameHasOwner',
                                  GLib.Variant('(s)', (BUS,)), None,
                                  Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]

    def wait(self, predicate, label, timeout=12):
        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            pump()
            try:
                result = predicate()
                if result:
                    return result
            except GLib.Error as error:
                last_error = error
            if hasattr(self, 'process') and self.process.poll() is not None and label == 'service startup':
                break
            time.sleep(0.05)
        self.log.seek(0)
        self.fail(f'Timed out: {label}; {last_error}\n{self.log.read()}')

    def call(self, name, signature=None, args=(), interface=IFACE, path=APP):
        return self.bus.call_sync(BUS, path, interface, name,
                                  GLib.Variant(signature, args) if signature else None,
                                  None, Gio.DBusCallFlags.NONE, 3000, None).unpack()

    def prop(self, interface, name, path=MPRIS):
        return self.call('Get', '(ss)', (interface, name),
                         'org.freedesktop.DBus.Properties', path)[0]

    def state(self):
        return json.loads(self.prop(IFACE, 'State', APP))

    def add(self, suffix='/plain', name='Test radio'):
        return self.call('AddStation', '(ss)', (name, self.url + suffix))[0]

    def media(self, name):
        return self.call(name, interface=PLAYER, path=MPRIS)

    def test_saved_stations_survive_restart_and_validate_input(self):
        identifier = self.add()
        self.call('SetNotifications', '(b)', (True,))
        for name, url in [('Unsafe', 'file:///etc/passwd'), ('', self.url + '/other'),
                          ('Duplicate', self.url + '/plain')]:
            with self.assertRaises(GLib.Error):
                self.call('AddStation', '(ss)', (name, url))
        self.shutdown()
        self.start()
        state = self.state()
        self.assertEqual(state['selected'], identifier)
        self.assertTrue(state['notifications'])
        self.assertEqual(len(state['stations']), 1)
        self.call('RemoveStation', '(s)', (identifier,))
        self.assertEqual(self.state()['stations'], [])
        self.assertFalse(self.prop(PLAYER, 'CanPlay'))

    def test_actual_playback_and_media_controls_share_state(self):
        self.add()
        self.call('PlayPause')
        self.wait(lambda: self.state()['status'] == 'Playing', 'audio playing')
        self.assertEqual(self.prop(PLAYER, 'PlaybackStatus'), 'Playing')
        self.media('PlayPause')
        self.assertEqual(self.state()['status'], 'Paused')
        self.assertEqual(self.prop(PLAYER, 'PlaybackStatus'), 'Paused')
        self.media('Play')
        self.wait(lambda: self.state()['status'] == 'Playing', 'audio resumed')
        self.call('Set', '(ssv)', (PLAYER, 'Volume', GLib.Variant('d', 0.4)),
                  'org.freedesktop.DBus.Properties', MPRIS)
        self.assertAlmostEqual(self.prop(PLAYER, 'Volume'), 0.4)
        self.media('Stop')
        self.assertEqual(self.state()['status'], 'Stopped')
        self.assertEqual(self.state()['title'], '')

    def test_station_edits_validate_and_persist_without_changing_identity(self):
        identifier = self.add()
        other = self.add('/other.mp3', 'Other')
        self.call('UpdateStation', '(sss)', (identifier, 'Edited', self.url + '/station.m3u'))
        expected = self.state()['stations']
        for args in [(identifier, '', self.url + '/new'), (identifier, 'Bad', 'file:///tmp/audio'),
                     (identifier, 'Duplicate', self.url + '/other.mp3'), ('missing', 'Name', self.url + '/new')]:
            with self.assertRaises(GLib.Error):
                self.call('UpdateStation', '(sss)', args)
            self.assertEqual(self.state()['stations'], expected)
        self.shutdown()
        self.start()
        state = self.state()
        self.assertEqual(state['selected'], identifier)
        self.assertEqual(state['stations'][0], {'id': identifier, 'name': 'Edited', 'url': self.url + '/station.m3u'})
        self.assertEqual(state['stations'][1]['id'], other)

    def test_editing_playing_station_renames_without_interruption_and_reconnects_url(self):
        identifier = self.add('/icy')
        self.call('PlayPause')
        self.wait(lambda: self.state()['status'] == 'Playing' and self.state()['title'], 'ICY playback')
        title = self.state()['title']
        self.call('UpdateStation', '(sss)', (identifier, 'Renamed', self.url + '/icy'))
        self.assertEqual(self.state()['status'], 'Playing')
        self.assertEqual(self.state()['title'], title)
        self.assertEqual(self.prop(PLAYER, 'Metadata')['xesam:album'], 'Renamed')
        self.call('UpdateStation', '(sss)', (identifier, 'Renamed', self.url + '/plain.mp3'))
        self.wait(lambda: self.state()['status'] == 'Playing' and self.state()['resolvedUrl'].endswith('/plain.mp3'), 'edited URL playback')
        self.assertEqual(self.state()['title'], '')
        self.media('Pause')
        self.call('UpdateStation', '(sss)', (identifier, 'Paused edit', self.url + '/other.mp3'))
        self.assertEqual(self.state()['status'], 'Paused')
        self.media('Play')
        self.wait(lambda: self.state()['status'] == 'Playing', 'paused edit resume')

    def test_m3u_xspf_and_content_type_playlists_reach_real_audio(self):
        for path, resolved in [('/station.m3u', '/plain.mp3'), ('/station.xspf', '/icy'),
                               ('/playlist', '/plain.mp3'), ('/redirect.m3u', '/plain.mp3')]:
            with self.subTest(path=path):
                self.media('Stop')
                identifier = self.add(path, path)
                self.call('SelectStation', '(s)', (identifier,))
                self.media('Play')
                self.wait(lambda: self.state()['status'] == 'Playing', f'{path} decoded')
                self.assertEqual(self.state()['resolvedUrl'], self.url + resolved)
                self.assertEqual(self.state()['stations'][-1]['url'], self.url + path)
                self.assertEqual(self.prop(PLAYER, 'Metadata')['xesam:url'], self.url + resolved)

    def test_bad_playlists_report_errors_without_hanging(self):
        for path in ['/loop.m3u', '/empty.m3u', '/huge.m3u', '/bad.xspf']:
            with self.subTest(path=path):
                identifier = self.add(path, path)
                self.call('SelectStation', '(s)', (identifier,))
                self.media('Play')
                self.wait(lambda: self.state()['error'], path)
                self.assertEqual(self.state()['status'], 'Stopped')

    def test_edit_and_pause_cancel_pending_playlist_without_stale_playback(self):
        identifier = self.add('/slow.m3u')
        self.media('Play')
        self.wait(lambda: Streams.slow_started.is_set(), 'slow playlist requested')
        self.call('UpdateStation', '(sss)', (identifier, 'New source', self.url + '/plain.mp3'))
        self.wait(lambda: self.state()['status'] == 'Playing', 'new source plays')
        time.sleep(1.2)
        self.assertEqual(self.state()['resolvedUrl'], self.url + '/plain.mp3')
        self.media('Stop')
        Streams.slow_started.clear()
        self.call('UpdateStation', '(sss)', (identifier, 'Slow source', self.url + '/slow.m3u'))
        self.media('Play')
        self.wait(lambda: Streams.slow_started.is_set(), 'second slow playlist requested')
        self.media('Pause')
        time.sleep(1.2)
        self.assertEqual(self.state()['status'], 'Paused')
        self.assertEqual(self.state()['resolvedUrl'], '')

    def test_icy_metadata_notifications_and_switching(self):
        self.add('/icy')
        self.call('PlayPause')
        self.wait(lambda: self.state()['title'] == 'First song', 'initial ICY title')
        self.wait(lambda: self.state()['status'] == 'Playing', 'ICY playback')
        self.assertEqual(self.tracks, [])
        Streams.title = 'Second song'
        self.wait(lambda: self.state()['title'] == 'Second song', 'next title with notifications disabled')
        self.assertEqual(self.tracks, [])
        self.call('SetNotifications', '(b)', (True,))
        Streams.title = 'Third song'
        self.wait(lambda: len(self.tracks) == 1, 'track notification')
        self.assertEqual(self.tracks[0], ('Test radio', 'Third song'))
        self.assertEqual(self.prop(PLAYER, 'Metadata')['xesam:title'], 'Third song')
        deadline = time.monotonic() + 0.8
        while time.monotonic() < deadline:
            pump()
            time.sleep(0.05)
        self.assertEqual(len(self.tracks), 1)
        plain = self.add('/plain', 'No metadata')
        self.call('SelectStation', '(s)', (plain,))
        self.wait(lambda: self.state()['status'] == 'Playing', 'new station playback')
        self.assertEqual(self.state()['title'], '')
        self.call('RemoveStation', '(s)', (plain,))
        self.assertEqual(self.state()['status'], 'Stopped')

    def test_artist_tags_combined_icy_and_stale_metadata(self):
        self.add('/tagged.mp3')
        self.call('PlayPause')
        self.wait(lambda: self.state()['artist'] == 'Tagged artist', 'explicit artist tag')
        self.assertEqual(self.state()['title'], 'Tagged song')
        self.assertEqual(self.prop(PLAYER, 'Metadata')['xesam:artist'], ['Tagged artist'])
        icy = self.add('/icy', 'ICY radio')
        self.call('SelectStation', '(s)', (icy,))
        self.wait(lambda: self.state()['title'] == 'First song', 'new station metadata')
        self.assertEqual(self.state()['artist'], '')
        self.assertNotIn('xesam:artist', self.prop(PLAYER, 'Metadata'))
        Streams.title = 'ICY artist - Another song'
        self.wait(lambda: self.state()['artist'] == 'ICY artist', 'combined ICY artist')
        self.assertEqual(self.state()['title'], 'Another song')
        self.assertEqual(self.prop(PLAYER, 'Metadata')['xesam:artist'], ['ICY artist'])
        Streams.title = 'Title without artist'
        self.wait(lambda: self.state()['title'] == 'Title without artist', 'artist-less next track')
        self.assertEqual(self.state()['artist'], '')
        self.media('Stop')
        self.assertEqual(self.state()['artist'], '')

    def test_recent_limit_history_and_persistence(self):
        ids = [self.add(f'/plain.mp3?station={i}', f'Radio {i}') for i in range(11)]
        self.assertEqual(self.state()['recent'], [])
        self.assertEqual(self.state()['recentLimit'], 3)
        self.assertFalse(self.state()['playButtonOnLeft'])
        self.assertFalse(self.state()['groupWithAppIndicators'])
        for identifier in ids:
            self.call('SelectStation', '(s)', (identifier,))
            self.media('Play')
            self.wait(lambda: self.state()['status'] == 'Playing', 'recent station actually playing')
            self.wait(lambda: self.state()['recent'][0] == identifier, 'recent history recorded')
        self.assertEqual(self.state()['recent'], list(reversed(ids))[:10])
        for limit in (0, 11):
            with self.assertRaises(GLib.Error):
                self.call('SetRecentLimit', '(u)', (limit,))
        self.assertEqual(self.state()['recentLimit'], 3)
        history = self.state()['recent']
        self.call('SetRecentLimit', '(u)', (1,))
        self.assertEqual(self.state()['recent'], history)
        self.assertEqual(self.state()['status'], 'Playing')
        self.call('SetRecentLimit', '(u)', (7,))
        self.assertEqual(self.state()['recentLimit'], 7)
        self.call('SetPlayButtonOnLeft', '(b)', (True,))
        self.assertTrue(self.state()['playButtonOnLeft'])
        self.call('SetGroupWithAppIndicators', '(b)', (True,))
        self.assertTrue(self.state()['groupWithAppIndicators'])
        self.assertEqual(self.state()['status'], 'Playing')
        self.call('SelectStation', '(s)', (ids[2],))
        self.wait(lambda: self.state()['recent'][0] == ids[2], 'replayed station moved to front')
        recent = self.state()['recent']
        self.assertEqual(len(recent), len(set(recent)))
        self.shutdown(); self.start()
        self.assertEqual(self.state()['recent'], recent)
        self.assertEqual(self.state()['recentLimit'], 7)
        self.assertTrue(self.state()['playButtonOnLeft'])
        self.assertTrue(self.state()['groupWithAppIndicators'])
        self.call('SetGroupWithAppIndicators', '(b)', (False,))
        self.assertFalse(self.state()['groupWithAppIndicators'])
        self.call('RemoveStation', '(s)', (ids[2],))
        self.assertNotIn(ids[2], self.state()['recent'])

    def test_optional_favicons_bounds_cache_and_cancellation(self):
        identifier = self.add('/plain.mp3')
        self.assertFalse(self.state()['fetchFavicons'])
        self.assertEqual(Streams.favicon_requests, 0)
        for mode in ('html', 'huge'):
            Streams.favicon_mode = mode
            count = Streams.favicon_requests
            self.call('SetFetchFavicons', '(b)', (True,))
            self.wait(lambda: Streams.favicon_requests > count, 'bounded favicon request')
            time.sleep(0.2); pump()
            self.assertEqual(self.state()['favicons'], {})
            self.call('SetFetchFavicons', '(b)', (False,))
        Streams.favicon_mode = 'slow'
        count = Streams.favicon_requests
        self.call('SetFetchFavicons', '(b)', (True,))
        self.wait(lambda: Streams.favicon_requests > count, 'slow icon started')
        self.call('SetFetchFavicons', '(b)', (False,))
        time.sleep(1.1); pump()
        self.assertEqual(self.state()['favicons'], {})
        Streams.favicon_mode = 'png'
        self.call('SetFetchFavicons', '(b)', (True,))
        self.wait(lambda: identifier in self.state()['favicons'], 'favicon cached')
        self.assertTrue(self.state()['favicons'][identifier].startswith('file://'))
        count = Streams.favicon_requests
        self.shutdown(); self.start()
        self.wait(lambda: identifier in self.state()['favicons'], 'favicon read from cache')
        self.assertEqual(Streams.favicon_requests, count)
        self.assertTrue(self.state()['fetchFavicons'])
        self.call('SetFetchFavicons', '(b)', (False,))
        self.assertEqual(self.state()['favicons'], {})

    def test_network_failure_is_recoverable(self):
        bad = self.add('/missing', 'Unavailable')
        self.call('PlayPause')
        self.wait(lambda: self.state()['error'], 'HTTP failure')
        self.assertEqual(self.state()['status'], 'Stopped')
        good = self.add('/plain', 'Working')
        self.call('SelectStation', '(s)', (good,))
        self.call('PlayPause')
        self.wait(lambda: self.state()['status'] == 'Playing', 'recovered playback')
        self.assertEqual(self.state()['error'], '')
        self.call('RemoveStation', '(s)', (bad,))

    def test_corrupt_configuration_is_never_overwritten(self):
        self.shutdown()
        saved = Path(self.directory.name) / 'gnome-radio/stations.json'
        saved.parent.mkdir(exist_ok=True)
        saved.write_text('{broken')
        self.start()
        self.assertIn('repair', self.state()['error'])
        with self.assertRaises(GLib.Error):
            self.add()
        self.assertEqual(saved.read_text(), '{broken')

    def test_idle_service_resource_sample(self):
        stat = Path(f'/proc/{self.process.pid}/stat')
        before = stat.read_text().split()
        start = time.monotonic()
        time.sleep(1)
        after = stat.read_text().split()
        cpu_seconds = sum(int(after[i]) - int(before[i]) for i in (13, 14)) / os.sysconf('SC_CLK_TCK')
        rss_mib = int(after[23]) * os.sysconf('SC_PAGE_SIZE') / (1024 * 1024)
        print(f'Idle service: {rss_mib:.1f} MiB RSS, {cpu_seconds:.3f}s CPU / {time.monotonic() - start:.2f}s')
        self.assertLess(cpu_seconds, 0.2, 'Idle service unexpectedly busy')

    def test_service_exits_when_its_shell_connection_disappears(self):
        self.shutdown()
        parent = Gio.DBusConnection.new_for_address_sync(os.environ['DBUS_SESSION_BUS_ADDRESS'],
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None, None)
        self.start((f'--owner={parent.get_unique_name()}',))
        parent.close_sync(None)
        self.process.wait(timeout=5)
        self.assertEqual(self.process.returncode, 0)
        self.assertFalse(self.has_owner())


if __name__ == '__main__':
    unittest.main(verbosity=2)
