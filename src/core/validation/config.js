// SPDX-License-Identifier: MIT
import {validateUrl} from './urls.js';
import {cleanText} from './text.js';

export const DEFAULT_RECENT_LIMIT = 3;
export const MAX_RECENT_LIMIT = 10;
export const MAX_CONFIG_BYTES = 1024 * 1024;
export const MAX_STATION_ID_LENGTH = 128;

const CONFIG_FIELDS = new Set(['version', 'stations', 'selected', 'notifications',
    'recent', 'recentLimit', 'fetchFavicons', 'showStopButton', 'playButtonOnLeft',
    'groupWithAppIndicators']);
const STATION_FIELDS = new Set(['id', 'name', 'url']);

function validateFields(value, fields) {
    if (!value || typeof value !== 'object' || Array.isArray(value))
        throw new Error('Invalid configuration object.');
    if (Object.keys(value).some(key => !fields.has(key)))
        throw new Error('Unknown configuration fields; keep only documented settings and station fields.');
}

export function validateRecentLimit(value) {
    if (!Number.isInteger(value) || value < 1 || value > MAX_RECENT_LIMIT)
        throw new Error(`Recent stations must be between 1 and ${MAX_RECENT_LIMIT}.`);
    return value;
}

export function validateConfig(config) {
    validateFields(config, CONFIG_FIELDS);
    if (config.version !== 1 || !Array.isArray(config.stations) ||
        config.stations.length > 200 || typeof config.notifications !== 'boolean')
        throw new Error('Invalid station configuration.');
    const ids = new Set();
    const urls = new Set();
    for (const station of config.stations) {
        validateFields(station, STATION_FIELDS);
        if (typeof station.id !== 'string' || station.id.length > MAX_STATION_ID_LENGTH ||
            !/^[a-zA-Z0-9_-]+$/.test(station.id) || ids.has(station.id) ||
            !station.name || station.name !== cleanText(station.name, 80) ||
            station.url !== validateUrl(station.url) || urls.has(station.url))
            throw new Error('Invalid or duplicate saved station.');
        ids.add(station.id);
        urls.add(station.url);
    }
    if (config.selected !== '' && !ids.has(config.selected))
        throw new Error('Selected station is missing.');
    const recent = config.recent ?? [];
    if (!Array.isArray(recent) || recent.length > MAX_RECENT_LIMIT || new Set(recent).size !== recent.length ||
        recent.some(id => !ids.has(id)) ||
        (config.fetchFavicons !== undefined && typeof config.fetchFavicons !== 'boolean') ||
        (config.showStopButton !== undefined && typeof config.showStopButton !== 'boolean') ||
        (config.playButtonOnLeft !== undefined && typeof config.playButtonOnLeft !== 'boolean') ||
        (config.groupWithAppIndicators !== undefined && typeof config.groupWithAppIndicators !== 'boolean'))
        throw new Error('Invalid recent stations or display settings.');
    const recentLimit = validateRecentLimit(config.recentLimit === undefined ? DEFAULT_RECENT_LIMIT : config.recentLimit);
    return {version: 1, stations: config.stations.map(({id, name, url}) => ({id, name, url})),
        selected: config.selected, notifications: config.notifications,
        recent: [...recent], recentLimit, fetchFavicons: config.fetchFavicons ?? false,
        showStopButton: config.showStopButton ?? false,
        playButtonOnLeft: config.playButtonOnLeft ?? false,
        groupWithAppIndicators: config.groupWithAppIndicators ?? false};
}

export function emptyConfig() {
    return {version: 1, stations: [], selected: '', notifications: false, recent: [],
        recentLimit: DEFAULT_RECENT_LIMIT, fetchFavicons: false, playButtonOnLeft: false,
        groupWithAppIndicators: false, showStopButton: false};
}
