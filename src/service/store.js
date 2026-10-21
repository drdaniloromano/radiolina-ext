// SPDX-License-Identifier: MIT
import {UserError, publicErrorMessage} from '../core/errors.js';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {emptyConfig, validateConfig, MAX_CONFIG_BYTES} from '../core/validation/config.js';

function readConfig(file) {
    const input = file.read(null);
    try {
        const chunks = [];
        let length = 0;
        while (true) {
            // Probe one byte past the limit, including if the file grows during reading.
            const bytes = input.read_bytes(Math.min(16384, MAX_CONFIG_BYTES + 1 - length), null).toArray();
            length += bytes.length;
            if (length > MAX_CONFIG_BYTES)
                throw new UserError('Station file exceeds the 1 MiB limit.');
            if (!bytes.length) break;
            chunks.push(bytes);
        }
        const result = new Uint8Array(length);
        let offset = 0;
        for (const chunk of chunks) {
            result.set(chunk, offset);
            offset += chunk.length;
        }
        return new TextDecoder('utf-8', {fatal: true}).decode(result);
    } finally {
        input.close(null);
    }
}

export class Store {
    constructor(directory = GLib.build_filenamev([GLib.get_user_config_dir(), 'gnome-radio'])) {
        this.directory = directory;
        this.file = Gio.File.new_for_path(GLib.build_filenamev([directory, 'stations.json']));
    }

    load() {
        try {
            return validateConfig(JSON.parse(readConfig(this.file)));
        } catch (error) {
            if (error.matches?.(Gio.IOErrorEnum, Gio.IOErrorEnum.NOT_FOUND))
                return emptyConfig();
            const detail = error instanceof SyntaxError || error instanceof TypeError ?
                'Invalid JSON or UTF-8.' : error instanceof GLib.Error ? 'File read failed.' : publicErrorMessage(error, 'Invalid station configuration.');
            throw new UserError(`Saved stations could not be read. ${detail} Back up and repair stations.json, then restart radiolina.`);
        }
    }

    save(config) {
        const bytes = new TextEncoder().encode(JSON.stringify(validateConfig(config), null, 2));
        if (bytes.length > MAX_CONFIG_BYTES)
            throw new UserError('Station file exceeds the 1 MiB limit.');
        GLib.mkdir_with_parents(this.directory, 0o700);
        this.file.replace_contents(bytes, null, false,
            Gio.FileCreateFlags.PRIVATE | Gio.FileCreateFlags.REPLACE_DESTINATION, null);
    }
}
