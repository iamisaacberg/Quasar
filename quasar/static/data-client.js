/* Session-only public data reuse. No credentials or forecast values on disk. */
(function(root,factory){
  if(typeof module==="object" && module.exports) module.exports=factory();
  else {root.QuasarPerformance=factory().metrics();root.QuasarData=factory().create({measure:root.QuasarPerformance.record});}
})(typeof globalThis!=="undefined"?globalThis:this,function(){
  "use strict";
  function metrics(){
    const samples=[];
    return {record(name,detail={}){samples.push({name,at:Date.now(),...detail});if(samples.length>500)samples.shift();},
      snapshot:()=>samples.map(sample=>({...sample})),clear:()=>{samples.length=0;}};
  }
  function create({fetcher=(...args)=>fetch(...args),now=Date.now,maxBytes=20*1024*1024,measure=()=>{}}={}){
    const cache=new Map(), flights=new Map(), generations=new Map();
    function invalidate(prefix=""){
      for(const key of new Set([...cache.keys(),...flights.keys(),...generations.keys()]))if(key.startsWith(prefix)){
        cache.delete(key);flights.delete(key);generations.set(key,(generations.get(key)||0)+1);
      }
    }
    function remember(key,value,ttl,bytes){
      const expiry=Date.parse(value.expires_at);
      const until=Math.min(now()+ttl,Number.isFinite(expiry)?expiry:Infinity);
      if(until<=now() || bytes>maxBytes)return;
      cache.delete(key);cache.set(key,{value,until,bytes});
      let total=[...cache.values()].reduce((n,e)=>n+e.bytes,0);
      while(total>maxBytes){const oldest=cache.keys().next().value;total-=cache.get(oldest).bytes;cache.delete(oldest);}
    }
    function peek(key){
      const entry=cache.get(key);
      if(!entry || entry.until<=now()){cache.delete(key);return;}
      cache.delete(key);cache.set(key,entry);return entry.value;
    }
    function consumer(promise,signal){
      if(!signal)return promise;
      return new Promise((resolve,reject)=>{
        const abort=()=>reject(new DOMException("Request abandoned","AbortError"));
        if(signal.aborted)return abort();
        signal.addEventListener("abort",abort,{once:true});
        promise.then(value=>{signal.removeEventListener("abort",abort);if(!signal.aborted)resolve(value);},error=>{signal.removeEventListener("abort",abort);reject(error);});
      });
    }
    function get(key,{signal,force=false,ttl=15000}={}){
      if(key.startsWith("/api/exposure"))ttl=0;
      if(force)invalidate(key);
      const cached=peek(key);
      if(cached){measure("request",{url:key,cache:"hit",duration_ms:0});return consumer(Promise.resolve(cached),signal);}
      if(flights.has(key)){measure("request",{url:key,cache:"shared"});return consumer(flights.get(key),signal);}
      const generation=generations.get(key)||0,start=now();
      const promise=(async()=>{
        const response=await fetcher(key,{cache:"no-store"});
        let value,bytes;
        if(response.text){const body=await response.text();bytes=new TextEncoder().encode(body).byteLength;value=JSON.parse(body);}
        else {value=await response.json();bytes=JSON.stringify(value).length*2;}
        if(!response.ok)throw new Error(value.error||"Request failed");
        measure("request",{url:key,cache:"miss",duration_ms:now()-start,bytes});
        // Failed/unavailable reads never become successful cached states.
        if(generation===(generations.get(key)||0) && !["unavailable","invalid","changed","stale","not_configured"].includes(value.status))remember(key,value,ttl,bytes);
        return value;
      })().finally(()=>{if(flights.get(key)===promise)flights.delete(key);});
      flights.set(key,promise);return consumer(promise,signal);
    }
    return {get,invalidate,peek};
  }
  return {create,metrics};
});
