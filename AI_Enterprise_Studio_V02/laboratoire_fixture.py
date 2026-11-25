"""Reconstructed audit JS from the owner's pasted V1; not the original SQLite artifact."""
HTML="""<!doctype html><html lang="fr"><meta charset="utf-8"><title>Mini-audit catalogue interne</title>
<textarea id="data">{}</textarea><button id="run" type="button">Auditer</button><pre id="out"></pre>
<script>
(function(){
 'use strict';
 const input=document.getElementById('data'), out=document.getElementById('out');
 function run(){
  try{
   const d=JSON.parse(input.value);
   if(!d || !Array.isArray(d.locales) || !d.locales.length || !Array.isArray(d.rows)) throw Error('Format attendu : locales non vide et rows, deux tableaux.');
   const clean=x=>typeof x==='string'?x.trim():'';
   const locales=d.locales.map(clean);
   if(locales.some(x=>!x) || new Set(locales).size!==locales.length) throw Error('Locales attendues invalides ou répétées.');
   const rows=d.rows.map((r,i)=>{
    if(!r || typeof r!=='object' || Array.isArray(r) || !clean(r.sku) || !clean(r.locale)) throw Error('SKU ou locale invalide à la ligne '+(i+1)+'.');
    return {sku:clean(r.sku),locale:clean(r.locale),title:clean(r.title)};
   });
   const required=[], duplicates=[], missing=[], first=new Map(), skus=new Map();
   rows.forEach((r,i)=>{
    const n=i+1;
    if(!r.title) required.push(`P1 | CHAMP_REQUIS | ligne ${n} | SKU ${r.sku} | locale ${r.locale} | title`);
    if(!skus.has(r.sku)) skus.set(r.sku,new Set());
    const key=JSON.stringify([r.sku,r.locale]);
    if(first.has(key)) duplicates.push(`P1 | DOUBLON | ligne ${n} | SKU ${r.sku} | locale ${r.locale} | première ligne ${first.get(key)}`);
    else first.set(key,n);
    skus.get(r.sku).add(r.locale);
   });
   skus.forEach((seen,sku)=>locales.forEach(locale=>{if(!seen.has(locale)) missing.push(`P2 | LOCALE_MANQUANTE | SKU ${sku} | locale ${locale}`);}));
   out.textContent=[...required,...duplicates,...missing,`TOTAL | P1 ${required.length+duplicates.length} | P2 ${missing.length}`].join('\\n');
  }catch(e){out.textContent='ERREUR | '+e.message;}
 }
 document.getElementById('run').addEventListener('click',run);run();
})();
</script></html>"""
