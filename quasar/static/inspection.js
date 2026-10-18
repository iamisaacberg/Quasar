/* Descriptive context is independent from illustrative exercise scoring. */
(function(root,factory) {
  if(typeof module==="object" && module.exports) module.exports=factory();
  else root.QuasarInspection=factory();
})(typeof globalThis!=="undefined"?globalThis:this,function() {
  "use strict";
  const number=value=>typeof value==="number" && Number.isFinite(value);
  const value=(n,unit="")=>number(n)?`${n.toFixed(2)}${unit}`:"Unknown";
  const percent=n=>number(n)?`${(n*100).toFixed(2)}%`:"Unknown";
  function rainfallSummary(context,current) {
    const overlaps=context?.forecast_overlaps || [], features=current?.weather_cells?.features || [];
    const matched=overlaps.map(overlap=>features.find(f=>f.id===overlap.native_cell_id && JSON.stringify(f.geometry)===JSON.stringify(overlap.geometry)));
    const values=matched.filter(f=>f?.properties.status==="ready" && number(f.properties.rainfall_6h_mm) && f.properties.rainfall_6h_mm>=0).map(f=>f.properties.rainfall_6h_mm);
    if(!values.length) return {value:"Unavailable",detail:overlaps.length ? "Rainfall is unavailable for the selected archive hour." : "Prepared native-cell overlaps are unavailable for this selection."};
    const low=Math.min(...values),high=Math.max(...values);
    return {value:low===high ? low.toFixed(1) : `${low.toFixed(1)}–${high.toFixed(1)}`,
      detail:`${values.length}/${overlaps.length} overlapping native cells available${values.length<overlaps.length || context?.forecast_coverage_complete===false ? " · Partial coverage; hex remains transparent" : ""}. Forecast rainfall at the source grid resolution, not parcel flood depth.`};
  }
  function forecastRows(context,current) {
    if(current?.mode==="synthetic_demo") return [["Forecast rainfall","Exercise rainfall is not applied to real parcels."]];
    const overlaps=context?.forecast_overlaps || [], cells=current?.weather_cells;
    if(!cells || !overlaps.length) return [["Forecast rainfall","Unavailable: native forecast overlap is not prepared for this selection."]];
    const native=new Map(cells.features.map(f=>[f.id,f]));
    const rows=overlaps.map((overlap,index)=>{
      const feature=native.get(overlap.native_cell_id), p=feature?.properties;
      const match=feature && JSON.stringify(feature.geometry)===JSON.stringify(overlap.geometry);
      const ready=match && p.status==="ready" && number(p.rainfall_6h_mm) && p.rainfall_6h_mm>=0;
      return [`Native rainfall ${index+1}${number(overlap.area_fraction) ? ` · ${percent(overlap.area_fraction)} overlap` : ""}`,
        ready?`${p.rainfall_6h_mm.toFixed(1)} mm / 6h`:`Unavailable · ${match?p.status:"native geometry not matched"}`];
    });
    const initializations=[...new Set(overlaps.map(o=>native.get(o.native_cell_id)?.properties.init_time).filter(Boolean))];
    rows.push(["Forecast window",`${cells.valid_from || current.scenario?.valid_from || "Unknown"} – ${cells.valid_to || current.scenario?.valid_to || "Unknown"}`],
      ["Initialized",initializations.join(", ") || current.forecast?.init_time || "Unknown"],
      ["Imported",cells.retrieved_at || "Unknown"], ["Native resolution",`${cells.native_resolution || "Unknown"} · ensemble mean`],
      ["Forecast source",cells.source_table || "Unknown"]);
    if(current.mode==="what_if_exercise") rows.push(["Rainfall scenario","Includes the selected synthetic what-if addition; not archived rainfall alone."]);
    return rows;
  }
  function parcelRows(context,current) {
    const inputs=context?.inputs || {}, terrain=inputs.terrain || {}, fema=inputs.fema || {}, hydro=inputs.hydrography || {};
    const rows=forecastRows(context,current);
    rows.push(["Geometry input status",inputs.geometry_status?.replaceAll("_"," ") || "Unknown"],
      ["Terrain coverage",terrain.status?.replaceAll("_"," ") || "Unknown"],
      ["Terrain minimum / mean / maximum",`${value(terrain.min_m)} / ${value(terrain.mean_m)} / ${value(terrain.max_m)} m`],
      ["Valid native pixel centers",`${terrain.valid_pixel_centers ?? "Unknown"} / ${terrain.pixel_centers ?? "Unknown"} · ${percent(terrain.valid_fraction)}`],
      ["Interior point sample (separate)",value(terrain.representative_point_m," m")],
      ["Terrain datum",terrain.vertical_datum || "Unknown; not building/floor elevation"],
      ["FEMA coverage",fema.status || "Unknown"], ["FEMA mapped / unmapped",`${percent(fema.mapped_area_fraction)} / ${percent(fema.unmapped_area_fraction)}`],
      ["Mapped SFHA fraction",percent(fema.sfha_mapped_area_fraction)],
      ["FEMA reference status",fema.sfha_reference_status || context?.provenance?.fema?.later_revision_completeness || "Unknown"]);
    for(const hit of fema.overlaps || []) rows.push([`FEMA ${hit.FLD_ZONE || "Unknown"}${hit.ZONE_SUBTY?` · ${hit.ZONE_SUBTY}`:""}`,
      `${percent(hit.parcel_area_fraction)} · source ${hit.FLD_AR_ID || "Unknown"}`]);
    rows.push(["Mapped river/stream distance",value(hydro.nearest_retained_river_stream_distance_m," m")],
      ["Mapped waterway source",hydro.nearest_feature ? `${hydro.nearest_feature.layer} · ${hydro.nearest_feature.source_id}` : "Unknown"],
      ["Waterway coverage",hydro.status?.replaceAll("_"," ") || "Unknown"], ["Hydrologic connectivity / gauge linkage","Unknown; mapped proximity is descriptive only"]);
    return rows;
  }
  function provenance(context) {
    if(!context) return "Prepared input provenance unavailable.";
    const p=context.provenance || {}, terrain=p.terrain || {}, fema=p.fema || {};
    return `Prepared ${context.prepared_at || "Unknown"}. Terrain: ${terrain.source_dates?.join?.(", ") || terrain.source_date_range || "see source metadata"}; ${terrain.vertical_datum || "NAVD88"}, meters. FEMA panel dates: ${(fema.panel_effective_dates || []).join(", ") || "Unknown"}; package publication: ${(fema.package_publication_dates || []).join(", ") || "Unknown"}. ${fema.later_revision_completeness || "Later map revisions unverified"}. Lakes, canals and coastal water coverage are incomplete. No parcel score is calculated.`;
  }
  return {forecastRows,parcelRows,provenance,rainfallSummary};
});
