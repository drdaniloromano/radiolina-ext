// SPDX-License-Identifier: MIT
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Soup from 'gi://Soup?version=3.0';
import {validateUrl} from '../core/stations.js';
import {validFavicon, MAX_FAVICON_BYTES} from '../core/favicons.js';

export function faviconUrl(source) {
    return validateUrl(GLib.Uri.resolve_relative(validateUrl(source), '/favicon.ico', 0));
}

export async function fetchFavicon(url, cancellable) {
    const directory = GLib.build_filenamev([GLib.get_user_cache_dir(), 'gnome-radio', 'favicons']);
    const key = GLib.compute_checksum_for_string(GLib.ChecksumType.SHA256, url, -1);
    const file = Gio.File.new_for_path(GLib.build_filenamev([directory, `${key}.ico`]));
    try {
        const size = file.query_info('standard::size', 0, null).get_size();
        if (size <= MAX_FAVICON_BYTES && validFavicon(file.load_contents(null)[1])) return file.get_uri();
    } catch { /* A missing or invalid cache entry is fetched again. */ }
    const session = new Soup.Session({timeout: 5, user_agent: 'GNOME Radio'});
    let timeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 5000, () => {
        timeout = null;
        session.abort();
        return GLib.SOURCE_REMOVE;
    });
    try {
        for (let redirects = 0; redirects <= 3; redirects++) {
            const message = Soup.Message.new('GET', validateUrl(url));
            message.set_flags(Soup.MessageFlags.NO_REDIRECT);
            const input = await new Promise((resolve, reject) => session.send_async(message,
                GLib.PRIORITY_DEFAULT, cancellable, (object, result) => {
                    try { resolve(object.send_finish(result)); } catch (error) { reject(error); }
                }));
            try {
                if ([301, 302, 303, 307, 308].includes(message.status_code)) {
                    const target = message.response_headers.get_one('Location');
                    if (!target) return null;
                    url = validateUrl(GLib.Uri.resolve_relative(url, target, 0));
                    continue;
                }
                if (message.status_code !== 200 || message.response_headers.get_content_length() > MAX_FAVICON_BYTES)
                    return null;
                const chunks = [];
                let length = 0;
                while (true) {
                    const bytes = await new Promise((resolve, reject) => input.read_bytes_async(4096,
                        GLib.PRIORITY_DEFAULT, cancellable, (object, result) => {
                            try { resolve(object.read_bytes_finish(result).get_data()); } catch (error) { reject(error); }
                        }));
                    if (!bytes.length) break;
                    length += bytes.length;
                    if (length > MAX_FAVICON_BYTES) return null;
                    chunks.push(bytes);
                }
                const data = new Uint8Array(length);
                let offset = 0;
                for (const chunk of chunks) { data.set(chunk, offset); offset += chunk.length; }
                if (!validFavicon(data) || cancellable.is_cancelled()) return null;
                GLib.mkdir_with_parents(directory, 0o700);
                file.replace_contents(data, null, false, Gio.FileCreateFlags.PRIVATE | Gio.FileCreateFlags.REPLACE_DESTINATION, null);
                return file.get_uri();
            } finally { input.close(null); }
        }
    } catch { /* Optional icons never interrupt playback or station management. */ }
    finally {
        if (timeout) GLib.source_remove(timeout);
        session.abort();
    }
    return null;
}
