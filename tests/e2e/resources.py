# SPDX-License-Identifier: MIT
"""Ten-minute local-fixture lifecycle probe; Linux /proc, silent audio, no GC hooks."""
import json
import os
from pathlib import Path
import re
import threading
import time
import unittest

from service import ServiceFixture, Streams, pump


class ResourceStreams(Streams):
    active = 0
    lock = threading.Lock()

    def setup(self):
        super().setup()
        with self.lock:
            type(self).active += 1

    def finish(self):
        try:
            super().finish()
        finally:
            with self.lock:
                type(self).active -= 1


class ResourceE2E(ServiceFixture):
    stream_handler = ResourceStreams

    def measure(self, phase, started, cycles):
        base = Path('/proc', str(self.process.pid))
        memory = (base / 'smaps_rollup').read_text()
        status = (base / 'status').read_text()
        stat = (base / 'stat').read_text().split()
        targets = []
        for entry in (base / 'fd').iterdir():
            try:
                targets.append(str(entry.readlink()))
            except FileNotFoundError:
                pass
        result = {'phase': phase, 'seconds': round(time.monotonic() - started, 3),
                  'cycles': cycles, 'rss_kib': int(re.search(r'^Rss:\s+(\d+)', memory, re.M)[1]),
                  'pss_kib': int(re.search(r'^Pss:\s+(\d+)', memory, re.M)[1]),
                  'fds': len(targets), 'sockets': sum(t.startswith('socket:') for t in targets),
                  'eventfds': sum('eventfd' in t for t in targets),
                  'threads': int(re.search(r'^Threads:\s+(\d+)', status, re.M)[1]),
                  'cpu_seconds': sum(int(stat[i]) for i in (13, 14)) / os.sysconf('SC_CLK_TCK'),
                  'fixture_connections': ResourceStreams.active}
        print('RESOURCE_SAMPLE ' + json.dumps(result), flush=True)
        # Safety ceilings terminate the probe well before exhausting host resources.
        self.assertLess(result['rss_kib'], 256 * 1024, 'Resource probe RSS safety ceiling')
        self.assertLess(result['fds'], 256, 'Resource probe descriptor safety ceiling')
        self.assertLess(result['threads'], 64, 'Resource probe thread safety ceiling')
        return result

    def idle_until(self, deadline):
        while time.monotonic() < deadline:
            pump()
            time.sleep(min(0.2, max(0, deadline - time.monotonic())))

    def test_ten_minute_playback_cleanup_without_forced_gc(self):
        started = time.monotonic()
        ids = [self.add(path, name) for path, name in
               [('/plain.mp3', 'Plain'), ('/icy', 'Metadata'),
                ('/slow.m3u', 'Cancellation'), ('/missing', 'Failure')]]

        def cycle(index):
            self.media('Stop')
            kind = index % 5
            self.call('SelectStation', '(s)', (ids[{0: 0, 1: 1, 2: 2, 3: 3, 4: 0}[kind]],))
            Streams.slow_started.clear()
            self.media('Play')
            if kind == 2:
                self.wait(Streams.slow_started.is_set, 'pending playlist')
                self.media('Pause')
            elif kind == 3:
                self.wait(lambda: self.state()['error'], 'failed source')
            elif kind != 4:
                self.wait(lambda: self.state()['status'] == 'Playing', 'cycle playback')
                if kind == 0:
                    self.media('Pause')
                    self.media('Play')
                else:
                    self.wait(lambda: self.state()['title'], 'cycle metadata')
                    self.call('SelectStation', '(s)', (ids[0],))
                    self.wait(lambda: self.state()['status'] == 'Playing' and not self.state()['title'],
                              'switch clears old metadata')
            self.media('Stop')
            self.assertEqual(self.state()['status'], 'Stopped')

        for index in range(5):
            cycle(index)
        self.idle_until(started + 30)
        baseline = self.measure('warm-idle', started, 5)
        cycles = 5
        next_sample = time.monotonic() + 30
        samples = [baseline]
        while time.monotonic() < started + 510:
            tick = time.monotonic()
            cycle(cycles)
            cycles += 1
            self.idle_until(min(tick + 5, started + 510))
            if time.monotonic() >= next_sample:
                samples.append(self.measure('cycling', started, cycles))
                next_sample = time.monotonic() + 30
        self.media('Stop')
        for elapsed in (540, 570, 600):
            self.idle_until(started + elapsed)
            samples.append(self.measure('final-idle', started, cycles))
        final = samples[-1]
        previous = samples[-2]
        self.assertEqual(final['fixture_connections'], 0, 'Stop must close all fixture connections')
        self.assertLessEqual(final['fds'], baseline['fds'] + 24, 'Descriptors retained after 90 seconds idle')
        self.assertLessEqual(final['threads'], baseline['threads'] + 4, 'Threads retained after idle')
        self.assertLessEqual(final['pss_kib'], baseline['pss_kib'] + 32 * 1024, 'Private memory retention')
        self.assertLess(final['cpu_seconds'] - previous['cpu_seconds'], 0.5, 'Idle service CPU over 30 seconds')
        self.shutdown()
        self.assertFalse(Path('/proc', str(self.process.pid)).exists())
        print('RESOURCE_RESULT ' + json.dumps({'samples': samples, 'cycles': cycles,
              'forced_gc': False, 'service_exited': True}), flush=True)


if __name__ == '__main__':
    unittest.main(defaultTest='ResourceE2E', verbosity=2)
