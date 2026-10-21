// SPDX-License-Identifier: MIT
// Inspect installed factories without constructing pipelines or opening streams.
import Gio from 'gi://Gio';
import Gst from 'gi://Gst?version=1.0';

Gst.init(null);
const source = new TextDecoder().decode(Gio.File.new_for_path(ARGV[0]).load_contents(null)[1]);
// Conservatively inspect every literal factory-like name in the explicit policy,
// including installed fallback decoders. Package dependency closure adds coverage
// beyond these named factories; dynamic output backends still need manual review.
const candidates = [...new Set([...source.matchAll(/'([a-z][a-z0-9_]*)'/g)].map(match => match[1]))];
const elements = candidates.flatMap(name => {
    const factory = Gst.ElementFactory.find(name);
    if (!factory) return [];
    const plugin = factory.get_plugin();
    return [{name, plugin: plugin?.get_name(), file: plugin?.get_filename() ?? null}];
});
print(JSON.stringify({elements}));
