// SPDX-License-Identifier: MIT
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Soup from 'gi://Soup?version=3.0';
import {validateUrl} from '../core/stations.js';
import {MAX_PLAYLIST_BYTES, playlistKind, parsePlaylist} from '../core/playlists.js';

export async function resolveStream(sourceUrl, cancellable) {
    const session = new Soup.Session({timeout: 10, user_agent: 'GNOME Radio'});
    let timeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 15000, () => {
        timeout = null;
        cancellable.cancel();
        return GLib.SOURCE_REMOVE;
    });
    const seen = new Set();
    let url = sourceUrl;
    let depth = 0;
    let redirects = 0;
    try {
        while (true) {
            if (seen.has(url)) throw new Error('Playlist contains a circular stream reference.');
            seen.add(url);
            const message = Soup.Message.new('GET', validateUrl(url));
            message.set_flags(Soup.MessageFlags.NO_REDIRECT);
            const input = await new Promise((resolve, reject) => session.send_async(message,
                GLib.PRIORITY_DEFAULT, cancellable, (object, result) => {
                    try { resolve(object.send_finish(result)); } catch (error) { reject(error); }
                }));
            try {
                const code = message.status_code;
                if ([301, 302, 303, 307, 308].includes(code)) {
                    if (++redirects > 5) throw new Error('Too many playlist redirects.');
                    const location = message.response_headers.get_one('Location');
                    if (!location) throw new Error('Playlist redirect has no destination.');
                    url = validateUrl(GLib.Uri.resolve_relative(url, location, 0));
                    continue;
                }
                if (code < 200 || code >= 300) throw new Error(`Stream source returned HTTP ${code}. Check the URL.`);
                const kind = playlistKind(url, message.response_headers.get_one('Content-Type') ?? '');
                if (!kind) return url;
                if (++depth > 3) throw new Error('Playlists are nested too deeply.');
                const chunks = [];
                let length = 0;
                while (true) {
                    const bytes = await new Promise((resolve, reject) => input.read_bytes_async(8192,
                        GLib.PRIORITY_DEFAULT, cancellable, (object, result) => {
                            try { resolve(object.read_bytes_finish(result).get_data()); }
                            catch (error) { reject(error); }
                        }));
                    if (!bytes.length) break;
                    length += bytes.length;
                    if (length > MAX_PLAYLIST_BYTES) throw new Error('Playlist is too large (maximum 256 KiB).');
                    chunks.push(bytes);
                }
                const data = new Uint8Array(length);
                let offset = 0;
                for (const chunk of chunks) { data.set(chunk, offset); offset += chunk.length; }
                url = parsePlaylist(new TextDecoder('utf-8', {fatal: true}).decode(data), kind, url);
            } finally {
                input.close(null);
            }
        }
    } catch (error) {
        if (error.matches?.(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED))
            throw new Error('Stream source loading was cancelled or timed out.');
        throw error;
    } finally {
        if (timeout) GLib.source_remove(timeout);
        session.abort();
    }
}
