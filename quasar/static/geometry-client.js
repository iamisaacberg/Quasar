/* Geometry work stays off the UI thread; stale replies cannot own a selection. */
(function(root,factory){
  if(typeof module==="object" && module.exports)module.exports=factory();else root.QuasarGeometryClient=factory();
})(typeof globalThis!=="undefined"?globalThis:this,function(){
  function create(worker){
    let next=0,boundary,epoch=0,failed;
    const pending=new Map(),grids=new Map(),flights=new Map();
    function fail(error){failed=error;for(const request of pending.values())request.reject(error);pending.clear();flights.clear();grids.clear();}
    worker.onmessage=({data})=>{
      const request=pending.get(data.id);if(!request)return;pending.delete(data.id);
      if(data.error)return request.reject(new Error(data.error));
      if(request.epoch!==epoch)return request.reject(new Error("County geometry changed"));
      if(data.grid)grids.set(data.resolution,data.grid);
      if(typeof globalThis!=="undefined")globalThis.QuasarPerformance?.record("geometry",{duration_ms:data.duration_ms,resolution:data.resolution});
      request.resolve({grid:grids.get(data.resolution),rainfall:data.rainfall});
    };
    worker.onerror=()=>fail(new Error("Geometry worker unavailable. County overlays could not be prepared."));
    worker.onmessageerror=()=>fail(new Error("Geometry worker returned an unreadable response."));
    return {coverage(geometry,resolution,weather){
      if(failed)return Promise.reject(failed);
      if(boundary!==geometry){boundary=geometry;epoch++;grids.clear();worker.postMessage({type:"boundary",geometry});}
      const key=JSON.stringify([epoch,resolution,weather]);
      if(flights.has(key))return flights.get(key);
      const id=++next;
      const promise=new Promise((resolve,reject)=>{
        pending.set(id,{resolve,reject,epoch});worker.postMessage({type:"coverage",id,resolution,weather});
      }).finally(()=>flights.delete(key));
      flights.set(key,promise);return promise;
    }};
  }
  return {create};
});
