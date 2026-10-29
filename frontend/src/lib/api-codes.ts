/**
 * The few backend error codes a screen reacts to rather than merely prints.
 *
 * Deliberately short. The backend's `message` is the user-facing text everywhere else, and a
 * list of codes mirrored here is a second place for the wording to live and drift.
 */

/** A shop has closed its door to this buyer — see the backend's services/customer_blocks.py. */
export const STORE_BLOCKED_CODE = "store_access_blocked";
