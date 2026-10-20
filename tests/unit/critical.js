// SPDX-License-Identifier: MIT
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {cleanText, validateUrl, validateConfig, emptyConfig, MetadataTracker} from '../../src/core/stations.js';
import {Store} from '../../src/service/store.js';
import {parsePlaylist, MAX_PLAYLIST_BYTES} from '../../src/core/playlists.js';
import {validFavicon, MAX_FAVICON_BYTES} from '../../src/core/favicons.js';

let count = 0;
function test(name, run) {
    run();
    count++;
    print(`ok ${count} - ${name}`);
}
function assert(value, message = 'Assertion failed') {
    if (!value) throw new Error(message);
}
function rejects(fn) {
    try { fn(); } catch { return; }
    throw new Error('Expected rejection');
}

test('accepts HTTP streams and rejects unsafe or malformed URLs', () => {
    for (const value of ['https://radio.example/live?x=1', 'http://127.0.0.1:8000/live', 'https://[::1]/live'])
        assert(validateUrl(value) === value);
    for (const value of ['', 'file:///etc/passwd', 'javascript:alert(1)', 'https:///live',
        'https://a:bad/live', 'https://user:pass@radio.example/live', 'https://radio.example/#x',
        'https://radio.example/\nheader', 'https://radio.example/a b'])
        rejects(() => validateUrl(value));
});
test('sanitizes untrusted metadata and bounds its length', () => {
    assert(cleanText('  Title\nartist\0  ') === 'Title artist');
    assert(cleanText('x'.repeat(1000)).length === 256);
});
test('deduplicates tracks and clears missing or stale metadata', () => {
    const tracker = new MetadataTracker();
    assert(!tracker.update('First').notify);
    assert(!tracker.update('First').changed);
    assert(!tracker.update('').notify);
    assert(!tracker.update('First').notify);
    assert(tracker.update('Second').notify);
    tracker.reset();
    assert(tracker.title === '');
    assert(!tracker.update('Second').notify);
});
test('reads explicit and combined artist metadata without retaining stale artists', () => {
    const tracker = new MetadataTracker();
    tracker.update('Artist - Song - live');
    assert(tracker.artist === 'Artist' && tracker.title === 'Song - live');
    assert(!tracker.update('Artist - Song - live').changed);
    tracker.update('New title');
    assert(tracker.artist === '' && tracker.title === 'New title');
    tracker.update(undefined, 'Explicit\nartist');
    assert(tracker.artist === 'Explicit artist' && tracker.title === 'New title');
    tracker.update('Track - Part two', 'Actual artist');
    assert(tracker.artist === 'Actual artist' && tracker.title === 'Track - Part two');
    tracker.update('Unknown', 'x'.repeat(1000));
    assert(tracker.artist.length === 256);
    tracker.update('');
    assert(tracker.artist === '' && tracker.title === '');
    tracker.reset();
    assert(tracker.artist === '' && tracker.rawArtist === '');
    tracker.update(undefined, 'Artist first');
    tracker.update('Title later');
    assert(tracker.artist === 'Artist first');
});
test('rejects invalid persisted state and duplicate stations', () => {
    const config = emptyConfig();
    config.stations = [{id: 'a', name: 'Radio', url: 'https://radio.example/'}];
    config.selected = 'a';
    validateConfig(config);
    rejects(() => validateConfig({...config, selected: 'missing'}));
    rejects(() => validateConfig({...config, stations: [...config.stations, ...config.stations]}));
    rejects(() => validateConfig({...config, version: 2}));
    assert(validateConfig({version: 1, stations: [], selected: '', notifications: false}).recent.length === 0);
    assert(!validateConfig({version: 1, stations: [], selected: '', notifications: false}).fetchFavicons);
    assert(!config.showStopButton);
    assert(!validateConfig({version: 1, stations: [], selected: '', notifications: false}).showStopButton);
    for (const showStopButton of ['yes', null, 0])
        rejects(() => validateConfig({...config, showStopButton}));
    assert(validateConfig({...config, showStopButton: true}).showStopButton);
    assert(!validateConfig({version: 1, stations: [], selected: '', notifications: false}).playButtonOnLeft);
    rejects(() => validateConfig({...config, playButtonOnLeft: 'yes'}));
    assert(!validateConfig({version: 1, stations: [], selected: '', notifications: false}).groupWithAppIndicators);
    for (const groupWithAppIndicators of ['yes', null, 0])
        rejects(() => validateConfig({...config, groupWithAppIndicators}));
    assert(validateConfig({...config, groupWithAppIndicators: true}).groupWithAppIndicators);
    assert(validateConfig({version: 1, stations: [], selected: '', notifications: false}).recentLimit === 3);
    for (const recentLimit of [0, 11, -1, 1.5, '3', null])
        rejects(() => validateConfig({...config, recentLimit}));
    assert(validateConfig({...config, recentLimit: 10}).recentLimit === 10);
    rejects(() => validateConfig({...config, recent: ['missing']}));
    rejects(() => validateConfig({...config, recent: ['a', 'a']}));
    rejects(() => validateConfig({...config, fetchFavicons: 'yes'}));
});
test('bounds untrusted favicon images and rejects active or oversized formats', () => {
    assert(!validFavicon(new TextEncoder().encode('<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>')));
    assert(!validFavicon(new Uint8Array(MAX_FAVICON_BYTES + 1)));
    const png = new Uint8Array(24);
    png.set([137, 80, 78, 71, 13, 10, 26, 10]);
    const view = new DataView(png.buffer);
    view.setUint32(12, 0x49484452); view.setUint32(16, 16); view.setUint32(20, 16);
    assert(validFavicon(png));
    const wrapped = new Uint8Array(22 + png.length);
    wrapped.set([0, 0, 1, 0, 1, 0, 16, 16]);
    const directory = new DataView(wrapped.buffer);
    directory.setUint32(14, png.length, true); directory.setUint32(18, 22, true);
    wrapped.set(png, 22);
    assert(validFavicon(wrapped));
    view.setUint32(16, 65535);
    assert(!validFavicon(png));
    const ico = new Uint8Array(40);
    ico.set([0, 0, 1, 0, 1, 0]);
    new DataView(ico.buffer).setUint32(14, 100, true);
    assert(!validFavicon(ico));
});
test('persists private configuration and refuses corrupt data without overwriting it', () => {
    const path = GLib.dir_make_tmp('gnome-radio-unit-XXXXXX');
    const store = new Store(path);
    try {
        assert(store.load().stations.length === 0);
        const config = emptyConfig();
        config.notifications = true;
        store.save(config);
        assert(store.load().notifications);
        const mode = store.file.query_info('unix::mode', Gio.FileQueryInfoFlags.NONE, null)
            .get_attribute_uint32('unix::mode');
        assert((mode & 0o077) === 0, 'Station file must be private');
        store.file.replace_contents('{broken', null, false, Gio.FileCreateFlags.PRIVATE, null);
        rejects(() => store.load());
        assert(new TextDecoder().decode(store.file.load_contents(null)[1]) === '{broken');
    } finally {
        store.file.delete(null);
        Gio.File.new_for_path(path).delete(null);
    }
});
test('resolves ordinary M3U URLs and rejects empty or HLS playlists', () => {
    assert(parsePlaylist('\uFEFF#EXTM3U\r\n#EXTINF:-1,Radio\r\n../live.mp3\r\n', 'm3u',
        'https://radio.example/lists/station.m3u') === 'https://radio.example/live.mp3');
    assert(parsePlaylist('file:///etc/passwd\nhttps://radio.example/live', 'm3u',
        'https://radio.example/list.m3u') === 'https://radio.example/live');
    rejects(() => parsePlaylist('#EXTM3U\n#EXT-X-TARGETDURATION:10\npart.ts', 'm3u', 'https://radio.example/'));
    rejects(() => parsePlaylist('#EXTM3U\n', 'm3u', 'https://radio.example/'));
    rejects(() => parsePlaylist('x'.repeat(MAX_PLAYLIST_BYTES + 1), 'm3u', 'https://radio.example/'));
});
test('reads namespaced XSPF, entities, CDATA and relative bases safely', () => {
    const xml = '<x:playlist xmlns:x="http://xspf.org/ns/0/" xml:base="../audio/">' +
        '<x:trackList><x:track><x:location>live.mp3?one=1&amp;two=2</x:location></x:track></x:trackList></x:playlist>';
    assert(parsePlaylist(xml, 'xspf', 'https://radio.example/lists/station.xspf') ===
        'https://radio.example/audio/live.mp3?one=1&two=2');
    const wrap = value => `<playlist xmlns="http://xspf.org/ns/0/"><trackList><track><location>${value}</location></track></trackList></playlist>`;
    assert(parsePlaylist(wrap('<![CDATA[https://radio.example/live?a=1&b=2]]>'), 'xspf',
        'https://radio.example/') === 'https://radio.example/live?a=1&b=2');
    rejects(() => parsePlaylist('<!DOCTYPE playlist [<!ENTITY x SYSTEM "file:///etc/passwd">]>' + wrap('&x;'), 'xspf', 'https://radio.example/'));
    rejects(() => parsePlaylist(wrap('&unknown;'), 'xspf', 'https://radio.example/'));
    rejects(() => parsePlaylist(wrap('file:///etc/passwd'), 'xspf', 'https://radio.example/'));
    rejects(() => parsePlaylist(wrap('https://radio.example/').replace('</track>', '</bad>'), 'xspf', 'https://radio.example/'));
});
print(`1..${count}`);
