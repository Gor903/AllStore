/**
 * The few backend error codes a screen reacts to rather than merely prints.
 *
 * Deliberately short. The backend's `message` is the user-facing text everywhere else, and a
 * list of codes mirrored here is a second place for the wording to live and drift.
 */

/** A shop has closed its door to this buyer — see the backend's services/customer_blocks.py. */
export const STORE_BLOCKED_CODE = "store_access_blocked";

/** The password was right and the sign-in is not finished — see the backend's api/totp.py. */
export const SECOND_FACTOR_REQUIRED_CODE = "totp_required";

/** Staff with no authenticator yet: nothing opens until one is set up. */
export const SECOND_FACTOR_SETUP_CODE = "totp_setup_required";
