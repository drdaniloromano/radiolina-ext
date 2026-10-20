// SPDX-License-Identifier: MIT
// GNOME 49 Looking Glass update helper. Uses a new content-addressed UI module
// instead of attempting to unload cached JavaScript or changing other settings.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {ExtensionState} from 'resource:///org/gnome/shell/misc/extensionUtils.js';

const UUID = 'radiolina@drdaniloromano.github.io';
const BUS = 'org.mpris.MediaPlayer2.GnomeRadio';
async function stopService() {
    await new Promise((resolve, reject) => {
        let watch;
        let timeout;
        let settled = false;
        const finish = error => {
            if (settled) return;
            settled = true;
            if (watch) Gio.bus_unwatch_name(watch);
            if (timeout) GLib.source_remove(timeout);
            if (error) reject(error); else resolve();
        };
        watch = Gio.bus_watch_name_on_connection(Gio.DBus.session, BUS,
            Gio.BusNameWatcherFlags.NONE, null, () => finish());
        timeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 5000, () => {
            timeout = null;
            finish(new Error('The old radio service did not stop.'));
            return GLib.SOURCE_REMOVE;
        });
        Gio.DBus.session.call(BUS, '/org/gnome/Radio', 'org.gnome.Radio1', 'Quit', null,
            null, Gio.DBusCallFlags.NO_AUTO_START, 3000, null, (connection, result) => {
                try { connection.call_finish(result); }
                catch (error) {
                    if (!error.matches(Gio.DBusError, Gio.DBusError.SERVICE_UNKNOWN) &&
                        !error.matches(Gio.DBusError, Gio.DBusError.NAME_HAS_NO_OWNER)) finish(error);
                }
            });
    });
}

export async function update(Main) {
    const manager = Main.extensionManager;
    const directory = Gio.File.new_for_path(GLib.build_filenamev([
        GLib.get_user_data_dir(), 'gnome-shell', 'extensions', UUID,
    ]));
    const metadata = JSON.parse(new TextDecoder().decode(directory.get_child('metadata.json').load_contents(null)[1]));
    const runtime = metadata['radio-runtime'];
    if (!/^radio-[0-9a-f]{12}\.js$/.test(runtime ?? ''))
        throw new Error('Install the newly built ZIP before updating.');
    const module = await import(directory.get_child(runtime).get_uri());
    const previous = manager.lookup(UUID);
    previous?.stateObj?.disable();
    Main.panel.statusArea[UUID]?.destroy();
    await stopService();
    if (previous) await manager.unloadExtension(previous);
    manager._extensionOrder = manager._extensionOrder.filter(uuid => uuid !== UUID);
    manager._unloadedExtensions.delete(UUID);
    const extension = manager.createExtensionObject(UUID, directory, 2);
    extension.stateObj = new module.default({...extension.metadata, dir: directory, path: directory.get_path()});
    extension.isImported = true;
    extension.state = ExtensionState.INACTIVE;
    manager.enableExtension(UUID);
    await manager._callExtensionEnable(UUID);
    manager._updateCanChange(extension);
    if (extension.error) throw new Error(extension.error);
    return 'radiolina updated. Close Looking Glass with Esc.';
}
