// SPDX-License-Identifier: MIT
import GLib from 'gi://GLib';
import {validateUrl} from './stations.js';

export const MAX_PLAYLIST_BYTES = 256 * 1024;
export function playlistKind(url, type = '') {
    const path = GLib.Uri.parse(url, 0).get_path().toLowerCase();
    type = type.split(';')[0].trim().toLowerCase();
    if (path.endsWith('.xspf') || type === 'application/xspf+xml') return 'xspf';
    if (/\.m3u8?$/.test(path) || ['audio/x-mpegurl', 'audio/mpegurl',
        'application/x-mpegurl', 'application/vnd.apple.mpegurl'].includes(type)) return 'm3u';
    return '';
}
export function isDirectAudioUrl(url) {
    return /\.(mp3|ogg|opus|aac|flac|wav|m4a)$/i.test(GLib.Uri.parse(url, 0).get_path());
}
function decodeXml(text) {
    const entities = {amp: '&', lt: '<', gt: '>', quot: '"', apos: "'"};
    return text.replace(/&([^;\s]+);|&/g, (_match, name) => {
        if (Object.hasOwn(entities, name)) return entities[name];
        if (/^#(?:[0-9]+|x[0-9a-f]+)$/i.test(name ?? '')) {
            const value = name[1].toLowerCase() === 'x' ? parseInt(name.slice(2), 16) : Number(name.slice(1));
            if (value > 0 && value <= 0x10ffff && !(value >= 0xd800 && value <= 0xdfff))
                return String.fromCodePoint(value);
        }
        throw new Error('Invalid XML entity in XSPF playlist.');
    });
}
// Bounded XSPF reader with nesting, namespaces, xml:base and CDATA support.
// DTDs and external entities are deliberately never evaluated.
function xspfLocations(text, baseUrl) {
    const tokens = /<!--[\s\S]*?-->|<\?[\s\S]*?\?>|<!\[CDATA\[[\s\S]*?\]\]>|<\/[A-Za-z_][\w:.-]*\s*>|<[A-Za-z_][\w:.-]*(?:\s+[A-Za-z_][\w:.-]*\s*=\s*(?:"[^"<]*"|'[^'<]*'))*\s*\/?>|[^<]+/gy;
    const stack = [];
    const locations = [];
    const local = name => name.split(':').at(-1);
    let root = false;
    let offset = 0;
    while (offset < text.length) {
        tokens.lastIndex = offset;
        const match = tokens.exec(text);
        if (!match) throw new Error('Malformed XSPF playlist; declarations are unsupported.');
        const token = match[0];
        offset = tokens.lastIndex;
        if (token.startsWith('<!--') || token.startsWith('<?')) continue;
        if (token.startsWith('<![CDATA[')) {
            if (!stack.length) throw new Error('Invalid XSPF document.');
            if (stack.at(-1).isLocation) stack.at(-1).text += token.slice(9, -3);
        } else if (!token.startsWith('<')) {
            const value = decodeXml(token);
            if (!stack.length && value.trim()) throw new Error('Invalid XSPF document.');
            if (stack.at(-1)?.isLocation) stack.at(-1).text += value;
        } else if (token.startsWith('</')) {
            const node = stack.pop();
            if (!node || node.name !== token.slice(2, -1).trim()) throw new Error('Mismatched XSPF tags.');
            if (node.isLocation) locations.push([node.text.trim(), node.base]);
        } else {
            const name = token.match(/^<([\w:.-]+)/)[1];
            const attrs = {};
            for (const attr of token.matchAll(/\s+([\w:.-]+)\s*=\s*("[^"]*"|'[^']*')/g)) {
                if (Object.hasOwn(attrs, attr[1])) throw new Error('Duplicate XSPF attribute.');
                attrs[attr[1]] = decodeXml(attr[2].slice(1, -1));
            }
            const namespaces = {...stack.at(-1)?.namespaces};
            for (const [key, value] of Object.entries(attrs)) {
                if (key === 'xmlns') namespaces[''] = value;
                else if (key.startsWith('xmlns:')) namespaces[key.slice(6)] = value;
            }
            const ns = namespaces[name.includes(':') ? name.split(':')[0] : ''];
            if (!stack.length) {
                if (root || local(name) !== 'playlist' || ns !== 'http://xspf.org/ns/0/')
                    throw new Error('Expected an XSPF playlist.');
                root = true;
            }
            if (stack.length >= 64) throw new Error('XSPF playlist is nested too deeply.');
            const parentBase = stack.at(-1)?.base ?? baseUrl;
            const base = attrs['xml:base'] ? GLib.Uri.resolve_relative(parentBase, attrs['xml:base'], 0) : parentBase;
            const node = {name, namespaces, base, text: '', isLocation: ns === 'http://xspf.org/ns/0/' &&
                local(name) === 'location' && local(stack.at(-1)?.name ?? '') === 'track' &&
                local(stack.at(-2)?.name ?? '') === 'trackList'};
            if (!/\/\s*>$/.test(token)) stack.push(node);
        }
    }
    if (!root || stack.length) throw new Error('Incomplete XSPF playlist.');
    return locations;
}
export function parsePlaylist(text, kind, baseUrl) {
    if (new TextEncoder().encode(text).length > MAX_PLAYLIST_BYTES)
        throw new Error('Playlist is too large (maximum 256 KiB).');
    text = text.replace(/^\uFEFF/, '');
    let candidates;
    if (kind === 'm3u') {
        if (/^#EXT-X-/m.test(text)) throw new Error('HLS playlists are unsupported. Use an ordinary radio M3U.');
        candidates = text.split(/\r?\n/).map(line => line.trim()).filter(line => line && !line.startsWith('#'))
            .map(url => [url, baseUrl]);
    } else {
        candidates = xspfLocations(text, baseUrl);
    }
    for (const [url, base] of candidates) {
        try {
            if (url) return validateUrl(GLib.Uri.resolve_relative(base, url, 0));
        } catch { /* Skip invalid and non-HTTP entries. */ }
    }
    throw new Error('Playlist has no usable HTTP or HTTPS stream URL.');
}
