function onReady(fn){if(document.readyState!=='loading'){fn();}else{document.addEventListener('DOMContentLoaded',fn);}}
onReady(function(){
var mt=document.querySelector('.menu-toggle'),nv=document.querySelector('.blk-nav');
if(mt&&nv){var mSync=function(open){nv.classList.toggle('open',open);mt.setAttribute('aria-expanded',open)};
mt.addEventListener('click',function(){mSync(!nv.classList.contains('open'))});
nv.addEventListener('click',function(e){if(e.target.closest('a'))mSync(false)});
document.addEventListener('keydown',function(e){if(e.key==='Escape')mSync(false)});
document.addEventListener('click',function(e){if(nv.classList.contains('open')&&!nv.contains(e.target)&&!mt.contains(e.target))mSync(false)});
}
/* contact e-mail: built here so the hosting proxy never rewrites a plain-text
   mailto into an undecodable "[email protected]" stub (broken link on live pages) */
[].slice.call(document.querySelectorAll('.js-mail')).forEach(function(a){
var u=a.getAttribute('data-u'),d=a.getAttribute('data-d');
if(!u||!d){return}
var mail=u+'@'+d;a.textContent=mail;a.setAttribute('href','mailto:'+mail)});
/* sticky header: elevated state after a small scroll */
var hd=document.querySelector('.blk-header');
if(hd){var hUpd=function(){hd.classList.toggle('is-scrolled',window.scrollY>18)};
window.addEventListener('scroll',hUpd,{passive:true});hUpd();}
/* floating mobile CTA: appears deep into the page, points at the form */
if(window.matchMedia&&window.matchMedia('(max-width:760px)').matches&&!document.querySelector('.blk-float-cta')){
var fEl=document.createElement('div');fEl.className='blk-float-cta';
var fSrc=document.querySelector('.blk-header .blk-btn');
var fTgt=document.getElementById('claim')?'#claim':'index.php#claim';
fEl.innerHTML='<a class="blk-btn" href="'+fTgt+'">'+(fSrc?fSrc.textContent:'Open account')+'</a>';
document.body.appendChild(fEl);
var fUpd=function(){fEl.classList.toggle('is-on',window.scrollY>700)};
window.addEventListener('scroll',fUpd,{passive:true});fUpd();}
/* reveal on scroll: sections fade in once (skipped for reduced motion / no IO) */
var secs=[].slice.call(document.querySelectorAll('main > .sec'));
var still=function(){document.documentElement.classList.add('has-anim')};
if('IntersectionObserver' in window&&!(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches)){
still();
var io=new IntersectionObserver(function(es){es.forEach(function(e){
if(e.isIntersecting){e.target.classList.add('is-in');io.unobserve(e.target)}})},
{threshold:.08,rootMargin:'0px 0px -36px'});
secs.forEach(function(s,i){s.style.setProperty('--reveal-order',i%4);io.observe(s)});
}else{secs.forEach(function(s){s.classList.add('is-in')});}
/* editorial numbering: 01/ 02/ ... chips inside each section eyebrow */
var sn=0;secs.forEach(function(s){var ey=s.querySelector('.eyebrow');if(!ey)return;
sn++;var chip=document.createElement('i');chip.className='sec-num';chip.setAttribute('aria-hidden','true');
chip.textContent=(sn<10?'0':'')+sn;ey.insertBefore(chip,ey.firstChild)});
var ll=document.getElementById('live-latency'),lo=document.getElementById('live-orders');
if(ll&&!window.__noLiveTick){setInterval(function(){ll.textContent=(38+Math.floor(Math.random()*24))+' ms'},4000)}
if(lo){setInterval(function(){lo.textContent=(1200+Math.floor(Math.random()*400)).toLocaleString()},5000)}
var cd=document.getElementById('countdown');
if(cd){var end=Date.now()+1000*60*60*26+1000*60*13;
setInterval(function(){var s=Math.max(0,Math.floor((end-Date.now())/1000));
var d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60),sec=s%60;
var map={'days':[d,2],'hours':[h,2],'minutes':[m,2],'seconds':[sec,2]};
Object.keys(map).forEach(function(k){var el=cd.querySelector('[data-unit="'+k+'"]');
if(el)el.textContent=String(map[k][0]).padStart(map[k][1],'0')})},1000)}
});