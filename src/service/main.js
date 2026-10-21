#!@GJS@ -m
// SPDX-License-Identifier: MIT
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GLibUnix from 'gi://GLibUnix';
import {cleanText, emptyConfig, validateUrl, validateRecentLimit, MAX_RECENT_LIMIT, MetadataTracker} from '../core/stations.js';
import {Store} from './store.js';
import {Player} from './player.js';
import {configureOomPreference} from './resource-policy.js';

configureOomPreference();

const BUS = 'org.mpris.MediaPlayer2.GnomeRadio';
const APP_PATH = '/org/gnome/Radio';
const MPRIS_PATH = '/org/mpris/MediaPlayer2';
const directory = Gio.File.new_for_uri(import.meta.url).get_parent();
function read(relative) {
    return new TextDecoder().decode(directory.resolve_relative_path(relative).load_contents(null)[1]);
}

const loop = new GLib.MainLoop(null, false);
const store = new Store();
const metadata = new MetadataTracker();
let config;
let startupError = '';
try {
    config = store.load();
} catch (error) {
    startupError = error.message;
    config = emptyConfig();
}
let status = 'Stopped';
let errorText = startupError;
let appExport;
let playerExport;
let rootExport;
let volume = 1;
let loadGeneration = 0;
let loadCancellable = null;
let resolvedUrl = '';
let favicons = {};
let faviconSignature = '';
let faviconCancellable = null;
function refreshFavicons() {
    const signature = JSON.stringify([config.fetchFavicons, config.stations.map(s => [s.id, s.url])]);
    if (signature === faviconSignature) return;
    faviconSignature = signature;
    faviconCancellable?.cancel();
    const cancellable = new Gio.Cancellable();
    faviconCancellable = cancellable;
    favicons = {};
    if (!config.fetchFavicons) return;
    const stations = [...config.stations];
    (async () => {
        const {faviconUrl, fetchFavicon} = await import('./favicon.js');
        const origins = new Map();
        for (const saved of stations) {
            if (cancellable.is_cancelled()) return;
            const url = faviconUrl(saved.url);
            if (!origins.has(url)) origins.set(url, await fetchFavicon(url, cancellable));
            if (cancellable.is_cancelled()) return;
            const icon = origins.get(url);
            if (icon) { favicons[saved.id] = icon; publish(); }
        }
    })().catch(error => { if (!cancellable.is_cancelled()) console.warn(`Favicon unavailable: ${error.message}`); });
}
function station() {
    return config.stations.find(item => item.id === config.selected);
}
function publish() {
    appExport?.emit_property_changed('State', new GLib.Variant('s', JSON.stringify({
        ...config, favicons, status, title: metadata.title, artist: metadata.artist, error: errorText, resolvedUrl,
    })));
    playerExport?.emit_property_changed('PlaybackStatus', new GLib.Variant('s', mpris.PlaybackStatus));
    playerExport?.emit_property_changed('Metadata', new GLib.Variant('a{sv}', mpris.Metadata));
    playerExport?.emit_property_changed('CanPlay', new GLib.Variant('b', Boolean(station())));
    playerExport?.emit_property_changed('CanPause', new GLib.Variant('b', Boolean(station())));
}

const player = new Player(value => {
    status = value;
    if (value === 'Playing' && config.selected && config.recent[0] !== config.selected) {
        try {
            const next = {...config, recent: [config.selected, ...config.recent.filter(id => id !== config.selected)].slice(0, MAX_RECENT_LIMIT)};
            store.save(next);
            config = next;
        } catch { errorText = 'Recent stations could not be saved.'; }
    }
    publish();
}, (title, artist) => {
    const result = metadata.update(title, artist);
    if (result.changed)
        publish();
    if (result.notify && config.notifications && status === 'Playing')
        appExport?.emit_signal('TrackChanged', new GLib.Variant('(ss)', [station()?.name ?? '', metadata.title]));
}, message => {
    errorText = message;
    metadata.reset();
    publish();
});

