// SPDX-License-Identifier: MIT
import {cleanText} from './validation/text.js';

// Opt in only for code-authored messages. Never wrap a native error's message,
// server text, URL, path, or user input in UserError: secrets can appear anywhere.
export class UserError extends Error {}

export function publicErrorMessage(error, fallback) {
    return error instanceof UserError ? cleanText(error.message, 384) : fallback;
}
