// SPDX-License-Identifier: MIT
// Bounded recognition of supported containers/codecs, independent of filenames/MIME.
// This is an admission policy, not a replacement for native format parsers.
export const MAX_PROBE_BYTES = 64 * 1024;
export const MAX_ICY_INTERVAL = 1024 * 1024;
const unsupported = () => new Error('Unsupported stream format. Use a supported audio stream or M3U/XSPF playlist.');
const text = (data, start, length) => String.fromCharCode(...data.subarray(start, start + length));
const u32 = (data, offset, little = false) => new DataView(data.buffer, data.byteOffset, data.byteLength).getUint32(offset, little);
const u16 = (data, offset) => new DataView(data.buffer, data.byteOffset, data.byteLength).getUint16(offset, true);

export function validateIcyInterval(value) {
    if (value === null) return 0;
    if (!/^[0-9]+$/.test(value) || Number(value) < 1 || Number(value) > MAX_ICY_INTERVAL)
        throw new Error('Invalid stream metadata interval.');
    return Number(value);
}

// Inspect audio without consuming or modifying interleaved bytes sent to icydemux.
function audioPrefix(data, interval) {
    if (!interval) return data;
    const chunks = [];
    let length = 0;
    for (let offset = 0; offset < data.length;) {
        const chunk = data.subarray(offset, Math.min(offset + interval, data.length));
        chunks.push(chunk); length += chunk.length; offset += interval;
        if (offset >= data.length) break;
        offset += 1 + data[offset] * 16;
    }
    const audio = new Uint8Array(length);
    let offset = 0;
    for (const chunk of chunks) { audio.set(chunk, offset); offset += chunk.length; }
    return audio;
}

function oggCodec(data) {
    let offset = 0;
    const codecs = [];
    while (offset + 27 <= data.length) {
        if (text(data, offset, 4) !== 'OggS' || data[offset + 4] !== 0) throw unsupported();
        if (!(data[offset + 5] & 2)) {
            if (!codecs.length) throw unsupported();
            return codecs[0];
        }
        const segments = data[offset + 26];
        const header = offset + 27 + segments;
        if (!segments || header > data.length) return null;
        let size = 0;
        for (let i = offset + 27; i < header; i++) size += data[i];
        if (header + size > data.length) return null;
        const signature = text(data, header, Math.min(size, 8));
        const codec = signature.startsWith('\x01vorbis') ? 'vorbis' :
            signature === 'OpusHead' ? 'opus' : signature.startsWith('\x7fFLAC') ? 'flac' : null;
        if (!codec) throw unsupported(); // Includes Theora, Speex, and unknown BOS tracks.
        codecs.push(codec);
        if (codecs.length > 8) throw unsupported();
        offset = header + size;
    }
    return null;
}

