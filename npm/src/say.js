// The four kinds of line on stderr, as kaeris/cli.py prints them.
export const color = (text, code) => (process.env.NO_COLOR || !process.stderr.isTTY ? text : `\x1b[${code}m${text}\x1b[0m`);
export const out = (line) => process.stderr.write(line + "\n");
export const info = (msg) => out(`${color("→", "36")} ${msg}`);
export const ok = (msg) => out(`${color("✓", "32")} ${msg}`);
export const warn = (msg) => out(`${color("!", "33")} ${msg}`);
export const err = (msg) => out(`${color("✗", "31")} ${msg}`);
