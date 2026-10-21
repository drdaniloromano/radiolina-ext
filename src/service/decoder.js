// SPDX-License-Identifier: MIT
import Gst from 'gi://Gst?version=1.0';

// Explicit pipelines: no decodebin/playbin, URI sources, plugin autoselection, or
// JavaScript callbacks from streaming threads. All strings below are owned code.
const CODECS = {
    mp3: {caps: 'audio/mpeg,mpegversion=1,layer=3', parser: 'mpegaudioparse', decoders: ['mpg123audiodec', 'avdec_mp3', 'mad']},
    aac: {caps: 'audio/mpeg,mpegversion=(int){2,4}', parser: 'aacparse', decoders: ['avdec_aac', 'fdkaacdec', 'faad']},
    vorbis: {caps: 'audio/x-vorbis', decoders: ['vorbisdec', 'avdec_vorbis']},
    opus: {caps: 'audio/x-opus', decoders: ['opusdec', 'avdec_opus']},
    flac: {caps: 'audio/x-flac', parser: 'flacparse', decoders: ['flacdec', 'avdec_flac']},
    pcm: {caps: 'audio/x-raw', decoders: []},
};

export function createPipeline(source, testAudio) {
    const codec = CODECS[source.media.codec];
    if (!codec) throw new Error('Unsupported stream format.');
    const decoder = codec.decoders.find(name => Gst.ElementFactory.find(name));
    if (codec.decoders.length && !decoder)
        throw new Error(`Required codec unavailable: ${source.media.codec.toUpperCase()}.`);
    const container = {ogg: 'oggdemux', mp4: 'qtdemux', wav: 'wavparse', '': null}[source.media.container];
    if (container === undefined) throw new Error('Unsupported audio container.');
    const elements = ['giostreamsrc', source.icyInterval ? 'icydemux' : null,
        source.media.id3 ? 'id3demux' : null, container, codec.parser, decoder,
        'queue2', 'audioconvert', 'audioresample', 'volume', testAudio ? 'fakesink' : 'autoaudiosink'].filter(Boolean);
    if (elements.some(name => !Gst.ElementFactory.find(name)))
        throw new Error(`Required codec or audio component unavailable: ${source.media.codec.toUpperCase()}.`);
    const chain = ['giostreamsrc name=input blocksize=8192'];
    if (source.icyInterval) chain.push(`application/x-icy,metadata-interval=${source.icyInterval}`, 'icydemux');
    if (source.media.id3) chain.push('id3demux');
    if (container) chain.push(container);
    if (codec.parser) chain.push(codec.parser);
    chain.push(codec.caps);
    if (decoder) chain.push(decoder);
    chain.push('queue2 use-buffering=true max-size-buffers=0 max-size-bytes=262144 max-size-time=1000000000',
        'audioconvert', 'audioresample', 'volume name=volume', testAudio ? 'fakesink sync=true' : 'autoaudiosink');
    const pipeline = Gst.parse_launch(chain.join(' ! '));
    pipeline.get_by_name('input').stream = source.input;
    return pipeline;
}
