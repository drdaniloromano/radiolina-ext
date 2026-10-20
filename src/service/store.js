// SPDX-License-Identifier: MIT
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {emptyConfig, validateConfig} from '../core/stations.js';

export class Store {
    constructor(directory = GLib.build_filenamev([GLib.get_user_config_dir(), 'gnome-radio'])) {
        this.directory = directory;
        this.file = Gio.File.new_for_path(GLib.build_filenamev([directory, 'stations.json']));
    }

    load() {
        try {
            const [, bytes] = this.file.load_contents(null);
            return validateConfig(JSON.parse(new TextDecoder().decode(bytes)));
        } catch (error) {
            if (error.matches?.(Gio.IOErrorEnum, Gio.IOErrorEnum.NOT_FOUND))
                return emptyConfig();
            throw new Error('Saved stations could not be read. Back up and repair stations.json.');
        }
    }

    save(config) {
        validateConfig(config);
        GLib.mkdir_with_parents(this.directory, 0o700);
        this.file.replace_contents(JSON.stringify(config, null, 2), null, false,
            Gio.FileCreateFlags.PRIVATE | Gio.FileCreateFlags.REPLACE_DESTINATION, null);
    }
}
