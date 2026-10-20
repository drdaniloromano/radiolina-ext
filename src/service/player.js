// SPDX-License-Identifier: MIT
import Gst from 'gi://Gst?version=1.0';

export class Player {
    constructor(onState, onMetadata, onError) {
        Gst.init(null);
        this.onState = onState;
        this.onMetadata = onMetadata;
        this.onError = onError;
        this.pipeline = null;
        this.buffering = false;
        this.desired = 'Stopped';
    }

    start(url) {
        this.stop();
        const pipeline = Gst.ElementFactory.make('playbin', null);
        if (!pipeline)
            throw new Error('GStreamer playback support is unavailable.');
        pipeline.uri = url;
        pipeline.flags = 2; // Audio only: no video or subtitle processing.
        if (ARGV.includes('--test-audio')) {
            const sink = Gst.ElementFactory.make('fakesink', null);
            sink.sync = true;
            pipeline.audio_sink = sink;
        }
        pipeline.connect('source-setup', (_pipeline, source) => {
            if (source.constructor.find_property('timeout'))
                source.set_property('timeout', 15);
            if (source.constructor.find_property('iradio-mode'))
                source.set_property('iradio-mode', true);
        });
        this.pipeline = pipeline;
        this.desired = 'Playing';
        this.buffering = false;
        const bus = pipeline.get_bus();
        bus.add_signal_watch();
        this.bus = bus;
        this.busSignal = bus.connect('message', (_bus, message) => {
            if (this.pipeline !== pipeline)
                return;
            switch (message.type) {
            case Gst.MessageType.ERROR:
                console.warn(message.parse_error()[0].message);
                this.stop();
                this.onError('Cannot play this stream. Check the URL or connection and try again.');
                break;
            case Gst.MessageType.EOS:
                this.stop();
                this.onError('The stream ended. Press Play to reconnect.');
                break;
            case Gst.MessageType.TAG: {
                const tags = message.parse_tag();
                const [hasTitle, title] = tags.get_string(Gst.TAG_TITLE);
                const [hasArtist, artist] = tags.get_string(Gst.TAG_ARTIST);
                if (hasTitle || hasArtist)
                    this.onMetadata(hasTitle ? title : undefined, hasArtist ? artist : undefined);
                break;
            }
            case Gst.MessageType.BUFFERING: {
                const percent = message.parse_buffering();
                this.buffering = percent < 100;
                if (this.desired === 'Playing') {
                    pipeline.set_state(this.buffering ? Gst.State.PAUSED : Gst.State.PLAYING);
                    this.onState(this.buffering ? 'Connecting' : 'Playing');
                }
                break;
            }
            case Gst.MessageType.STATE_CHANGED:
                if (message.src === pipeline && this.desired === 'Playing' &&
                    message.parse_state_changed()[1] === Gst.State.PLAYING)
                    this.onState('Playing');
                break;
            }
        });
        this.onState('Connecting');
        if (pipeline.set_state(Gst.State.PLAYING) === Gst.StateChangeReturn.FAILURE) {
            this.stop();
            this.onError('Playback could not start. Check audio and codec support.');
        }
    }

    pause() {
        if (!this.pipeline)
            return;
        this.desired = 'Paused';
        this.pipeline.set_state(Gst.State.PAUSED);
        this.onState('Paused');
    }

    resume() {
        if (!this.pipeline)
            return;
        this.desired = 'Playing';
        this.pipeline.set_state(this.buffering ? Gst.State.PAUSED : Gst.State.PLAYING);
        this.onState(this.buffering ? 'Connecting' : 'Playing');
    }

    stop() {
        if (this.bus) {
            this.bus.disconnect(this.busSignal);
            this.bus.remove_signal_watch();
            this.bus = null;
        }
        this.pipeline?.set_state(Gst.State.NULL);
        this.pipeline = null;
        this.desired = 'Stopped';
        this.onState('Stopped');
    }
}
