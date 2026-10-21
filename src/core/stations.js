// SPDX-License-Identifier: MIT
import {cleanText} from './validation/text.js';
export {cleanText} from './validation/text.js';
export {validateUrl} from './validation/urls.js';
export {validateConfig, emptyConfig, validateRecentLimit, DEFAULT_RECENT_LIMIT, MAX_RECENT_LIMIT} from './validation/config.js';

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