function mp4Codec(data) {
    let boxes = 0;
    const tracks = [];
    function descriptor(offset, end) {
        if (offset + 2 > end) throw unsupported();
        const tag = data[offset++];
        let size = 0;
        let count = 0;
        let byte;
        do {
            if (offset >= end || ++count > 4) throw unsupported();
            byte = data[offset++]; size = size * 128 + (byte & 127);
        } while (byte & 128);
        if (offset + size > end) throw unsupported();
        return {tag, start: offset, end: offset + size};
    }
    function mpegCodec(start, end) {
        if (start + 28 > end || u16(data, start + 8) !== 0) throw unsupported();
        for (let offset = start + 28; offset + 8 <= end;) {
            const size = u32(data, offset);
            if (size < 8 || offset + size > end) throw unsupported();
            if (text(data, offset + 4, 4) === 'esds') {
                const es = descriptor(offset + 12, offset + size);
                if (es.tag !== 3 || es.start + 3 > es.end) throw unsupported();
                const flags = data[es.start + 2];
                let position = es.start + 3;
                if (flags & 128) position += 2;
                if (flags & 64) {
                    if (position >= es.end) throw unsupported();
                    position += 1 + data[position];
                }
                if (flags & 32) position += 2;
                const config = descriptor(position, es.end);
                if (config.tag !== 4 || config.end - config.start < 13) throw unsupported();
                const type = data[config.start];
                if ([0x40, 0x66, 0x67, 0x68].includes(type)) return 'aac';
                if ([0x69, 0x6b].includes(type)) return 'mp3';
                throw unsupported();
            }
            offset += size;
        }
        throw unsupported();
    }
    function walk(start, end, depth, track = null) {
        if (depth > 12) throw unsupported();
        for (let offset = start; offset < end;) {
            if (offset + 8 > data.length) return false;
            let size = u32(data, offset);
            const kind = text(data, offset + 4, 4);
            let header = 8;
            if (size === 1) {
                if (offset + 16 > data.length) return false;
                const high = u32(data, offset + 8);
                if (high) throw unsupported();
                size = u32(data, offset + 12); header = 16;
            }
            if (size < header || ++boxes > 512) throw unsupported();
            if (offset + size > end || offset + size > data.length) return false;
            const body = offset + header;
            if (kind === 'trak') {
                const next = {};
                if (!walk(body, offset + size, depth + 1, next)) return false;
                if (next.handler !== 'soun' || !next.codec) throw unsupported();
                tracks.push(next.codec);
            } else if (['moov', 'mdia', 'minf', 'stbl'].includes(kind)) {
                if (!walk(body, offset + size, depth + 1, track)) return false;
            } else if (kind === 'hdlr' && track) {
                if (body + 12 > offset + size) throw unsupported();
                track.handler = text(data, body + 8, 4);
            } else if (kind === 'stsd' && track) {
                if (body + 16 > offset + size || u32(data, body + 4) !== 1) throw unsupported();
                const entry = text(data, body + 12, 4);
                const entrySize = u32(data, body + 8);
                if (entrySize < 36 || body + 8 + entrySize > offset + size) throw unsupported();
                track.codec = entry === 'mp4a' ? mpegCodec(body + 16, body + 8 + entrySize) :
                    {'.mp3': 'mp3', Opus: 'opus', fLaC: 'flac'}[entry];
                if (!track.codec) throw unsupported();
            }
            offset += size;
        }
        return true;
    }
    for (let offset = 0; offset + 8 <= data.length;) {
        const size = u32(data, offset);
        const kind = text(data, offset + 4, 4);
        if (kind === 'mdat') throw new Error('MP4 audio headers must precede the audio data.');
        if (size < 8 || size > MAX_PROBE_BYTES) throw unsupported();
        if (offset + size > data.length) return null;
        if (kind === 'moov') {
            if (!walk(offset + 8, offset + size, 0) || !tracks.length) throw unsupported();
            return tracks[0];
        }
        offset += size;
    }
    return null;
}

function wav(data) {
    for (let offset = 12; offset + 8 <= data.length;) {
        const kind = text(data, offset, 4);
        const size = u32(data, offset + 4, true);
        if (kind === 'data') throw unsupported();
        if (kind === 'fmt ') {
            if (size < 16) throw unsupported();
            if (offset + 8 + size > data.length) return null;
            let code = u16(data, offset + 8);
            if (code === 0xfffe) {
                if (size < 40) throw unsupported();
                code = u32(data, offset + 32, true);
                if (text(data, offset + 36, 12) !== '\0\0\x10\0\x80\0\0\xaa\0\x38\x9b\x71') throw unsupported();
            }
            if (code !== 1 && code !== 3) throw unsupported();
            return true;
        }
        if (size > MAX_PROBE_BYTES) throw unsupported();
        offset += 8 + size + (size % 2);
    }
    return false;
}

