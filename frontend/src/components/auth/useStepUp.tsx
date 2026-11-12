"use client";

import { useRef, useState, type ReactNode } from "react";

import { StepUp } from "@/components/auth/StepUp";
import { VERIFICATION_REQUIRED_CODE } from "@/lib/api-codes";
import type { ApiResult } from "@/lib/browser-api";

type Waiting = { replay: () => Promise<void>; cancel: () => void };

/**
 * Runs an action the server may refuse until the password is given again.
 *
 * That refusal is a question, not a sentence to print, and the answer is a screen. So the
 * promise deliberately does not settle on it: it settles on what the action did *after* the
 * password was confirmed. The call site keeps one path — ask, read the answer — instead of
 * growing a second one for the case where the answer arrives a minute later.
 *
 * The action is replayed rather than the form resubmitted, because the alternative is to
 * confirm the password and then be handed back an empty form: a lesson in leaving tabs
 * signed in, which is the habit this check exists to make unnecessary.
 */
export function useStepUp(): {
  attempt: <T>(action: () => Promise<ApiResult<T>>) => Promise<ApiResult<T>>;
  prompt: ReactNode;
} {
  const waiting = useRef<Waiting | null>(null);
  const [reason, setReason] = useState<string | null>(null);

  function close() {
    waiting.current = null;
    setReason(null);
  }

  async function attempt<T>(action: () => Promise<ApiResult<T>>): Promise<ApiResult<T>> {
    const result = await action();
    if (result.ok || result.error.code !== VERIFICATION_REQUIRED_CODE) {
      return result;
    }
    // the server's own words: it already says what to do, and a second wording would drift
    setReason(result.error.message);
    return new Promise<ApiResult<T>>((settle) => {
      waiting.current = {
        // through `attempt` again, so a confirmation that went stale asks once more
        replay: async () => {
          close();
          settle(await attempt(action));
        },
        // the refusal that started this, so the caller shows what the server said
        cancel: () => {
          close();
          settle(result);
        },
      };
    });
  }

  const prompt =
    reason === null ? null : (
      <StepUp
        reason={reason}
        onDone={() => void waiting.current?.replay()}
        onCancel={() => waiting.current?.cancel()}
      />
    );

  return { attempt, prompt };
}
