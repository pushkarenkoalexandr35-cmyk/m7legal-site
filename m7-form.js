(()=>{
  const form=document.getElementById('m7lead-form');
  if(!form)return;

  const button=form.querySelector('button[type="submit"]');
  if(!button)return;

  const API='/api/lead';
  const formStarted=Math.floor(Date.now()/1000);
  let tokenPromise=null;

  const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));

  async function getToken(){
    if(!tokenPromise){
      tokenPromise=fetch(API,{
        method:'GET',
        headers:{'Accept':'application/json'},
        cache:'no-store',
        credentials:'same-origin'
      }).then(async response=>{
        if(!response.ok)throw new Error('token '+response.status);
        const data=await response.json();
        if(!data.form_token)throw new Error('token missing');
        return data.form_token;
      }).catch(error=>{
        tokenPromise=null;
        throw error;
      });
    }
    return tokenPromise;
  }

  let status=document.getElementById('m7lead-status')||
             form.querySelector('[data-form-status]');

  if(!status){
    status=document.createElement('small');
    status.id='m7lead-status';
    status.dataset.formStatus='';
    form.append(status);
  }

  let consent=form.querySelector('[name="privacy_consent"]');

  if(!consent){
    const label=document.createElement('label');
    label.className='form-consent';
    label.style.cssText='display:flex;align-items:flex-start;gap:9px;font-size:12px;line-height:1.45;text-transform:none;letter-spacing:0';
    label.innerHTML='<input type="checkbox" name="privacy_consent" required style="width:auto;margin-top:2px;accent-color:#e86832"><span>Я ознакомился(ась) с <a href="/privacy/" target="_blank" rel="noopener">политикой обработки персональных данных</a> и согласен(на) на обработку данных.</span>';
    form.insertBefore(label,button);
    consent=label.querySelector('input');
  }

  if(!form.querySelector('[name="website"]')){
    const trap=document.createElement('input');
    trap.name='website';
    trap.autocomplete='off';
    trap.tabIndex=-1;
    trap.setAttribute('aria-hidden','true');
    trap.style.cssText='position:absolute;left:-9999px';
    form.append(trap);
  }

  document.querySelectorAll('[data-tariff]').forEach(link=>{
    link.addEventListener('click',()=>{
      const field=form.querySelector('[name="selected_tariff"]');
      if(field)field.value=link.dataset.tariff||'';
    });
  });

  form.addEventListener('submit',async event=>{
    event.preventDefault();

    const data=new FormData(form);
    const contact=String(data.get('contact')||'').trim();

    if(!contact){
      status.textContent='Укажите телефон или email.';
      return;
    }

    if(!consent.checked){
      status.textContent='Подтвердите согласие на обработку персональных данных.';
      return;
    }

    const source=String(data.get('source')||'Проверка китайского контрагента');
    const tariff=String(data.get('selected_tariff')||'не выбран');
    const company=String(data.get('company')||'').trim();

    button.disabled=true;
    status.textContent='Отправляем заявку…';

    try{
      const submitStarted=Math.floor(Date.now()/1000);
      tokenPromise=null;
      const formToken=await getToken();

      await wait(2200);
      const elapsed=Math.floor(Date.now()/1000)-submitStarted;

      const payload={
        name:String(data.get('name')||'').trim(),
        phone:contact.includes('@')?'':contact,
        email:contact.includes('@')?contact:'',
        task:'M7Legal — '+source+'. Тариф: '+tariff+'. Компания или код ЕСКК: '+company,
        website:String(data.get('website')||''),
        page:location.href,
        form_token:formToken,
        form_started:submitStarted,
        form_elapsed:elapsed
      };

      const response=await fetch(API,{
        method:'POST',
        headers:{
          'Content-Type':'application/json',
          'Accept':'application/json'
        },
        credentials:'same-origin',
        body:JSON.stringify(payload)
      });

      const result=await response.json().catch(()=>({}));

      if(!response.ok){
        const baseError=result.error||String(response.status);
        const details=result.details?'.'+result.details:'';
        throw new Error(baseError+details);
      }

      form.reset();
      tokenPromise=null;
      getToken().catch(()=>{});

      status.textContent='Заявка отправлена. Мы свяжемся с вами в ближайшее время.';

      if(typeof ym==='function'){
        ym(111107130,'reachGoal','lead_sent');
      }
    }catch(error){
      console.error('M7Legal form:',error);
      tokenPromise=null;

      const errorCode=String(error?.message||'unknown')
        .replace(/[^a-zA-Z0-9_. -]/g,'')
        .slice(0,120);

      status.textContent='Не удалось отправить заявку. Код: '+errorCode+'. Позвоните: 8 (495) 246-08-08';

      if(typeof ym==='function'){
        ym(111107130,'reachGoal','lead_error',{error_code:errorCode});
      }
    }finally{
      button.disabled=false;
    }
  });

  getToken().catch(()=>{});
})();
