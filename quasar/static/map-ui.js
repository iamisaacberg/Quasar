/* Search and playback controls. Geocodes are temporary; playback never imports. */
(function(root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.QuasarMapUI = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function() {
  "use strict";
  function ringLocation(point, ring) {
    let inside = false;
    for (let i=1;i<ring.length;i++) {
      const a=ring[i-1], b=ring[i];
      const cross=(point[0]-a[0])*(b[1]-a[1])-(point[1]-a[1])*(b[0]-a[0]);
      if (Math.abs(cross)<1e-12 && [0,1].every(k=>point[k]>=Math.min(a[k],b[k])-1e-12 && point[k]<=Math.max(a[k],b[k])+1e-12)) return 0;
      if ((a[1]>point[1]) !== (b[1]>point[1]) && point[0]<(b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0]) inside=!inside;
    }
    return inside ? 1 : -1;
  }
  function covers(point, geometry) {
    if (!Array.isArray(point) || point.length!==2 || !point.every(Number.isFinite)) return false;
    const parts=geometry.type==="MultiPolygon" ? geometry.coordinates : geometry.type==="Polygon" ? [geometry.coordinates] : [];
    return parts.some(rings=>ringLocation(point,rings[0])>=0 && rings.slice(1).every(hole=>ringLocation(point,hole)<=0));
  }
  function bounds(geometry) {
    const points=geometry.coordinates.flat(geometry.type==="MultiPolygon" ? 2 : 1);
    return [Math.min(...points.map(p=>p[0])),Math.min(...points.map(p=>p[1])),Math.max(...points.map(p=>p[0])),Math.max(...points.map(p=>p[1]))];
  }
  function createSearch({get, element, token, geometry, select, request=fetch, schedule=setTimeout, cancel=clearTimeout}) {
    const input=get("map-search"), list=get("map-search-results"), status=get("map-search-status");
    let results=[], active=-1, version=0, controller, timer;
    const message=text=>{status.textContent=text;};
    function draw() {
      list.replaceChildren(); list.hidden=results.length===0;
      input.setAttribute("aria-expanded",String(results.length>0));
      input.removeAttribute("aria-activedescendant");
      results.forEach((feature,i)=>{
        const option=element("li"); option.id=`map-search-option-${i}`;option.setAttribute("role","option");
        option.setAttribute("aria-selected",String(i===active));
        const button=element("button",feature.properties?.full_address || feature.properties?.name || "Location");
        button.type="button";button.tabIndex=-1;button.onclick=()=>choose(i);option.append(button);list.append(option);
        if(i===active)input.setAttribute("aria-activedescendant",option.id);
      });
    }
    function invalidate() {version++;controller?.abort();cancel(timer);}
    function choose(index) {
      const feature=results[index]; if(!feature)return;
      invalidate(); input.value=feature.properties?.full_address || feature.properties?.name || "Location";
      results=[];active=-1;draw();select(feature);message("Location selected. Parcel and flood scores remain unknown.");
      input.focus();
    }
    const enabled=Boolean(token?.startsWith("pk.") && geometry);
    input.disabled=!enabled;get("map-search-clear").disabled=!enabled;
    message(enabled ? "Search addresses and places in Okaloosa County." : "Search requires a configured map and an available county boundary.");
    input.oninput=()=>{
      invalidate(); results=[];active=-1;draw();
      const query=input.value.trim(), ticket=version;
      if(query.length<3){message("Enter at least three characters.");return;}
      message("Searching Okaloosa County…");
      timer=schedule(async()=>{
        controller=new AbortController();
        try {
          const params=new URLSearchParams({q:query,access_token:token,country:"us",bbox:bounds(geometry).join(","),types:"address,street,place,locality,neighborhood",autocomplete:"true",limit:"5"});
          const response=await request(`https://api.mapbox.com/search/geocode/v6/forward?${params}`,{signal:controller.signal});
          if(!response.ok)throw new Error("Search provider unavailable");
          const data=await response.json(); if(ticket!==version)return;
          results=(data.features||[]).filter(f=>f.geometry?.type==="Point" && covers(f.geometry.coordinates,geometry));
          active=-1;draw();message(results.length ? `${results.length} county results. Use arrow keys and Enter to select.` : "No matching locations in Okaloosa County.");
        } catch(error) {if(ticket===version && error.name!=="AbortError")message("Search unavailable. Try again shortly.");}
      },300);
    };
    input.onkeydown=event=>{
      if(event.key==="Escape"){invalidate();results=[];active=-1;draw();message("Search closed.");}
      if(["ArrowDown","ArrowUp"].includes(event.key) && results.length){event.preventDefault();active=event.key==="ArrowDown"?(active+1)%results.length:active<=0?results.length-1:active-1;draw();}
      if(event.key==="Enter"){event.preventDefault();if(results.length)choose(active<0?0:active);}
    };
    get("map-search-clear").onclick=()=>{invalidate();input.value="";results=[];active=-1;draw();select(null);message("Search cleared.");input.focus();};
    return {close:()=>{invalidate();results=[];active=-1;draw();}};
  }
  const localTime=value=>new Date(value).toLocaleString("en-US",{timeZone:"America/Chicago",month:"short",day:"numeric",hour:"numeric",timeZoneName:"short"});
  function createPlayback({get, select, every=setInterval, stop=clearInterval}) {
    let kind="none", times=[], index=0, timer=null, busy=false, generation=0, available=false, note="Waiting for imported forecast data.";
    function draw() {
      get("replay-play").textContent=timer===null ? "▶" : "Ⅱ";
      get("replay-play").setAttribute("aria-label",timer===null?"Play Isaias timeline":"Pause playback");
      get("replay-play").setAttribute("aria-pressed",String(timer!==null));
      get("replay-prev").disabled=!available || busy || index===0;
      get("replay-next").disabled=!available || busy || index>=times.length-1;
      get("replay-play").disabled=!available || busy || times.length<2;
      get("replay-hour").disabled=!available || busy || times.length<2;
      get("replay-hour").max=String(Math.max(0,times.length-1));get("replay-hour").value=String(index);
      get("replay-hour").setAttribute("aria-valuetext",times[index]?localTime(times[index]):"Unavailable");
      get("playback-clock").textContent=times[index] ? `${kind==="archive"?"Isaias":"Forecast"} · ${localTime(times[index])}` : "Isaias archive unavailable";
      get("playback-status").textContent=busy?"Loading selected hour…":note;
    }
    function pause() {if(timer!==null)stop(timer);timer=null;draw();}
    async function go(next) {
      if(!available || busy || next<0 || next>=times.length)return;
      const ticket=++generation;busy=true;draw();
      try {
        const ok=await select(kind,next);
        if(ticket!==generation)return;
        if(ok===false){note="Selected hour unavailable. Previous results retained.";pause();}
        else {index=next;if(index===times.length-1)pause();}
      } catch {if(ticket===generation){note="Selected hour unavailable. Previous results retained.";pause();}}
      finally {if(ticket===generation){busy=false;draw();}}
    }
    get("replay-prev").onclick=()=>{pause();return go(index-1);};
    get("replay-next").onclick=()=>{pause();return go(index+1);};
    get("replay-hour").oninput=()=>{const next=Number(get("replay-hour").value);pause();return go(next);};
    get("replay-play").onclick=async()=>{
      if(timer!==null){pause();return;}
      if(!available || busy || times.length<2)return;
      if(index===times.length-1)await go(0);
      if(!available || index===times.length-1)return;
      timer=every(()=>{if(!busy)void go(index+1);},1000);draw();
    };
    return {pause, configure(nextKind,nextTimes,nextIndex=0,enabled=true,message="Following six-hour rainfall · mm / 6h") {
      if(nextKind!==kind){pause();generation++;busy=false;}
      kind=nextKind;times=nextTimes;index=nextIndex;available=enabled && times.length>0;note=message;
      if(!available)pause();draw();
    }};
  }
  return {covers,bounds,createSearch,createPlayback,localTime};
});
