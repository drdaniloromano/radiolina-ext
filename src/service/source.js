// SPDX-License-Identifier: MIT
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {HttpSession, readBounded} from './http.js';
import {MAX_PLAYLIST_BYTES, playlistKind, parsePlaylist} from '../core/playlists.js';
import {inspectMedia, MAX_PROBE_BYTES, validateIcyInterval} from '../core/validation/media.js';
import {validateRedirect} from '../core/validation/urls.js';

// Own the validated response through playback. Never reopen its URL in a decoder.
export async function openStream(sourceUrl, cancellable) {
    const http = new HttpSession(cancellable);
    let timeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 15000, () => {
        timeout = null;
        cancellable.cancel();
        return GLib.SOURCE_REMOVE;
    });
    let input;
    let handedOff = false;
    let url = sourceUrl;
    let depth = 0;
    try {
        while (true) {
            const response = await http.open(url);
            input = Gio.BufferedInputStream.new_sized(response.input, MAX_PROBE_BYTES);
            const icyInterval = validateIcyInterval(response.headers.get_one('icy-metaint'));
            const hint = playlistKind(response.url, response.headers.get_one('Content-Type') ?? '');
            let media;
            while (!media) {
                const available = input.get_available();
                const count = await new Promise((resolve, reject) => input.fill_async(
                    Math.min(8192, MAX_PROBE_BYTES - available), GLib.PRIORITY_DEFAULT, cancellable,
                    (object, result) => {
                        try { resolve(object.fill_finish(result)); } catch (error) { reject(error); }
                    }));
                media = inspectMedia(input.peek_buffer(), {icyInterval, playlistHint: hint, final: count === 0});
                if (!media && (!count || input.get_available() >= MAX_PROBE_BYTES))
                    throw new Error('Stream audio headers exceed the 64 KiB identification limit or are incomplete.');
            }
            if (media.kind === 'playlist') {
                if (icyInterval) throw new Error('A playlist cannot contain interleaved radio metadata.');
                if (++depth > 3) throw new Error('Playlists are nested too deeply.');
                const data = await readBounded(input, MAX_PLAYLIST_BYTES, cancellable);
                input.close(null); input = null;
                url = parsePlaylist(new TextDecoder('utf-8', {fatal: true}).decode(data), media.format, response.url);
                // Playlist entries obey the same transport/downgrade policy as redirects.
                url = validateRedirect(response.url, url);
                continue;
            }
            handedOff = true;
            let closed = false;
            let aborted = false;
            const stream = input;
            const abort = () => {
                if (aborted) return;
                aborted = true;
                cancellable.cancel();
                http.abort();
            };
            return {url: response.url, input: stream, media, icyInterval, abort,
                close() {
                    if (closed) return;
                    closed = true;
                    abort();
                    try { stream.close(null); } catch { /* Native source may already have closed it. */ }
                }};
        }
    } catch (error) {
        if (error.matches?.(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED))
            throw new Error('Stream source loading was cancelled or timed out.');
        throw error;
    } finally {
        if (timeout) GLib.source_remove(timeout);
        if (!handedOff) {
            http.abort();
            try { input?.close(null); } catch { /* Cancelled input is already closed. */ }
        }
    }
}
