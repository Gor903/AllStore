import type { User } from "@/lib/api";

/**
 * Where a role belongs when nothing else was asked for.
 *
 * Everyone used to land in the cabinet, and for the two roles that run the platform that is
 * a waiting room: an administrator has nothing of their own there, and a moderator has one
 * link out of it. Landing people in the room they came to work in removes a click that
 * existed only because the login form did not know who it had just let in.
 *
 * Plain module, no `server-only`: the login form decides this in the browser from the answer
 * it already holds, and the data layer decides it on the server.
 */
export function homeFor(role: User["role"]): string {
  switch (role) {
    case "admin":
      return "/admin";
    case "moderator":
      return "/moderation";
    default:
      return "/dashboard";
  }
}
