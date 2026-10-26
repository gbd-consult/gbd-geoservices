// The category picker on the Search tab: a button showing the chosen
// category, which opens a tree of all of them. A plain <select> flattened
// ~600 categories four levels deep into one indented list.

export function create({ button, label, popup }) {
  const byId = new Map();
  let selected = '';

  function nodeFor(entry, depth, parentIds) {
    const item = document.createElement('div');
    item.className = 'cat-node';
    item.setAttribute('role', 'treeitem');

    const row = document.createElement('div');
    row.className = 'cat-row';
    row.style.paddingLeft = `${4 + depth * 14}px`;
    row.dataset.id = entry.id;

    const subs = entry.subs || [];
    const toggle = document.createElement(subs.length ? 'button' : 'span');
    toggle.className = subs.length ? 'cat-toggle' : 'cat-toggle cat-toggle-leaf';
    if (subs.length) {
      toggle.type = 'button';
      toggle.textContent = '▸';
      toggle.setAttribute('aria-label', 'expand');
      item.setAttribute('aria-expanded', 'false');
    }
    const name = document.createElement('span');
    name.className = 'cat-name';
    name.textContent = entry.name;
    row.append(toggle, name);
    item.appendChild(row);

    byId.set(entry.id, { name: entry.name, row, item, parentIds });

    if (subs.length) {
      const children = document.createElement('div');
      children.className = 'cat-children hidden';
      children.setAttribute('role', 'group');
      for (const sub of subs) {
        children.appendChild(nodeFor(sub, depth + 1, [...parentIds, entry.id]));
      }
      item.appendChild(children);
    }
    return item;
  }

  function setExpanded(item, expanded) {
    const children = item.querySelector(':scope > .cat-children');
    if (!children) return;
    children.classList.toggle('hidden', !expanded);
    item.setAttribute('aria-expanded', String(expanded));
    item.querySelector(':scope > .cat-row > .cat-toggle').setAttribute(
      'aria-label', expanded ? 'collapse' : 'expand');
  }

  function select(id) {
    const previous = byId.get(selected);
    if (previous) previous.row.classList.remove('selected');
    selected = byId.has(id) ? id : '';
    const current = byId.get(selected);
    if (current) current.row.classList.add('selected');
    label.textContent = current ? current.name : '…';
    label.classList.toggle('cat-picker-empty', !current);
    button.title = current ? `${current.name} (${selected})` : '';
  }

  function open() {
    popup.classList.remove('hidden');
    button.setAttribute('aria-expanded', 'true');
    const current = byId.get(selected);
    if (current) {
      for (const parentId of current.parentIds) setExpanded(byId.get(parentId).item, true);
      current.row.scrollIntoView({ block: 'nearest' });
    }
  }

  function close() {
    popup.classList.add('hidden');
    button.setAttribute('aria-expanded', 'false');
  }

  button.addEventListener('click', () => {
    if (popup.classList.contains('hidden')) open();
    else close();
  });

  popup.addEventListener('click', (event) => {
    const row = event.target.closest('.cat-row');
    if (!row) return;
    if (event.target.closest('.cat-toggle:not(.cat-toggle-leaf)')) {
      const item = row.parentElement;
      setExpanded(item, item.getAttribute('aria-expanded') !== 'true');
      return;
    }
    select(row.dataset.id);
    close();
    button.focus();
  });

  document.addEventListener('mousedown', (event) => {
    if (!popup.classList.contains('hidden')
        && !popup.contains(event.target) && !button.contains(event.target)) {
      close();
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !popup.classList.contains('hidden')) {
      close();
      button.focus();
    }
  });

  return {
    load(tree, selectedId) {
      popup.replaceChildren();
      byId.clear();
      const any = document.createElement('div');
      any.className = 'cat-row cat-any';
      any.dataset.id = '';
      any.innerHTML = '<span class="cat-toggle cat-toggle-leaf"></span><span class="cat-name">…</span>';
      popup.appendChild(any);
      for (const entry of tree) popup.appendChild(nodeFor(entry, 0, []));
      select(selectedId || '');
    },
    get value() {
      return selected;
    },
    set disabled(value) {
      button.disabled = value;
      if (value) close();
    },
  };
}
