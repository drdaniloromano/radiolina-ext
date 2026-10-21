# SPDX-License-Identifier: MIT
"""Validate real response bytes and transport; no public endpoints or host trust changes."""
import gzip
import http.server
import json
from pathlib import Path
import shutil
import ssl
import subprocess
import threading
import time
import unittest
from urllib.parse import parse_qs, urlsplit
from service import ServiceFixture, Streams, ROOT, PLAYER, MPRIS, Gio, GLib


class ValidationStreams(Streams):
    requests = []
    private_requests = []
    formats = {}
    http_url = ''
    tls_url = ''

    def do_GET(self):
        parts = urlsplit(self.path)
        path = parts.path
        self.requests.append(path)
        if path.startswith('/private-'):
            self.private_requests.append(self.path)
        if path == '/private-start/source-secret':
            self.send_response(302)
            self.send_header('Location', '/private-final/redirect-secret?token=redirect-token')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        location = None
        if path.startswith('/redirect/'):
            kind = path.split('/')[2].split('.')[0]
            location = {
                'credentials': self.http_url.replace('://', '://audit:fixture@') + '/target',
                'fragment': self.http_url + '/target#fragment',
                'file': 'file:///tmp/synthetic-fixture',
                'data': 'data:audio/mpeg,fixture',
                'upgrade': self.tls_url + '/plain.mp3',
                'downgrade': self.http_url + '/target',
            }.get(kind)
            if kind in ('five', 'six'):
                count = int(parse_qs(parts.query).get('n', ['0'])[0])
                maximum = 5 if kind == 'five' else 6
                location = f'{path}?n={count + 1}' if count + 1 < maximum else '/plain.mp3'
        if location:
            self.send_response(302)
            self.send_header('Location', location)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        bodies = {
            '/disguised-html.mp3': (b'<html>not audio</html>', 'audio/mpeg'),
            '/disguised-hls.mp3': (b'#EXTM3U\n#EXT-X-TARGETDURATION:10\n/target\n', 'audio/mpeg'),
            '/disguised-playlist.mp3': (b'#EXTM3U\n/plain.mp3\n', 'audio/mpeg'),
            '/huge-id3.mp3': (b'ID3\x04\0\0\x7f\x7f\x7f\x7f', 'audio/mpeg'),
            '/compressed-playlist.mp3': (gzip.compress(b'#EXTM3U\n' + b'x' * (256 * 1024)), 'audio/mpeg'),
            '/downgrade-entry.m3u': ((self.http_url + '/target\n').encode(), 'audio/x-mpegurl'),
            '/single-response.mp3': (Streams.audio if self.requests.count(path) == 1 else b'<html>changed</html>', 'text/plain'),
            '/invalid-icy.mp3': (Streams.audio, 'audio/mpeg'),
            # Two bounded synthetic ADTS frames exercise unavailable-codec reporting.
            '/aac.aac': ((b'\xff\xf1\x50\x80\x01\x7f\xfc' + b'\0' * 4) * 2, 'audio/aac'),
        }
        bodies.update({f'/format/{name}': (data, 'application/octet-stream') for name, data in self.formats.items()})
        if path in bodies:
            body, content_type = bodies[path]
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            if path == '/compressed-playlist.mp3': self.send_header('Content-Encoding', 'gzip')
            if path == '/invalid-icy.mp3': self.send_header('icy-metaint', '2147483648')
            self.end_headers()
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass
            return
        super().do_GET()


