# SPDX-License-Identifier: MIT
"""Exercise native Shell actors on an isolated, headless GNOME 49 desktop."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import time
import unittest

from service import BUS, APP, IFACE, ServiceE2E, Streams, Gio, GLib, pump

ROOT = Path(__file__).resolve().parents[2]
UUID = json.loads((ROOT / 'extension/metadata.json').read_text())['uuid']
INDICATOR = f"Main.panel.statusArea['{UUID}']"
PEERS = ['radio-peer-one@test', 'radio-peer-two@test']
GROUP_WARNING = 'Grouping may be incompatible with some extensions or panel customizations. Disable this option if icons, menus, or clicks behave unexpectedly.'


class ShellE2E(unittest.TestCase):
    def test_popup_station_form_artist_no_notifications_and_cleanup(self):
        ServiceE2E.setUpClass()
        self.addCleanup(ServiceE2E.tearDownClass)
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        log = tempfile.TemporaryFile(mode='w+')
        scale = float(os.environ.get('GNOME_RADIO_TEST_SCALE', '1'))
        shell = subprocess.Popen(['gnome-shell', '--headless', '--wayland', '--no-x11',
                                  '--virtual-monitor', f'{round(1024 * scale)}x{round(768 * scale)}'],
                                 stdout=log, stderr=log)
        def cleanup():
            shell.terminate()
            try:
                shell.wait(timeout=10)
            except subprocess.TimeoutExpired:
                shell.kill()
                shell.wait()
            log.seek(0)
            text = log.read()
            Path('workspace/shell-e2e.log').write_text(text)
            log.close()
            self.assertNotIn('has been already disposed', text, 'Popup interactions must not retain destroyed station actors')
        self.addCleanup(cleanup)

        def call(name, path, interface, method, params=None):
            return bus.call_sync(name, path, interface, method, params, None,
                                 Gio.DBusCallFlags.NONE, 3000, None).unpack()

        def wait(predicate, label, timeout=25):
            deadline = time.monotonic() + timeout
            last = None
            while time.monotonic() < deadline:
                pump()
                try:
                    value = predicate()
                    if value:
                        return value
                except (GLib.Error, AssertionError) as error:
                    last = error
                if shell.poll() is not None:
                    break
                time.sleep(0.05)
            log.seek(0)
            ok, diagnostics = call('org.gnome.Shell', '/org/gnome/Shell', 'org.gnome.Shell', 'Eval',
                                   GLib.Variant('(s)', (f'''JSON.stringify({{
                                       updateError: global._radioUpdateError,
                                       extensionError: Main.extensionManager.lookup('{UUID}')?.error,
                                       addLabel: {INDICATOR}?._add?.accessible_name,
                                       owner: {INDICATOR}?._proxy?.g_name_owner,
                                       radioState: {INDICATOR}?._state,
                                       sessionMode: Main.sessionMode.currentMode,
                                       focus: String(global.stage.get_key_focus()),
                                       quitFocused: global.stage.get_key_focus() === {INDICATOR}?._quitButton,
                                       themeVariant: Main.getStyleVariant(),
                                       themeStyle: global._radioSt?.ThemeContext.get_for_stage(global.stage).get_theme().default_stylesheet?.get_uri(),
                                   }})''',)))
            self.fail(f'{label}: {last}; diagnostics: {ok}, {diagnostics}\n{log.read()[-12000:]}')

        def evaluate(source):
            ok, value = call('org.gnome.Shell', '/org/gnome/Shell', 'org.gnome.Shell',
                             'Eval', GLib.Variant('(s)', (source,)))
            self.assertTrue(ok, value)
            return json.loads(value) if value else None

        def standalone_panel():
            return evaluate(f'''Boolean({INDICATOR}?.container.get_parent() === Main.panel._rightBox &&
                {json.dumps(PEERS)}.every(role => !Main.panel.statusArea[role] ||
                    Main.panel.statusArea[role].container.get_parent() === Main.panel._rightBox))''')

        def other_panel_placement():
            return evaluate(f'''(() => {{
                const roles = new Map(Object.entries(Main.panel.statusArea)
                    .map(([role, actor]) => [actor.container, role]));
                // Native containers stay visible even when their indicator is
                // hidden, and Shell can reorder them when rebasing extensions.
                return [Main.panel._leftBox, Main.panel._centerBox, Main.panel._rightBox]
                    .map(box => box.get_children().filter(actor => roles.get(actor) !== '{UUID}' &&
                        (Main.panel.statusArea[roles.get(actor)] ?? actor).visible)
                        .map(actor => roles.get(actor) ?? String(actor)));
            }})()''')

        def assert_separator_spacing():
            self.assertEqual(evaluate(f'{INDICATOR}.menu.actor.width'), popup_width, 'Popup width must stay fixed')
            gaps = evaluate(f'''(() => {{
                const i = {INDICATOR};
                const top = actor => actor.get_transformed_position()[1];
                const bottom = actor => top(actor) + actor.get_transformed_size()[1];
                const info = i._infoFrame;
                const recent = [...i._recentButtons.values()].at(-1).edit;
                return [[info, i._infoSeparator._separator, i._recentHeading],
                    [recent, i._stationsSeparator._separator, i._expandButton],
                    [recent.child, i._stationsSeparator._separator, i._expandButton.child]].map(([above, line, below]) =>
                    [top(line) - bottom(above), top(below) - bottom(line)]);
            }})()''')
            for above, below in gaps:
                self.assertAlmostEqual(above, below, delta=1.1, msg=f'Uneven separator spacing: {gaps}')

        wait(lambda: evaluate('global.context.unsafe_mode'), 'headless Shell test bootstrap')
        wait(lambda: evaluate('Main.layoutManager._startingUp === false'), 'Shell initialized')
        input_setup = """global._radioClutter = (await import('gi://Clutter')).default;
            global._radioSt = (await import('gi://St')).default;
            global._radioPanelMenu = await import('resource:///org/gnome/shell/ui/panelMenu.js');
            global._radioSeat = global._radioClutter.get_default_backend().get_default_seat();
            global._radioKeyboard = global._radioSeat.create_virtual_device(global._radioClutter.InputDeviceType.KEYBOARD_DEVICE);
            global._radioPointer = global._radioSeat.create_virtual_device(global._radioClutter.InputDeviceType.POINTER_DEVICE);"""
        evaluate(f'Main.createLookingGlass()._evaluate({json.dumps(input_setup)}); true')
        wait(lambda: evaluate('Boolean(global._radioKeyboard && global._radioPointer)'), 'isolated virtual input')
        if scale != 1:
            serial, monitors, _logical, _properties = call('org.gnome.Mutter.DisplayConfig',
                '/org/gnome/Mutter/DisplayConfig', 'org.gnome.Mutter.DisplayConfig', 'GetCurrentState')
            connector = monitors[0][0][0]
            mode = next(mode for mode in monitors[0][1] if mode[6].get('is-current'))
            self.assertTrue(any(abs(value - scale) < 0.01 for value in mode[5]), 'Test monitor supports requested scale')
            call('org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig',
                 'org.gnome.Mutter.DisplayConfig', 'ApplyMonitorsConfig',
                 GLib.Variant('(uua(iiduba(ssa{sv}))a{sv})',
                     (serial, 1, [(0, 0, scale, 0, True, [(connector, mode[0], {})])], {})))
            time.sleep(0.3)

        def capture_final():
            try:
                call('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
                     'org.gnome.Shell.Screenshot', 'Screenshot',
                     GLib.Variant('(bbs)', (False, False, str(Path('workspace/shell-final.png').resolve()))))
            except GLib.Error:
                pass
        self.addCleanup(capture_final)

        def key(keyval, control=False):
            if control:
                evaluate('global._radioKeyboard.notify_keyval(GLib.get_monotonic_time(), 0xffe3, global._radioClutter.KeyState.PRESSED); true')
            evaluate(f'''global._radioKeyboard.notify_keyval(GLib.get_monotonic_time(), {keyval}, global._radioClutter.KeyState.PRESSED);
                global._radioKeyboard.notify_keyval(GLib.get_monotonic_time(), {keyval}, global._radioClutter.KeyState.RELEASED); true''')
            if control:
                evaluate('global._radioKeyboard.notify_keyval(GLib.get_monotonic_time(), 0xffe3, global._radioClutter.KeyState.RELEASED); true')
            time.sleep(0.1)

        def pointer(x, y):
            x, y = round(x), round(y)
            def settled():
                actual = evaluate('global.get_pointer().slice(0, 2)')
                if actual == [x, y]:
                    return True
                evaluate(f'global._radioPointer.notify_absolute_motion(GLib.get_monotonic_time(), {x}, {y}); true')
                return False
            wait(settled, 'virtual pointer reaches target', timeout=3)
            time.sleep(0.1)

        def panel_click(actor):
            wait(lambda: evaluate(f'{actor}.mapped && {actor}.has_allocation() && {actor}.width > 0'), 'panel button allocation ready')
            x, y = evaluate(f'''(() => {{const a = {actor}; const [x, y] = a.get_transformed_position();
                const [w, h] = a.get_transformed_size(); return [x + w / 2, y + h / 2];}})()''')
            pointer(x, y)
            evaluate('''global._radioPointer.notify_button(GLib.get_monotonic_time(), 1, global._radioClutter.ButtonState.PRESSED);
                global._radioPointer.notify_button(GLib.get_monotonic_time(), 1, global._radioClutter.ButtonState.RELEASED); true''')

        def click(actor):
            self.assertTrue(evaluate(f'{INDICATOR}.menu.isOpen'), 'Popup must be open before pointer interaction')
            wait(lambda: evaluate(f'''(() => {{const actor = {actor};
                return actor.mapped && actor.has_allocation() && actor.width > 0 && actor.height > 0;
            }})()'''), 'pointer target allocated')
            evaluate(f'''(() => {{const menu = {INDICATOR}.menu;
                global._radioCloseReason = null;
                if (!menu._radioTestClose) {{
                    menu._radioTestClose = menu.close.bind(menu);
                    menu.close = (...args) => {{global._radioCloseReason = new Error().stack; menu._radioTestClose(...args);}};
                }}
            }})(); true''')
            x, y = evaluate(f'''(() => {{const actor = {actor};
                const [x, y] = actor.get_transformed_position();
                return [x + actor.get_transformed_size()[0] / 2, y + actor.get_transformed_size()[1] / 2];}})()''')
            pointer(x, y)
            pointer_debug = evaluate(f'''(() => {{const i = {INDICATOR};
                const picked = global.stage.get_actor_at_pos(global._radioClutter.PickMode.REACTIVE, {x}, {y});
                return {{x: {x}, y: {y}, pointer: global.get_pointer(), picked: String(picked),
                    inside: i.menu.actor.contains(picked), bounds: i.menu.actor.get_transformed_position(),
                    size: [i.menu.actor.width, i.menu.actor.height]}};
            }})()''')
            evaluate('global._radioPointer.notify_button(GLib.get_monotonic_time(), 1, global._radioClutter.ButtonState.PRESSED); true')
            time.sleep(0.05)
            evaluate('global._radioPointer.notify_button(GLib.get_monotonic_time(), 1, global._radioClutter.ButtonState.RELEASED); true')
            time.sleep(0.15)
            self.assertTrue(evaluate(f'{INDICATOR}.menu.isOpen'),
                            f'Clicking {actor} must keep the popup open: {pointer_debug}; ' + str(evaluate('global._radioCloseReason')))
            self.assertTrue(evaluate(f'''[{INDICATOR}._stationContainer,
                {INDICATOR}._settingsSection.actor, {INDICATOR}._form].filter(actor => actor.visible).length <= 1'''),
                'Stations, Settings, and the form must replace one another')

        def toolbar_geometry():
            return evaluate(f'''(() => {{const i = {INDICATOR}; return [i._toolbar.height,
                i._expandButton.y, i._searchButton.y, i._stationsSeparator.height];}})()''')

        def entry_style(actor):
            return evaluate(f'''(() => {{
                const entry = {actor};
                const node = entry.get_theme_node();
                const sides = global._radioSt.Side;
                const border = node.get_border_color(sides.TOP);
                return {{height: entry.height, textY: entry.clutter_text.y,
                    padding: [sides.TOP, sides.BOTTOM, sides.LEFT, sides.RIGHT].map(side => node.get_padding(side)),
                    backgroundAlpha: node.get_background_color().alpha,
                    border: [border.red, border.green, border.blue, border.alpha],
                    borderWidth: node.get_border_width(sides.TOP),
                    radius: node.get_border_radius(global._radioSt.Corner.TOPLEFT)}};
            }})()''')

        def assert_input_ratio():
            wait(lambda: evaluate(f'''(() => {{const i = {INDICATOR};
                return Math.abs(i._nameEntry.width / (i._nameEntry.width + i._urlEntry.width) - 0.3) < 0.005;
            }})()'''), 'form inputs settle at their 30/70 allocation')
            widths = evaluate(f'[{INDICATOR}._nameEntry.width, {INDICATOR}._urlEntry.width]')
            self.assertAlmostEqual(widths[0] / sum(widths), 0.3, delta=0.005,
                                   msg='Name/URL must split available input width 30/70')
            geometry = evaluate(f'''(() => {{const i = {INDICATOR};
                const right = actor => actor.get_transformed_position()[0] + actor.get_transformed_size()[0];
                const box = i._nameEntry.get_parent().get_parent().get_parent();
                return {{urlRight: right(i._urlEntry), popupRight: right(i.menu.actor),
                    copyRight: i._copySource.visible ? right(i._copySource) : 0,
                    boxWidth: box.width,
                    available: i._form.width - i._form.get_theme_node().get_horizontal_padding()}};
            }})()''')
            self.assertTrue(geometry['urlRight'] < geometry['popupRight'] and
                            geometry['copyRight'] < geometry['popupRight'] and
                            abs(geometry['boxWidth'] - geometry['available']) < 1,
                            f'Form must fill available width and contain inputs and Copy: {geometry}')

        def assert_theme_variants(prefix):
            original_scheme = evaluate("new Gio.Settings({schema_id: 'org.gnome.desktop.interface'}).get_string('color-scheme')")
            colors = []
            for variant in ('light', 'dark'):
                evaluate(f"new Gio.Settings({{schema_id: 'org.gnome.desktop.interface'}}).set_string('color-scheme', 'prefer-{variant}'); true")
                wait(lambda: evaluate(f"Main.getStyleVariant() === '{variant}'"), 'native theme variant changed')
                wait(lambda: evaluate(f"global._radioSt.ThemeContext.get_for_stage(global.stage).get_theme().default_stylesheet.get_uri().includes('-{variant}.css')"), 'native stylesheet changed')
                time.sleep(0.3)
                # Use a generic native panel reference with zero icon padding/margins.
                # Keep the reference independent of installed extensions.
                evaluate(f'''global._radioSpacingReference = new global._radioPanelMenu.Button(0.5, 'Spacing reference');
                    global._radioSpacingBox = new global._radioSt.BoxLayout({{style: 'spacing: 6px;'}});
                    global._radioSpacingIcon = new global._radioSt.Icon({{
                        gicon: {INDICATOR}._icon.gicon, style_class: 'system-status-icon',
                        style: 'padding: 0; margin: 0;'}});
                    global._radioSpacingBox.add_child(global._radioSpacingIcon);
                    global._radioSpacingReference.add_child(global._radioSpacingBox);
                    Main.panel.addToStatusArea('radio-spacing-reference', global._radioSpacingReference); true''')
                time.sleep(0.1)
                compact = evaluate(f'[{INDICATOR}.width, {INDICATOR}._icon.width, {INDICATOR}.height]')
                reference = evaluate('[global._radioSpacingReference.width, global._radioSpacingIcon.width, global._radioSpacingReference.height]')
                self.assertEqual(compact, reference, 'radiolina indicator must preserve native button height and compact icon spacing')
                self.assertTrue(standalone_panel(), 'Theme changes must preserve other app containers')
                evaluate('global._radioSpacingIcon.set_style(null); true')
                time.sleep(0.1)
                self.assertLess(compact[0], evaluate('global._radioSpacingReference.width'),
                                'Remove the extra space around a standard panel icon')
                evaluate('global._radioSpacingReference.destroy(); true')
                time.sleep(0.1)
                colors.append(evaluate(f'{INDICATOR}._name.get_theme_node().get_foreground_color().to_string()'))
                self.assertTrue(evaluate(f'''(() => {{const i = {INDICATOR};
                    const name = i._name.get_theme_node(), track = i._title.get_theme_node();
                    return name.get_font().get_weight() >= 700 &&
                        track.get_font().get_size() < name.get_font().get_size() &&
                        track.get_foreground_color().to_string() === name.get_foreground_color().to_string() &&
                        i._title.get_paint_opacity() > 0 &&
                        i._title.get_paint_opacity() < i._name.get_paint_opacity();
                }})()'''), 'Infobox must show a bold name and smaller, subdued theme-colored track text')
                self.assertEqual(evaluate(f'{INDICATOR}._details.height'), info_height)
                self.assertEqual(evaluate(f'{INDICATOR}.menu.actor.width'), popup_width)
                self.assertAlmostEqual(evaluate(f'{INDICATOR}._play.get_transformed_position()[0]'),
                                       evaluate(f'{INDICATOR}._recentHeading.get_transformed_position()[0]'),
                                       delta=1, msg='Play/Pause must align with the section text below')
                success, _filename = call('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
                    'org.gnome.Shell.Screenshot', 'Screenshot', GLib.Variant('(bbs)',
                        (False, False, str(Path(f'workspace/{prefix}-{variant}.png').resolve()))))
                self.assertTrue(success)
            self.assertNotEqual(colors[0], colors[1], 'Native text colors must follow light/dark changes')
            evaluate(f"new Gio.Settings({{schema_id: 'org.gnome.desktop.interface'}}).set_string('color-scheme', {json.dumps(original_scheme)}); true")
            time.sleep(0.3)

        def assert_large_text():
            settings = "new Gio.Settings({schema_id: 'org.gnome.desktop.interface'})"
            original = evaluate(f'''(() => {{const s = {settings}; return {{
                font: s.get_string('font-name'), scale: s.get_double('text-scaling-factor'),
                scheme: s.get_string('color-scheme')}};}})()''')
            original_name_height = evaluate(f'{INDICATOR}._name.height')

            def assert_fit(actors):
                self.assertTrue(evaluate(f'''(() => {{const i = {INDICATOR};
                    const bounds = actor => {{const [x, y] = actor.get_transformed_position();
                        const [w, h] = actor.get_transformed_size();
                        return {{x, y, right: x + w, bottom: y + h, w, h}};}};
                    const popup = bounds(i.menu.actor);
                    return popup.w === {popup_width} && popup.y >= 0 &&
                        popup.bottom <= Main.layoutManager.primaryMonitor.height &&
                        [{actors}].every(actor => {{const b = bounds(actor);
                            return actor.mapped && b.w > 0 && b.h > 0 &&
                                b.x >= popup.x && b.right <= popup.right + 1 &&
                                b.y >= popup.y && b.bottom <= popup.bottom + 1;
                        }});
                }})()'''), f'Large-text controls must remain inside the fixed-width popup: {actors}')

            def screenshot(view, variant):
                success, _filename = call('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
                    'org.gnome.Shell.Screenshot', 'Screenshot', GLib.Variant('(bbs)',
                        (False, False, str(Path(f'workspace/large-text-{variant}-{view}.png').resolve()))))
                self.assertTrue(success)

            try:
                evaluate(f'''(() => {{const s = {settings};
                    s.set_string('font-name', 'Serif 12');
                    s.set_double('text-scaling-factor', 1.25);}})(); true''')
                wait(lambda: evaluate(f'''{INDICATOR}._name.height > {original_name_height} &&
                    {INDICATOR}._name.get_theme_node().get_font().get_family().toLowerCase() === 'serif' '''),
                    'alternate font and larger text applied to actual Shell actors')
                for variant in ('light', 'dark'):
                    evaluate(f"{settings}.set_string('color-scheme', 'prefer-{variant}'); true")
                    wait(lambda: evaluate(f"Main.getStyleVariant() === '{variant}'"), 'large-text theme variant')
                    evaluate(f'{INDICATOR}._showView(null); {INDICATOR}.menu.open(); true')
                    time.sleep(0.3)
                    assert_fit('i._name, i._title, i._play, i._stopButton, i._quitButton, '
                               'i._stationsHeading, i._expandButton, i._searchButton, i._add, i._settingsButton')
                    self.assertTrue(evaluate(f'''(() => {{const i = {INDICATOR};
                        return [i._name, i._title].every(label =>
                            label.height >= label.clutter_text.get_preferred_height(label.width)[1]) &&
                            i._title.get_transformed_position()[1] + i._title.height <=
                                i._infoFrame.get_transformed_position()[1] + i._infoFrame.height;
                    }})()'''), 'Large station/track text must fit the infobox height')
                    screenshot('popup', variant)
                    click(f'{INDICATOR}._searchButton')
                    assert_fit('i._searchEntry, i._expandButton, i._searchButton, i._add, i._settingsButton')
                    self.assertFalse(evaluate(f'{INDICATOR}._stationsHeading.clutter_text.get_layout().is_ellipsized()'),
                                     'Search must leave the Stations heading readable with larger text')
                    row = f'{INDICATOR}._stationButtons.get({json.dumps(identifier)})'
                    evaluate(f'{row}.select.grab_key_focus(); true')
                    wait(lambda: evaluate(f'{row}.edit.opacity === 255'), 'large-text row actions revealed')
                    assert_fit(f'{row}.label, {row}.play, {row}.edit, {row}.remove')
                    screenshot('search', variant)
                    click(f'{row}.edit')
                    screenshot('edit', variant)
                    assert_input_ratio()
                    assert_fit('i._nameEntry, i._urlEntry, i._copySource, i._save, i._cancel, i._remove')
                    click(f'{INDICATOR}._add')
                    assert_input_ratio()
                    assert_fit('i._nameEntry, i._urlEntry, i._save, i._cancel')
                    screenshot('editor', variant)
                    click(f'{INDICATOR}._settingsButton')
                    assert_fit('i._faviconToggle, i._groupToggle, i._groupWarning, '
                               'i._recentLess, i._recentMore, i._recentCount')
                    screenshot('settings', variant)
            finally:
                evaluate(f'''(() => {{const s = {settings};
                    s.set_string('font-name', {json.dumps(original['font'])});
                    s.set_double('text-scaling-factor', {original['scale']});
                    s.set_string('color-scheme', {json.dumps(original['scheme'])});
                    {INDICATOR}._showView(null);}})(); true''')
                wait(lambda: evaluate(f'{INDICATOR}._details.height === {info_height} && '
                                      f'{INDICATOR}._name.height === {original_name_height}'),
                     'original private desktop typography restored')

        evaluate('Main.welcomeDialog?.close(); Main.overview.hide(); '
                 'Main.messageTray.getSources().forEach(source => source.destroy()); true')
        self.assertFalse(evaluate(f"Boolean(Main.extensionManager.lookup('{UUID}'))"))
        root = Path(__file__).resolve().parents[2]
        installed = Path(os.environ['XDG_DATA_HOME']) / 'gnome-shell/extensions' / UUID
        bundle = root / 'build' / f'{UUID}.zip'

        def install_bundle():
            result = subprocess.run(['gnome-extensions', 'install', '--force', str(bundle)],
                                    text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads((installed / 'metadata.json').read_text())['uuid'], UUID)

        install_bundle()
        entry = installed / 'src/service/main.js'
        entry.write_text('Temporary overwritten-file fixture for the ZIP update check.\n')
        install_bundle()
        self.assertEqual(entry.read_bytes(), (root / 'src/service/main.js').read_bytes(),
                         'Forced ZIP installation must replace existing runtime files')
        # Exercise a previous development identity in the same Shell process.
        # Disabled modules stay imported, so both paths must have distinct GTypes.
        old_uuid = 'gnome-radio@local'
        old_indicator = f"Main.panel.statusArea['{old_uuid}']"
        previous = installed.parent / old_uuid
        shutil.copytree(installed, previous)
        old_metadata = json.loads((previous / 'metadata.json').read_text())
        old_metadata['uuid'] = old_uuid
        (previous / 'metadata.json').write_text(json.dumps(old_metadata))
        # Cold GStreamer registry discovery can exceed the old ten-second
        # readiness deadline. Delay only this disposable backend, never Shell.
        previous_entry = previous / 'src/service/main.js'
        previous_entry.write_text(previous_entry.read_text().replace(
            "const BUS =", "GLib.usleep(12_000_000);\nconst BUS =", 1))
        load_previous = (
            f"await Main.extensionManager.loadExtension(Main.extensionManager.createExtensionObject("
            f"'{old_uuid}', Gio.File.new_for_path({json.dumps(str(previous))}), 2)); "
            f"Main.extensionManager.enableExtension('{old_uuid}')"
        )
        evaluate(f'Main.createLookingGlass()._evaluate({json.dumps(load_previous)}); true')
        wait(lambda: evaluate(f'Boolean({old_indicator}?._extension._process)'), 'slow backend spawned')
        cancelled_pid = evaluate(f'{old_indicator}._extension._process.get_identifier()')
        evaluate(f'{old_indicator}._stopPlayback(); true')
        wait(lambda: evaluate(f'!{old_indicator}._extension._starting && !{old_indicator}._extension._process')
             and not Path(f'/proc/{cancelled_pid}').exists(), 'Stop cancels slow initial startup', timeout=5)
        self.assertFalse(evaluate(f'Boolean({old_indicator}._state.error)'))
        started = time.monotonic()
        evaluate(f"{old_indicator}._call('SetRecentLimit', new GLib.Variant('(u)', [3])); true")
        wait(lambda: evaluate(f'Boolean({old_indicator}?._proxy?.g_name_owner) && !{old_indicator}._pending'),
             'first activation survives slow backend initialization', timeout=35)
        self.assertGreaterEqual(time.monotonic() - started, 12)
        self.assertFalse(evaluate(f'Boolean({old_indicator}._state.error)'),
                         'Slow successful startup must not leave an unavailable error')
        evaluate(f'{old_indicator}._stopPlayback(); true')
        wait(lambda: evaluate(f'!{old_indicator}._extension._process && !{old_indicator}._proxy.g_name_owner'),
             'backend stopped before early-exit fixture')
        previous_entry.write_text(entry.read_text().replace(
            'const BUS =', "import System from 'system';\nSystem.exit(7);\nconst BUS =", 1))
        evaluate(f"{old_indicator}._call('SetRecentLimit', new GLib.Variant('(u)', [3])); true")
        wait(lambda: evaluate(f'!{old_indicator}._pending && !{old_indicator}._extension._starting && '
                              f'Boolean({old_indicator}._state.error)'),
             'early backend exit fails promptly instead of waiting for the readiness deadline', timeout=5)
        shutil.copyfile(entry, previous_entry)
        evaluate(f"{old_indicator}._call('SetRecentLimit', new GLib.Variant('(u)', [3])); true")
        wait(lambda: evaluate(f'Boolean({old_indicator}._proxy.g_name_owner) && !{old_indicator}._pending && !{old_indicator}._state.error'),
             'backend recovers after early startup failure')
        saved_id = call(BUS, APP, IFACE, 'AddStation', GLib.Variant('(ss)',
            ('Migration station', ServiceE2E.url + '/icy')))[0]
        call(BUS, APP, IFACE, 'SetRecentLimit', GLib.Variant('(u)', (7,)))
        call(BUS, APP, IFACE, 'PlayPause')
        wait(lambda: evaluate(f"{old_indicator}._state.status === 'Playing'"), 'development station plays')
        old_pid = int(evaluate(f'{old_indicator}._extension._process.get_identifier()'))
        evaluate(f"Main.extensionManager.disableExtension('{old_uuid}'); true")
        wait(lambda: evaluate(f'!{old_indicator}'), 'development indicator disabled')
        wait(lambda: not call('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'NameHasOwner', GLib.Variant('(s)', (BUS,)))[0], 'development service stopped')
        wait(lambda: not Path(f'/proc/{old_pid}').exists(), 'development backend process exited')
        saved_file = Path(os.environ['XDG_CONFIG_HOME']) / 'gnome-radio/stations.json'
        saved_bytes = saved_file.read_bytes()
        # An identifiable earlier applet stylesheet still sets the old form-wide
        # width. Reserve damaged duplicate registries for the later lifecycle case.
        legacy_css = '.radio-form StEntry { width: 276px; } .radio-station { font-weight: bold; }'
        orphan_css = installed / 'legacy-session.css'
        orphan_css.write_text(legacy_css)
        unrelated_css = installed.parent / 'unrelated-test.css'
        unrelated_css.write_text('.unrelated-test-control { padding: 1px; }')
        cache_probe_css = installed.parent / 'cached-theme-probe.css'
        cache_probe_css.write_text('.cached-theme-probe { padding: 7px; }')
        evaluate(f'''global._radioLegacyStyles = [Gio.File.new_for_uri({json.dumps(orphan_css.as_uri())})];
            global._radioUnrelatedStyle = Gio.File.new_for_uri({json.dumps(unrelated_css.as_uri())});
            global._radioCacheProbeStyle = Gio.File.new_for_uri({json.dumps(cache_probe_css.as_uri())});
            global._radioSharedTheme = global._radioSt.ThemeContext.get_for_stage(global.stage).get_theme();
            [global._radioUnrelatedStyle, ...global._radioLegacyStyles].forEach(file =>
                global._radioSharedTheme.load_stylesheet(file));
            true''')

        def assert_cached_theme():
            self.assertTrue(evaluate('global._radioSt.ThemeContext.get_for_stage(global.stage).get_theme() === global._radioSharedTheme'),
                            'Radio operations must preserve the actual shared theme object')
            self.assertTrue(evaluate('''(() => {
                const theme = global._radioSharedTheme;
                const probe = new global._radioSt.Widget({style_class: 'cached-theme-probe'});
                Main.uiGroup.add_child(probe);
                try {
                    theme.load_stylesheet(global._radioCacheProbeStyle);
                    const loaded = probe.get_theme_node().get_horizontal_padding() > 0;
                    theme.unload_stylesheet(global._radioCacheProbeStyle);
                    return loaded && probe.get_theme_node().get_horizontal_padding() === 0;
                } finally {
                    theme.unload_stylesheet(global._radioCacheProbeStyle);
                    probe.destroy();
                }
            })()'''), 'A peer must still be able to load/unload styles through its cached theme')

        legacy_width = evaluate('''(() => {const parent = new global._radioSt.BoxLayout({style_class: 'radio-form'});
            const entry = new global._radioSt.Entry({style_class: 'radio-name-entry'});
            parent.add_child(entry); Main.uiGroup.add_child(parent);
            const width = entry.get_preferred_width(-1)[1]; parent.destroy(); return width;})()''')
        self.assertGreaterEqual(legacy_width, 276, 'Legacy stylesheet must be active before testing upgrade repair')
        command = (
            f"if (!Main.extensionManager.lookup('{UUID}')) await "
            "Main.extensionManager.loadExtension(Main.extensionManager.createExtensionObject("
            f"'{UUID}', Gio.File.new_for_path(GLib.get_user_data_dir() + "
            f"'/gnome-shell/extensions/{UUID}'), 2)); "
            f"Main.extensionManager.enableExtension('{UUID}')"
        )
        # Run the exact documented command through the real Looking Glass evaluator.
        evaluate(f'Main.createLookingGlass()._evaluate({json.dumps(command)}); true')
        wait(lambda: evaluate(f'Boolean({INDICATOR}?._proxy?.g_name_owner)'), 'extension and service ready')
        wait(lambda: evaluate(f'{INDICATOR}._state.selected === {json.dumps(saved_id)} && '
                             f'{INDICATOR}._state.recentLimit === 7'), 'saved selection and settings survive new identity')
        self.assertEqual(evaluate(f'{INDICATOR}._state.stations'),
                         [{'id': saved_id, 'name': 'Migration station', 'url': ServiceE2E.url + '/icy'}])
        self.assertEqual(evaluate(f'{INDICATOR}._state.recent'), [saved_id])
        self.assertEqual(saved_file.read_bytes(), saved_bytes, 'Loading the new ID must not rewrite saved data')
        self.assertFalse(evaluate(f'Boolean({old_indicator})'))
        self.assertFalse(evaluate(f"new Gio.Settings({{schema_id: 'org.gnome.shell'}}).get_strv('enabled-extensions').includes('{old_uuid}')"))
        # Reproduce a host still running the development ID while the new ZIP
        # exists on disk but has never been registered in this Shell session.
        evaluate(f"Main.extensionManager.disableExtension('{UUID}'); true")
        wait(lambda: evaluate(f'!{INDICATOR}'), 'new indicator disabled before legacy-only update fixture')
        unload_new = f"await Main.extensionManager.unloadExtension(Main.extensionManager.lookup('{UUID}'));"
        evaluate(f'Main.createLookingGlass()._evaluate({json.dumps(unload_new)}); true')
        wait(lambda: evaluate(f"!Main.extensionManager.lookup('{UUID}')"), 'new identity unregistered')
        evaluate(f"Main.extensionManager.enableExtension('{old_uuid}'); true")
        wait(lambda: evaluate(f'Boolean({old_indicator}?._proxy?.g_name_owner)'), 'legacy-only indicator active')
        legacy_pid = int(evaluate(f'{old_indicator}._extension._process.get_identifier()'))
        migration_update = (
            f"await (await import({json.dumps((root / 'scripts/live-update.js').as_uri())})).update(Main);"
        )
        evaluate(f'Main.createLookingGlass()._evaluate({json.dumps(migration_update)}); true')
        wait(lambda: evaluate(f'Boolean({INDICATOR}?._proxy?.g_name_owner) && !{old_indicator}'),
             'updater replaces active development ID with previously unregistered radiolina')
        wait(lambda: not Path(f'/proc/{legacy_pid}').exists(), 'legacy-only backend exited')
        self.assertFalse(evaluate(f"global.settings.get_strv('enabled-extensions').includes('{old_uuid}')"))
        self.assertEqual(saved_file.read_bytes(), saved_bytes, 'Updater migration must preserve saved data bytes')
        self.assertEqual(evaluate(f"Main.extensionManager.lookup('{UUID}').metadata['radio-runtime']"),
                         json.loads((installed / 'metadata.json').read_text())['radio-runtime'])
        # Restore an empty/default profile for the existing station/UI workflow.
        call(BUS, APP, IFACE, 'RemoveStation', GLib.Variant('(s)', (saved_id,)))
        call(BUS, APP, IFACE, 'SetRecentLimit', GLib.Variant('(u)', (3,)))
        wait(lambda: evaluate(f'{INDICATOR}._state.stations.length === 0 && '
                             f'{INDICATOR}._state.recentLimit === 3'), 'migration fixture cleared')
        assert_cached_theme()
        self.assertEqual(evaluate(f"Main.extensionManager.lookup('{UUID}').metadata.name"), 'radiolina')
        wait(lambda: evaluate(f"{INDICATOR}.accessible_name.startsWith('radiolina: ')"), 'radiolina panel identity')
        evaluate(f'Main.createLookingGlass()._evaluate({json.dumps(command)}); true')
        self.assertEqual(evaluate(f"Main.extensionManager.lookup('{UUID}').error"), '')
        self.assertTrue(evaluate(f'{INDICATOR}.container.get_parent() === Main.panel._rightBox'))
        evaluate(f'''global._radioSystemParents = Object.entries(Main.panel.statusArea)
            .filter(([role]) => role !== '{UUID}').map(([role, actor]) => [role, actor.container.get_parent()]); true''')
        for role in PEERS:
            neighbor = installed.parent / role
            neighbor.mkdir()
            (neighbor / 'metadata.json').write_text(json.dumps({'uuid': role,
                'name': 'Generic panel fixture', 'description': 'Panel-only test fixture', 'shell-version': ['49']}))
            shutil.copy2(root / 'tests/fixtures/panel-neighbor.js', neighbor / 'extension.js')
            load_neighbor = (f"await Main.extensionManager.loadExtension(Main.extensionManager.createExtensionObject("
                             f"'{role}', Gio.File.new_for_path({json.dumps(str(neighbor))}), 2)); "
                             f"Main.extensionManager.enableExtension('{role}')")
            evaluate(f'Main.createLookingGlass()._evaluate({json.dumps(load_neighbor)}); true')
            wait(lambda: evaluate(f"Boolean(Main.panel.statusArea['{role}'])"), 'generic app indicator enabled')
            self.assertTrue(standalone_panel(), 'A non-system indicator is not an opt-in grouping host')
        self.assertTrue(evaluate('global._radioSystemParents.every(([role, parent]) => Main.panel.statusArea[role].container.get_parent() === parent)'))
        self.assertTrue(evaluate(f"Main.panel.statusArea['{PEERS[1]}'].container.get_parent() === Main.panel._rightBox"))
        evaluate('Main.overview.hide(); true')
        wait(lambda: evaluate('!Main.overview.visible'), 'desktop ready for independent panel clicks')
        panel_click(INDICATOR)
        wait(lambda: evaluate(f'{INDICATOR}.menu.isOpen'), 'single radio click opens its own popup')
        self.assertFalse(evaluate('Main.overview.visible'))
        self.assertFalse(evaluate(f"Main.panel.statusArea['{PEERS[0]}'].menu.isOpen"))
        evaluate(f'{INDICATOR}.menu.close(); true')
        panel_click(f"Main.panel.statusArea['{PEERS[0]}']")
        wait(lambda: evaluate(f"Main.panel.statusArea['{PEERS[0]}'].menu.isOpen && !{INDICATOR}.menu.isOpen"), 'peer click opens only its own popup')
        self.assertFalse(evaluate('Main.overview.visible'))
        evaluate(f"Main.panel.statusArea['{PEERS[0]}'].menu.close(); Main.extensionManager.disableExtension('{PEERS[0]}'); true")
        wait(lambda: evaluate(f"!Main.panel.statusArea['{PEERS[0]}']"), 'Peer disables independently')
        self.assertTrue(standalone_panel())
        self.assertTrue(evaluate(f'Boolean({INDICATOR}._proxy.g_name_owner)'))
        evaluate(f"Main.panel.statusArea['{PEERS[1]}'].hide(); true")
        self.assertTrue(standalone_panel(), 'Peer visibility must not change ownership')
        evaluate(f"Main.panel.statusArea['{PEERS[1]}'].show(); true")
        self.assertTrue(standalone_panel())
        evaluate(f"Main.extensionManager.disableExtension('{PEERS[1]}'); true")
        wait(lambda: evaluate(f"!Main.panel.statusArea['{PEERS[1]}']"), 'Second peer disables independently')
        self.assertTrue(standalone_panel())
        for role in PEERS:
            evaluate(f"Main.extensionManager.enableExtension('{role}'); true")
            wait(lambda: evaluate(f"Boolean(Main.panel.statusArea['{role}'])"), 'Peer re-enabled')
            self.assertTrue(standalone_panel(), 'Peer re-enable must preserve separate containers')
        def own_styles():
            return evaluate(f'''global._radioSt.ThemeContext.get_for_stage(global.stage).get_theme()
                .get_custom_stylesheets().filter(file => file?.get_uri().startsWith(
                    Gio.File.new_for_path({json.dumps(str(installed))}).get_uri() + '/'))
                .map(file => file.get_basename())''')
        packaged_metadata = json.loads((installed / 'metadata.json').read_text())
        self.assertEqual(own_styles(), [packaged_metadata['radio-stylesheet']])
        self.assertTrue(evaluate('global._radioSt.ThemeContext.get_for_stage(global.stage).get_theme().get_custom_stylesheets().some(file => file?.equal(global._radioUnrelatedStyle))'))
        self.assertTrue(evaluate(f"{INDICATOR}._icon.gicon.get_file().get_basename() === 'radio-symbolic.svg'"))
        self.assertTrue(evaluate(f"{INDICATOR}._icon.has_style_class_name('system-status-icon')"))
        self.assertTrue(evaluate(f'''(() => {{
            const i = {INDICATOR};
            return [i._play, i._searchButton, i._add].every(button =>
                button.has_style_class_name('icon-button') &&
                !button.has_style_class_name('flat') &&
                !button.has_style_class_name('radio-icon-button'));
        }})()'''))
        self.assertFalse(evaluate(f"Boolean({INDICATOR}._icon.get_transition('radio-playback'))"))
        self.assertEqual(evaluate(f'{INDICATOR}._name.text'), 'Add your first station')
        self.assertFalse(evaluate(f'{INDICATOR}._stationContainer.visible'))
        self.assertEqual(evaluate(f'{INDICATOR}._recentButtons.size'), 0)
        evaluate(f'{INDICATOR}.menu.open(); true')
        time.sleep(0.2)
        popup_width = evaluate(f'{INDICATOR}.menu.actor.width')
        self.assertTrue(evaluate(f'''(() => {{const i = {INDICATOR};
            const children = i._details.get_children();
            return [i._play, i._stopButton, i._infoFrame, i._quitButton]
                .every((actor, index, controls) => actor.get_parent() === i._details && actor.mapped &&
                    (index === 0 || children.indexOf(actor) > children.indexOf(controls[index - 1]))) &&
                i._quitButton.accessible_name === 'Quit radiolina';
        }})()'''), 'Infobox order must be Play/Pause, Stop, text info, Quit without a bottom Quit row')
        self.assertEqual(evaluate(f'{INDICATOR}._settingsButton.child.icon_name'), 'preferences-system-symbolic')
        evaluate(f"{INDICATOR}._settingsButton.emit('clicked', 1); true")
        self.assertTrue(evaluate(f'{INDICATOR}._settingsSection.actor.visible'))
        self.assertFalse(evaluate(f'{INDICATOR}._faviconToggle.state'))
        self.assertFalse(evaluate(f'{INDICATOR}._groupToggle.state'))
        self.assertEqual(evaluate(f'{INDICATOR}._groupWarning.text'), GROUP_WARNING)
        self.assertFalse(evaluate(f'{INDICATOR}._groupUnavailableRow.visible'))
        other_placement = other_panel_placement()
        click(f'{INDICATOR}._groupToggle')
        wait(lambda: evaluate(f'{INDICATOR}._state.groupWithAppIndicators && !{INDICATOR}._pending'), 'Grouping preference enabled')
        self.assertTrue(evaluate(f'{INDICATOR}._groupUnavailableRow.visible'))
        self.assertTrue(standalone_panel(), 'A warning or preference must not make unsupported peers compatible')
        self.assertEqual(other_panel_placement(), other_placement, 'Enabling the preference must preserve panel order')
        for role in PEERS:
            evaluate(f"Main.panel.statusArea['{role}'].hide(); Main.panel.statusArea['{role}'].show(); true")
            self.assertTrue(standalone_panel())
        evaluate(f"Main.extensionManager.disableExtension('{PEERS[0]}'); true")
        wait(lambda: evaluate(f"!Main.panel.statusArea['{PEERS[0]}']"), 'Peer disables with grouping requested')
        self.assertTrue(standalone_panel())
        evaluate(f"Main.extensionManager.enableExtension('{PEERS[0]}'); true")
        wait(lambda: evaluate(f"Boolean(Main.panel.statusArea['{PEERS[0]}'])"), 'Peer re-enables with grouping requested')
        self.assertTrue(standalone_panel())
        other_placement = other_panel_placement()
        click(f'{INDICATOR}._groupToggle')
        wait(lambda: evaluate(f'!{INDICATOR}._state.groupWithAppIndicators && !{INDICATOR}._pending'), 'Grouping preference disabled')
        self.assertFalse(evaluate(f'{INDICATOR}._groupUnavailableRow.visible'))
        self.assertTrue(standalone_panel())
        self.assertEqual(other_panel_placement(), other_placement, 'Disabling the preference must preserve panel order')
        click(f'{INDICATOR}._groupToggle')
        wait(lambda: evaluate(f'{INDICATOR}._state.groupWithAppIndicators && !{INDICATOR}._pending'), 'Grouping preference saved for restart checks')
        self.assertEqual(evaluate(f'{INDICATOR}._recentCount.text'), '3')
        evaluate(f"{INDICATOR}._settingsButton.emit('clicked', 1); true")
        evaluate(f"{INDICATOR}.menu.open(); {INDICATOR}._add.emit('clicked', 1); true")
        self.assertTrue(evaluate(f'{INDICATOR}._form.visible && {INDICATOR}.menu.isOpen'))
        time.sleep(0.2)
        info_height = evaluate(f'{INDICATOR}._details.height')
        self.assertEqual(evaluate(f'{INDICATOR}.menu.actor.width'), popup_width)
        self.assertFalse(evaluate(f'{INDICATOR}._copySource.visible'))
        original_name_width = evaluate(f'{INDICATOR}._nameEntry.width')
        assert_input_ratio()
        self.assertLess(original_name_width, legacy_width / 2, 'Name input must use the new narrow style')
        self.assertTrue(evaluate(f'''(() => {{
            const i = {INDICATOR};
            const top = actor => actor.get_transformed_position()[1];
            const right = actor => actor.get_transformed_position()[0] + actor.get_transformed_size()[0];
            return Math.abs(top(i._nameEntry) - top(i._urlEntry)) < 1 &&
                i._nameEntry.get_parent() === i._urlEntry.get_parent() &&
                i._nameEntry.width < i._urlEntry.width &&
                right(i._nameEntry) < right(i._urlEntry) &&
                right(i._urlEntry) < right(i.menu.actor) &&
                Math.abs(top(i._save) - top(i._cancel)) < 1 &&
                top(i._save) >= top(i._nameEntry) + i._nameEntry.height &&
                i._form.width <= i.menu.actor.width;
        }})()'''), 'Compact form inputs and actions must each share a row')
        self.assertTrue(evaluate(f'{INDICATOR}._stationsSeparator.visible && {INDICATOR}._toolbar.get_previous_sibling() === {INDICATOR}._stationsSeparator'))
        self.assertTrue(evaluate(f'''[{INDICATOR}._recentHeading, {INDICATOR}._stationsHeading,
            {INDICATOR}._formHeading].every(label => label.get_theme_node().get_font().get_weight() >= 700)'''))
        self.assertFalse(evaluate(f'{INDICATOR}._searchEntry.visible'))
        self.assertTrue(evaluate(f"typeof {INDICATOR}._notifications === 'undefined'"))
        evaluate(f"{INDICATOR}._nameEntry.set_text('Fixture radio'); "
                 f"{INDICATOR}._urlEntry.set_text('file:///etc/passwd'); "
                 f"{INDICATOR}._save.emit('clicked', 1); true")
        wait(lambda: evaluate(f'{INDICATOR}._error.visible'), 'inline validation error')
        self.assertTrue(evaluate(f'{INDICATOR}._errorRow.visible'))
        self.assertEqual(evaluate(f'{INDICATOR}._details.height'), info_height)
        self.assertEqual(evaluate(f'{INDICATOR}.menu.actor.width'), popup_width)
        self.assertTrue(evaluate(f'{INDICATOR}._form.visible'))
        evaluate(f"{INDICATOR}._urlEntry.set_text('{ServiceE2E.url}/icy'); "
                 f"{INDICATOR}._save.emit('clicked', 1); true")
        wait(lambda: evaluate(f"{INDICATOR}._name.text === 'Fixture radio'"), 'station added from popup')
        self.assertFalse(evaluate(f'{INDICATOR}._form.visible'))
        self.assertTrue(evaluate(f"typeof {INDICATOR}._source === 'undefined'"))
        self.assertEqual(evaluate(f'{INDICATOR}._state.stations.find(station => station.id === {INDICATOR}._state.selected).url'), ServiceE2E.url + '/icy')
        self.assertEqual(evaluate(f'{INDICATOR}._title.text'), '')
        self.assertFalse(evaluate(f'{INDICATOR}._title.visible'))
        time.sleep(0.2)
        name_without_title = evaluate(f'{INDICATOR}._name.get_transformed_position()[1] - {INDICATOR}._details.get_transformed_position()[1]')
        self.assertTrue(evaluate(f'''(() => {{const i = {INDICATOR};
            const center = actor => actor.get_transformed_position()[1] + actor.get_transformed_size()[1] / 2;
            return Math.abs(center(i._name) - center(i._play)) < 1;
        }})()'''), 'Station-only text should be centered beside playback control')
        evaluate(f"{INDICATOR}._play.emit('clicked', 1); true")
        wait(lambda: evaluate(f"{INDICATOR}._state.status === 'Playing'"), 'popup playback')
        wait(lambda: evaluate(f"{INDICATOR}._title.text === 'First song'"), 'popup song title')
        self.assertTrue(evaluate(f'{INDICATOR}._title.visible'))
        time.sleep(0.2)
        self.assertEqual(evaluate(f'{INDICATOR}._details.height'), info_height)
        self.assertLess(evaluate(f'{INDICATOR}._name.get_transformed_position()[1] - {INDICATOR}._details.get_transformed_position()[1]'), name_without_title)
        self.assertTrue(evaluate(f'''(() => {{const i = {INDICATOR};
            const top = actor => actor.get_transformed_position()[1];
            return top(i._title) >= top(i._name) + i._name.height &&
                top(i._title) + i._title.height <= top(i._details) + i._details.height;
        }})()'''), 'Both metadata rows must fit in the fixed infobox')
        # Real stream errors must remain visible when the popup is reopened.
        working = evaluate(f'{INDICATOR}._state.selected')
        unavailable = call(BUS, APP, IFACE, 'AddStation', GLib.Variant('(ss)',
                           ('Unavailable stream', ServiceE2E.url + '/missing')))[0]
        call(BUS, APP, IFACE, 'SelectStation', GLib.Variant('(s)', (unavailable,)))
        wait(lambda: evaluate(f'{INDICATOR}._state.selected === {json.dumps(unavailable)}'), 'unavailable station selected')
        evaluate(f"{INDICATOR}._play.emit('clicked', 1); true")
        wait(lambda: evaluate(f'{INDICATOR}._errorRow.visible && !{INDICATOR}._pending && '
                              f"{INDICATOR}._state.status === 'Stopped'"), 'persistent stream error')
        self.assertTrue(evaluate(f'{INDICATOR}.menu.isOpen'))
        self.assertFalse(evaluate(f'{INDICATOR}._title.visible'), 'Stream errors clear stale metadata')
        error_text = evaluate(f'{INDICATOR}._error.text')
        evaluate(f'{INDICATOR}.menu.close(); {INDICATOR}.menu.open(); true')
        self.assertEqual(evaluate(f'{INDICATOR}._error.text'), error_text)
        original_scheme = evaluate("new Gio.Settings({schema_id: 'org.gnome.desktop.interface'}).get_string('color-scheme')")
        for variant in ('light', 'dark'):
            evaluate("new Gio.Settings({schema_id: 'org.gnome.desktop.interface'}).set_string('color-scheme', "
                     f"'prefer-{variant}'); true")
            wait(lambda: evaluate(f"Main.getStyleVariant() === '{variant}'"), 'stream-error native theme')
            time.sleep(0.2)
            self.assertTrue(evaluate(f'''(() => {{const i = {INDICATOR};
                return !i._errorRow.reactive && i._error.get_paint_opacity() === 255 &&
                    i._error.get_theme_node().get_foreground_color().to_string() ===
                    i._name.get_theme_node().get_foreground_color().to_string();
            }})()'''), 'Error text inherits the readable native foreground without disabled-row styling')
            self.assertTrue(evaluate(f'''(() => {{const i = {INDICATOR};
                const [x, y] = i._error.get_transformed_position();
                const [w, h] = i._error.get_transformed_size();
                const [mx, my] = i.menu.actor.get_transformed_position();
                return i._errorRow.visible && x >= mx && y >= my &&
                    x + w <= mx + i.menu.actor.width && y + h <= my + i.menu.actor.height;
            }})()'''), 'Stream error text must fit inside the popup')
            success, _filename = call('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
                'org.gnome.Shell.Screenshot', 'Screenshot', GLib.Variant('(bbs)',
                (False, False, str(Path(f'workspace/network-error-{variant}.png').resolve()))))
            self.assertTrue(success)
        evaluate("new Gio.Settings({schema_id: 'org.gnome.desktop.interface'}).set_string('color-scheme', "
                 f'{json.dumps(original_scheme)}); true')
        call(BUS, APP, IFACE, 'RemoveStation', GLib.Variant('(s)', (unavailable,)))
        wait(lambda: evaluate(f'{INDICATOR}._state.selected === {json.dumps(working)} && '
                              f'!{INDICATOR}._errorRow.visible'), 'error clears on station recovery')
        evaluate(f"{INDICATOR}._play.emit('clicked', 1); true")
        wait(lambda: evaluate(f"{INDICATOR}._state.status === 'Playing' && !{INDICATOR}._pending"),
             'popup recovers playback after stream failure')
        # Reproduce the supplied long-title screenshot, including fractional scaling.
        identifier = evaluate(f'{INDICATOR}._state.selected')
        call(BUS, APP, IFACE, 'UpdateStation', GLib.Variant('(sss)',
             (identifier, 'Nightride FM - EBSM', ServiceE2E.url + '/icy')))
        Streams.title = 'Mascarpone - Dissolution of Ego'
        wait(lambda: evaluate(f"{INDICATOR}._title.text === 'Mascarpone — Dissolution of Ego'"), 'screenshot title reproduced')
        time.sleep(0.2)
        success, _filename = call('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
                                  'org.gnome.Shell.Screenshot', 'Screenshot',
                                  GLib.Variant('(bbs)', (False, False, str(Path('workspace/screenshot-regression.png').resolve()))))
        self.assertTrue(success)
        self.assertTrue(evaluate(f'''(() => {{const i = {INDICATOR};
            const bounds = actor => {{const [x, y] = actor.get_transformed_position();
                const [w, h] = actor.get_transformed_size(); return {{x, y, right: x + w, bottom: y + h}};}};
            const box = bounds(i._details);
            const name = bounds(i._name), title = bounds(i._title), play = bounds(i._play);
            return [name, title, play].every(item => item.x >= box.x && item.y >= box.y &&
                item.right <= box.right + 0.1 && item.bottom <= box.bottom + 0.1) &&
                play.right <= bounds(i._stopButton).x && bounds(i._stopButton).right <= title.x &&
                title.right <= bounds(i._quitButton).x &&
                title.bottom < bounds(i._infoSeparator._separator).y;
        }})()'''), 'Metadata and playback must fit without crossing the separator or popup edge')
        self.assertEqual(evaluate(f'{INDICATOR}._details.height'), info_height)
        assert_theme_variants('screenshot-regression')
        assert_large_text()
        call(BUS, APP, IFACE, 'UpdateStation', GLib.Variant('(sss)',
             (identifier, 'Fixture radio', ServiceE2E.url + '/icy')))
        Streams.title = 'First song'
        wait(lambda: evaluate(f"{INDICATOR}._title.text === 'First song'"), 'restore fixture metadata')
        identifier = evaluate(f'{INDICATOR}._state.selected')
        wait(lambda: evaluate(f'{INDICATOR}._recentButtons.has({json.dumps(identifier)})'), 'recent row after playback')
        self.assertTrue(evaluate(f'{INDICATOR}._recentButtons.get({json.dumps(identifier)}).label.text.endsWith(" (playing)")'))
        self.assertTrue(evaluate(f'{INDICATOR}._recentButtons.get({json.dumps(identifier)}).label.get_theme_node().get_font().get_weight() < 700'))
        self.assertEqual(evaluate(f'{INDICATOR}._recentButtons.get({json.dumps(identifier)}).marker.icon_name'), 'media-playback-start-symbolic')
        click(f'{INDICATOR}._recentButtons.get({json.dumps(identifier)}).label')
        evaluate(f"{INDICATOR}._expandButton.emit('clicked', 1); true")
        self.assertTrue(evaluate(f'{INDICATOR}._stationContainer.visible'))
        evaluate(f"{INDICATOR}._settingsButton.emit('clicked', 1); {INDICATOR}._faviconToggle.toggle(); true")
        wait(lambda: evaluate(f'{INDICATOR}._stationIcon.visible && {INDICATOR}._state.fetchFavicons'), 'favicon setting and cached station icon')
        self.assertTrue(evaluate(f'{INDICATOR}._stationButtons.get({json.dumps(identifier)}).select.get_children().some(child => child.gicon?.get_file?.())'))
        time.sleep(0.2)
        success, _filename = call('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
                                  'org.gnome.Shell.Screenshot', 'Screenshot',
                                  GLib.Variant('(bbs)', (False, False, str(Path('workspace/settings.png').resolve()))))
        self.assertTrue(success, 'Favicon settings screenshot')
        self.assertFalse(evaluate(f'Boolean({INDICATOR}._playPositionToggle)'))
        call(BUS, APP, IFACE, 'SetPlayButtonOnLeft', GLib.Variant('(b)', (True,)))
        self.assertTrue(evaluate(f'{INDICATOR}._details.get_children().indexOf({INDICATOR}._play) < {INDICATOR}._details.get_children().indexOf({INDICATOR}._stopButton)'))
        self.assertEqual(evaluate(f'{INDICATOR}._details.height'), info_height)
        self.assertEqual(evaluate(f'{INDICATOR}._state.status'), 'Playing')
        time.sleep(0.2)
        success, _filename = call('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
                                  'org.gnome.Shell.Screenshot', 'Screenshot',
                                  GLib.Variant('(bbs)', (False, False, str(Path('workspace/play-left.png').resolve()))))
        self.assertTrue(success, 'Fixed transport layout ignores the legacy placement setting')
        evaluate(f"{INDICATOR}._faviconToggle.toggle(); true")
        wait(lambda: evaluate(f'!{INDICATOR}._stationIcon.visible && !{INDICATOR}._state.fetchFavicons'), 'favicon setting disabled')
        evaluate(f"{INDICATOR}._settingsButton.emit('clicked', 1); true")
        self.assertEqual(evaluate(f'{INDICATOR}._icon.gicon.get_file().get_basename()'), 'radio-active-symbolic.svg')
        self.assertTrue(evaluate(f"!{INDICATOR}._icon.get_transition('radio-playback') && {INDICATOR}._icon.opacity === 255"))
        time.sleep(0.3)
        self.assertEqual(evaluate(f'{INDICATOR}._icon.opacity'), 255)
        identifier = evaluate(f'{INDICATOR}._state.selected')
        edit_button = f'{INDICATOR}._stationButtons.get({json.dumps(identifier)}).edit'
        evaluate(f"{INDICATOR}.menu.open(); {edit_button}.emit('clicked', 1); true")
        self.assertEqual(evaluate(f'{INDICATOR}._nameEntry.get_text()'), 'Fixture radio')
        self.assertEqual(evaluate(f'{INDICATOR}._urlEntry.get_text()'), ServiceE2E.url + '/icy')
        time.sleep(0.2)
        self.assertEqual(evaluate(f'{INDICATOR}.menu.actor.width'), popup_width)
        self.assertLess(evaluate(f'{INDICATOR}._nameEntry.width'), evaluate(f'{INDICATOR}._urlEntry.width'))
        assert_input_ratio()
        evaluate(f"{INDICATOR}._copySource.emit('clicked', 1); global._radioClipboardText = null; "
                 'global._radioSt.Clipboard.get_default().get_text(global._radioSt.ClipboardType.CLIPBOARD, '
                 '(_clipboard, text) => {global._radioClipboardText = text;}); true')
        wait(lambda: evaluate(f'global._radioClipboardText === {json.dumps(ServiceE2E.url + "/icy")}'), 'copy source URL from editor')
        success, _filename = call('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
                                  'org.gnome.Shell.Screenshot', 'Screenshot',
                                  GLib.Variant('(bbs)', (False, False, str(Path('workspace/editor.png').resolve()))))
        self.assertTrue(success, 'Station editor screenshot')
        evaluate(f"{INDICATOR}._nameEntry.set_text('Edited radio'); {INDICATOR}._save.emit('clicked', 1); true")
        wait(lambda: evaluate(f"{INDICATOR}._name.text === 'Edited radio' && !{INDICATOR}._pending"), 'rename saved')
        self.assertEqual(evaluate(f'{INDICATOR}._title.text'), 'First song')
        evaluate(f"{edit_button}.emit('clicked', 1); {INDICATOR}._urlEntry.set_text('file:///etc/passwd'); {INDICATOR}._save.emit('clicked', 1); true")
        wait(lambda: evaluate(f'{INDICATOR}._error.visible && !{INDICATOR}._pending'), 'invalid edit rejected')
        self.assertEqual(evaluate(f'{INDICATOR}._state.stations.find(station => station.id === {INDICATOR}._state.selected).url'), ServiceE2E.url + '/icy')
        evaluate(f"{INDICATOR}._urlEntry.set_text('{ServiceE2E.url}/station.xspf'); {INDICATOR}._save.emit('clicked', 1); true")
        wait(lambda: evaluate(f"{INDICATOR}._state.status === 'Playing' && {INDICATOR}._state.resolvedUrl === '{ServiceE2E.url}/icy' && !{INDICATOR}._pending"), 'XSPF edit playing')
        self.assertEqual(evaluate(f'{INDICATOR}._state.stations.find(station => station.id === {INDICATOR}._state.selected).url'), ServiceE2E.url + '/station.xspf')
        wait(lambda: evaluate(f"{INDICATOR}._title.text === 'First song'"), 'XSPF song metadata displayed')
        other = call(BUS, APP, IFACE, 'AddStation', GLib.Variant('(ss)', ('Other radio', ServiceE2E.url + '/station.m3u')))[0]
        wait(lambda: evaluate(f'{INDICATOR}._stationButtons.has({json.dumps(other)})'), 'second station row')
        self.assertTrue(evaluate(f'''(() => {{
            const rows = [...{INDICATOR}._stationButtons.values()];
            return rows.every(row => row.select.has_style_class_name('popup-menu-item') &&
                !row.select._ornamentIcon.visible &&
                !row.select.has_style_class_name('button') &&
                !row.select.has_style_class_name('popup-inactive-menu-item') &&
                row.edit.has_style_class_name('icon-button') &&
                !row.edit.has_style_class_name('flat'));
        }})()'''))
        self.assertTrue(evaluate(f'''(() => {{
            const i = {INDICATOR};
            return i._state.stations.every(station => Boolean(i._stationButtons.get(station.id).marker) ===
                (station.id === i._state.selected));
        }})()'''))
        row = f'{INDICATOR}._stationButtons.get({json.dumps(other)})'
        evaluate(f'{INDICATOR}._setStationsExpanded(true); {INDICATOR}._searchButton.grab_key_focus(); true')
        time.sleep(0.2)
        pointer(0, 700)
        self.assertEqual(evaluate(f'{row}.edit.opacity'), 0)
        self.assertFalse(evaluate(f'{row}.play.reactive || {row}.remove.reactive || {row}.edit.can_focus'))
        before_width = evaluate(f'{row}.label.width')
        x, y = evaluate(f'''(() => {{const actor = {row}.select;
            const [x, y] = actor.get_transformed_position(); return [x + 20, y + actor.get_transformed_size()[1] / 2];}})()''')
        pointer(x, y)
        wait(lambda: evaluate(f'{row}.select.hover && {row}.play.opacity === 255 && {row}.edit.opacity === 255'), 'hover reveals row actions')
        self.assertEqual(evaluate(f'{row}.remove.opacity'), 255)
        self.assertTrue(evaluate(f"typeof {row}.copy === 'undefined'"))
        self.assertEqual(evaluate(f'{row}.label.width'), before_width)
        success, _filename = call('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
                                  'org.gnome.Shell.Screenshot', 'Screenshot',
                                  GLib.Variant('(bbs)', (False, False, str(Path('workspace/hover.png').resolve()))))
        self.assertTrue(success, 'Hover actions screenshot')
        pointer(0, 700)
        wait(lambda: evaluate(f'''[{row}.play, {row}.edit, {row}.remove]
            .every(button => button.opacity === 0 && !button.reactive && !button.can_focus)'''),
             'leaving a hovered row hides actions despite native focus retention')
        click(f'{row}.label')
        wait(lambda: evaluate(f'!{INDICATOR}._pending'), 'pointer-selected station settles')
        pointer(0, 700)
        wait(lambda: evaluate(f'''[...{INDICATOR}._stationButtons.values(), ...{INDICATOR}._recentButtons.values()]
            .every(row => [row.play, row.edit, row.remove].every(button => button.opacity === 0))'''),
             'leaving a selected row hides actions in both lists')
        recent_row = f'{INDICATOR}._recentButtons.get({INDICATOR}._state.selected)'
        click(f'{recent_row}.label')
        wait(lambda: evaluate(f'!{INDICATOR}._pending'), 'Recent pointer selection settles')
        x, y = evaluate(f'{INDICATOR}._recentHeading.get_transformed_position()')
        pointer(x + 5, y + 5)
        wait(lambda: evaluate(f'''[{recent_row}.play, {recent_row}.edit, {recent_row}.remove]
            .every(button => button.opacity === 0 && !button.reactive && !button.can_focus)'''),
             'moving from Recent to a heading hides its retained row actions')
        success, _filename = call('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
            'org.gnome.Shell.Screenshot', 'Screenshot', GLib.Variant('(bbs)',
                (False, False, str(Path('workspace/row-actions-hidden.png').resolve()))))
        self.assertTrue(success)
        evaluate(f'{row}.select.grab_key_focus(); true')
        self.assertTrue(evaluate(f'{row}.play.can_focus && {row}.edit.opacity === 255'))
        evaluate(f'{row}.edit.grab_key_focus(); true')
        self.assertEqual(evaluate(f'{row}.edit.opacity'), 255)
        evaluate(f'{INDICATOR}._searchButton.grab_key_focus(); true')
        self.assertEqual(evaluate(f'{row}.edit.opacity'), 0)
        playing_row = f'{INDICATOR}._stationButtons.get({json.dumps(identifier)})'
        evaluate(f"{playing_row}.play.emit('clicked', 1); true")
        wait(lambda: evaluate(f"!{INDICATOR}._pending && {INDICATOR}._state.status === 'Playing'"),
             'playing row action reconnects after pointer selection')
        self.assertEqual(evaluate(f'{INDICATOR}._state.status'), 'Playing')
        evaluate(f"{INDICATOR}._play.emit('clicked', 1); true")
        wait(lambda: evaluate(f"{INDICATOR}._state.status === 'Paused' && !{INDICATOR}._pending"), 'pause before row Play')
        evaluate(f"{playing_row}.play.emit('clicked', 1); true")
        wait(lambda: evaluate(f"{INDICATOR}._state.status === 'Playing' && !{INDICATOR}._pending"), 'row Play resumes without toggling playback')
        evaluate(f"{INDICATOR}._play.emit('clicked', 1); true")
        wait(lambda: evaluate(f"{INDICATOR}._state.status === 'Paused' && !{INDICATOR}._pending"), 'pause before switching with row Play')
        evaluate(f"{row}.play.emit('clicked', 1); true")
        wait(lambda: evaluate(f"{INDICATOR}._state.selected === {json.dumps(other)} && {INDICATOR}._state.status === 'Playing' && !{INDICATOR}._pending"), 'row Play switches and starts while paused')
        evaluate(f"{playing_row}.play.emit('clicked', 1); true")
        wait(lambda: evaluate(f"{INDICATOR}._state.selected === {json.dumps(identifier)} && {INDICATOR}._state.status === 'Playing' && !{INDICATOR}._pending"), 'row Play switches while playing')
        self.assertTrue(evaluate(f'''(() => {{
            const i = {INDICATOR};
            return i._state.stations.every(station => {{
                const row = i._stationButtons.get(station.id).select;
                const label = row.get_children().find(child => child.has_style_class_name('gnome-radio-station-content'));
                const expected = station.name + (station.id === i._state.selected && i._state.status === 'Playing' ? ' (playing)' : '');
                return label.text === expected && !label.text.includes(station.url) &&
                    !row.get_children().some(child => child.has_style_class_name('radio-source'));
            }});
        }})()'''))
        evaluate(f"{INDICATOR}._stationButtons.get({json.dumps(other)}).edit.emit('clicked', 1); true")
        self.assertEqual(evaluate(f'{INDICATOR}._state.selected'), identifier)
        key(ord('x'))
        self.assertEqual(evaluate(f'{INDICATOR}._nameEntry.get_text()'), 'Other radiox')
        self.assertFalse(evaluate(f'{INDICATOR}._searchEntry.visible'))
        evaluate(f"{INDICATOR}._nameEntry.set_text('Unsaved'); {INDICATOR}._cancel.emit('clicked', 1); true")
        self.assertEqual(evaluate(f'{INDICATOR}._state.stations[1].name'), 'Other radio')
        evaluate(f'{INDICATOR}._setStationsExpanded(false); {INDICATOR}._expandButton.grab_key_focus(); true')
        time.sleep(0.2)
        closed_toolbar = toolbar_geometry()
        key(ord('o'))
        wait(lambda: evaluate(f"{INDICATOR}._searchEntry.get_text() === 'o' && {INDICATOR}._stationContainer.visible"), 'typing opens search and retains first character')
        key(ord('t'))
        self.assertEqual(toolbar_geometry(), closed_toolbar, 'Opening search must not move controls or change padding')
        self.assertEqual(evaluate(f'{INDICATOR}._searchEntry.get_text()'), 'ot')
        self.assertEqual(evaluate(f'{INDICATOR}._stationButtons.size'), 1)
        evaluate(f"{INDICATOR}._searchEntry.emit('secondary-icon-clicked'); true")
        self.assertEqual(evaluate(f'{INDICATOR}._searchEntry.get_text()'), '')
        self.assertEqual(evaluate(f'{INDICATOR}._stationButtons.size'), 2)
        evaluate(f"{INDICATOR}._searchButton.emit('clicked', 1); {INDICATOR}._expandButton.grab_key_focus(); true")
        key(ord('f'), control=True)
        self.assertTrue(evaluate(f'{INDICATOR}._searchEntry.visible'))
        key(0xff1b)
        wait(lambda: evaluate(f'!{INDICATOR}.menu.isOpen && !{INDICATOR}._searchEntry.visible'), 'Escape closes popup and resets search')
        evaluate(f'{INDICATOR}.menu.open(); {INDICATOR}._expandButton.grab_key_focus(); true')
        key(ord('f'), control=True)
        evaluate(f"{INDICATOR}._searchEntry.set_text('OTHER'); true")
        self.assertTrue(evaluate(f'{INDICATOR}._searchEntry.visible'))
        self.assertTrue(evaluate(f'{INDICATOR}._searchEntry.get_parent() === {INDICATOR}._toolbar'))
        self.assertTrue(evaluate(f"{INDICATOR}._searchButton.has_style_class_name('icon-button')"))
        time.sleep(0.2)
        focused_search = entry_style(f'{INDICATOR}._searchEntry')
        self.assertEqual(focused_search['backgroundAlpha'], 255)
        self.assertEqual(focused_search['height'], evaluate(f'{INDICATOR}._searchButton.height'))
        evaluate(f'{INDICATOR}._expandButton.grab_key_focus(); true')
        time.sleep(0.2)
        self.assertEqual(entry_style(f'{INDICATOR}._searchEntry'), focused_search, 'Search focus must not change dimensions or padding')
        evaluate(f"{INDICATOR}._stationButtons.get({json.dumps(other)}).edit.emit('clicked', 1); true")
        wait(lambda: entry_style(f'{INDICATOR}._nameEntry') == focused_search,
             'remapped editor receives current typography and allocation')
        self.assertEqual(entry_style(f'{INDICATOR}._nameEntry'), focused_search, 'Search and name inputs must share native geometry/style')
        self.assertEqual(entry_style(f'{INDICATOR}._urlEntry'), focused_search, 'Search and URL inputs must share native geometry/style')
        evaluate(f"{INDICATOR}._cancel.emit('clicked', 1); {INDICATOR}._searchButton.emit('clicked', 1); {INDICATOR}._searchEntry.set_text('OTHER'); true")
        time.sleep(0.2)
        x, y = evaluate(f'''(() => {{const actor = {INDICATOR}._searchEntry;
            const [x, y] = actor.get_transformed_position(); return [x + actor.get_transformed_size()[0] / 2, y + actor.get_transformed_size()[1] / 2];}})()''')
        pointer(x, y)
        self.assertEqual(entry_style(f'{INDICATOR}._searchEntry'), focused_search, 'Search hover must not change dimensions or padding')
        pointer(0, 700)
        evaluate(f'{INDICATOR}._searchEntry.grab_key_focus(); true')
        self.assertTrue(evaluate(f'''(() => {{
            const i = {INDICATOR};
            const center = actor => actor.get_transformed_position()[1] + actor.get_transformed_size()[1] / 2;
            return Math.abs(center(i._searchEntry) - center(i._searchButton)) < 2 &&
                Math.abs(center(i._stationsHeading) - center(i._searchButton)) < 2 &&
                i._stationsHeading.get_next_sibling() === i._expandButton &&
                i._searchEntry.get_transformed_position()[0] + i._searchEntry.width <=
                i._searchButton.get_transformed_position()[0];
        }})()'''))
        success, _filename = call('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
                                  'org.gnome.Shell.Screenshot', 'Screenshot',
                                  GLib.Variant('(bbs)', (False, False, str(Path('workspace/search.png').resolve()))))
        self.assertTrue(success, 'Inline search screenshot')
        assert_separator_spacing()
        self.assertEqual(evaluate(f'{INDICATOR}._stationButtons.size'), 1)
        self.assertTrue(evaluate(f'{INDICATOR}._stationButtons.has({json.dumps(other)})'))
        self.assertEqual(evaluate(f'{INDICATOR}._state.selected'), identifier)
        evaluate(f"{INDICATOR}._searchEntry.set_text('not a saved station'); true")
        self.assertEqual(evaluate(f'{INDICATOR}._stationButtons.size'), 0)
        evaluate(f"{INDICATOR}._searchEntry.set_text('/station.m3u'); true")
        self.assertEqual(evaluate(f'{INDICATOR}._stationButtons.size'), 1)
        evaluate(f"{INDICATOR}._stationButtons.get({json.dumps(other)}).select.emit('activate', null); true")
        wait(lambda: evaluate(f"{INDICATOR}._name.text === 'Other radio' && {INDICATOR}._state.status === 'Playing'"), 'selection from search results')
        evaluate(f"{INDICATOR}._searchButton.emit('clicked', 1); true")
        self.assertFalse(evaluate(f'{INDICATOR}._searchEntry.visible'))
        self.assertEqual(evaluate(f'{INDICATOR}._stationButtons.size'), 2)
        evaluate(f"{INDICATOR}._stationButtons.get({json.dumps(identifier)}).select.emit('activate', null); true")
        wait(lambda: evaluate(f"{INDICATOR}._name.text === 'Edited radio' && {INDICATOR}._title.text === 'First song'"), 'restore radio after search')
        self.assertTrue(evaluate(f'{INDICATOR}._name.get_theme_node().get_foreground_color().to_string() === {INDICATOR}.menu.actor.get_theme_node().get_foreground_color().to_string()'))
        evaluate(f'{INDICATOR}.menu.open(); true')
        evaluate(f'{INDICATOR}._setStationsExpanded(true); true')
        time.sleep(0.2)
        self.assertTrue(evaluate(f'''(() => {{
            const center = actor => actor.get_transformed_position()[1] + actor.get_transformed_size()[1] / 2;
            return [...{INDICATOR}._stationButtons.values()].every(row => {{
                const label = row.select.get_children().find(child => child.has_style_class_name('gnome-radio-station-content'));
                return Math.abs(center(label) - center(row.edit)) < 2;
            }});
        }})()'''))
        self.assertTrue(evaluate(f'''(() => {{
            const i = {INDICATOR};
            const rows = [...i._stationButtons.values()];
            return [i._searchButton, i._add, ...rows.map(row => row.edit)].every(button =>
                button.height < i._play.height * 0.8) &&
                rows.every(row => row.select.height <= row.edit.height + 8);
        }})()'''))
        self.assertTrue(evaluate(f'''(() => {{
            const i = {INDICATOR};
            return i._details.height < 1.5 * (i._name.height + i._title.height);
        }})()'''))
        screenshot = str(Path('workspace/popup.png').resolve())
        assert_separator_spacing()
        success, _filename = call('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
                                  'org.gnome.Shell.Screenshot', 'Screenshot',
                                  GLib.Variant('(bbs)', (False, False, screenshot)))
        self.assertTrue(success, 'Popup screenshot')
        call(BUS, APP, IFACE, 'SetNotifications', GLib.Variant('(b)', (True,)))
        media_card = ("Main.panel.statusArea.dateMenu._messageList._messageView.messages.find("
                      "message => message._player?._busName === 'org.mpris.MediaPlayer2.GnomeRadio')")
        wait(lambda: evaluate(f"Boolean({media_card})"), 'native persistent media card')
        evaluate(f'global._radioMediaCard = {media_card}; true')
        self.assertFalse(evaluate('global._radioMediaCard.canClose()'))
        Streams.title = 'Fixture artist - Next song'
        wait(lambda: evaluate(f"{INDICATOR}._title.text === 'Fixture artist — Next song'"), 'artist and title on one row')
        wait(lambda: evaluate("global._radioMediaCard.title === 'Next song' && "
                              "global._radioMediaCard.body === 'Fixture artist'"), 'media card metadata updated')
        self.assertTrue(evaluate(f'{media_card} === global._radioMediaCard'))
        self.assertFalse(evaluate("Main.messageTray.getSources().some(source => source.title === 'radiolina')"))
        self.assertFalse(evaluate("Main.messageTray._notification?.source?.title === 'radiolina'"))
        self.assertFalse(evaluate("Main.messageTray._notificationQueue.some(notification => notification.source.title === 'radiolina')"))
        self.assertTrue(evaluate(f"typeof {INDICATOR}._notificationSource === 'undefined'"))
        evaluate(f'{INDICATOR}.menu.open(); true')
        time.sleep(0.2)
        self.assertTrue(evaluate(f'''(() => {{
            const i = {INDICATOR};
            return !i._title.clutter_text.line_wrap &&
                i._details.height < 1.5 * (i._name.height + i._title.height);
        }})()'''))
        success, _filename = call('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
                                  'org.gnome.Shell.Screenshot', 'Screenshot',
                                  GLib.Variant('(bbs)', (False, False, str(Path('workspace/artist.png').resolve()))))
        self.assertTrue(success, 'Artist infobox screenshot')
        assert_separator_spacing()
        evaluate(f'{INDICATOR}.menu.close(); Main.panel.statusArea.dateMenu.menu.open(); true')
        time.sleep(0.3)
        success, _filename = call('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
                                  'org.gnome.Shell.Screenshot', 'Screenshot',
                                  GLib.Variant('(bbs)', (False, False, str(Path('workspace/media-center.png').resolve()))))
        self.assertTrue(success, 'Persistent native media card screenshot')
        evaluate(f'Main.panel.statusArea.dateMenu.menu.close(); {INDICATOR}.menu.open(); true')
        Streams.title = 'Song without artist'
        wait(lambda: evaluate(f"{INDICATOR}._title.text === 'Song without artist'"), 'next track clears artist')
        self.assertEqual(evaluate(f'{INDICATOR}._state.artist'), '')
        evaluate(f"{INDICATOR}._play.emit('clicked', 1); true")
        wait(lambda: evaluate(f"{INDICATOR}._state.status === 'Paused'"), 'pause from popup')
        self.assertFalse(evaluate(f'{INDICATOR}._recentButtons.get({json.dumps(identifier)}).label.text.endsWith(" (playing)")'))
        self.assertEqual(evaluate(f'{INDICATOR}._recentButtons.get({json.dumps(identifier)}).marker.icon_name'), 'media-playback-pause-symbolic')
        self.assertTrue(evaluate(f'{media_card} === global._radioMediaCard'))
        self.assertEqual(evaluate(f'{INDICATOR}._icon.gicon.get_file().get_basename()'), 'radio-symbolic.svg')
        self.assertTrue(evaluate(f"!{INDICATOR}._icon.get_transition('radio-playback') && {INDICATOR}._icon.opacity === 255"))
        evaluate("global._radioMediaCard._playPauseButton.emit('clicked', 1); true")
        wait(lambda: evaluate(f"{INDICATOR}._state.status === 'Playing'"), 'resumed playback')
        self.assertEqual(evaluate(f'{INDICATOR}._icon.gicon.get_file().get_basename()'), 'radio-active-symbolic.svg')
        call(BUS, '/org/mpris/MediaPlayer2', 'org.mpris.MediaPlayer2.Player', 'Stop')
        wait(lambda: evaluate(f"{INDICATOR}._state.status === 'Stopped'"), 'stop reflected in panel')
        time.sleep(0.2)
        self.assertEqual(evaluate(f'{INDICATOR}._details.height'), info_height)
        self.assertEqual(evaluate(f'{INDICATOR}._icon.gicon.get_file().get_basename()'), 'radio-symbolic.svg')
        self.assertTrue(evaluate(f"!{INDICATOR}._icon.get_transition('radio-playback') && {INDICATOR}._icon.opacity === 255"))
        evaluate(f"{INDICATOR}._play.emit('clicked', 1); true")
        wait(lambda: evaluate(f"{INDICATOR}._state.status === 'Playing'"), 'playback after stop')
        evaluate(f'{INDICATOR}.menu.close(); {INDICATOR}.menu.open(); true')
        self.assertEqual(evaluate(f'{INDICATOR}._quitButton.accessible_name'), 'Quit radiolina')
        self.assertFalse(evaluate(f'{INDICATOR}._settingsSection.actor.visible'))
        self.assertEqual(evaluate(f'{INDICATOR}.menu.actor.width'), popup_width)
        panel_click(f'{INDICATOR}._quitButton')
        wait(lambda: evaluate(f'!{INDICATOR}'), 'pointer Quit removes the indicator while playing')
        self.assertFalse(evaluate(f"new Gio.Settings({{schema_id: 'org.gnome.shell'}}).get_strv('enabled-extensions').includes('{UUID}')"),
                         'Quit must persistently disable radiolina')
        wait(lambda: not call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                             'org.freedesktop.DBus', 'NameHasOwner',
                             GLib.Variant('(s)', (BUS,)))[0], 'playback process stopped')
        evaluate(f"Main.extensionManager.enableExtension('{UUID}'); true")
        wait(lambda: evaluate(f"{INDICATOR}?._name.text === 'Edited radio'"), 'clean re-enable and edit persistence')
        self.assertTrue(standalone_panel(), 'Pre-existing indicators must not become implicit grouping hosts')
        self.assertEqual(other_panel_placement(), other_placement, 'radiolina restart must preserve panel order')
        self.assertTrue(evaluate(f'{INDICATOR}._groupToggle.state'), 'Grouping preference persists across service/UI restart')
        self.assertFalse(evaluate(f'{INDICATOR}._stationContainer.visible'))
        wait(lambda: evaluate(f'{INDICATOR}._recentButtons.size > 0'), 'recent rows persisted')
        self.assertEqual(evaluate(f'{INDICATOR}._icon.gicon.get_file().get_basename()'), 'radio-symbolic.svg')
        evaluate(f"{INDICATOR}.menu.open(); {INDICATOR}._recentButtons.get({json.dumps(identifier)}).select.emit('activate', null); true")
        wait(lambda: evaluate(f"{INDICATOR}._state.status === 'Playing'"), 'play from recent station row')
        evaluate(f'{INDICATOR}.menu.close(); {INDICATOR}.menu.open(); true')
        self.assertFalse(evaluate(f'{INDICATOR}._stationContainer.visible'))
        time.sleep(0.2)
        success, _filename = call('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
                                  'org.gnome.Shell.Screenshot', 'Screenshot',
                                  GLib.Variant('(bbs)', (False, False, str(Path('workspace/recent.png').resolve()))))
        self.assertTrue(success, 'Recent stations with collapsed saved list')
        assert_separator_spacing()
        # Actual pointer/keyboard input, rather than signal emission, exercises
        # GNOME's automatic menu dismissal and parent click-gesture handling.
        click(f'{INDICATOR}._expandButton')
        click(f'{INDICATOR}._stationButtons.get({json.dumps(other)}).label')
        wait(lambda: evaluate(f'{INDICATOR}._state.selected === {json.dumps(other)} && !{INDICATOR}._pending'), 'pointer selection keeps popup')
        self.assertTrue(evaluate(f'{INDICATOR}._stationContainer.visible'))
        evaluate(f'{INDICATOR}._stationButtons.get({json.dumps(identifier)}).select.grab_key_focus(); true')
        key(0xff0d)
        wait(lambda: evaluate(f'{INDICATOR}._state.selected === {json.dumps(identifier)} && !{INDICATOR}._pending'), 'keyboard selection keeps popup')
        self.assertTrue(evaluate(f'{INDICATOR}.menu.isOpen && {INDICATOR}._stationContainer.visible'))
        evaluate(f'{INDICATOR}._stationButtons.get({json.dumps(other)}).select.grab_key_focus(); true')
        click(f'{INDICATOR}._stationButtons.get({json.dumps(other)}).play')
        wait(lambda: evaluate(f'{INDICATOR}._state.selected === {json.dumps(other)} && !{INDICATOR}._pending'), 'pointer row Play')
        evaluate(f'{INDICATOR}._stationButtons.get({json.dumps(identifier)}).select.grab_key_focus(); true')
        click(f'{INDICATOR}._stationButtons.get({json.dumps(identifier)}).edit')
        self.assertTrue(evaluate(f'{INDICATOR}._form.visible'))
        click(f'{INDICATOR}._copySource')
        click(f'{INDICATOR}._settingsButton')
        self.assertTrue(evaluate(f'{INDICATOR}._settingsSection.actor.visible && !{INDICATOR}._form.visible'))
        click(f'{INDICATOR}._add')
        self.assertTrue(evaluate(f'{INDICATOR}._form.visible && !{INDICATOR}._settingsSection.actor.visible'))
        click(f'{INDICATOR}._expandButton')
        self.assertTrue(evaluate(f'{INDICATOR}._stationContainer.visible && !{INDICATOR}._form.visible'))
        evaluate(f'{INDICATOR}._stationButtons.get({json.dumps(identifier)}).select.grab_key_focus(); true')
        click(f'{INDICATOR}._stationButtons.get({json.dumps(identifier)}).edit')
        click(f'{INDICATOR}._save')
        wait(lambda: evaluate(f'!{INDICATOR}._form.visible && !{INDICATOR}._pending'), 'pointer Save keeps popup')
        click(f'{INDICATOR}._add')
        click(f'{INDICATOR}._cancel')
        click(f'{INDICATOR}._searchButton')
        self.assertTrue(evaluate(f'{INDICATOR}._searchEntry.visible'))
        click(f'{INDICATOR}._searchButton')
        click(f'{INDICATOR}._settingsButton')
        self.assertFalse(evaluate(f'Boolean({INDICATOR}._playPositionToggle)'))
        click(f'{INDICATOR}._settingsButton')
        click(f'{INDICATOR}._play')
        wait(lambda: evaluate(f"{INDICATOR}._state.status === 'Paused' && !{INDICATOR}._pending"), 'pointer main Pause keeps popup')
        click(f'{INDICATOR}._play')
        wait(lambda: evaluate(f"{INDICATOR}._state.status === 'Playing' && !{INDICATOR}._pending"), 'pointer main Play keeps popup')
        stopped_owner = evaluate(f'{INDICATOR}._proxy.g_name_owner')
        stopped_selection = evaluate(f'{INDICATOR}._state.selected')
        stopped_pid = evaluate(f'{INDICATOR}._extension._process.get_identifier()')
        status_lines = Path(f'/proc/{stopped_pid}/status').read_text().splitlines()
        backend_rss = next(int(line.split()[1]) / 1024 for line in status_lines if line.startswith('VmRSS:'))
        click(f'{INDICATOR}._stopButton')
        wait(lambda: evaluate(f'!{INDICATOR}._proxy.g_name_owner && !{INDICATOR}._extension._process'),
             'Stop exits the backend while retaining the indicator')
        wait(lambda: not Path(f'/proc/{stopped_pid}').exists(), 'Stop reaps the backend process')
        print(f'Stop resource check: backend {backend_rss:.1f} MiB RSS before Stop; process absent afterward; Shell indicator retained')
        self.assertTrue(evaluate(f'''{INDICATOR}._backendIdle && {INDICATOR}._play.reactive &&
            !{INDICATOR}._stopButton.reactive && !{INDICATOR}._errorRow.visible &&
            {INDICATOR}._state.status === 'Stopped' && !{INDICATOR}._title.visible'''))
        self.assertEqual(evaluate(f'{INDICATOR}._state.selected'), stopped_selection)
        self.assertTrue(standalone_panel())
        click(f'{INDICATOR}._play')
        wait(lambda: evaluate(f"{INDICATOR}._state.status === 'Playing' && !{INDICATOR}._pending && "
                              f'{INDICATOR}._proxy.g_name_owner !== {json.dumps(stopped_owner)}'),
             'Play starts a fresh backend and reconnects after Stop')
        # Stop again while a restart is waiting for the old process to exit.
        evaluate(f'''{INDICATOR}._stopPlayback(); {INDICATOR}._play.emit('clicked', 1);
            {INDICATOR}._stopButton.emit('clicked', 1); true''')
        wait(lambda: evaluate(f'!{INDICATOR}._proxy.g_name_owner && !{INDICATOR}._extension._starting && !{INDICATOR}._pending'),
             'Stop cancels a pending restart without an orphan process')
        time.sleep(0.3)
        self.assertTrue(evaluate(f'!{INDICATOR}._extension._process && !{INDICATOR}._errorRow.visible'))
        evaluate(f'{INDICATOR}._openEditor({json.dumps(identifier)}); true')
        click(f'{INDICATOR}._save')
        wait(lambda: evaluate(f'!{INDICATOR}._pending && !{INDICATOR}._form.visible && Boolean({INDICATOR}._proxy.g_name_owner)'),
             'Editing a cached station wakes the backend after Stop')
        self.assertEqual(evaluate(f'{INDICATOR}._state.status'), 'Stopped')
        click(f'{INDICATOR}._play')
        wait(lambda: evaluate(f"{INDICATOR}._state.status === 'Playing' && !{INDICATOR}._pending"), 'resume after stopped station editing')
        pointer(20, 700)
        evaluate('global._radioPointer.notify_button(GLib.get_monotonic_time(), 1, global._radioClutter.ButtonState.PRESSED); '
                 'global._radioPointer.notify_button(GLib.get_monotonic_time(), 1, global._radioClutter.ButtonState.RELEASED); true')
        wait(lambda: evaluate(f'!{INDICATOR}.menu.isOpen'), 'outside click still dismisses popup')
        evaluate(f'{INDICATOR}.menu.open(); {INDICATOR}._setStationsExpanded(true); true')
        time.sleep(0.2)
        extra_ids = []
        for index in range(2):
            extra = call(BUS, APP, IFACE, 'AddStation', GLib.Variant('(ss)',
                         (f'Extra radio {index}', f'{ServiceE2E.url}/plain.mp3?extra={index}')))[0]
            extra_ids.append(extra)
            call(BUS, APP, IFACE, 'SelectStation', GLib.Variant('(s)', (extra,)))
            wait(lambda: evaluate(f'{INDICATOR}._state.recent[0] === {json.dumps(extra)} && '
                                  f"{INDICATOR}._state.status === 'Playing'"), 'additional recently played station')
        self.assertEqual(evaluate(f'{INDICATOR}._recentButtons.size'), 3)
        history = evaluate(f'{INDICATOR}._state.recent')
        self.assertEqual(len(history), 4)
        evaluate(f"{INDICATOR}._settingsButton.emit('clicked', 1); true")
        for expected in (2, 1):
            evaluate(f"{INDICATOR}._recentLess.emit('clicked', 1); true")
            wait(lambda: evaluate(f'{INDICATOR}._state.recentLimit === {expected} && !{INDICATOR}._pending'), 'decreased recent limit')
            self.assertEqual(evaluate(f'{INDICATOR}._recentButtons.size'), expected)
        self.assertFalse(evaluate(f'{INDICATOR}._recentLess.reactive'))
        for expected in (2, 3, 4):
            evaluate(f"{INDICATOR}._recentMore.emit('clicked', 1); true")
            wait(lambda: evaluate(f'{INDICATOR}._state.recentLimit === {expected} && !{INDICATOR}._pending'), 'increased recent limit')
        self.assertEqual(evaluate(f'{INDICATOR}._recentButtons.size'), 4)
        self.assertEqual(evaluate(f'{INDICATOR}._state.recent'), history)
        for expected in (3, 2):
            evaluate(f"{INDICATOR}._recentLess.emit('clicked', 1); true")
            wait(lambda: evaluate(f'{INDICATOR}._state.recentLimit === {expected} && !{INDICATOR}._pending'), 'recent limit saved')
        evaluate(f'{INDICATOR}._recentButtons.get({json.dumps(extra_ids[1])}).select.grab_key_focus(); true')
        click(f'{INDICATOR}._recentButtons.get({json.dumps(extra_ids[1])}).remove')
        wait(lambda: evaluate(f'!{INDICATOR}._pending && !{INDICATOR}._state.stations.some(s => s.id === {json.dumps(extra_ids[1])})'), 'remove station from Recent')
        self.assertNotIn(extra_ids[1], evaluate(f'{INDICATOR}._state.recent'))
        evaluate(f'{INDICATOR}._setStationsExpanded(true); {INDICATOR}._stationButtons.get({json.dumps(extra_ids[0])}).select.grab_key_focus(); true')
        click(f'{INDICATOR}._stationButtons.get({json.dumps(extra_ids[0])}).remove')
        wait(lambda: evaluate(f'!{INDICATOR}._pending && !{INDICATOR}._state.stations.some(s => s.id === {json.dumps(extra_ids[0])})'), 'remove station from saved list')
        evaluate(f"{INDICATOR}._stationButtons.get({json.dumps(identifier)}).play.emit('clicked', 1); true")
        wait(lambda: evaluate(f"{INDICATOR}._name.text === 'Edited radio' && {INDICATOR}._state.status === 'Playing'"), 'restore selected station after settings')
        # Load a different module in the same Shell to exercise real update-cache behavior.
        metadata_file = installed / 'metadata.json'
        metadata = json.loads(metadata_file.read_text())
        original_runtime = metadata['radio-runtime']
        original_stylesheet = metadata['radio-stylesheet']
        alternate = 'radio-000000000001.js'
        (installed / alternate).write_text((installed / original_runtime).read_text().replace("'Add station'", "'Add station (updated)'"))
        metadata['radio-runtime'] = alternate
        alternate_css = (installed / original_stylesheet).read_text().replace(
            '.gnome-radio-form-inputs { spacing: 6px; }', '.gnome-radio-form-inputs { spacing: 14px; }')
        alternate_stylesheet = f'radio-style-{hashlib.sha256(alternate_css.encode()).hexdigest()[:12]}.css'
        self.assertNotEqual(original_stylesheet, alternate_stylesheet)
        (installed / alternate_stylesheet).write_text(alternate_css)
        metadata['radio-stylesheet'] = alternate_stylesheet
        metadata_file.write_text(json.dumps(metadata))
        evaluate('global._radioSharedTheme = global._radioSt.ThemeContext.get_for_stage(global.stage).get_theme(); true')
        updater = (f"try {{ await (await import({json.dumps((root / 'scripts/live-update.js').as_uri())})).update(Main); "
                   "global._radioUpdateError = null; } catch (error) { global._radioUpdateError = String(error); throw error; }")
        evaluate(f'Main.createLookingGlass()._evaluate({json.dumps(updater)}); true')
        wait(lambda: evaluate(f"{INDICATOR}?._add.accessible_name === 'Add station (updated)' && Boolean({INDICATOR}?._proxy?.g_name_owner)"), 'fresh module live update')
        assert_cached_theme()
        self.assertEqual(evaluate(f'{INDICATOR}._name.text'), 'Edited radio')
        self.assertEqual(evaluate(f'{INDICATOR}._recentCount.text'), '2')
        self.assertTrue(evaluate(f'{INDICATOR}._details.get_children().indexOf({INDICATOR}._play) < {INDICATOR}._details.get_children().indexOf({INDICATOR}._stopButton)'))
        self.assertEqual(evaluate(f'{INDICATOR}._recentButtons.size'), 2)
        self.assertEqual(own_styles(), [alternate_stylesheet])
        evaluate(f"{INDICATOR}.menu.open(); {INDICATOR}._add.emit('clicked', 1); true")
        time.sleep(0.2)
        self.assertLess(evaluate(f'{INDICATOR}._nameEntry.width'), original_name_width,
                        'Same-session updates must load changed stylesheet contents')
        self.assertEqual(evaluate(f'{INDICATOR}.menu.actor.width'), popup_width)
        metadata['radio-runtime'] = original_runtime
        metadata['radio-stylesheet'] = original_stylesheet
        metadata_file.write_text(json.dumps(metadata))
        # During teardown the object may vanish before its bus name. The
        # updater must wait for name release rather than reject UnknownMethod.
        evaluate(f'{INDICATOR}._stopPlayback(); true')
        wait(lambda: evaluate(f'!{INDICATOR}._extension._process && !{INDICATOR}._proxy.g_name_owner'),
             'backend stopped before shutdown-race fixture')
        evaluate(f'''global._radioShutdownRaceReady = false;
            global._radioShutdownRaceOwner = Gio.bus_own_name_on_connection(Gio.DBus.session,
                '{BUS}', Gio.BusNameOwnerFlags.DO_NOT_QUEUE,
                () => {{global._radioShutdownRaceReady = true;}}, null); true''')
        wait(lambda: evaluate('global._radioShutdownRaceReady'), 'unexported shutdown owner ready')
        evaluate('''GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => {
            Gio.bus_unown_name(global._radioShutdownRaceOwner);
            return GLib.SOURCE_REMOVE;
        }); true''')
        evaluate(f'Main.createLookingGlass()._evaluate({json.dumps(updater)}); true')
        wait(lambda: evaluate(f"{INDICATOR}?._add.accessible_name === 'Add station' && Boolean({INDICATOR}?._proxy?.g_name_owner)"), 'repeat live update restores module')
        assert_cached_theme()
        self.assertEqual(own_styles(), [original_stylesheet])
        evaluate(f"{INDICATOR}.menu.open(); {INDICATOR}._add.emit('clicked', 1); true")
        time.sleep(0.2)
        self.assertEqual(evaluate(f'{INDICATOR}._nameEntry.width'), original_name_width)
        evaluate(f'{INDICATOR}.menu.open(); true')
        time.sleep(0.2)
        assert_theme_variants('after-update')
        # Shell light/dark changes legitimately replace the theme. Cache the new
        # object before Radio operations, then add an unrelated unaddressable sheet.
        unrelated_orphan = installed.parent / 'unrelated-orphan.css'
        unrelated_orphan.write_text('.unrelated-orphan-control { padding: 3px; }')
        order_first = installed.parent / 'foreign-order-first.css'
        order_second = installed.parent / 'foreign-order-second.css'
        order_first.write_text('.foreign-order-control { padding: 2px; }')
        order_second.write_text('.foreign-order-control { padding: 5px; }')
        evaluate(f'''(() => {{
            const theme = global._radioSt.ThemeContext.get_for_stage(global.stage).get_theme();
            global._radioSharedTheme = theme;
            [{json.dumps(order_first.as_uri())}, {json.dumps(order_second.as_uri())}]
                .forEach(uri => theme.load_stylesheet(Gio.File.new_for_uri(uri)));
            const legacy = Gio.File.new_for_uri({json.dumps(unrelated_orphan.as_uri())});
            theme.load_stylesheet(legacy); theme.load_stylesheet(legacy); theme.unload_stylesheet(legacy);
            const own = global._radioLegacyStyles[0];
            theme.load_stylesheet(own); theme.load_stylesheet(own);
            global._radioForeignStyles = () => global._radioSharedTheme.get_custom_stylesheets()
                .filter(file => file && !file.has_prefix(Gio.File.new_for_path({json.dumps(str(installed))})))
                .map(file => file.get_uri()).sort();
            global._radioForeignBefore = global._radioForeignStyles();
            global._radioUnknownBefore = theme.get_custom_stylesheets().filter(file => !file).length;
            global._radioOrphanProbe = new global._radioSt.Widget({{style_class: 'unrelated-orphan-control'}});
            Main.uiGroup.add_child(global._radioOrphanProbe);
            global._radioOrphanPadding = global._radioOrphanProbe.get_theme_node().get_horizontal_padding();
            global._radioOrderProbe = new global._radioSt.Widget({{style_class: 'foreign-order-control'}});
            Main.uiGroup.add_child(global._radioOrderProbe);
            global._radioOrderPadding = global._radioOrderProbe.get_theme_node().get_horizontal_padding();
        }})(); true''')
        self.assertTrue(evaluate('global._radioSt.ThemeContext.get_for_stage(global.stage).get_theme().get_custom_stylesheets().some(file => !file)'))
        self.assertGreater(evaluate('global._radioOrphanPadding'), 0)

        def assert_foreign_styles():
            assert_cached_theme()
            self.assertEqual(evaluate('global._radioForeignStyles()'), evaluate('global._radioForeignBefore'),
                             'Foreign stylesheet registrations must remain intact')
            self.assertTrue(evaluate('global._radioSharedTheme.get_custom_stylesheets().filter(file => !file).length >= global._radioUnknownBefore'),
                            'Radio must not discard unidentified entries')
            self.assertEqual(evaluate('global._radioOrphanProbe.get_theme_node().get_horizontal_padding()'),
                             evaluate('global._radioOrphanPadding'), 'An unaddressable foreign rule must stay effective')
            self.assertEqual(evaluate('global._radioOrderProbe.get_theme_node().get_horizontal_padding()'),
                             evaluate('global._radioOrderPadding'), 'Foreign CSS precedence must remain intact')

        previous_owner = evaluate(f'{INDICATOR}._proxy.g_name_owner')
        evaluate(f'Main.createLookingGlass()._evaluate({json.dumps(updater)}); true')
        wait(lambda: evaluate(f'Boolean({INDICATOR}?._proxy?.g_name_owner) && '
                              f'{INDICATOR}._proxy.g_name_owner !== {json.dumps(previous_owner)}'),
             'live update with duplicate own styles and an unrelated orphan')
        assert_foreign_styles()
        self.assertEqual(own_styles(), [original_stylesheet])
        self.assertTrue(standalone_panel(), 'Live updates must preserve independent ownership')
        self.assertEqual(other_panel_placement(), other_placement, 'Live updates must preserve panel order')
        self.assertTrue(evaluate(f'{INDICATOR}._groupToggle.state'))
        previous_owner = evaluate(f'{INDICATOR}._proxy.g_name_owner')
        evaluate(f"Main.extensionManager.disableExtension('{UUID}'); "
                 f"Main.extensionManager.enableExtension('{UUID}'); true")
        wait(lambda: evaluate(f'Boolean({INDICATOR}?._proxy?.g_name_owner) && '
                              f'{INDICATOR}._proxy.g_name_owner !== {json.dumps(previous_owner)}'),
             'rapid toggle starts a new service owner')
        assert_foreign_styles()
        self.assertTrue(standalone_panel(), 'radiolina starting after other indicators must stay separate')
        # Reproduce the reported duplicate actor conflict, then verify live repair.
        evaluate(f"Main.extensionManager.createExtensionObject('{UUID}', "
                 f"Gio.File.new_for_path({json.dumps(str(installed))}), 2); "
                 f"Main.extensionManager.loadExtension(Main.extensionManager.lookup('{UUID}')); true")
        wait(lambda: evaluate(f"Boolean(Main.extensionManager.lookup('{UUID}').error)"), 'duplicate actor error reproduced')
        assert_foreign_styles()
        repair = f"(await import({json.dumps((root / 'scripts/live-recover.js').as_uri())})).recover(Main)"
        evaluate(f'Main.createLookingGlass()._evaluate({json.dumps(repair)}); true')
        wait(lambda: evaluate(f"!Main.extensionManager.lookup('{UUID}').error && "
                              f'Boolean({INDICATOR}?._proxy?.g_name_owner)'), 'live duplicate recovery')
        assert_foreign_styles()
        self.assertTrue(standalone_panel(), 'Error recovery must preserve other indicators')
        self.assertEqual(other_panel_placement(), other_placement, 'Error recovery must preserve panel order')
        evaluate(f'{INDICATOR}.menu.open(); {INDICATOR}._settingsButton.emit("clicked", 1); true')
        click(f'{INDICATOR}._groupToggle')
        wait(lambda: evaluate(f'!{INDICATOR}._state.groupWithAppIndicators && !{INDICATOR}._pending'), 'Disable grouping after error recovery')
        self.assertTrue(standalone_panel())
        call(BUS, APP, IFACE, 'Quit')
        wait(lambda: not call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                             'org.freedesktop.DBus', 'NameHasOwner',
                             GLib.Variant('(s)', (BUS,)))[0], 'service unavailable before keyboard Quit')
        wait(lambda: evaluate(f'!{INDICATOR}._proxy.g_name_owner && !{INDICATOR}._extension._process'),
             'Shell processes the service loss before keyboard navigation')
        pointer(20, 700)
        evaluate(f'{INDICATOR}._quitButton.grab_key_focus(); true')
        wait(lambda: evaluate(f'global.stage.get_key_focus() === {INDICATOR}._quitButton'), 'Quit button has keyboard focus')
        key(0xff0d)
        wait(lambda: evaluate(f'!{INDICATOR}'), 'keyboard Quit works without the playback service')
        assert_foreign_styles()
        evaluate('global._radioOrphanProbe.destroy(); global._radioOrderProbe.destroy(); true')
        wait(lambda: evaluate(f'''{json.dumps(PEERS)}.every(role =>
            Main.panel.statusArea[role]?.container.get_parent() === Main.panel._rightBox)'''), 'radiolina disable preserves the other indicators')
        self.assertEqual(other_panel_placement(), other_placement, 'radiolina disable must preserve panel order')
        self.assertTrue(evaluate('global._radioSystemParents.every(([role, parent]) => Main.panel.statusArea[role].container.get_parent() === parent)'),
                        'Native indicators must retain their original containers through recovery and disable')
        for role in PEERS:
            evaluate(f"Main.extensionManager.disableExtension('{role}'); true")
        self.assertEqual(own_styles(), [])
        self.assertTrue(evaluate('global._radioSt.ThemeContext.get_for_stage(global.stage).get_theme().get_custom_stylesheets().some(file => file?.equal(global._radioUnrelatedStyle))'))
        evaluate('global._radioSt.ThemeContext.get_for_stage(global.stage).get_theme().unload_stylesheet(global._radioUnrelatedStyle); true')
        saved_before_uninstall = saved_file.read_bytes()
        # The CLI forwards through GNOME's separate management service. Start it
        # explicitly on our private bus/display; host service activation stays off.
        management_script = next(Path(directory) / 'gnome-shell/org.gnome.Shell.Extensions'
                                 for directory in GLib.get_system_data_dirs()
                                 if (Path(directory) / 'gnome-shell/org.gnome.Shell.Extensions').is_file())
        sockets = [path for path in Path(os.environ['XDG_RUNTIME_DIR']).glob('wayland-*') if path.is_socket()]
        self.assertEqual(len(sockets), 1, 'The test must have one private Wayland display')
        management_env = dict(os.environ, WAYLAND_DISPLAY=sockets[0].name, GDK_BACKEND='wayland')
        management = subprocess.Popen(['gjs', '-m', str(management_script)], env=management_env,
                                      stdout=log, stderr=log)
        try:
            wait(lambda: call('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                              'NameHasOwner', GLib.Variant('(s)', ('org.gnome.Shell.Extensions',)))[0],
                 'private GNOME extension-management service ready')
            result = subprocess.run(['gnome-extensions', 'uninstall', UUID],
                                    text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        finally:
            if management.poll() is None:
                management.terminate()
                try:
                    management.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    management.kill()
                    management.wait(timeout=5)
        self.assertFalse(installed.exists(), 'Uninstall must remove extension files')
        self.assertEqual(saved_file.read_bytes(), saved_before_uninstall,
                         'Uninstall must preserve saved stations and settings')
        self.assertFalse(evaluate(f'Boolean({INDICATOR})'))
        self.assertFalse(call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                              'org.freedesktop.DBus', 'NameHasOwner',
                              GLib.Variant('(s)', (BUS,)))[0], 'Uninstall must leave no playback service')


if __name__ == '__main__':
    unittest.main(defaultTest='ShellE2E', verbosity=2)
