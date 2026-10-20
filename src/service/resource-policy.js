// SPDX-License-Identifier: MIT
import Gio from 'gi://Gio';
import {OOM_SCORE_ADJ} from './build-config.js';

export function configureOomPreference() {
    if (OOM_SCORE_ADJ === null) return;
    let stream;
    try {
        // This module runs only in the playback service. Never target Shell or
        // another PID, and never replace/rename a procfs control file.
        stream = Gio.File.new_for_path('/proc/self/oom_score_adj').open_readwrite(null);
        stream.get_output_stream().write_all(new TextEncoder().encode(String(OOM_SCORE_ADJ)), null);
    } catch (error) {
        // Sandboxes or another OS may not expose a writable Linux OOM control.
        console.warn(`Playback OOM preference unavailable; keeping system policy: ${error.message}`);
    } finally {
        try { stream?.close(null); }
        catch (error) { console.warn(`Could not close playback OOM control: ${error.message}`); }
    }
}
