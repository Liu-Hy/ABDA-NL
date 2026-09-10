/* Browser-local history. A transaction owns each revision and deletion marker.
   Shared source text and immutable snapshots are stored once per account. */
const conversationHistory = (() => {
  let database;
  const packedSnapshots = new WeakMap();
  const request = value => new Promise((resolve, reject) => {
    value.onsuccess = () => resolve(value.result);
    value.onerror = () => reject(value.error);
  });
  const completed = tx => new Promise((resolve, reject) => {
    tx.oncomplete = resolve;
    tx.onabort = () => reject(tx.error || new Error('History transaction aborted'));
    tx.onerror = () => {}; // The abort reports the transaction's final result.
  });
  async function open() {
    if (!database) database = new Promise((resolve, reject) => {
      const opening = indexedDB.open('abda-conversations', 1);
      opening.onupgradeneeded = () => {
        for (const name of ['records', 'blobs']) {
          opening.result.createObjectStore(name, { keyPath: 'key' }).createIndex('owner', 'owner');
        }
        opening.result.createObjectStore('migrations');
      };
      opening.onsuccess = () => resolve(opening.result);
      opening.onerror = () => { database = null; reject(opening.error); };
      opening.onblocked = () => reject(new Error('Close older demo tabs and retry saving'));
    });
    return database;
  }
  async function signature(text) {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
    return 'sha256:' + Array.from(new Uint8Array(digest), n => n.toString(16).padStart(2, '0')).join('');
  }
  async function blob(value, blobs) {
    const data = JSON.stringify(value);
    const id = (await signature(data)).slice('sha256:'.length);
    blobs.set(id, data);
    return id;
  }
  async function pack(record) {
    const snapshots = {};
    const blobs = new Map();
    for (const [id, snapshot] of Object.entries(record.snapshots || {})) {
      let packed = packedSnapshots.get(snapshot);
      if (!packed) {
        const parts = new Map();
        const copy = structuredClone(snapshot);
        delete copy.captured_at;
        const scenario = copy.scenario?.scenario;
        const sources = scenario?.sources;
        if (sources) {
          copy.source_refs = await Promise.all(sources.map(source => blob(source, parts)));
          delete scenario.sources;
        }
        const ref = await blob(copy, parts);
        packed = { ref, parts };
        packedSnapshots.set(snapshot, packed);
      }
      for (const [key, value] of packed.parts) blobs.set(key, value);
      snapshots[id] = { ref: packed.ref, captured_at: snapshot.captured_at };
    }
    const data = { ...structuredClone({ ...record, snapshots: undefined }), snapshots };
    const signatures = new Map();
    const referenceValues = [...(data.context_refs || []),
      ...(data.draft_segments || []).filter(item => item.type === 'reference').map(item => item.ref),
      ...(data.messages || []).flatMap(message => (message.segments || []).filter(item => item.type === 'reference').map(item => item.ref))];
    for (const ref of referenceValues) {
      if (ref.scenario_signature && !ref.scenario_signature.startsWith('sha256:')) {
        const text = ref.scenario_signature;
        if (!signatures.has(text)) signatures.set(text, signature(text));
        ref.scenario_signature = await signatures.get(text);
      }
    }
    return { data, blobs };
  }
  function unpack(row, blobs) {
    const record = structuredClone(row.data);
    for (const [id, saved] of Object.entries(record.snapshots || {})) {
      const snapshot = JSON.parse(blobs.get(saved.ref));
      if (snapshot.source_refs) {
        snapshot.scenario.scenario.sources = snapshot.source_refs.map(ref => JSON.parse(blobs.get(ref)));
        delete snapshot.source_refs;
      }
      record.snapshots[id] = { ...snapshot, captured_at: saved.captured_at };
    }
    return { record, revision: row.revision };
  }
  function putBlobs(tx, owner, blobs) {
    const store = tx.objectStore('blobs');
    for (const [id, data] of blobs) {
      const existing = store.get([owner, id]);
      existing.onsuccess = () => {
        if (!existing.result) store.put({ key: [owner, id], owner, id, data });
      };
    }
  }
  async function list(owner) {
    const db = await open();
    const tx = db.transaction(['records', 'blobs'], 'readonly');
    const done = completed(tx);
    const [rows, parts] = await Promise.all(['records', 'blobs'].map(name => request(tx.objectStore(name).index('owner').getAll(owner))));
    await done;
    const blobs = new Map(parts.map(part => [part.id, part.data]));
    return { records: rows.filter(row => !row.deleted).map(row => unpack(row, blobs)),
      deleted: rows.filter(row => row.deleted).map(row => row.id),
      bytes: parts.reduce((sum, part) => sum + part.data.length * 2, 0)
        + rows.reduce((sum, row) => sum + JSON.stringify(row).length * 2, 0) };
  }
  async function save(owner, record, expectedRevision, mayWrite = () => true) {
    const packed = await pack(record);
    const db = await open();
    if (!mayWrite()) return { cancelled: true };
    const tx = db.transaction(['records', 'blobs'], 'readwrite');
    const done = completed(tx);
    const store = tx.objectStore('records');
    let result;
    const current = store.get([owner, record.id]);
    current.onsuccess = () => {
      const row = current.result;
      if (row?.deleted) { result = { deleted: true }; return; }
      if (!mayWrite()) { result = { cancelled: true }; return; }
      const conflict = Boolean(row && row.revision !== expectedRevision
        && JSON.stringify(row.data) !== JSON.stringify(packed.data));
      const id = conflict ? conversationId() : record.id;
      const data = packed.data;
      if (conflict) {
        data.id = id;
        data.title = `Concurrent copy: ${data.title.replace(/^Concurrent copy: /, '')}`;
        data.concurrent_copy_of = record.id;
      }
      const revision = conflict ? 1 : (row?.revision || 0) + 1;
      putBlobs(tx, owner, packed.blobs);
      store.put({ key: [owner, id], owner, id, revision, data });
      result = { id, revision, conflict, title: data.title };
    };
    await done;
    return result;
  }
  async function migrate(owner, records) {
    const packed = await Promise.all(records.map(record => pack(record)));
    // An older open tab can write v1 again after the first migration. Deduplicate
    // each imported payload, while retaining subsequent older-tab edits as copies.
    const migrationKey = [owner, await blob(packed.map(item => item.data), new Map())];
    const db = await open();
    const tx = db.transaction(['records', 'blobs', 'migrations'], 'readwrite');
    const done = completed(tx);
    const marker = tx.objectStore('migrations').get(migrationKey);
    marker.onsuccess = () => {
      if (marker.result) return;
      records.forEach((record, index) => {
        const lookup = tx.objectStore('records').get([owner, record.id]);
        lookup.onsuccess = () => {
          const existing = lookup.result;
          if (existing?.deleted) return;
          const data = packed[index].data;
          if (existing && JSON.stringify(existing.data) === JSON.stringify(data)) return;
          const id = existing ? conversationId() : record.id;
          if (existing) {
            data.id = id;
            data.title = `Recovered older tab: ${data.title}`;
            data.legacy_copy_of = record.id;
          }
          putBlobs(tx, owner, packed[index].blobs);
          tx.objectStore('records').put({ key: [owner, id], owner, id, revision: 1, data });
        };
      });
      tx.objectStore('migrations').put(true, migrationKey);
    };
    await done;
  }
  async function remove(owner, id) {
    const db = await open();
    const tx = db.transaction(['records', 'blobs'], 'readwrite');
    const done = completed(tx);
    const store = tx.objectStore('records');
    // A tombstone wins over stale saves and delayed responses in every tab.
    store.put({ key: [owner, id], owner, id, deleted: true });
    const rows = store.index('owner').getAll(owner);
    rows.onsuccess = () => {
      const used = new Set();
      for (const row of rows.result.filter(row => !row.deleted)) {
        for (const snapshot of Object.values(row.data.snapshots || {})) used.add(snapshot.ref);
      }
      const parts = tx.objectStore('blobs').index('owner').getAll(owner);
      parts.onsuccess = () => {
        for (const part of parts.result) {
          if (used.has(part.id)) {
            for (const ref of JSON.parse(part.data).source_refs || []) used.add(ref);
          }
        }
        for (const part of parts.result) {
          if (!used.has(part.id)) tx.objectStore('blobs').delete(part.key);
        }
      };
    };
    await done;
  }
  return { list, save, migrate, remove, signature };
})();