function framedAudio(data, start) {
    const bitrates = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320];
    const lowerRates = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160];
    for (let i = start; i + 4 < Math.min(data.length, start + 4096); i++) {
        if (data[i] !== 255 || (data[i + 1] & 0xe0) !== 0xe0) continue;
        const version = (data[i + 1] >> 3) & 3;
        const layer = (data[i + 1] >> 1) & 3;
        const rate = (data[i + 2] >> 2) & 3;
        const bitrate = data[i + 2] >> 4;
        if (version !== 1 && layer === 1 && rate !== 3 && bitrate > 0 && bitrate < 15) {
            const sampleRate = [44100, 48000, 32000][rate] / (version === 3 ? 1 : version === 2 ? 2 : 4);
            const length = Math.floor((version === 3 ? 144000 : 72000) *
                (version === 3 ? bitrates : lowerRates)[bitrate] / sampleRate) + ((data[i + 2] >> 1) & 1);
            const next = i + length;
            if (next + 3 < data.length && data[next] === 255 &&
                (data[next + 1] & 0xfe) === (data[i + 1] & 0xfe)) return 'mp3';
        }
        if ((data[i + 1] & 0xf6) === 0xf0 && ((data[i + 2] >> 2) & 15) <= 12 && i + 7 <= data.length) {
            const length = ((data[i + 3] & 3) << 11) | (data[i + 4] << 3) | (data[i + 5] >> 5);
            const next = i + length;
            if (length >= 7 && next + 2 < data.length && data[next] === 255 &&
                (data[next + 1] & 0xf6) === 0xf0) return 'aac';
        }
    }
    return null;
}

export function inspectMedia(bytes, {icyInterval = 0, final = false, playlistHint = ''} = {}) {
    if (bytes.length > MAX_PROBE_BYTES) throw new Error('Stream identification exceeded its size limit.');
    const data = audioPrefix(bytes, icyInterval);
    const beginning = new TextDecoder().decode(data.subarray(0, 1024)).replace(/^\uFEFF/, '').trimStart();
    if (/^(?:<!DOCTYPE\s+html|<html\b)/i.test(beginning)) throw unsupported();
    if (/^#EXT-X-/m.test(beginning)) throw new Error('HLS streams are unsupported. Use an ordinary radio stream.');
    if (/^(?:#|https?:\/\/)/i.test(beginning)) return {kind: 'playlist', format: 'm3u'};
    if (/^(?:<\?xml\b|<!DOCTYPE\b|<(?:[\w.-]+:)?playlist\b)/i.test(beginning))
        return {kind: 'playlist', format: 'xspf'};
    if (playlistHint && /^[\x20-\x7e\r\n\t]*$/.test(beginning) && beginning &&
        !['ID3', 'OggS', 'fLaC', 'RIFF', 'RF64', 'ADIF'].some(prefix => beginning.startsWith(prefix)))
        return {kind: 'playlist', format: playlistHint};
    let offset = 0;
    const id3 = text(data, 0, 3) === 'ID3';
    if (id3) {
        if (data.length < 10) {
            if (final || bytes.length >= MAX_PROBE_BYTES) throw unsupported();
            return null;
        }
        if (data[3] < 2 || data[3] > 4 || Array.from(data.subarray(6, 10)).some(value => value & 128)) throw unsupported();
        offset = 10 + ((data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]) + ((data[5] & 16) ? 10 : 0);
        if (offset + 16 > MAX_PROBE_BYTES) throw new Error('Stream audio headers exceed the 64 KiB identification limit.');
        if (data.length < offset + 16) {
            if (final || bytes.length >= MAX_PROBE_BYTES) throw unsupported();
            return null;
        }
    }
    const audio = data.subarray(offset);
    let codec;
    let container = '';
    if (text(audio, 0, 4) === 'OggS') { container = 'ogg'; codec = oggCodec(audio); }
    else if (text(audio, 0, 4) === 'fLaC') codec = 'flac';
    else if (text(audio, 0, 4) === 'ADIF') codec = 'aac';
    else if (['RIFF', 'RF64'].includes(text(audio, 0, 4)) && text(audio, 8, 4) === 'WAVE') {
        container = 'wav'; if (wav(audio)) codec = 'pcm';
    } else if (text(audio, 4, 4) === 'ftyp') { container = 'mp4'; codec = mp4Codec(audio); }
    else codec = framedAudio(data, offset);
    if (codec) return {kind: 'audio', codec, container, id3};
    if (final || bytes.length >= MAX_PROBE_BYTES || (!container && data.length >= offset + 4096)) throw unsupported();
    return null;
}
