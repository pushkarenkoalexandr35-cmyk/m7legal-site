(()=>{"use strict";
  const button=document.querySelector(".menu-toggle");
  const nav=document.getElementById("main-nav");
  if(!button||!nav)return;
  const setOpen=(open)=>{
    nav.classList.toggle("open",open);
    button.setAttribute("aria-expanded",String(open));
    button.setAttribute("aria-label",open?"Закрыть меню":"Открыть меню");
  };
  button.addEventListener("click",()=>setOpen(button.getAttribute("aria-expanded")!=="true"));
  nav.addEventListener("click",e=>{if(e.target.closest("a"))setOpen(false)});
  document.addEventListener("keydown",e=>{if(e.key==="Escape")setOpen(false)});
  document.addEventListener("click",e=>{if(!nav.contains(e.target)&&!button.contains(e.target))setOpen(false)});
})();
