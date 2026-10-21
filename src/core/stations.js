// SPDX-License-Identifier: MIT
import {validateUrl} from './validation/urls.js';
export {validateUrl} from './validation/urls.js';

export const DEFAULT_RECENT_LIMIT = 3;
export const MAX_RECENT_LIMIT = 10;

export function validateRecentLimit(value) {
    if (!Number.isInteger(value) || value < 1 || value > MAX_RECENT_LIMIT)
        throw new Error(`Recent stations must be between 1 and ${MAX_RECENT_LIMIT}.`);
    return value;
}

export function cleanText(value, limit = 256) {
    return String(value ?? '').replace(/[\x00-\x1f\x7f]/g, ' ').trim().slice(0, limit);
}

export function validateConfig(config) {
    if (config?.version !== 1 || !Array.isArray(config.stations) ||
        config.stations.length > 200 || typeof config.notifications !== 'boolean')
        throw new Error('Invalid station configuration.');
    const ids = new Set();
    const urls = new Set();
    for (const station of config.stations) {
        if (!station || typeof station.id !== 'string' ||
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
    return {...config, recent, recentLimit, fetchFavicons: config.fetchFavicons ?? false,
        showStopButton: config.showStopButton ?? false,
        playButtonOnLeft: config.playButtonOnLeft ?? false,
        groupWithAppIndicators: config.groupWithAppIndicators ?? false};
}

export function emptyConfig() {
    return {version: 1, stations: [], selected: '', notifications: false, recent: [],
        recentLimit: DEFAULT_RECENT_LIMIT, fetchFavicons: false, playButtonOnLeft: false,
        groupWithAppIndicators: false, showStopButton: false};
}

export class MetadataTracker {
    constructor() {
        this.reset();
    }

    reset() {
        this.title = '';
        this.artist = '';
        this.rawTitle = '';
        this.rawArtist = '';
        this.lastTitle = '';
        this.sequence = (this.sequence ?? 0) + 1;
    }

    update(value, artistValue) {
        if (value !== undefined) {
            const rawTitle = cleanText(value);
            if (rawTitle !== this.rawTitle && this.rawTitle) this.rawArtist = '';
            this.rawTitle = rawTitle;
        }
        if (artistValue !== undefined) this.rawArtist = cleanText(artistValue);
        let title = this.rawTitle;
        let artist = title ? this.rawArtist : '';
        // Many ICY streams expose both fields as a conventional "Artist - Title".
        const combined = title.match(/^(.+?)\s+[-–—]\s+(.+)$/u);
        if (combined && (!artist || artist === combined[1].trim())) {
            artist ||= combined[1].trim();
            title = combined[2].trim();
        }
        if (title === this.title && artist === this.artist)
            return {changed: false, notify: false};
        this.artist = artist;
        this.title = title;
        if (!title)
            return {changed: true, notify: false};
        const notify = Boolean(this.lastTitle && title !== this.lastTitle);
        if (title !== this.lastTitle)
            this.sequence++;
        this.lastTitle = title;
        return {changed: true, notify};
    }
}
