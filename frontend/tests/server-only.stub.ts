// `server-only` refuses to load outside a server component, which is the whole point of it
// in the build and an obstacle in a test. Vitest resolves the package to this empty module.
export {};
