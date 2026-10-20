// Arbitrarily named application indicator for isolated grouping/lifecycle checks.
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

export default class PanelNeighbor extends Extension {
    enable() {
        this._indicator = new PanelMenu.Button(0.5, this.metadata.name);
        const box = new St.BoxLayout({style: 'spacing: 6px;'});
        box.add_child(new St.Icon({icon_name: 'edit-paste-symbolic',
            style_class: 'system-status-icon', style: 'padding: 0; margin: 0;'}));
        this._indicator.add_child(box);
        this._indicator.menu.addMenuItem(new PopupMenu.PopupMenuItem('Fixture action'));
        Main.panel.addToStatusArea(this.uuid, this._indicator, 1, 'right');
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
