'use strict';
window.AtlasRouteEngine=(()=>{
  const distance=(a,b)=>Math.hypot((a.atlas_x-b.atlas_x)*4096,(a.atlas_y-b.atlas_y)*4096);
  function nearestNeighbor(points,start){
    if(!points.length)return[];
    const remaining=[...points],ordered=[];
    let current=start||remaining.shift();
    if(start)ordered.push(start);else ordered.push(current);
    while(remaining.length){
      let bestIndex=0,bestDistance=Infinity;
      for(let i=0;i<remaining.length;i++){
        const d=distance(current,remaining[i]);
        if(d<bestDistance){bestDistance=d;bestIndex=i}
      }
      current=remaining.splice(bestIndex,1)[0];ordered.push(current)
    }
    return ordered
  }
  function improveTwoOpt(route,maxPasses=4){
    if(route.length<4)return route;
    const result=[...route];
    for(let pass=0;pass<maxPasses;pass++){
      let improved=false;
      for(let i=1;i<result.length-2;i++)for(let k=i+1;k<result.length-1;k++){
        const before=distance(result[i-1],result[i])+distance(result[k],result[k+1]);
        const after=distance(result[i-1],result[k])+distance(result[i],result[k+1]);
        if(after+0.001<before){result.splice(i,k-i+1,...result.slice(i,k+1).reverse());improved=true}
      }
      if(!improved)break
    }
    return result
  }
  function optimize(points,start){
    const unique=[...new Map(points.map(p=>[p.id,p])).values()];
    if(!unique.length)return[];
    const startPoint=start&&unique.find(p=>p.id===start.id)||start||unique[0];
    const rest=unique.filter(p=>p.id!==startPoint.id);
    return improveTwoOpt(nearestNeighbor(rest,startPoint))
  }
  function totalDistance(route){let total=0;for(let i=1;i<route.length;i++)total+=distance(route[i-1],route[i]);return total}
  function estimateMinutes(distanceUnits){return Math.max(1,Math.round(distanceUnits/115))}
  function metrics(route){const d=totalDistance(route);return{distance:d,minutes:estimateMinutes(d),stops:route.length}}
  return{distance,optimize,totalDistance,estimateMinutes,metrics}
})();