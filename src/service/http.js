// SPDX-License-Identifier: MIT
import {UserError} from '../core/errors.js';
import GLib from 'gi://GLib';
import Soup from 'gi://Soup?version=3.0';
import {validateUrl, validateRedirect, MAX_REDIRECTS, REDIRECT_CODES} from '../core/validation/urls.js';

export class HttpSession {
    constructor(cancellable, maxRedirects = MAX_REDIRECTS) {
        this.cancellable = cancellable;
        this.session = new Soup.Session({timeout: 15, user_agent: 'radiolina'});
        this.redirects = 0;
        this.maxRedirects = maxRedirects;
        this.seen = new Set();
    }

    async open(sourceUrl) {
        let url = validateUrl(sourceUrl);
        while (true) {
            if (this.seen.has(url)) throw new UserError('Stream source contains a circular reference.');
            this.seen.add(url);
            const message = Soup.Message.new('GET', url);
            message.set_flags(Soup.MessageFlags.NO_REDIRECT);
            message.request_headers.append('Icy-MetaData', '1');
            const input = await new Promise((resolve, reject) => this.session.send_async(message,
                GLib.PRIORITY_DEFAULT, this.cancellable, (object, result) => {
                    try { resolve(object.send_finish(result)); } catch (error) { reject(error); }
                }));
            if (REDIRECT_CODES.has(message.status_code)) {
                try {
                    if (++this.redirects > this.maxRedirects) throw new UserError('Too many stream redirects (maximum five).');
                    url = validateRedirect(url, message.response_headers.get_one('Location'));
                } finally { await closeInput(input, this.cancellable); }
                continue;
            }
            if (message.status_code < 200 || message.status_code >= 300) {
                await closeInput(input, this.cancellable);
                throw new UserError(`Stream source returned HTTP ${message.status_code}. Check the URL.`);
            }
            return {input, url, headers: message.response_headers};
        }
    }

    abort() { this.session.abort(); }
}

function closeInput(input, cancellable) {
    return new Promise(resolve => input.close_async(GLib.PRIORITY_DEFAULT, cancellable, (object, result) => {
        try { object.close_finish(result); } catch { /* Session abort/cancellation also closes the response. */ }
        resolve();
    }));
}

export function readBytes(input, count, cancellable) {
    return new Promise((resolve, reject) => input.read_bytes_async(count,
        GLib.PRIORITY_DEFAULT, cancellable, (object, result) => {
            try { resolve(object.read_bytes_finish(result).get_data()); } catch (error) { reject(error); }
        }));
}

export async function readBounded(input, maximum, cancellable) {
    const chunks = [];
    let length = 0;
    while (true) {
        const chunk = await readBytes(input, Math.min(8192, maximum + 1 - length), cancellable);
        if (!chunk.length) break;
        length += chunk.length;
        if (length > maximum) throw new UserError('Playlist is too large (maximum 256 KiB).');
        chunks.push(chunk);
    }
    const data = new Uint8Array(length);
    let offset = 0;
    for (const chunk of chunks) { data.set(chunk, offset); offset += chunk.length; }
    return data;
}