function changeConfig(next) {
    if (startupError)
        throw new Error(startupError); // Never overwrite an unreadable station file.
    store.save(next); // Save before changing in-memory state.
    config = next;
    errorText = '';
    refreshFavicons();
    publish();
}
function play() {
    if (!station() || status === 'Playing' || status === 'Connecting')
        return;
    errorText = '';
    if (status === 'Paused' && player.pipeline) {
        player.resume();
    } else {
        metadata.reset();
        const sourceUrl = station().url;
        const generation = ++loadGeneration;
        const cancellable = new Gio.Cancellable();
        loadCancellable = cancellable;
        status = 'Connecting';
        (async () => {
            const source = await (await import('./source.js')).openStream(sourceUrl, cancellable);
            if (generation !== loadGeneration || cancellable.is_cancelled()) { source.close(); return; }
            resolvedUrl = source.url;
            player.start(source);
            player.setVolume(volume);
            publish();
        })().catch(error => {
            if (generation !== loadGeneration) return;
            errorText = error.message;
            status = 'Stopped';
            metadata.reset();
            publish();
        }).finally(() => {
            if (generation === loadGeneration) loadCancellable = null;
        });
    }
    publish();
}
function stop() {
    loadGeneration++;
    loadCancellable?.cancel();
    loadCancellable = null;
    resolvedUrl = '';
    player.stop();
    metadata.reset();
    publish();
}
function pause() {
    if (player.pipeline) player.pause();
    else if (status === 'Connecting') {
        stop();
        status = 'Paused';
        publish();
    }
}
const app = {
    get State() {
        return JSON.stringify({...config, favicons, status, title: metadata.title, artist: metadata.artist, error: errorText, resolvedUrl});
    },
    AddStation(name, url) {
        const normalized = validateUrl(url);
        const label = cleanText(name, 80);
        if (!label)
            throw new Error('Enter a station name.');
        if (config.stations.length >= 200)
            throw new Error('The station list is full.');
        if (config.stations.some(item => item.url === normalized))
            throw new Error('This stream is already saved.');
        const id = GLib.uuid_string_random();
        changeConfig({...config, selected: config.selected || id,
            stations: [...config.stations, {id, name: label, url: normalized}]});
        return id;
    },
    UpdateStation(id, name, url) {
        const existing = config.stations.find(item => item.id === id);
        if (!existing) throw new Error('Station not found.');
        const normalized = validateUrl(url);
        const label = cleanText(name, 80);
        if (!label) throw new Error('Enter a station name.');
        if (config.stations.some(item => item.id !== id && item.url === normalized))
            throw new Error('This stream is already saved.');
        const previousStatus = status;
        changeConfig({...config, stations: config.stations.map(item =>
            item.id === id ? {...item, name: label, url: normalized} : item)});
        if (id === config.selected && existing.url !== normalized) {
            stop();
            if (['Playing', 'Connecting'].includes(previousStatus)) play();
            else if (previousStatus === 'Paused') { status = 'Paused'; publish(); }
        }
    },
    RemoveStation(id) {
        if (!config.stations.some(item => item.id === id))
            throw new Error('Station not found.');
        const stations = config.stations.filter(item => item.id !== id);
        const selected = id === config.selected ? stations[0]?.id ?? '' : config.selected;
        const wasSelected = id === config.selected;
        changeConfig({...config, stations, selected, recent: config.recent.filter(item => item !== id)});
        if (wasSelected)
            stop();
    },
    SelectStation(id) {
        if (!config.stations.some(item => item.id === id))
            throw new Error('Station not found.');
        if (config.selected === id)
            return;
        const resume = ['Playing', 'Connecting'].includes(status);
        changeConfig({...config, selected: id});
        stop();
        if (resume)
            play();
    },
    PlayPause() {
        if (['Playing', 'Connecting'].includes(status))
            pause();
        else
            play();
    },
    Stop: stop,
    SetNotifications(enabled) {
        changeConfig({...config, notifications: enabled});
    },
    SetFetchFavicons(enabled) {
        changeConfig({...config, fetchFavicons: enabled});
    },
    SetShowStopButton(enabled) {
        changeConfig({...config, showStopButton: enabled});
    },
    SetRecentLimit(limit) {
        changeConfig({...config, recentLimit: validateRecentLimit(limit)});
    },
    SetPlayButtonOnLeft(enabled) {
        changeConfig({...config, playButtonOnLeft: enabled});
    },
    SetGroupWithAppIndicators(enabled) {
        changeConfig({...config, groupWithAppIndicators: enabled});
    },
    Quit() {
        stop();
        loop.quit();
    },
};
const mpris = {
    get PlaybackStatus() {
        return status === 'Paused' ? 'Paused' : ['Playing', 'Connecting'].includes(status) ? 'Playing' : 'Stopped';
    },
    get Metadata() {
        const current = station();
        if (!current)
            return {};
        return {
            'mpris:trackid': new GLib.Variant('o', `/org/gnome/Radio/track/${current.id.replace(/-/g, '_')}_${metadata.sequence}`),
            'xesam:title': new GLib.Variant('s', metadata.title || current.name),
            ...(metadata.artist ? {'xesam:artist': new GLib.Variant('as', [metadata.artist])} : {}),
            'xesam:album': new GLib.Variant('s', current.name),
            'xesam:url': new GLib.Variant('s', resolvedUrl || current.url),
        };
    },
    get Rate() { return 1; },
    set Rate(_value) {},
    get Volume() { return volume; },
    set Volume(value) {
        volume = Math.max(0, Math.min(1, value));
        player.setVolume(volume);
        playerExport.emit_property_changed('Volume', new GLib.Variant('d', volume));
    },
    get Position() { return 0; },
    MinimumRate: 1,
    MaximumRate: 1,
    CanGoNext: false,
    CanGoPrevious: false,
    get CanPlay() { return Boolean(station()); },
    get CanPause() { return Boolean(station()); },
    CanSeek: false,
    CanControl: true,
    Next() {},
    Previous() {},
    Seek(_offset) {},
    SetPosition(_id, _position) {},
    OpenUri() { throw new Error('Add custom streams through the station menu.'); },
    Pause: pause,
    Play: play,
    PlayPause: app.PlayPause,
    Stop: stop,
};