class ValidationE2E(ServiceFixture):
    stream_handler = ValidationStreams

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        base = Path(cls.fixture.name)
        for name, chain in {
            'flac': ['flacenc'],
            'vorbis.ogg': ['vorbisenc', '!', 'oggmux'],
            'opus.ogg': ['opusenc', '!', 'oggmux'],
            'wav': ['wavenc'],
            'opus.m4a': ['opusenc', '!', 'mp4mux', 'faststart=true'],
            'mp3.m4a': ['lamemp3enc', '!', 'mpegaudioparse', '!', 'mp4mux', 'faststart=true'],
        }.items():
            path = base / name
            subprocess.run(['gst-launch-1.0', '-q', 'audiotestsrc', 'num-buffers=200', '!',
                            'audioconvert', '!', *chain, '!', 'filesink', f'location={path}'], check=True)
            ValidationStreams.formats[name] = path.read_bytes()
        video = base / 'video.ogg'
        subprocess.run(['gst-launch-1.0', '-q', 'videotestsrc', 'num-buffers=2', '!',
                        'video/x-raw,width=32,height=32', '!', 'theoraenc', '!', 'oggmux',
                        '!', 'filesink', f'location={video}'], check=True)
        ValidationStreams.formats['video.mp3'] = video.read_bytes()
        video = base / 'video.m4a'
        subprocess.run(['gst-launch-1.0', '-q', 'videotestsrc', 'num-buffers=2', '!',
                        'video/x-raw,width=32,height=32', '!', 'jpegenc', '!', 'qtmux',
                        'faststart=true', '!', 'filesink', f'location={video}'], check=True)
        ValidationStreams.formats['video.m4a'] = video.read_bytes()
        cert, key = base / 'certificate.pem', base / 'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1',
                        '-keyout', str(key), '-out', str(cert)], check=True, capture_output=True)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        cls.tls_server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), ValidationStreams)
        cls.tls_server.daemon_threads = True
        cls.tls_server.socket = context.wrap_socket(cls.tls_server.socket, server_side=True)
        threading.Thread(target=cls.tls_server.serve_forever, daemon=True).start()
        ValidationStreams.http_url = cls.url
        ValidationStreams.tls_url = f'https://127.0.0.1:{cls.tls_server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.tls_server.shutdown(); cls.tls_server.server_close()
        super().tearDownClass()

    def setUp(self):
        ValidationStreams.requests.clear()
        ValidationStreams.private_requests.clear()
        super().setUp()

    def play_url(self, url, error=False):
        self.media('Stop')
        identifier = self.call('AddStation', '(ss)', ('Validation fixture', url))[0]
        self.call('SelectStation', '(s)', (identifier,))
        self.media('Play')
        self.wait(lambda: self.state()['error'] or self.state()['status'] == 'Playing',
                  'rejected source' if error else 'validated playback')
        if error: self.assertTrue(self.state()['error'], self.state())
        else: self.assertEqual(self.state()['status'], 'Playing', self.state()['error'])
        return self.state()

    def test_format_bytes_select_explicit_audio_pipeline(self):
        for name in ('flac', 'vorbis.ogg', 'opus.ogg', 'wav', 'opus.m4a', 'mp3.m4a'):
            with self.subTest(name=name):
                self.play_url(self.url + '/format/' + name)
                self.assertEqual(ValidationStreams.requests.count('/format/' + name), 1)

    def test_disguised_unsupported_content_and_bounds_are_rejected(self):
        for suffix in ('/disguised-html.mp3', '/disguised-hls.mp3', '/huge-id3.mp3',
                       '/compressed-playlist.mp3', '/invalid-icy.mp3', '/format/video.mp3', '/format/video.m4a'):
            with self.subTest(suffix=suffix):
                state = self.play_url(self.url + suffix, error=True)
                self.assertEqual(state['status'], 'Stopped')
                self.assertEqual(state['title'], '')
                self.assertNotIn('/target', ValidationStreams.requests)
        self.play_url(self.url + '/disguised-playlist.mp3')

    def test_playback_uses_the_inspected_response_without_second_get(self):
        self.play_url(self.url + '/single-response.mp3')
        self.assertEqual(ValidationStreams.requests.count('/single-response.mp3'), 1)

    def test_missing_audio_codec_has_a_specific_error(self):
        if any(subprocess.run(['gst-inspect-1.0', name], capture_output=True).returncode == 0
               for name in ('avdec_aac', 'fdkaacdec', 'faad')):
            self.skipTest('AAC decoder installed; synthetic ADTS fixture tests absence only')
        state = self.play_url(self.url + '/aac.aac', error=True)
        self.assertIn('Required codec unavailable: AAC', state['error'])

    def test_actual_redirects_apply_one_policy_to_all_source_names(self):
        for extension in ('mp3', 'm3u'):
            for kind in ('credentials', 'fragment', 'file', 'data', 'six'):
                with self.subTest(extension=extension, kind=kind):
                    state = self.play_url(f'{self.url}/redirect/{kind}.{extension}', error=True)
                    self.assertEqual(state['status'], 'Stopped')
                    self.assertNotIn('/target', ValidationStreams.requests)
            self.play_url(f'{self.url}/redirect/five.{extension}')

    def test_trusted_tls_upgrade_downgrade_and_playlist_entry_policy(self):
        self.shutdown()
        runtime = Path(self.directory.name, 'tls-runtime')
        shutil.copytree(ROOT / 'src', runtime)
        entry = runtime / 'service/main.js'
        cert = Path(self.fixture.name, 'certificate.pem')
        # Trust only this ephemeral CA in the disposable service process; do not
        # disable certificate checks or modify host/system trust stores.
        entry.write_text(entry.read_text().replace('configureOomPreference();',
                         f'Gio.TlsBackend.get_default().set_default_database(Gio.TlsFileDatabase.new({json.dumps(str(cert))}));\n'
                         'configureOomPreference();', 1))
        self.service_entry = entry
        self.start()
        self.play_url(self.url + '/redirect/upgrade.mp3')
        for suffix in ('/redirect/downgrade.mp3', '/redirect/downgrade.m3u', '/downgrade-entry.m3u'):
            state = self.play_url(ValidationStreams.tls_url + suffix, error=True)
            self.assertIn('unencrypted HTTP', state['error'])
            self.assertNotIn('/target', ValidationStreams.requests)

    def test_unsupported_bytes_never_reach_decoder_construction(self):
        self.shutdown()
        runtime = Path(self.directory.name, 'runtime')
        shutil.copytree(ROOT / 'src', runtime)
        decoder = runtime / 'service/decoder.js'
        marker = runtime / 'decoder-reached'
        decoder.write_text("import GLib from 'gi://GLib';\n" + decoder.read_text().replace(
            'export function createPipeline(source, testAudio) {',
            'export function createPipeline(source, testAudio) { '
            f'GLib.file_set_contents({json.dumps(str(marker))}, "called"); '
            "throw new Error('fixture: decoder reached');", 1))
        self.service_entry = runtime / 'service/main.js'
        self.start()
        state = self.play_url(self.url + '/disguised-html.mp3', error=True)
        self.assertIn('Unsupported stream format', state['error'])
        self.assertFalse(marker.exists(), 'Rejected content must not reach the decoder')
        state = self.play_url(self.url + '/plain.mp3', error=True)
        self.assertTrue(marker.exists(), 'The construction trap must be active')
        self.assertNotIn('decoder reached', state['error'], 'Unexpected errors stay private')

    def test_private_urls_stay_out_of_media_metadata_and_redirect_state(self):
        changes = []
        subscription = self.bus.signal_subscribe(
            'org.mpris.MediaPlayer2.GnomeRadio', 'org.freedesktop.DBus.Properties',
            'PropertiesChanged', MPRIS, None, Gio.DBusSignalFlags.NONE,
            lambda *_args: changes.append(_args[-1].unpack()))
        self.addCleanup(self.bus.signal_unsubscribe, subscription)
        for suffix in ('/private-final/direct-secret?token=direct-token',
                       '/private-start/source-secret?token=source-token'):
            url = self.url + suffix
            state = self.play_url(url)
            self.assertIn(suffix, ValidationStreams.private_requests)
            if 'private-start' in suffix:
                self.assertIn('/private-final/redirect-secret?token=redirect-token',
                              ValidationStreams.private_requests)
            self.assertNotIn('resolvedUrl', state)
            self.assertEqual(state['stations'][-1]['url'], url)
            for command in ('Pause', 'Play', 'Stop'):
                self.media(command)
                if command == 'Play':
                    self.wait(lambda: self.state()['status'] == 'Playing', 'private URL resumes')
                metadata = self.prop(PLAYER, 'Metadata')
                self.assertNotIn('xesam:url', metadata)
                self.assertIn('mpris:trackid', metadata)
                self.assertEqual(metadata['xesam:title'], 'Validation fixture')
                self.assertEqual(metadata['xesam:album'], 'Validation fixture')
        self.assertTrue(any('Metadata' in changed for _, changed, _ in changes))
        for _, changed, _ in changes:
            metadata = changed.get('Metadata', {})
            self.assertNotIn('xesam:url', metadata)
            self.assertNotIn('-secret', json.dumps(metadata))
            self.assertNotIn('-token', json.dumps(metadata))
        saved = Path(self.directory.name, 'gnome-radio/stations.json')
        self.assertEqual(json.loads(saved.read_text())['stations'], self.state()['stations'])
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        self.log.flush(); self.log.seek(0)
        self.assertNotIn('-secret', self.log.read())

    def test_unexpected_backend_errors_do_not_disclose_secrets(self):
        self.shutdown()
        secret = 'https://radio.example/path-secret?token=query-secret\nraw-backend-secret ' + 'x' * 8192
        payload = json.dumps(secret)
        for mode in ('http', 'player', 'save', 'startup'):
            with self.subTest(mode=mode):
                runtime = Path(self.directory.name, mode + '-runtime')
                shutil.copytree(ROOT / 'src', runtime)
                if mode == 'http':
                    path = runtime / 'service/http.js'
                    content = path.read_text().replace('async open(sourceUrl) {',
                        'async open(sourceUrl) { throw new GLib.Error('
                        f'GLib.quark_from_string("fixture"), 1, {payload});', 1)
                elif mode == 'player':
                    path = runtime / 'service/player.js'
                    content = path.read_text().replace('this.onState(\'Connecting\');\n        this._armBufferingTimeout();',
                        'GLib.idle_add(GLib.PRIORITY_DEFAULT, () => { '
                        'bus.post(Gst.Message.new_error(pipeline, new GLib.Error('
                        f'GLib.quark_from_string("fixture"), 1, {payload}), {payload})); '
                        'return GLib.SOURCE_REMOVE; });\n'
                        "        this.onState('Connecting');\n        this._armBufferingTimeout();", 1)
                elif mode in ('save', 'startup'):
                    path = runtime / 'service/store.js'
                    method = 'save(config)' if mode == 'save' else 'load()'
                    content = path.read_text().replace(method + ' {',
                        method + f' {{ throw new Error({payload});', 1)
                self.assertNotEqual(content, path.read_text(), 'Fixture trap must be injected')
                path.write_text(content)
                self.service_entry = runtime / 'service/main.js'
                self.start()
                if mode in ('save', 'startup'):
                    with self.assertRaises(GLib.Error) as failure:
                        self.add('/plain-' + mode)
                    self.assertNotIn('secret', str(failure.exception))
                    self.assertLess(len(str(failure.exception)), 600)
                else:
                    self.play_url(self.url + '/plain-' + mode, error=True)
                self.assertNotIn('secret', self.state()['error'])
                self.assertLessEqual(len(self.state()['error']), 384)
                self.shutdown()
                self.log.seek(0)
                log = self.log.read()
                for marker in ('path-secret', 'query-secret', 'raw-backend-secret'):
                    self.assertNotIn(marker, log)


if __name__ == '__main__':
    unittest.main(defaultTest='ValidationE2E', verbosity=2)
