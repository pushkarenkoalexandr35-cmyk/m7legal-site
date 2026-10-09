(()=>{"use strict";
  // New subpages share the production analytics setup. Avoid duplicate init on the homepage.
  if ((location.hostname==="m7legal.ru"||location.hostname==="www.m7legal.ru") && typeof window.ym!=="function") {
    (function(m,e,t,r,i,k,a) {
      m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
      m[i].l=1*new Date();
      k=e.createElement(t);a=e.getElementsByTagName(t)[0];k.async=1;k.src=r;a.parentNode.insertBefore(k,a);
    })(window,document,"script","https://mc.yandex.ru/metrika/tag.js?id=111107130","ym");
    ym(111107130,"init",{ssr:true,webvisor:true,clickmap:true,accurateTrackBounce:true,trackLinks:true});
    document.addEventListener("click",function(e){
      const a=e.target.closest("a");if(!a)return;
      const href=a.getAttribute("href")||"";
      if(href.startsWith("tel:"))ym(111107130,"reachGoal","phone_click");
      if(href.startsWith("mailto:"))ym(111107130,"reachGoal","email_click");
    });
  }


  // On secondary pages, legacy footer anchors must lead to the homepage section.
  document.querySelectorAll('a[href^="#"]').forEach(a=>{
    const hash=a.getAttribute("href");
    if(hash.length>1 && !document.getElementById(hash.slice(1))) a.setAttribute("href","/"+hash);
  });
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
