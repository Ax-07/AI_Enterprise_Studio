/* D07.3: isolated original Design 22.6 graphic functions, no simulation state or engine access.
 * robotSprite07, metal07 and tower181 are derived directly from design.js.
 * SVG strings contain only whitelisted static design palette and topology. */
(() => {
'use strict';
const robotNames07={'#49c9ff':'ATLAS','#48f4ad':'ORION','#37dded':'NEXUS','#ffcc67':'MIDAS','#c783ff':'HERMES','#ff9c67':'SENTINEL','#78a9ff':'CORE'};
function robotSprite07(c,n,scale=1){const name=robotNames07[c]||'CORE';const parts={ATLAS:'<path d="M-8 -28l3 -5 10 0 3 5" fill="#526f89" stroke="#bbd2e4"/><path d="M-3 -24h6" stroke="'+c+'" stroke-width="1.5"/>',ORION:'<circle cx="-10" cy="-24" r="3.5" fill="#254e47" stroke="'+c+'"/><circle cx="-10" cy="-24" r="1.6" fill="'+c+'"/>',NEXUS:'<path d="M10 -14l5 2 2 -5m-2 5 2 4" stroke="#d0ebf3" stroke-width="2" fill="none"/><path d="M-7 -31l3 -4 8 0 3 4" fill="#3c8293"/>',MIDAS:'<path d="M-8 -30l5 -3 6 0 5 3" fill="#e8ba6b"/><circle cy="-11" r="3" fill="#795c34" stroke="'+c+'"/>',HERMES:'<path d="M8 -28l4 -6" stroke="#d2c3ec" stroke-width="1.7"/><circle cx="12" cy="-34" r="2" fill="'+c+'"/><path d="M-10 -23v7m20 -7v7" stroke="'+c+'" stroke-width="2"/>',SENTINEL:'<path d="M-10 -16l-5 2v7l5 5 5 -5v-7z" fill="#8e6047" stroke="'+c+'"/><path d="M-7 -31h14l4 5" stroke="#d5ab88" stroke-width="2"/>',CORE:'<path d="M-4 -30h8" stroke="'+c+'" stroke-width="2"/>'};return `<g transform="scale(${scale})"><ellipse rx="10" ry="4" fill="#000a"/><ellipse rx="12" ry="5" fill="${c}" opacity=".14"/><g class="robot-body" style="--delay:-${n*.6}s"><path d="M-4 -8v5m8-5v5" stroke="#8297ac" stroke-width="4" stroke-linecap="round"/><path d="M-7 -2h5m4 0h5" stroke="#d6e6ee" stroke-width="3.1" stroke-linecap="round"/><path d="M-8 -17l-4 8m20-8 4 8" stroke="#7992a6" stroke-width="4.2" stroke-linecap="round"/><circle cx="-12" cy="-9" r="2" fill="#c7dce7"/><circle cx="12" cy="-9" r="2" fill="#c7dce7"/><path d="M-7 -19 Q-10 -13 -5 -7 H5 Q10 -13 7 -19Z" fill="url(#robot07Metal)" stroke="#6c879c"/><path d="M-4 -16h8l-1 4h-6z" fill="${c}" opacity=".9"/><rect x="-11" y="-33" width="22" height="17" rx="7" fill="url(#robot07Metal)" stroke="#c4deef" stroke-width=".6"/><rect x="-9" y="-29" width="18" height="10" rx="4.5" fill="#050e1d" stroke="#395a73" stroke-width=".7"/><path d="M-7 -28h12" stroke="#a8d9eb" stroke-opacity=".25" stroke-width=".7"/><g class="robot-eye" style="--delay:-${n*.41}s" fill="${c}"><rect x="-5.8" y="-25.8" width="4" height="4.5" rx="1.8"/><rect x="1.8" y="-25.8" width="4" height="4.5" rx="1.8"/></g>${parts[name]}<path d="M-8 -30l2 -1M-5 -18h10" stroke="#fff" stroke-opacity=".6" stroke-width=".65"/></g></g>`}
const metal07='<linearGradient id="robot07Metal" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#f1f8ff"/><stop offset=".30" stop-color="#bfdbec"/><stop offset=".67" stop-color="#8199af"/><stop offset="1" stop-color="#344b65"/></linearGradient>';
const levelLabel=n=>n===0?'RDC':String(n).padStart(2,'0');
function tower181(b,from){const ids=b.floors.map(f=>f.id),c=b.color,h=ids.length*32+80,base=ids.length*32+32;let q=`<svg class="lift-tower" viewBox="0 0 210 ${h}" aria-hidden="true"><defs><linearGradient id="wall181" x2="1" y2="1"><stop stop-color="#334e68"/><stop offset="1" stop-color="#142638"/></linearGradient><linearGradient id="side181" x2="1" y2="1"><stop stop-color="#1b3045"/><stop offset="1" stop-color="#0a1421"/></linearGradient><radialGradient id="light181"><stop stop-color="${c}" stop-opacity=".34"/><stop offset="1" stop-color="${c}" stop-opacity="0"/></radialGradient></defs><ellipse cx="110" cy="${base+17}" rx="100" ry="25" fill="url(#light181)"/><path d="M16 ${base+6} L105 ${base-37} 194 ${base+6} 105 ${base+49}Z" fill="#152c3d" stroke="#446176"/><path d="M16 ${base+6}v7l89 43 89-43v-7l-89 43Z" fill="#0a1927" stroke="#304b60"/><path d="M48 35L111 4 175 35 111 66Z" fill="#3d536b" stroke="${c}"/><path d="M67 35L111 13 157 35 111 57Z" fill="#1a3047" stroke="#80a9bd"/><path d="M111 5V0" stroke="${c}" stroke-width="2"/>`;
for(let i=ids.length-1;i>=0;i--){let y=35+(ids.length-1-i)*32;let id=ids[i];q+=`<g data-level181="${i}" class="level181 ${id===from?'current181':''}" data-level-id="${id}"><path d="M48 ${y}L111 ${y+31}V${y+63}L48 ${y+32}Z" fill="url(#wall181)" stroke="${c}" stroke-opacity=".6"/><path d="M111 ${y+31}L175 ${y}V${y+32}L111 ${y+63}Z" fill="url(#side181)" stroke="${c}" stroke-opacity=".7"/>`;
for(let j=0;j<4;j++){let x=54+j*14, yy=y+8+j*6.9;q+=`<path d="M${x} ${yy}l9 4.4v14l-9 -4.4Z" fill="${c}" opacity="${j%2?.48:.75}"/><path d="M${118+j*13} ${y+36-j*6.4}l9 -4.4v14l-9 4.4Z" fill="${c}" opacity="${j%2?.58:.85}"/>`}
q+=`<path d="M48 ${y+30}L111 ${y+61} 175 ${y+30}" fill="none" stroke="${c}" stroke-opacity=".65"/><text x="35" y="${y+21}" text-anchor="end" fill="${c}" font-size="11" font-weight="700">${levelLabel(i)}</text>${id===from?`<circle cx="182" cy="${y+18}" r="3.5" fill="${c}"/>`:''}</g>`}return q+'</svg>'}
const palette=new Set(Object.keys(robotNames07));
let serial=0;
function parse(markup){
    const doc=new DOMParser().parseFromString(markup,'image/svg+xml');
    if(doc.documentElement.localName!=='svg')throw Error('Dessin SVG invalide');
    return document.importNode(doc.documentElement,true);
}
function robot(color,scale=1){
    if(!palette.has(color))color='#78a9ff';
    const id='liveRobotMetal'+(++serial),safeScale=scale===.55?.55:scale===.8?.8:1;
    const graphic=parse('<svg xmlns="http://www.w3.org/2000/svg"><defs>'+metal07.replaceAll('robot07Metal',id)+'</defs>'+robotSprite07(color,0,safeScale).replaceAll('robot07Metal',id)+'</svg>');
    const g=document.createElementNS('http://www.w3.org/2000/svg','g');
    g.append(...graphic.children);return g;
}
function tower(b,from){
    if(!palette.has(b.color)||!Array.isArray(b.floors)||b.floors.length>20||b.floors.some(f=>!/^[A-Z][A-Z0-9]*$/.test(f.id)))throw Error('Topologie graphique invalide');
    return parse(tower181(b,from).replace('<svg ','<svg xmlns="http://www.w3.org/2000/svg" '));
}
window.AESLiveArt=Object.freeze({robot,tower});
})();
