// SPDX-License-Identifier: MIT
import Gst from 'gi://Gst?version=1.0';
import GLib from 'gi://GLib';
import {createPipeline} from './decoder.js';

const BUFFERING_TIMEOUT_SECONDS = 30;

export class Player {
    constructor(onState, onMetadata, onError) {
        Gst.init(null);
        this.onState = onState;
        this.onMetadata = onMetadata;
        this.onError = onError;
        this.pipeline = null;
        this.buffering = false;
        this.desired = 'Stopped';
        this.bufferingTimeout = 0;
        this.source = null;
        this.volume = 1;
    }

    _cancelBufferingTimeout() {
        if (this.bufferingTimeout) GLib.source_remove(this.bufferingTimeout);
        this.bufferingTimeout = 0;
    }

    _armBufferingTimeout() {
        if (this.bufferingTimeout) return;
        const pipeline = this.pipeline;
        this.bufferingTimeout = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, BUFFERING_TIMEOUT_SECONDS, () => {
            this.bufferingTimeout = 0;
            if (this.pipeline === pipeline && this.desired === 'Playing') {
                this.stop();
                this.onError('Stream connection timed out. Press Play to retry.');
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    start(source) {
        this.stop();
        let pipeline;
        try { pipeline = createPipeline(source, ARGV.includes('--test-audio')); }
        catch (error) { source.close(); throw error; }
        this.source = source;
        this.pipeline = pipeline;
        this.setVolume(this.volume);
        this.desired = 'Playing';
        this.buffering = false;
        const bus = pipeline.get_bus();
        bus.add_signal_watch();
        this.bus = bus;
        this.busSignal = bus.connect('message', (_bus, message) => {
            if (this.pipeline !== pipeline)
                return;
            switch (message.type) {
            case Gst.MessageType.ELEMENT:
                // An audio container must never initiate another media location.
                if (message.get_structure()?.get_name() === 'redirect') {
                    this.stop();
                    this.onError('Media-embedded redirects are unsupported. Use the stream URL directly.');
                }
                break;
            case Gst.MessageType.ERROR:
                // Native messages may contain private source URLs or server-supplied text.
                console.warn('Stream playback failed.');
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
                    if (this.buffering) this._armBufferingTimeout();
                    pipeline.set_state(this.buffering ? Gst.State.PAUSED : Gst.State.PLAYING);
                    this.onState(this.buffering ? 'Connecting' : 'Playing');
                }
                break;
            }
            case Gst.MessageType.STATE_CHANGED:
                if (message.src === pipeline && this.desired === 'Playing' && !this.buffering &&
                    message.parse_state_changed()[1] === Gst.State.PLAYING) {
                    this._cancelBufferingTimeout();
                    this.onState('Playing');
                }
                break;
            }
        });
        this.onState('Connecting');
        this._armBufferingTimeout();
        if (pipeline.set_state(Gst.State.PLAYING) === Gst.StateChangeReturn.FAILURE) {
            this.stop();
            this.onError('Playback could not start. Check audio and codec support.');
        }
    }

    pause() {
        if (!this.pipeline)
            return;
        this.desired = 'Paused';
        this._cancelBufferingTimeout();
        this.pipeline.set_state(Gst.State.PAUSED);
        this.onState('Paused');
    }

    resume() {
        if (!this.pipeline)
            return;
        this.desired = 'Playing';
        this._armBufferingTimeout();
        this.pipeline.set_state(this.buffering ? Gst.State.PAUSED : Gst.State.PLAYING);
        this.onState(this.buffering ? 'Connecting' : 'Playing');
    }

    stop() {
        this._cancelBufferingTimeout();
        if (this.bus) {
            this.bus.disconnect(this.busSignal);
            this.bus.remove_signal_watch();
            this.bus = null;
        }
        this.source?.abort();
        this.pipeline?.set_state(Gst.State.NULL);
        this.source?.close();
        this.source = null;
        this.pipeline = null;
        this.desired = 'Stopped';
        this.onState('Stopped');
    }

    setVolume(value) {
        this.volume = value;
        if (this.pipeline) this.pipeline.get_by_name('volume').volume = value;
    }
}
