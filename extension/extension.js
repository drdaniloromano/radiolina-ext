// SPDX-License-Identifier: MIT
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const BUS = 'org.mpris.MediaPlayer2.GnomeRadio';
const PATH = '/org/gnome/Radio';
// First-use GStreamer registry discovery can take over a minute on a small VM.
// This is a cancellable readiness deadline, not a delay or a recurring timer.
const SERVICE_START_TIMEOUT_MS = 120_000;

const RadioIndicator = GObject.registerClass({
    GTypeName: `RadiolinaIndicator_${GLib.compute_checksum_for_string(GLib.ChecksumType.SHA256, import.meta.url, -1).slice(0, 16)}`,
},
class RadioIndicator extends PanelMenu.Button {
    _init(extension) {
        super._init(0.0, 'radiolina');
        this.add_style_class_name('gnome-radio-indicator');
        this.menu.box.add_style_class_name('gnome-radio-popup');
        this._alive = true;
        this._extension = extension;
        this._backendIdle = false;
        this._callGeneration = 0;
        this._pending = false;
        this._editingId = null;
        this._stationButtons = new Map();
        this._recentButtons = new Map();
        this._stationsExpanded = false;
        this._cancellable = new Gio.Cancellable();
        this._state = {stations: [], selected: '', status: 'Stopped', notifications: false};
        this._radioIcon = new Gio.FileIcon({file: extension.dir.get_child('icons').get_child('radio-symbolic.svg')});
        this._activeRadioIcon = new Gio.FileIcon({file: extension.dir.get_child('icons').get_child('radio-active-symbolic.svg')});
        this._icon = new St.Icon({gicon: this._radioIcon, style_class: 'system-status-icon'});
        this.add_child(this._icon);

        const details = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        details.remove_style_class_name('popup-inactive-menu-item');
        details.remove_style_class_name('popup-menu-item');
        details.add_style_class_name('gnome-radio-now-playing');
        this._details = details;
        const box = new St.BoxLayout({vertical: true, style_class: 'gnome-radio-details', x_expand: true,
            y_align: Clutter.ActorAlign.CENTER});
        this._name = this._label('Add your first station', 'gnome-radio-station');
        this._title = this._label('', 'gnome-radio-song');
        this._title.opacity = 178;
        [this._name, this._title].forEach(label => box.add_child(label));
        const info = new St.BoxLayout({style_class: 'gnome-radio-info-content', x_expand: true});
        info.add_child(box);
        const frame = new St.Bin({child: info, style_class: 'gnome-radio-info-frame',
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER});
        this._infoFrame = frame;
        this._playIcon = new St.Icon({icon_name: 'media-playback-start-symbolic'});
        this._playCircle = new St.Bin({child: this._playIcon, style_class: 'icon-button',
            reactive: true, can_focus: false, track_hover: false,
            y_align: Clutter.ActorAlign.CENTER});
        const playback = new St.BoxLayout({style_class: 'gnome-radio-playback-content', x_expand: true});
        playback.add_child(this._playCircle);
        playback.add_child(frame);
        this._play = new St.Button({child: playback, style_class: 'button flat gnome-radio-playback',
            x_expand: true, can_focus: true, track_hover: true, accessible_name: 'Play radio',
            y_align: Clutter.ActorAlign.CENTER});
        this._play.connect('clicked', () => this._call('PlayPause', null));
        details.add_child(this._play);
        this._stopButton = new St.Button({child: new St.Icon({icon_name: 'media-playback-stop-symbolic'}),
            style_class: 'icon-button gnome-radio-compact-button', can_focus: true,
            accessible_name: 'Stop and release playback resources', y_align: Clutter.ActorAlign.CENTER});
        this._stopButton.connect('clicked', () => this._stopPlayback());
        details.add_child(this._stopButton);
        this._quitButton = new St.Button({child: new St.Icon({icon_name: 'system-shutdown-symbolic'}),
            style_class: 'icon-button gnome-radio-compact-button', can_focus: true,
            accessible_name: 'Quit radiolina', y_align: Clutter.ActorAlign.CENTER});
        this._quitButton.connect('clicked', () => {
            if (this._quitSource) return;
            this._quitSource = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                this._quitSource = null;
                if (this._alive) Main.extensionManager.disableExtension(extension.uuid);
                return GLib.SOURCE_REMOVE;
            });
        });
        details.add_child(this._quitButton);
        this.menu.addMenuItem(details);
        this._errorRow = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        this._errorRow.remove_style_class_name('popup-inactive-menu-item');
        this._errorRow.remove_style_class_name('popup-menu-item');
        this._errorRow.add_style_class_name('gnome-radio-error-row');
        this._error = this._label('', 'gnome-radio-error');
        this._error.clutter_text.line_wrap = true;
        this._errorRow.add_child(this._error);
        this.menu.addMenuItem(this._errorRow);
        this._errorRow.hide();
        this._infoSeparator = new PopupMenu.PopupSeparatorMenuItem();
        this.menu.addMenuItem(this._infoSeparator);
        const recentHeading = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        recentHeading.remove_style_class_name('popup-inactive-menu-item');
        recentHeading.remove_style_class_name('popup-menu-item');
        recentHeading.add_style_class_name('gnome-radio-toolbar');
        recentHeading.add_style_class_name('gnome-radio-recent-heading');
        this._recentHeading = new St.Label({text: 'Recent', style_class: 'gnome-radio-section-heading'});
        recentHeading.add_child(this._recentHeading);
        this.menu.addMenuItem(recentHeading);
        this._recent = new PopupMenu.PopupMenuSection();
        this.menu.addMenuItem(this._recent);
        this._stationsSeparator = new PopupMenu.PopupSeparatorMenuItem();
        this.menu.addMenuItem(this._stationsSeparator);
        const toolbar = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        toolbar.remove_style_class_name('popup-menu-item');
        toolbar.remove_style_class_name('popup-inactive-menu-item');
        toolbar.add_style_class_name('gnome-radio-toolbar');
        toolbar.add_style_class_name('gnome-radio-stations-toolbar');
        this._toolbar = toolbar;
        this._stationsHeading = new St.Label({text: 'Stations', style_class: 'gnome-radio-section-heading',
            y_align: Clutter.ActorAlign.CENTER});
        toolbar.add_child(this._stationsHeading);
        this._expandIcon = new St.Icon({icon_name: 'pan-down-symbolic'});
        this._expandButton = new St.Button({child: this._expandIcon,
            style_class: 'icon-button gnome-radio-compact-button', can_focus: true,
            y_align: Clutter.ActorAlign.CENTER, accessible_name: 'Show saved stations'});
        this._expandButton.connect('clicked', () => this._setStationsExpanded(!this._stationsExpanded));
        toolbar.add_child(this._expandButton);
        this._toolbarSpacer = new St.Widget({x_expand: true});
        toolbar.add_child(this._toolbarSpacer);
        this._searchEntry = new St.Entry({hint_text: 'Type to search', style_class: 'gnome-radio-entry gnome-radio-search-entry',
            can_focus: true, x_expand: true, y_align: Clutter.ActorAlign.CENTER,
            accessible_name: 'Search saved stations'});
        this._searchEntry.set_primary_icon(new St.Icon({icon_name: 'edit-find-symbolic',
            style_class: 'search-entry-icon', icon_size: 16}));
        this._searchEntry.set_secondary_icon(new St.Icon({icon_name: 'edit-clear-symbolic',
            style_class: 'search-entry-icon', icon_size: 16}));
        this._searchEntry.connect('secondary-icon-clicked', () => {
            this._searchEntry.set_text('');
            this._searchEntry.grab_key_focus();
        });
        this._searchEntry.clutter_text.connect('text-changed', () => this._render());
        toolbar.add_child(this._searchEntry);
        this._searchEntry.hide();
        this._searchButton = new St.Button({child: new St.Icon({icon_name: 'edit-find-symbolic'}),
            style_class: 'icon-button gnome-radio-compact-button', can_focus: true, y_align: Clutter.ActorAlign.CENTER,
            accessible_name: 'Search saved stations'});
        this._searchButton.connect('clicked', () => this._toggleSearch());
        this._add = new St.Button({child: new St.Icon({icon_name: 'list-add-symbolic'}),
            style_class: 'icon-button gnome-radio-compact-button', can_focus: true, y_align: Clutter.ActorAlign.CENTER,
            accessible_name: 'Add station'});
        this._add.connect('clicked', () => this._openAddForm());
        toolbar.add_child(this._searchButton);
        toolbar.add_child(this._add);
        this._settingsButton = new St.Button({child: new St.Icon({icon_name: 'preferences-system-symbolic'}),
            style_class: 'icon-button gnome-radio-compact-button', can_focus: true,
            y_align: Clutter.ActorAlign.CENTER, accessible_name: 'Settings'});
        this._settingsButton.connect('clicked', () => {
            this._showView(this._settingsSection.actor.visible ? null : 'settings');
        });
        toolbar.add_child(this._settingsButton);
        this.menu.addMenuItem(toolbar);
        this._stations = new PopupMenu.PopupMenuSection();
        const stationContainer = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        stationContainer.remove_style_class_name('popup-inactive-menu-item');
        stationContainer.remove_style_class_name('popup-menu-item');
        this._stationContainer = stationContainer;
        const scroll = new St.ScrollView({style_class: 'gnome-radio-stations', x_expand: true,
            hscrollbar_policy: St.PolicyType.NEVER, vscrollbar_policy: St.PolicyType.AUTOMATIC});
        scroll.set_child(this._stations.actor);
        stationContainer.add_child(scroll);
        this.menu.addMenuItem(stationContainer);
        stationContainer.hide();

        this._settingsSection = new PopupMenu.PopupMenuSection();
        this._showStopToggle = new PopupMenu.PopupSwitchMenuItem('Show Stop button', false);
        this._showStopToggle.connect('toggled', (_item, enabled) => {
            if (!this._syncingSettings) this._call('SetShowStopButton', new GLibVariant('(b)', [enabled]));
        });
        this._settingsSection.addMenuItem(this._showStopToggle);
        this._groupToggle = new PopupMenu.PopupSwitchMenuItem('Group with other app indicators', false);
        this._groupToggle.connect('toggled', (_item, enabled) => {
            if (!this._syncingSettings) this._call('SetGroupWithAppIndicators', new GLibVariant('(b)', [enabled]));
        });
        this._settingsSection.addMenuItem(this._groupToggle);
        const helpRow = text => {
            const row = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
            const label = new St.Label({text, style_class: 'gnome-radio-setting-help', x_expand: true});
            label.clutter_text.line_wrap = true;
            label.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
            row.add_child(label);
            this._settingsSection.addMenuItem(row);
            return [row, label];
        };
        [, this._groupWarning] = helpRow('Grouping may be incompatible with some extensions or panel customizations. Disable this option if icons, menus, or clicks behave unexpectedly.');
        [this._groupUnavailableRow] = helpRow('No supported indicator group is available. radiolina stays separate.');
        const recentOption = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        recentOption.remove_style_class_name('popup-inactive-menu-item');
        recentOption.add_child(new St.Label({text: 'Recent stations', x_expand: true,
            y_align: Clutter.ActorAlign.CENTER}));
        this._recentLess = new St.Button({child: new St.Icon({icon_name: 'list-remove-symbolic'}),
            style_class: 'icon-button gnome-radio-compact-button', can_focus: true,
            accessible_name: 'Show fewer recent stations'});
        this._recentCount = new St.Label({text: '3', y_align: Clutter.ActorAlign.CENTER});
        this._recentMore = new St.Button({child: new St.Icon({icon_name: 'list-add-symbolic'}),
            style_class: 'icon-button gnome-radio-compact-button', can_focus: true,
            accessible_name: 'Show more recent stations'});
        this._recentLess.connect('clicked', () => this._call('SetRecentLimit',
            new GLibVariant('(u)', [(this._state.recentLimit ?? 3) - 1])));
        this._recentMore.connect('clicked', () => this._call('SetRecentLimit',
            new GLibVariant('(u)', [(this._state.recentLimit ?? 3) + 1])));
        [this._recentLess, this._recentCount, this._recentMore].forEach(actor => recentOption.add_child(actor));
        this._settingsSection.addMenuItem(recentOption);
        this.menu.addMenuItem(this._settingsSection);
        this._settingsSection.actor.hide();

        this._createForm();
        // St.Entry measures hidden hints too. Refresh their inherited font when
        // the theme changes, even while populated fields hide the hint actor.
        for (const entry of [this._searchEntry, this._nameEntry, this._urlEntry])
            entry.connect('style-changed', () => entry.get_hint_actor()?.ensure_style());
        // These controls update an inline panel; activation must not dismiss it.
        for (const menu of [this.menu, this._recent, this._stations, this._settingsSection])
            menu.itemActivated = () => {};
        this.menu.actor.connect('captured-event', (_actor, event) => this._searchKey(event));
        this.menu.connect('open-state-changed', (_menu, open) => {
            if (!open && this._alive) {
                this._showView(null);
            }
        });
        this._render();

        const xmlFile = extension.dir.get_child('src').get_child('service').get_child('radio.xml');
        const xml = new TextDecoder().decode(xmlFile.load_contents(null)[1]);
        const Proxy = Gio.DBusProxy.makeProxyWrapper(xml);
        this._proxy = new Proxy(Gio.DBus.session, BUS, PATH, (proxy, error) => {
            if (!this._alive)
                return;
            if (error) {
                this._showError('radiolina service unavailable. Disable and re-enable the extension to retry.');
                return;
            }
            this._propertySignal = proxy.connect('g-properties-changed', () => this._sync());
            this._ownerSignal = proxy.connect('notify::g-name-owner', () => this._sync());
            this._raiseSignal = proxy.connectSignal('Raise', () => this.menu.open());
            this._sync();
        }, this._cancellable);
    }

    _label(text, style) {
        const label = new St.Label({text, style_class: style});
        label.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        return label;
    }

    _createForm() {
        this._form = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        this._form.remove_style_class_name('popup-menu-item');
        this._form.remove_style_class_name('popup-inactive-menu-item');
        const box = new St.BoxLayout({vertical: true, style_class: 'gnome-radio-form', x_expand: true});
        this._formHeading = new St.Label({text: 'Add station', style_class: 'gnome-radio-section-heading'});
        this._nameEntry = new St.Entry({hint_text: 'Station name', can_focus: true,
            style_class: 'gnome-radio-entry gnome-radio-name-entry', accessible_name: 'Station name'});
        this._urlEntry = new St.Entry({hint_text: 'Stream, M3U or XSPF URL', can_focus: true,
            style_class: 'gnome-radio-entry gnome-radio-url-entry', x_expand: true, accessible_name: 'Station source URL'});
        const fields = new St.BoxLayout({style_class: 'gnome-radio-form-fields'});
        const inputs = new St.BoxLayout({style_class: 'gnome-radio-form-inputs', x_expand: true});
        inputs.add_child(this._nameEntry);
        inputs.add_child(this._urlEntry);
        // Divide the input space after reserving the gap and optional Copy button.
        const sizeInputs = () => {
            const width = inputs.get_allocation_box().get_width() - inputs.get_theme_node().get_length('spacing');
            if (width > 0) {
                const nameWidth = Math.round(width * 0.3);
                // Keep minimum widths flexible when Copy appears or fonts change.
                for (const [entry, share] of [[this._nameEntry, nameWidth], [this._urlEntry, width - nameWidth]]) {
                    const contentWidth = Math.max(0, share - entry.get_theme_node().get_horizontal_padding());
                    entry.set_style(`width: ${contentWidth}px; max-width: ${contentWidth}px;`);
                }
            }
        };
        inputs.connect('notify::allocation', sizeInputs);
        inputs.connect('style-changed', sizeInputs);
        fields.add_child(inputs);
        this._copySource = new St.Button({child: new St.Icon({icon_name: 'edit-copy-symbolic'}),
            style_class: 'icon-button gnome-radio-compact-button', can_focus: true,
            y_align: Clutter.ActorAlign.CENTER, accessible_name: 'Copy stream URL'});
        this._copySource.connect('clicked', () => St.Clipboard.get_default().set_text(
            St.ClipboardType.CLIPBOARD, this._urlEntry.get_text()));
        fields.add_child(this._copySource);
        this._save = new St.Button({label: 'Save', can_focus: true,
            style_class: 'button', accessible_name: 'Save station'});
        this._save.connect('clicked', () => this._saveStation());
        const actions = new St.BoxLayout({style_class: 'gnome-radio-form-actions'});
        this._cancel = new St.Button({label: 'Cancel', can_focus: true, style_class: 'button'});
        this._cancel.connect('clicked', () => this._closeForm());
        this._remove = new St.Button({label: 'Delete', can_focus: true, style_class: 'button'});
        this._remove.connect('clicked', () => {
            if (this._editingId)
                this._call('RemoveStation', new GLibVariant('(s)', [this._editingId]), () => this._closeForm());
        });
        [this._save, this._cancel, this._remove].forEach(actor => actions.add_child(actor));
        this._urlEntry.clutter_text.connect('activate', () => this._saveStation());
        this._nameEntry.clutter_text.connect('key-press-event', (_actor, event) => {
            if (event.get_key_symbol() === Clutter.KEY_Return) {
                this._urlEntry.grab_key_focus();
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        [this._formHeading, fields, actions].forEach(actor => box.add_child(actor));
        this._form.add_child(box);
        this.menu.addMenuItem(this._form);
        this._form.hide();
    }

    _saveStation() {
        const editing = this._editingId;
        const values = [this._nameEntry.get_text(), this._urlEntry.get_text()];
        this._call(editing ? 'UpdateStation' : 'AddStation',
            new GLibVariant(editing ? '(sss)' : '(ss)', editing ? [editing, ...values] : values), () => {
            this._closeForm();
        });
    }

    _closeForm() {
        if (!this._alive) return;
        this._editingId = null;
        this._form.hide();
        this._add.remove_style_pseudo_class('checked');
        this._formHeading.text = 'Add station';
        this._save.accessible_name = 'Save station';
        this._nameEntry.set_text('');
        this._urlEntry.set_text('');
        this._render();
    }

    _openAddForm() {
        if (this._pending) return;
        this._closeForm();
        this._showView('form');
        this.menu.open();
        this._nameEntry.grab_key_focus();
    }

    _toggleSearch() {
        const show = !this._searchEntry.visible;
        this._searchEntry.visible = show;
        this._toolbarSpacer.visible = !show;
        if (show) {
            this._setStationsExpanded(true);
            this._searchButton.add_style_pseudo_class('checked');
            this._searchEntry.grab_key_focus();
        } else {
            this._searchButton.remove_style_pseudo_class('checked');
            this._searchEntry.set_text('');
        }
        this._render();
    }

    _searchKey(event) {
        if (!this.menu.isOpen || event.type() !== Clutter.EventType.KEY_PRESS)
            return Clutter.EVENT_PROPAGATE;
        const focus = global.stage.get_key_focus();
        // Preserve normal editing, including compose/IME input, in every text field.
        if ([this._nameEntry, this._urlEntry, this._searchEntry].some(entry => focus && entry.contains(focus)))
            return Clutter.EVENT_PROPAGATE;
        const key = event.get_key_symbol();
        const modifiers = event.get_state();
        const control = modifiers & Clutter.ModifierType.CONTROL_MASK;
        if (modifiers & (Clutter.ModifierType.MOD1_MASK | Clutter.ModifierType.SUPER_MASK))
            return Clutter.EVENT_PROPAGATE;
        const find = control && (key === Clutter.KEY_f || key === Clutter.KEY_F);
        const unicode = Clutter.keysym_to_unicode(key);
        const printable = unicode && String.fromCodePoint(unicode).trim().length > 0;
        if (!find && (control || !(printable || key === Clutter.KEY_Multi_key)))
            return Clutter.EVENT_PROPAGATE;
        if (!this._searchEntry.visible) this._toggleSearch();
        this._searchEntry.grab_key_focus();
        // Forward the original event so the first character and keyboard layout survive.
        return find ? Clutter.EVENT_STOP : this._searchEntry.clutter_text.event(event, false);
    }

    _setStationsExpanded(expanded) {
        this._showView(expanded ? 'stations' : null);
    }

    _showView(view) {
        if (view !== 'form') this._closeForm();
        const expanded = view === 'stations';
        this._stationsExpanded = expanded;
        this._stationContainer.visible = expanded;
        this._expandIcon.icon_name = expanded ? 'pan-up-symbolic' : 'pan-down-symbolic';
        this._expandButton.accessible_name = expanded ? 'Hide saved stations' : 'Show saved stations';
        if (!expanded && this._searchEntry.visible) this._toggleSearch();
        this._settingsSection.actor.visible = view === 'settings';
        this._form.visible = view === 'form';
        for (const [button, active] of [[this._add, view === 'form'], [this._settingsButton, view === 'settings']]) {
            if (active) button.add_style_pseudo_class('checked');
            else button.remove_style_pseudo_class('checked');
        }
    }

    _openEditor(id) {
        if (this._pending) return;
        const station = this._state.stations.find(item => item.id === id);
        if (!station) return;
        this._editingId = id;
        this._formHeading.text = 'Edit station';
        this._save.accessible_name = 'Save changes';
        this._nameEntry.set_text(station.name);
        this._urlEntry.set_text(station.url);
        this._render();
        this.menu.open();
        this._showView('form');
        this._nameEntry.grab_key_focus();
    }

    _call(method, params, onSuccess = null) {
        if (!this._alive || this._pending)
            return;
        const generation = ++this._callGeneration;
        this._backendIdle = false;
        this._pending = true;
        this._render();
        this._extension.startService().then(() => {
            if (!this._alive || generation !== this._callGeneration) return;
            this._proxy.call(method, params, Gio.DBusCallFlags.NONE, 5000, this._cancellable,
                (proxy, result) => {
                    if (!this._alive || generation !== this._callGeneration) return;
                    this._pending = false;
                    try {
                        proxy.call_finish(result);
                        onSuccess?.();
                        this._sync();
                    } catch (error) {
                        Gio.DBusError.strip_remote_error(error);
                        this._showError(error.message);
                        this._render(false);
                        this.menu.open();
                    }
                });
        }).catch(() => {
            if (!this._alive || generation !== this._callGeneration) return;
            this._pending = false;
            this._state.error = 'Could not start the radio service. Press Play to retry.';
            this._render();
        });
    }

    _stopPlayback() {
        this._callGeneration++;
        this._backendIdle = true;
        this._pending = false;
        this._state = {...this._state, status: 'Stopped', title: '', artist: '', error: ''};
        this._extension.stopService();
        this._render();
    }

    _sync() {
        if (this._backendIdle || !this._proxy?.g_name_owner) {
            this._state.status = 'Stopped';
            this._state.title = '';
            this._state.artist = '';
            this._state.error = this._backendIdle || this._pending || this._extension._starting ? '' :
                'radiolina service unavailable. Press Play to retry.';
        } else if (this._proxy.State) {
            this._state = JSON.parse(this._proxy.State);
        }
        this._render();
    }

    _showError(message) {
        this._error.text = message;
        this._error.visible = Boolean(message);
        this._errorRow.visible = Boolean(message);
    }

    _render(resetError = true) {
        if (!this._alive) return;
        const state = this._state;
        const station = state.stations.find(item => item.id === state.selected);
        const active = ['Playing', 'Connecting'].includes(state.status);
        const ready = !this._pending;
        const playing = state.status === 'Playing';
        const statusIcon = playing ? this._activeRadioIcon : this._radioIcon;
        if (!this._icon.gicon.equal(statusIcon)) this._icon.gicon = statusIcon;
        this._icon.accessible_name = playing ? 'radiolina playing' : 'radiolina inactive';
        this._name.text = station?.name ?? 'Add your first station';
        this._title.text = [state.artist, state.title].filter(Boolean).join(' — ');
        this._title.visible = Boolean(station && this._title.text);
        this._playIcon.icon_name = active ? 'media-playback-pause-symbolic' : 'media-playback-start-symbolic';
        this._play.accessible_name = `${active ? 'Pause' : 'Play'} ${station?.name ?? 'radio'}`;
        // _call ignores repeats while pending. Keep the native input/focus target
        // intact until its pointer or keyboard gesture has finished.
        this._play.reactive = Boolean(station);
        this._play.can_focus = this._play.reactive;
        this._playCircle.opacity = ready && station ? 255 : 100;
        this._stopButton.visible = Boolean(state.showStopButton);
        this._stopButton.reactive = this._stopButton.visible && !this._backendIdle &&
            Boolean(this._proxy?.g_name_owner || this._extension._starting);
        this._stopButton.can_focus = this._stopButton.reactive;
        this._stopButton.opacity = this._stopButton.reactive ? 255 : 100;
        if (state.status === 'Connecting' && !state.title) {
            this._title.text = 'Connecting…';
            this._title.show();
        }
        this._add.reactive = ready;
        this._add.can_focus = ready;
        this._remove.visible = Boolean(this._editingId);
        this._copySource.visible = Boolean(this._editingId);
        this._remove.reactive = ready;
        this._save.reactive = ready;
        this._save.can_focus = ready;
        this._syncingSettings = true;
        this._showStopToggle.setToggleState(Boolean(state.showStopButton));
        this._showStopToggle.setSensitive(ready);
        this._groupToggle.setToggleState(Boolean(state.groupWithAppIndicators));
        this._groupToggle.setSensitive(ready);
        // No cooperative host integration is supported yet. A saved preference
        // never authorizes discovering, moving, or patching third-party actors.
        this._groupUnavailableRow.visible = Boolean(state.groupWithAppIndicators);
        this._syncingSettings = false;
        const recentLimit = state.recentLimit ?? 3;
        this._recentCount.text = String(recentLimit);
        for (const [button, enabled] of [[this._recentLess, recentLimit > 1], [this._recentMore, recentLimit < 10]]) {
            button.reactive = ready && enabled;
            button.can_focus = button.reactive;
            button.opacity = button.reactive ? 255 : 100;
        }
        if (resetError)
            this._showError(state.error ?? '');
        this.accessible_name = `radiolina: ${state.status}${station ? `, ${station.name}` : ''}`;
        const query = this._searchEntry.get_text().trim().normalize('NFKC').toLocaleLowerCase();
        const signature = JSON.stringify([state.stations, state.selected, state.status, state.recent, recentLimit, query]);
        if (signature !== this._stationSignature) {
            this._stationSignature = signature;
            const focus = global.stage.get_key_focus();
            const focusedRows = [this._stationButtons, this._recentButtons];
            let restoreFocus = null;
            for (const rows of focusedRows) {
                for (const [id, row] of rows) {
                    if (focus && row.select.contains(focus)) restoreFocus = {rows, id};
                    // Clear native section/parent selection before destroying actors.
                    row.select.active = false;
                }
            }
            this._stations.removeAll();
            this._stationButtons.clear();
            this._recent.removeAll();
            this._recentButtons.clear();
            const recent = (state.recent ?? []).slice(0, recentLimit)
                .map(id => state.stations.find(saved => saved.id === id)).filter(Boolean);
            for (const saved of recent) this._addStationRow(saved, this._recent, this._recentButtons);
            if (!recent.length) this._addEmptyRow(this._recent, 'No recent stations');
            for (const saved of state.stations) {
                if (query && !`${saved.name} ${saved.url}`.normalize('NFKC').toLocaleLowerCase().includes(query))
                    continue;
                this._addStationRow(saved, this._stations, this._stationButtons);
            }
            if (!this._stationButtons.size) {
                this._addEmptyRow(this._stations, query ? 'No matching stations' : 'No saved stations');
            }
            if (restoreFocus) {
                const row = restoreFocus.rows.get(restoreFocus.id) ?? restoreFocus.rows.values().next().value;
                if (row?.select.mapped) row.select.grab_key_focus();
                else this.menu.actor.grab_key_focus();
            }
        }
    }

    _addEmptyRow(section, text) {
        const item = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        item.remove_style_class_name('popup-inactive-menu-item');
        item.remove_style_class_name('popup-menu-item');
        item.add_child(new St.Label({text}));
        section.addMenuItem(item);
    }

    _addStationRow(saved, section, buttons) {
        const selected = saved.id === this._state.selected;
        const playing = selected && this._state.status === 'Playing';
        const item = new PopupMenu.PopupBaseMenuItem();
        item.add_style_class_name('gnome-radio-station-row');
        item.setOrnament(PopupMenu.Ornament.HIDDEN);
        item.accessible_name = `Select ${saved.name}${playing ? ' (playing)' : ''}`;
        item.connect('activate', () => this._call('SelectStation', new GLibVariant('(s)', [saved.id]), () => {
            if (section === this._recent && !['Playing', 'Connecting'].includes(this._state.status))
                this._call('PlayPause', null);
        }));
        let marker = null;
        if (selected) {
            const paused = this._state.status === 'Paused';
            marker = new St.Icon({icon_name: playing ? 'media-playback-start-symbolic' :
                paused ? 'media-playback-pause-symbolic' : 'media-playback-stop-symbolic',
            icon_size: 12, y_align: Clutter.ActorAlign.CENTER,
            accessible_name: playing ? 'Playing' : paused ? 'Paused' : 'Selected station'});
            item.add_child(marker);
        }
        const label = this._label(`${saved.name}${playing ? ' (playing)' : ''}`, 'gnome-radio-station-content');
        label.x_expand = true;
        label.y_align = Clutter.ActorAlign.CENTER;
        item.add_child(label);
        const play = new St.Button({child: new St.Icon({icon_name: 'media-playback-start-symbolic'}),
            can_focus: true, y_align: Clutter.ActorAlign.CENTER, style_class: 'icon-button gnome-radio-compact-button',
            accessible_name: `Play ${saved.name}`});
        play.connect('clicked', () => this._call('SelectStation', new GLibVariant('(s)', [saved.id]), () => {
            this._sync();
            if (!['Playing', 'Connecting'].includes(this._state.status)) this._call('PlayPause', null);
        }));
        const remove = new St.Button({child: new St.Icon({icon_name: 'user-trash-symbolic'}),
            can_focus: true, y_align: Clutter.ActorAlign.CENTER, style_class: 'icon-button gnome-radio-compact-button',
            accessible_name: `Remove ${saved.name}`});
        remove.connect('clicked', () => this._call('RemoveStation', new GLibVariant('(s)', [saved.id])));
        const edit = new St.Button({child: new St.Icon({icon_name: 'document-edit-symbolic'}),
            can_focus: true, y_align: Clutter.ActorAlign.CENTER, style_class: 'icon-button gnome-radio-compact-button',
            accessible_name: `Edit ${saved.name}`});
        edit.connect('clicked', () => this._openEditor(saved.id));
        item.add_child(play);
        item.add_child(edit);
        item.add_child(remove);
        const revealActions = () => {
            const focus = global.stage.get_key_focus();
            const reveal = item.hover || Boolean(focus && item.contains(focus));
            // Reserve the space to avoid moving station names when the pointer enters.
            for (const button of [play, edit, remove]) {
                button.opacity = reveal ? 255 : 0;
                button.reactive = reveal;
                button.can_focus = reveal;
            }
        };
        item.connect('notify::hover', () => {
            // Native menu hover can leave keyboard focus on the last row.
            // Hand focus back when the pointer leaves; keyboard-only navigation
            // still reveals actions through the stage's focus signal below.
            const focus = global.stage.get_key_focus();
            if (!item.hover && focus && item.contains(focus))
                this.menu.actor.grab_key_focus();
            revealActions();
        });
        global.stage.connectObject('notify::key-focus', revealActions, item);
        revealActions();
        buttons.set(saved.id, {select: item, play, edit, remove, label, marker});
        section.addMenuItem(item);
    }

    destroy() {
        this._alive = false;
        if (this._quitSource) GLib.source_remove(this._quitSource);
        this._quitSource = null;
        this._cancellable.cancel();
        if (this._proxy) {
            if (this._propertySignal) this._proxy.disconnect(this._propertySignal);
            if (this._ownerSignal) this._proxy.disconnect(this._ownerSignal);
            if (this._raiseSignal) this._proxy.disconnectSignal(this._raiseSignal);
        }
        this._proxy = null;
        super.destroy();
    }
});

const GLibVariant = GLib.Variant;

export default class RadioExtension extends Extension {
    _loadStylesheet() {
        const filename = this.metadata['radio-stylesheet'];
        if (!filename) return; // Unpackaged development uses Shell's stylesheet.css.
        if (!/^radio-style-[0-9a-f]{12}\.css$/.test(filename))
            throw new Error('Invalid radio stylesheet. Rebuild and reinstall the extension.');
        const theme = St.ThemeContext.get_for_stage(global.stage).get_theme();
        const prefix = `${this.dir.get_uri()}/`;
        const ownFiles = new Map();
        // A missing file mapping cannot establish ownership. Leave those entries
        // and foreign styles alone; never rebuild the Shell's shared theme.
        for (const file of theme.get_custom_stylesheets()) {
            if (file?.get_uri().startsWith(prefix)) ownFiles.set(file.get_uri(), file);
        }
        for (const file of ownFiles.values()) theme.unload_stylesheet(file);
        const stylesheet = this.dir.get_child(filename);
        theme.load_stylesheet(stylesheet);
        this._stylesheet = stylesheet;
    }

    _unloadStylesheet() {
        if (!this._stylesheet) return;
        St.ThemeContext.get_for_stage(global.stage).get_theme().unload_stylesheet(this._stylesheet);
        this._stylesheet = null;
    }

    enable() {
        if (this._indicator)
            return;
        this._loadStylesheet();
        let indicator;
        try {
            indicator = new RadioIndicator(this);
            this._indicator = indicator;
            Main.panel.addToStatusArea(this.uuid, indicator);
        } catch (error) {
            indicator?.destroy();
            this._indicator = null;
            this._unloadStylesheet();
            throw error;
        }
        this.startService().catch(() => {
            if (indicator._alive && !indicator._backendIdle)
                indicator._showError('Could not start the radio service. Check GJS and GStreamer.');
        });
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
        this._unloadStylesheet();
        this.stopService();
    }

    startService() {
        if (this._starting) return this._starting;
        const indicator = this._indicator;
        if (this._process && indicator?._proxy?.g_name_owner) return Promise.resolve();
        const token = {cancelled: false, cancel: null};
        this._startToken = token;
        const starting = (async () => {
            // Reconnect only after the preceding process has fully exited.
            await this._shutdown;
            if (token.cancelled || this._indicator !== indicator || !indicator?._alive)
                throw new Error('radiolina startup cancelled.');
            if (!this._process) {
                const args = ['gjs', '-m', `${this.path}/src/service/main.js`,
                    `--owner=${Gio.DBus.session.get_unique_name()}`];
                if (GLib.getenv('GNOME_RADIO_TEST_AUDIO') === '1') args.push('--test-audio');
                const process = Gio.Subprocess.new(args, Gio.SubprocessFlags.NONE);
                this._process = process;
                this._processExit = new Promise(resolve => process.wait_async(null, (child, result) => {
                    try { child.wait_finish(result); } catch (error) { console.warn(error.message); }
                    if (this._process === process) this._process = null;
                    resolve();
                }));
            }
            await new Promise((resolve, reject) => {
                let watch;
                let timeout;
                let settled = false;
                const finish = error => {
                    if (settled) return;
                    settled = true;
                    if (watch) Gio.bus_unwatch_name(watch);
                    if (timeout) GLib.source_remove(timeout);
                    token.cancel = null;
                    if (error) reject(error); else resolve();
                };
                token.cancel = () => finish(new Error('radiolina startup cancelled.'));
                watch = Gio.bus_watch_name_on_connection(Gio.DBus.session, BUS,
                    Gio.BusNameWatcherFlags.NONE, () => finish(), null);
                this._processExit.then(() => finish(new Error('radiolina service exited before becoming ready.')));
                timeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, SERVICE_START_TIMEOUT_MS, () => {
                    timeout = null;
                    finish(new Error('radiolina service did not start.'));
                    return GLib.SOURCE_REMOVE;
                });
            });
        })();
        this._starting = starting;
        indicator?._render();
        return starting.catch(error => {
            if (this._startToken === token && !token.cancelled) this.stopService();
            throw error;
        }).finally(() => {
            if (this._starting === starting) this._starting = null;
            if (this._startToken === token) this._startToken = null;
            if (indicator?._alive) indicator._render();
        });
    }

    stopService() {
        const token = this._startToken;
        this._startToken = null;
        this._starting = null;
        if (token) {
            token.cancelled = true;
            token.cancel?.();
        }
        const process = this._process;
        this._process = null;
        if (process) {
            this._shutdown = this._processExit;
            process.send_signal(15);
        }
        return this._shutdown ?? Promise.resolve();
    }
}
