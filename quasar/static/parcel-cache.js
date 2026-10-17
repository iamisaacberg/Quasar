/* Public county geometry only. Credentials and forecast values are never persisted. */
(function(root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.QuasarParcelCache = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function() {
  "use strict";
  const RETENTION = 7 * 86400000, CHECK_INTERVAL = 15 * 60000;
  function disk(indexedDB) {
    let opened;
    function open() {
      if (!opened) opened = new Promise((resolve, reject) => {
        if (!indexedDB) return reject(new Error("Browser storage unavailable"));
        const request = indexedDB.open("quasar-public-parcels", 2);
        request.onupgradeneeded = () => {
          const db=request.result;
          // Geometry cached by an older schema can safely be reacquired.
          if(db.objectStoreNames.contains("cells")) db.deleteObjectStore("cells");
          const cells=db.createObjectStore("cells", {keyPath:"key"}); cells.createIndex("cell","cell");
          db.createObjectStore("metadata",{keyPath:"key"});
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
        request.onblocked = () => reject(new Error("Browser storage blocked"));
      });
      return opened;
    }
    async function run(mode, callback, stores=["cells"]) {
      const db = await open();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(stores, mode), request = callback(tx.objectStore(stores[0]),tx);
        tx.oncomplete = () => resolve(request.result);
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
      });
    }
    const metadata=entry=>Object.fromEntries(["key","cell","county_fips","savedAt","accessedAt","bytes"].map(k=>[k,entry[k]]));
    return {get:key=>run("readonly", s=>s.get(key)), all:()=>run("readonly", s=>s.getAll()),
      list:()=>run("readonly",s=>s.getAll(),["metadata"]),
      forCell:cell=>run("readonly",s=>s.index("cell").getAll(cell)),
      put:entry=>run("readwrite", (s,tx)=>{
        const request=s.get(entry.key);
        request.onsuccess=()=>{
          const old=request.result;
          if(!old || (old.checked_count || 0)<=(entry.checked_count || 0)) {
            s.put(entry);tx.objectStore("metadata").put(metadata(entry));
          }
        };
        return request;
      },["cells","metadata"]),
      touch:(key,time)=>run("readwrite", (s,tx)=>{
        const request=s.get(key);
        request.onsuccess=()=>{if(request.result) {
          const entry={...request.result,accessedAt:time};s.put(entry);tx.objectStore("metadata").put(metadata(entry));
        }};
        return request;
      },["cells","metadata"]),
      delete:key=>run("readwrite",(s,tx)=>{tx.objectStore("metadata").delete(key);return s.delete(key);},["cells","metadata"]),
      clear:()=>run("readwrite",(s,tx)=>{tx.objectStore("metadata").clear();return s.clear();},["cells","metadata"])};
  }
  function create({indexedDB, storage, now=Date.now, maxBytes=100*1024*1024}={}) {
    const backing = storage || disk(indexedDB), memory = new Map(), flights = new Map();
    let manifest, checkedAt=0, checking, epoch=0, diskFailed=false;
    const keyFor = (m,cell) => JSON.stringify(["v1","12091",m.source_url,m.dataset_version,m.boundary_version,m.crs,cell]);
    const retained = e => e && e.county_fips === "12091" && now()-e.savedAt < RETENTION && e.savedAt <= now();
    const valid = e => retained(e) && Array.isArray(e.features);
    async function safe(method, ...args) {
      try { return await backing[method](...args); }
      catch { diskFailed=true; return undefined; }
    }
    function trimMemory() {
      let bytes=0, count=0;
      for (const entry of [...memory.values()].sort((a,b)=>b.accessedAt-a.accessedAt)) {
        bytes+=entry.bytes; count++;
        if (bytes > Math.min(maxBytes,25*1024*1024) || count > 3) memory.delete(entry.key);
      }
    }
    async function prune() {
      const entries = await safe(backing.list ? "list" : "all") || [];
      let bytes=0;
      for (const entry of entries.sort((a,b)=>b.accessedAt-a.accessedAt)) {
        if(!retained(entry)) { await safe("delete",entry.key); continue; }
        bytes+=entry.bytes;
        if (bytes>maxBytes) { memory.delete(entry.key); await safe("delete",entry.key); }
      }
      trimMemory();
    }
    async function check(fetchManifest, force=false) {
      if (!force && manifest && now()-checkedAt < CHECK_INTERVAL
          && (!manifest.geometry_valid_until || Date.parse(manifest.geometry_valid_until)>now())) return {manifest};
      if (checking) {
        if(!force) return checking;
        await checking;
      }
      const checkEpoch=epoch;
      checking = (async()=>{
        try {
          const next = await fetchManifest();
          if (next.status!=="ready" || next.county_fips!=="12091"
              || !["source_url","dataset_version","boundary_version","crs"].every(k=>typeof next[k]==="string" && next[k])) throw new Error("Parcel manifest is invalid");
          if(checkEpoch!==epoch) throw new Error("Parcel cache was cleared during the version check");
          manifest=next; checkedAt=now(); return {manifest};
        } catch(error) { return {manifest,error}; }
        finally { checking=undefined; }
      })();
      return checking;
    }
    async function get(cell, m) {
      let entry;
      if (m) {
        const key=keyFor(m,cell);
        entry=memory.get(key) || await safe("get",key);
      } else {
        const entries=[...memory.values(),...(await safe(backing.forCell ? "forCell" : "all",cell) || [])];
        entry=entries.filter(e=>e.cell===cell && valid(e)).sort((a,b)=>b.savedAt-a.savedAt)[0];
      }
      if (!valid(entry)) return undefined;
      entry={...entry,accessedAt:now()}; memory.set(entry.key,entry); trimMemory();
      if(backing.touch) await safe("touch",entry.key,now());
      return entry;
    }
    async function put(cell,m,value,token=epoch) {
      if (token!==epoch) return;
      const entry={...value,key:keyFor(m,cell),cell,county_fips:"12091",manifest:m,savedAt:now(),accessedAt:now()};
      entry.bytes=JSON.stringify(entry).length*2;
      if (entry.bytes>maxBytes) return;
      memory.set(entry.key,entry); trimMemory();
      await safe("put",entry); await prune();
      return entry;
    }
    // One in-flight loader per version/cell. Selection ownership belongs to the caller.
    function single(cell,m,loader) {
      const key=keyFor(m,cell);
      if (!flights.has(key)) {
        const promise=Promise.resolve().then(loader).finally(()=>{if(flights.get(key)===promise) flights.delete(key);});
        flights.set(key,promise);
      }
      return flights.get(key);
    }
    async function remove(cell) {
      epoch++;
      for(const key of flights.keys()) if(JSON.parse(key).at(-1)===cell) flights.delete(key);
      for (const e of [...memory.values(),...(await safe(backing.list ? "list" : "all") || [])]) if(e.cell===cell) {
        memory.delete(e.key); await safe("delete",e.key);
      }
    }
    async function clear() { epoch++; memory.clear(); flights.clear(); manifest=undefined; checkedAt=0; await safe("clear"); }
    return {check,get,put,single,remove,clear,keyFor,prune,
      get token(){return epoch;}, get diskFailed(){return diskFailed;}};
  }
  return {create, disk, RETENTION, CHECK_INTERVAL};
});
