// SPDX-License-Identifier: MIT
export const MAX_FAVICON_BYTES = 256 * 1024;

function pngSize(data) {
    if (data.length < 24 || ![137, 80, 78, 71, 13, 10, 26, 10].every((value, i) => data[i] === value))
        return false;
    const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
    return view.getUint32(12) === 0x49484452 && view.getUint32(16) > 0 && view.getUint32(16) <= 512 &&
        view.getUint32(20) > 0 && view.getUint32(20) <= 512;
}

export function validFavicon(data) {
    if (data.length > MAX_FAVICON_BYTES || data.length < 24) return false;
    if (pngSize(data)) return true;
    const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
    if (view.getUint16(0, true) !== 0 || view.getUint16(2, true) !== 1) return false;
    const count = view.getUint16(4, true);
    if (!count || count > 32 || 6 + count * 16 > data.length) return false;
    for (let i = 0; i < count; i++) {
        const entry = 6 + i * 16;
        const size = view.getUint32(entry + 8, true);
        const offset = view.getUint32(entry + 12, true);
        if (!size || offset < 6 + count * 16 || offset + size > data.length) return false;
        const image = data.subarray(offset, offset + size);
        if (image[0] === 137) { if (!pngSize(image)) return false; }
        else {
            if (image.length < 40) return false;
            const bitmap = new DataView(image.buffer, image.byteOffset, image.byteLength);
            if (bitmap.getUint32(0, true) < 40 || bitmap.getInt32(4, true) <= 0 || bitmap.getInt32(4, true) > 256 ||
                bitmap.getInt32(8, true) <= 0 || bitmap.getInt32(8, true) > 512) return false;
        }
    }
    return true;
}
