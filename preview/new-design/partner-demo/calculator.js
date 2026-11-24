/* calculator.js — deposit projection demo. Illustrative only, no promises.
   Reads currency/locale words from data attributes on #calculator (ui.* content keys). */
(function(){
'use strict';
var LOCALE=document.documentElement.getAttribute('lang')||'cs-CZ';
function fmtNum(v){
  try{return new Intl.NumberFormat(LOCALE,{maximumFractionDigits:0}).format(v);}
  catch(e){return Math.round(v).toString();}
}
function compound(start,monthly,years,rate){
  var r=Math.pow(1+rate/100,1/12)-1,v=start,m=monthly;
  var pts=[],yr=0;
  for(var i=1;i<=years*12;i++){
    v=v*(1+r)+m;
    if(i%12===0){yr++;pts.push(v);}
  }
  return{final:v,series:pts};
}
function onReady(fn){if(document.readyState!=='loading'){fn();}else{document.addEventListener('DOMContentLoaded',fn);}}
onReady(function(){
  var box=document.getElementById('calculator');if(!box)return;
  var $=function(id){return document.getElementById(id);};
  var eInit=$('initial'),eMon=$('monthly'),eYrs=$('years'),
      eRate=$('rate'),eVal=$('future-value'),eRes=$('result-years'),
      eCon=$('contributed'),eGain=$('gain'),eErr=$('calc-error'),
      gLine=$('growth-line'),gArea=$('calc-area'),cLine=$('contribution-line'),
      eYL=$('years-label'),eRL=$('rate-label'),eEnd=$('end-year'),axis=box.querySelector('.chart-axis span:last-child');
  var curSym=box.getAttribute('data-cur-sym')||'',curCode=box.getAttribute('data-cur-code')||'',
      wFull=box.getAttribute('data-w-full')||'',wShort=box.getAttribute('data-w-short')||'',
      minInit=parseFloat(box.getAttribute('data-min-init'))||250;
  if(curCode==='CZK'){eInit.min=minInit;eInit.step=50;}
  function money(v,sign){
    var s=fmtNum(Math.abs(Math.round(v)));
    return(sign&&v>=0?'+':'')+(curSym?s+'\u00a0'+curSym:s);
  }
  function draw(){
    var start=parseFloat(eInit.value)||0,mon=parseFloat(eMon.value)||0,
        yrs=parseInt(eYrs.value,10)||1,rate=parseFloat(eRate.value)||0;
    if(curCode==='CZK'&&start<minInit){eErr.textContent='';
      start=minInit;eInit.value=String(minInit);}
    eYL.textContent=String(yrs);eRL.textContent=(new Intl.NumberFormat(LOCALE,{maximumFractionDigits:1}).format(rate))+' %';
    var res=compound(start,mon,yrs,rate),
        contributed=start+mon*yrs*12,gain=res.final-contributed;
    eVal.textContent=money(res.final,false);
    eRes.textContent=yrs+'\u00a0'+wFull;
    eCon.textContent=money(contributed,false);
    eGain.textContent=money(gain,true);
    eEnd.textContent='+'+yrs+'\u00a0'+wShort;
    /* svg paths */
    var svg=$('calc-chart');if(svg){
      var W=500,H=200,pad=8,series=res.series,len=series.length||1,
          max=Math.max(start,res.final)||1,st=(W-pad*2)/Math.max(1,len);
      function Y(v){return(H-pad)-(v/max)*(H-pad*2);}
      function X(i){return pad+i*st;}
      var dg='',dc='',cr=start;
      for(var i=0;i<len;i++){dg+=(i?' L':'M')+X(i).toFixed(1)+' '+Y(series[i]).toFixed(1);
        dc+=(i?' L':'M')+X(i).toFixed(1)+' '+Y(cr).toFixed(1);cr+=mon*12;}
      gLine.setAttribute('d',dg);
      gArea.setAttribute('d',dg+' L'+X(len-1).toFixed(1)+' '+(H-pad)+' L'+pad+' '+(H-pad)+' Z');
      cLine.setAttribute('d',dc);
    }
  }
  ['initial','monthly','years','rate'].forEach(function(id){
    var el=$(id);if(!el)return;
    el.addEventListener('input',draw);
  });
  Array.prototype.forEach.call(box.querySelectorAll('.rate-presets button'),function(b){
    b.addEventListener('click',function(){eRate.value=b.getAttribute('data-rate');draw();});
  });
  draw();
});
})();
