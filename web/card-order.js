(() => {
  const cards=[['SE01','card-SE01'],['SE02','card-SE02'],['MA01','card-MA01'],['IDEX','idex-card'],['INTAMSYS','intamsys-card']];
  const key='lab-card-last-received-v1';let timestamps={};
  try{timestamps=JSON.parse(localStorage.getItem(key)||'{}');}catch(_){}
  function arrange(){cards.map(([name,id],index)=>({name,id,index,time:Number(timestamps[name])||0})).sort((a,b)=>b.time-a.time||a.index-b.index).forEach((item,index)=>{const card=document.getElementById(item.id);if(card){card.style.order=String(index);card.dataset.lastReceived=String(item.time);}});}
  async function update(){try{const response=await fetch('/api/card-order',{cache:'no-store',signal:AbortSignal.timeout(25000)});if(!response.ok)throw Error();const data=await response.json();for(const [name,row] of Object.entries(data)){if(row.available)timestamps[name]=Math.max(Number(timestamps[name])||0,Number(row.timestamp)||0);}localStorage.setItem(key,JSON.stringify(timestamps));arrange();}catch(_){}finally{setTimeout(update,30000);}}
  arrange();update();
})();
