// SPDX-License-Identifier: MIT
// Run from GNOME 49 Looking Glass; never enables remote evaluator access.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const UUID = 'radiolina@drdaniloromano.github.io';
const BUS = 'org.mpris.MediaPlayer2.GnomeRadio';

async function stopService() {
    await new Promise((resolve, reject) => {
        let watch;
        let timeout;
        let settled = false;
        const finish = error => {
            if (settled)
                return;
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
                try {
                    connection.call_finish(result);
                } catch (error) {
                    if (!error.matches(Gio.DBusError, Gio.DBusError.SERVICE_UNKNOWN) &&
                        !error.matches(Gio.DBusError, Gio.DBusError.NAME_HAS_NO_OWNER))
                        finish(error);
                }
            });
    });
}

export async function recover(Main) {
    const manager = Main.extensionManager;
    const previous = manager.lookup(UUID);
    previous?.stateObj?.disable();
    Main.panel.statusArea[UUID]?.destroy(); // Also release orphaned duplicate actors.
    await stopService();
    if (previous)
        await manager.unloadExtension(previous);
    // ERROR-state unloading skips GNOME's normal order cleanup. A stale UUID
    // there would make the next disable re-enable the same indicator again.
    manager._extensionOrder = manager._extensionOrder.filter(uuid => uuid !== UUID);
    const directory = Gio.File.new_for_path(GLib.build_filenamev([
        GLib.get_user_data_dir(), 'gnome-shell', 'extensions', UUID,
    ]));
    const extension = manager.createExtensionObject(UUID, directory, 2);
    await manager.loadExtension(extension);
    manager.enableExtension(UUID);
    // Already imported modules are cached until a new Shell session. Repair the
    // old module's icon too, so recovery works immediately after updating files.
    const indicator = Main.panel.statusArea[UUID];
    if (indicator) {
        const iconName = indicator._state?.status === 'Playing' ? 'radio-active-symbolic.svg' : 'radio-symbolic.svg';
        const radio = directory.get_child('icons').get_child(iconName);
        if (radio.query_exists(null))
            indicator._icon.gicon = new Gio.FileIcon({file: radio});
        else
            indicator._icon.icon_name = 'audio-headphones-symbolic';
        indicator.show();
    }
    if (extension.error)
        throw new Error(extension.error);
    return 'radiolina recovered. Close Looking Glass with Esc.';
}