function wrap(xml, name, object) {
    const info = Gio.DBusNodeInfo.new_for_xml(xml).lookup_interface(name);
    for (const method of info.methods) {
        const handler = object[method.name];
        object[method.name] = (...args) => {
            try {
                return handler.apply(object, args);
            } catch (error) {
                // Expected validation errors belong to the caller, not the Shell log.
                throw new GLib.Error(Gio.DBusError, Gio.DBusError.INVALID_ARGS, error.message);
            }
        };
    }
    return Gio.DBusExportedObject.wrapJSObject(info, object);
}
const owner = Gio.bus_own_name(Gio.BusType.SESSION, BUS, Gio.BusNameOwnerFlags.DO_NOT_QUEUE,
    connection => {
        appExport = wrap(read('radio.xml'), 'org.gnome.Radio1', app);
        appExport.export(connection, APP_PATH);
        const xml = read('mpris.xml');
        playerExport = wrap(xml, 'org.mpris.MediaPlayer2.Player', mpris);
        playerExport.export(connection, MPRIS_PATH);
        rootExport = wrap(xml, 'org.mpris.MediaPlayer2', {
            Identity: 'radiolina', CanQuit: true, CanRaise: true, HasTrackList: false,
            SupportedUriSchemes: [], SupportedMimeTypes: [],
            Raise() { appExport.emit_signal('Raise', null); }, Quit: app.Quit,
        });
        rootExport.export(connection, MPRIS_PATH);
        refreshFavicons();
    }, null, () => loop.quit());
const signals = [2, 15].map(signal => GLibUnix.signal_add_full(GLib.PRIORITY_DEFAULT, signal, () => {
    loop.quit();
    return GLib.SOURCE_CONTINUE;
}));
const parentName = ARGV.find(arg => arg.startsWith('--owner='))?.slice(8);
const parentWatch = parentName ? Gio.bus_watch_name_on_connection(Gio.DBus.session,
    parentName, Gio.BusNameWatcherFlags.NONE, null, () => loop.quit()) : null;
try {
    loop.run();
} finally {
    signals.forEach(id => GLib.source_remove(id));
    loadGeneration++;
    loadCancellable?.cancel();
    faviconCancellable?.cancel();
    if (parentWatch !== null)
        Gio.bus_unwatch_name(parentWatch);
    player.stop();
    [appExport, playerExport, rootExport].forEach(object => object?.unexport());
    Gio.bus_unown_name(owner);
}
