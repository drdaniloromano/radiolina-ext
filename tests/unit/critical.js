// SPDX-License-Identifier: MIT
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {cleanText, validateUrl, validateConfig, emptyConfig, MetadataTracker} from '../../src/core/stations.js';
import {Store} from '../../src/service/store.js';
import {parsePlaylist, MAX_PLAYLIST_BYTES} from '../../src/core/playlists.js';
import {validFavicon, MAX_FAVICON_BYTES} from '../../src/core/favicons.js';
import {validateRedirect} from '../../src/core/validation/urls.js';
import {inspectMedia, validateIcyInterval, MAX_PROBE_BYTES} from '../../src/core/validation/media.js';
import {MAX_CONFIG_BYTES, MAX_STATION_ID_LENGTH} from '../../src/core/validation/config.js';

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
test('applies URL policy to relative redirects and rejects HTTPS downgrades', () => {
    assert(validateRedirect('https://radio.example/path/live', '../audio') === 'https://radio.example/audio');
    assert(validateRedirect('http://127.0.0.1/live', '/other') === 'http://127.0.0.1/other');
    assert(validateRedirect('http://radio.example/live', 'https://radio.example/audio') === 'https://radio.example/audio');
    for (const target of ['', 'http://radio.example/audio', 'https://name:password@radio.example/audio',
        'https://radio.example/audio#fragment', 'file:///tmp/audio', 'data:audio/mpeg,abc',
        '/bad path', 'x'.repeat(2049)])
        rejects(() => validateRedirect('https://radio.example/live', target));
});
test('bounds byte-level media admission and rejects unsupported or disguised input', () => {
    const encode = value => new TextEncoder().encode(value);
    for (const data of ['<html>not audio</html>', '<!DOCTYPE html><html/>', '#EXTM3U\n#EXT-X-VERSION:3\nsegment.ts'])
        rejects(() => inspectMedia(encode(data), {final: true}));
    assert(inspectMedia(encode('#EXTM3U\nhttp://radio.example/live'))?.format === 'm3u');
    assert(inspectMedia(encode('<playlist xmlns="http://xspf.org/ns/0/">'))?.format === 'xspf');
    assert(inspectMedia(encode('/relative.mp3'), {playlistHint: 'm3u'})?.format === 'm3u');
    rejects(() => inspectMedia(new Uint8Array(MAX_PROBE_BYTES + 1)));
    rejects(() => inspectMedia(encode('ID3\x04\0\0\x7f\x7f\x7f\x7f')));
    assert(inspectMedia(new Uint8Array([255])) === null);
    rejects(() => inspectMedia(new Uint8Array([255]), {final: true}));
    rejects(() => inspectMedia(encode('ID3\x04'), {final: true}));
    for (const value of ['0', '-1', 'abc', '2147483648']) rejects(() => validateIcyInterval(value));
    assert(validateIcyInterval(null) === 0 && validateIcyInterval('4096') === 4096);
    // A bounded WAV PCM/float header is allowed; compressed WAV is outside policy.
    const wave = new Uint8Array(44);
    wave.set(encode('RIFF')); wave.set(encode('WAVEfmt '), 8);
    const view = new DataView(wave.buffer);
    view.setUint32(16, 16, true); view.setUint16(20, 1, true);
    assert(inspectMedia(wave).codec === 'pcm');
    view.setUint16(20, 7, true);
    rejects(() => inspectMedia(wave));
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
test('bounds saved station IDs and rejects unknown config or station fields', () => {
    const id = 'x'.repeat(MAX_STATION_ID_LENGTH);
    const config = {...emptyConfig(), selected: id, recent: [id],
        stations: [{id, name: 'My radio', url: 'https://radio.example/live'}]};
    const valid = validateConfig(config);
    assert(valid.selected === id);
    assert(valid !== config && valid.stations[0] !== config.stations[0] && valid.recent !== config.recent);
    rejects(() => validateConfig({...config, stations: [{...config.stations[0], id: id + 'x'}]}));
    for (const key of ['extra', 'status', '__proto__']) {
        rejects(() => validateConfig({...config, [key]: 'unused'}));
        rejects(() => validateConfig({...config, stations: [{...config.stations[0], [key]: 'unused'}]}));
    }
    for (const value of [null, [], 'text', 1]) rejects(() => validateConfig(value));
    const many = {...emptyConfig(), stations: Array.from({length: 200}, (_, n) =>
        ({id: `radio_${n}`, name: 'Radio', url: `https://radio.example/${n}`}))};
    assert(validateConfig(many).stations.length === 200);
    rejects(() => validateConfig({...many, stations: [...many.stations, {id: 'extra', name: 'Extra', url: 'https://radio.example/extra'}]}));
});
test('bounds file bytes before parsing and preserves oversized or invalid UTF-8 input', () => {
    const path = GLib.dir_make_tmp('gnome-radio-bounds-XXXXXX');
    const store = new Store(path);
    const write = bytes => store.file.replace_contents(bytes, null, false, Gio.FileCreateFlags.PRIVATE, null);
    const json = JSON.stringify({version: 1, stations: [], selected: '', notifications: false});
    try {
        const exact = new TextEncoder().encode(json + ' '.repeat(MAX_CONFIG_BYTES - json.length));
        write(exact);
        assert(store.load().recentLimit === 3, 'Legacy defaults must survive at the byte boundary');
        const oversized = new Uint8Array(MAX_CONFIG_BYTES + 1);
        oversized.set(exact); oversized[MAX_CONFIG_BYTES] = 32;
        for (const bytes of [oversized, new Uint8Array([0xff])]) {
            write(bytes);
            rejects(() => store.load());
            const after = store.file.load_contents(null)[1];
            assert(after.length === bytes.length && after.every((v, i) => v === bytes[i]));
        }
        store.save({version: 1, stations: [], selected: '', notifications: false});
        assert(JSON.parse(new TextDecoder().decode(store.file.load_contents(null)[1])).recentLimit === 3);
    } finally {
        store.file.delete(null);
        Gio.File.new_for_path(path).delete(null);
    }
    // A growing/size-less input must also stop at the bound and always close.
    let read = 0;
    let closed = false;
    store.file = {read: () => ({read_bytes: count => {
        read += count;
        if (read > MAX_CONFIG_BYTES + 1) throw new Error('Unbounded read');
        return GLib.Bytes.new(new Uint8Array(count).fill(32));
    }, close: () => { closed = true; }})};
    rejects(() => store.load());
    assert(read === MAX_CONFIG_BYTES + 1 && closed, 'Read must stop and close at overflow');
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
