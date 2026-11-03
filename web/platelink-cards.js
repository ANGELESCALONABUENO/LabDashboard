/* Add a physical plate row below each material section, using the shared PlateLink inventory. */
(()=>{const definitions=[['card-SE01','SE01'],['card-SE02','SE02'],['card-MA01','MA01'],['intamsys-card','HT09'],['idex-card','22IDEX V3']];
 function attach(){for(const [id,printer] of definitions){const card=document.getElementById(id);if(!card||card.querySelector('.lab-plate-row'))continue;const material=card.querySelector('.cam-material,.idex-materials');if(!material)continue;const holder=document.createElement('div');holder.className='lab-plate-row';holder.dataset.printer=printer;if(material.classList.contains('idex-materials'))material.after(holder);else material.append(holder);PlateLinkChooser.mount(holder,printer);}}
 attach();const grid=document.getElementById('grid');if(grid)new MutationObserver(attach).observe(grid,{childList:true});window.addEventListener('pageshow',()=>PlateLinkChooser.load(true).catch(()=>{}));
})();
