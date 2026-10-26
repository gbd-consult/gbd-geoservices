// The scripts' texts, in the page's language. The server renders them into
// the page (the `messages` meta, from lib/messages.yaml's `devtools.js.*`),
// so there is no copy of the catalogue here to keep in step.
//
// `{name}` placeholders are filled by name, as lib/i18n.py fills them.

export const lang = document.documentElement.lang;

const MESSAGES = JSON.parse(document.querySelector('meta[name="messages"]').content);

// A missing id is an error rather than the id shown in its place: the server
// test checks the catalogue, so a gap here is a typo in a script.
export function t(id, values = {}) {
  const text = MESSAGES[id];
  if (text === undefined) {
    throw new Error(`no text ${id}`);
  }
  return text.replace(/\{(\w+)\}/g, (match, name) => (name in values ? String(values[name]) : match));
}
