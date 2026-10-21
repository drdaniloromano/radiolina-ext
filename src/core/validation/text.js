// SPDX-License-Identifier: MIT
export function cleanText(value, limit = 256) {
    return String(value ?? '').replace(/[\x00-\x1f\x7f]/g, ' ').trim().slice(0, limit);
}
