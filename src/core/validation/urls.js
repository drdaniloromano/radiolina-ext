// SPDX-License-Identifier: MIT
import {UserError} from '../errors.js';
import GLib from 'gi://GLib';

export const MAX_REDIRECTS = 5;
export const REDIRECT_CODES = new Set([301, 302, 303, 307, 308]);

export function validateUrl(value) {
    const url = String(value ?? '').trim();
    if (!url || url.length > 2048 || /[\s\x00-\x1f\x7f]/.test(url))
        throw new UserError('Enter a valid HTTP or HTTPS stream URL.');
    let uri;
    try { uri = GLib.Uri.parse(url, GLib.UriFlags.NONE); }
    catch { throw new UserError('Enter a valid HTTP or HTTPS stream URL.'); }
    if (!['http', 'https'].includes(uri.get_scheme()?.toLowerCase()) ||
        !uri.get_host() || uri.get_userinfo() !== null || uri.get_fragment() !== null)
        throw new UserError('Use an HTTP or HTTPS stream URL without credentials or fragments.');
    return uri.to_string();
}

export function validateRedirect(from, location) {
    if (!location) throw new UserError('Stream redirect has no destination.');
    if (typeof location !== 'string' || location.length > 2048 || /[\s\x00-\x1f\x7f]/.test(location))
        throw new UserError('Invalid stream redirect destination.');
    const target = validateUrl(GLib.Uri.resolve_relative(validateUrl(from), location, 0));
    if (GLib.Uri.parse(from, 0).get_scheme().toLowerCase() === 'https' &&
        GLib.Uri.parse(target, 0).get_scheme().toLowerCase() !== 'https')
        throw new UserError('An HTTPS stream cannot redirect to unencrypted HTTP.');
    return target;
}
