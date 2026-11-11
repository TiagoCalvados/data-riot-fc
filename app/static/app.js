'use strict';
const messageTranslations = {};
const translateMessage = value => messageTranslations[value] || value;
const locale = document.documentElement.lang === 'en' ? 'en' : 'nl';
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state = null, csrf = '', page = 'overview', filter = '', matchFilter = 'all';
let analyticsReport=null, analyticsLoading=false, analyticsDays=30, analyticsMobile=false;
const incomingShare=new URLSearchParams(location.search).get('share')||'';
const labels = {overview:'Overzicht', schedule:'Kantineplanning', fixtures:'Wedstrijden', parents:'Ouders & verzorgers', mail:'Uitnodigingen', analytics:'Bezoekers', settings:'Instellingen', mine:'Mijn diensten', account:'Mijn account'};
const statusLabels = {open:'Open', pending:'Wacht op reactie', queued:'Klaar voor verzending', confirmed:'Bevestigd', declined:'Geweigerd', expired:'Verlopen', cancelled:'Geannuleerd', completed:'Afgerond', no_show:'Niet verschenen', review:'Controleren', scheduled:'Gepland', postponed:'Uitgesteld', sent:'Verzonden', simulated:'Gesimuleerd', failed:'Mislukt', success:'Geslaagd'};
const fmt = (date, options) => new Intl.DateTimeFormat('nl-NL', {timeZone:'Europe/Amsterdam', ...options}).format(new Date(date));
const day = d => fmt(d,{weekday:'long',day:'numeric',month:'long'});
const shortDay = d => fmt(d,{day:'numeric',month:'short'});
const time = d => fmt(d,{hour:'2-digit',minute:'2-digit'});
const datetime = d => `${shortDay(d)} · ${time(d)}`;
const dateKey = d => fmt(d,{year:'numeric',month:'2-digit',day:'2-digit'});
const initials = name => name.split(' ').map(x => x[0]).filter(Boolean).slice(0,2).join('').toUpperCase();
const badge = (s, label) => `<span class="badge ${['confirmed','completed','sent','success'].includes(s)?'green':['pending','queued','expired','review','simulated'].includes(s)?'amber':['cancelled','declined','no_show','failed'].includes(s)?'red':''}">${esc(label || statusLabels[s] || s)}</span>`;
const empty = (title, text='') => `<div class="empty"><strong>${esc(title)}</strong>${esc(text)}</div>`;
const activeShifts = () => state.shifts.filter(s=>s.state==='open' && new Date(s.ends_at)>new Date());
const isAdmin = () => state?.user.role === 'admin';
function toast(message, error=false) { const t=$('#toast'); t.textContent=translateMessage(message); t.className=`toast${error?' error':''}`; clearTimeout(toast.timer); toast.timer=setTimeout(()=>t.classList.add('hidden'),6000); }
async function api(path, options={}) {
  let response;
  try { response=await fetch(path,{...options,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,...options.headers},credentials:'same-origin'}); }
  catch { throw new Error('Geen verbinding. Controleer je internet en probeer opnieuw.'); }
  const body=await response.json().catch(()=>({detail:'De server reageert niet zoals verwacht.'}));
  if(!response.ok) { if(response.status===401 && path!='/api/login') showLogin(); throw new Error(translateMessage(typeof body.detail==='string'?body.detail:'Controleer de ingevulde gegevens.')); }
  return body;
}
const post = (path, body={}) => api(path,{method:'POST',body:JSON.stringify(body)});
async function refresh() { state=await api('/api/dashboard'); render(); }
function showLogin() { setMobileMenu(false); $('#app-screen').classList.add('hidden'); $('#login-screen').classList.remove('hidden'); state=null; csrf=''; page='overview'; filter=''; matchFilter='all'; analyticsReport=null; $('#main-content').replaceChildren(); $('#navigation').replaceChildren(); $('#mobile-navigation').replaceChildren(); }
async function showApp() {
  await refresh(); $('#login-screen').classList.add('hidden'); $('#app-screen').classList.remove('hidden');
  const token = new URLSearchParams(location.search).get('invitation');
  if(token) { try { const invite=await api('/api/invitations/by-token/'+encodeURIComponent(token)); page='mine'; render(); const item=state.shifts.find(s=>s.id===invite.shift_id); if(item) invitationModal(item); } catch(e) { toast(e.message,true); } history.replaceState(null,'','/'); }
}
function heading(title, subtitle, buttons='', eyebrow='DE KANTINE VAN ONS ALLEMAAL') {
  return `<div class="page-heading"><div><span class="eyebrow">${esc(eyebrow)}</span><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="actions">${buttons}</div></div>`;
}
function navigation() {
  const items = isAdmin() ? [['overview','▦'],['schedule','▤'],['fixtures','⚑'],['parents','♧'],['mail','✉'],['analytics','◴'],['settings','⚙']] : [['overview','▦'],['mine','▤'],['fixtures','⚑']];
  $('#navigation').innerHTML=items.map(([key, icon])=>`<button data-page="${key}" class="${page===key?'active':''}" ${page===key?'aria-current="page"':''}><span class="nav-icon" aria-hidden="true">${icon}</span>${esc(labels[key])}${key==='schedule'?`<span class="nav-count">${activeShifts().filter(s=>s.confirmed+(s.demo_assigned||0)<s.capacity).length}</span>`:''}</button>`).join('');
  const quick = isAdmin() ? [['overview','▦','Overzicht'],['schedule','▤','Planning'],['fixtures','⚑','Wedstrijden']] : [['overview','▦','Overzicht'],['mine','▤','Mijn diensten'],['fixtures','⚑','Wedstrijden']];
  $('#mobile-navigation').innerHTML=quick.map(([key,icon,label])=>`<button data-page="${key}" ${page===key?'aria-current="page"':''}><span aria-hidden="true">${icon}</span>${esc(label)}</button>`).join('')+(isAdmin()?`<button data-action="open-menu" ${['parents','mail','analytics','settings','account'].includes(page)?'aria-current="page"':''}><span aria-hidden="true">☰</span>Meer</button>`:`<button data-page="account" ${page==='account'?'aria-current="page"':''}><span aria-hidden="true">⚙</span>Account</button>`);
}
function render() {
  navigation(); $('#breadcrumb').textContent=labels[page]; $('#user-name').textContent=state.user.name; $('#user-role').textContent=isAdmin()?'Kantinecoördinator':'Ouder / verzorger'; $('#user-avatar').textContent=initials(state.user.name);
  $('#today').textContent=fmt(new Date(),{weekday:'short',day:'numeric',month:'short',year:'numeric'});
  $('#demo-banner').classList.toggle('hidden',!state.demo_mode); $('#demo-banner span').textContent=state.local_mail_capture?'Lokale testomgeving · fictieve gegevens · e-mails alleen in de lokale testinbox.':state.fixture_snapshot?'Fictieve bezetting · echte wedstrijden uit een gecontroleerde momentopname · e-mails blijven gesimuleerd.':'Fictieve ouders en wedstrijden · e-mails worden gesimuleerd en niet verzonden.';
  $('#main-content').innerHTML=({overview:overview,schedule:schedule,fixtures:fixtures,parents:parents,mail:mail,analytics:analyticsPage,settings:settingsPage,mine:mine,account:account}[page]||overview)();
  document.querySelectorAll('#main-content table').forEach(table=>{
    const headers=[...table.querySelectorAll('thead th')].map(th=>th.textContent);
    table.querySelectorAll('tbody tr').forEach(row=>[...row.cells].forEach((cell,index)=>cell.dataset.label=headers[index]||''));
  });
  updateInstallButtons();
}

const mobileWidth = window.matchMedia('(max-width: 720px)');
function setMobileMenu(open, restoreFocus=false) {
  const sidebar=$('#sidebar');
  open=Boolean(open && mobileWidth.matches);
  sidebar.classList.toggle('mobile-open',open);
  sidebar.inert=mobileWidth.matches&&!open;
  $('#menu-backdrop').classList.toggle('hidden',!open);
  $('#mobile-menu').setAttribute('aria-expanded',String(open));
  $('#mobile-navigation').inert=open;
  $('.workspace').inert=open;
  document.body.classList.toggle('menu-open',open);
  if(open)$('#menu-close').focus();
  else if(restoreFocus)$('#mobile-menu').focus();
}
function navigateTo(next) {
  page=next;filter='';setMobileMenu(false);render();
  $('#main-content').focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});
  if(page==='analytics')void loadAnalytics();
}

async function recordVisit(){
  if(state?.user.role==='admin'||navigator.doNotTrack==='1'||navigator.globalPrivacyControl)return;
  const share=/^[a-zA-Z0-9_-]{1,32}$/.test(incomingShare)?incomingShare:'';
  try{await api('/api/visits',{method:'POST',headers:{'X-SDW-Statistics':'1'},body:JSON.stringify({share})});}catch{/* Statistics never block using the club app. */}
}
async function loadAnalytics(){
  if(!isAdmin()||analyticsLoading)return;analyticsLoading=true;
  const requestedDays=analyticsDays,requestedMobile=analyticsMobile;
  try{const report=await api(`/api/admin/analytics?days=${requestedDays}&mobile_only=${requestedMobile}`);if(isAdmin())analyticsReport=report;}
  catch(error){toast(error.message,true);}
  finally{analyticsLoading=false;if(state&&isAdmin()&&page==='analytics'){if(requestedDays!==analyticsDays||requestedMobile!==analyticsMobile)void loadAnalytics();else render();}}
}
function analyticsPage(){
  if(!isAdmin())return '';
  const report=analyticsReport;
  let html=heading('Wie vindt de kantine?','Bekijk het bereik van je gedeelde links. Alleen de coördinator ziet deze statistieken.','<button class="button" data-action="analytics-refresh">↻ Vernieuwen</button><button class="button primary" data-action="new-share">+ Deellink maken</button>','BEZOEKERSSTATISTIEKEN');
  html+=`<section class="panel"><div class="filter-row"><select id="analytics-period" aria-label="Periode">${[7,30,90].map(days=>`<option value="${days}" ${analyticsDays===days?'selected':''}>${days} dagen</option>`).join('')}</select><select id="analytics-device" aria-label="Apparaten"><option value="all" ${!analyticsMobile?'selected':''}>Alle apparaten</option><option value="mobile" ${analyticsMobile?'selected':''}>Alleen mobiel / tablet</option></select></div><div class="panel-body"><p class="subtle">Een willekeurige browsercode herkent herhaalbezoek. IP-adressen en namen worden niet opgeslagen. Andere apparaten, gewiste cookies en privacykeuzes kunnen de schatting beïnvloeden. Gedeelde links meten vanaf nu; eerdere bezoeken zijn niet bekend.</p></div></section>`;
  if(!report)return html+empty('Statistieken laden…','Tik op Vernieuwen als de cijfers niet verschijnen.');
  const t=report.totals;
  html+=`<section class="stats"><div class="stat"><div class="stat-top">Unieke bezoekers</div><strong>${t.visitors}</strong><small>Verschillende browsers in deze periode</small></div><div class="stat"><div class="stat-top">Paginaweergaven</div><strong>${t.views}</strong><small>Iedere nieuwe paginalading</small></div><div class="stat"><div class="stat-top">Mobiele bezoekers</div><strong>${t.mobile_visitors}</strong><small>Unieke browsers op telefoon of tablet</small></div><div class="stat"><div class="stat-top">Herhaalde weergaven</div><strong>${Math.max(0,t.views-t.visitors)}</strong><small>Extra weergaven van dezelfde browsers</small></div></section>`;
  html+=`<section class="panel"><div class="panel-head"><div><h2>Resultaat per deellink</h2><p>Maak voor iedere groep of deelronde een eigen link.</p></div></div><div class="table-wrap"><table><thead><tr><th>Deellink</th><th>Unieke bezoekers</th><th>Paginaweergaven</th><th>Mobiel</th><th>Delen</th></tr></thead><tbody>${report.links.map(link=>`<tr><td><strong>${esc(link.id?link.label:'Direct / overige links')}</strong><small class="share-url">${esc(link.url)}</small></td><td>${link.visitors}</td><td>${link.views}</td><td>${link.mobile_visitors}</td><td><button class="button small" data-action="copy-share" data-id="${link.id}">Link kopiëren</button></td></tr>`).join('')}</tbody></table>${!report.links.length?empty('Nog geen bezoeken','Maak een deellink om te beginnen.'):''}</div><div class="footer-note">Een browser die meerdere links opent telt één keer in het totaal, maar kan bij meerdere links voorkomen. Ingelogde coördinatoren en bekende preview-bots worden niet meegeteld.</div></section>`;
  const max=Math.max(1,...report.daily.map(d=>d.views));
  html+=`<section class="panel"><div class="panel-head"><h2>Bezoek per dag</h2><span class="subtle">Europe/Amsterdam</span></div><div class="panel-body analytics-days">${report.daily.slice(-14).map(d=>`<div class="coverage-row"><div class="coverage-title"><span>${esc(shortDay(d.day+'T12:00:00Z'))}</span><small>${d.visitors} uniek · ${d.views} weergaven</small></div><progress value="${d.views}" max="${max}" aria-label="${esc(d.day)}"></progress></div>`).join('')}</div><div class="footer-note">De grafiek toont maximaal de laatste 14 dagen. Totalen volgen de gekozen periode. Cijfers worden iedere 30 seconden vernieuwd.</div></section>`;
  return html;
}
function shareModal(){modal('Een deellink maken','<form id="share-form"><label>Naam van deze deelronde<input name="label" required maxlength="120" placeholder="Bijvoorbeeld: WhatsApp ouders november"></label><p class="form-help">Gebruik dezelfde link voor één groep of deelronde. Voor een volgende deelronde maak je een nieuwe link.</p><div class="modal-actions"><button type="submit" class="button primary">Deellink maken</button></div></form>');}
function statisticsPrivacy(){
  const off=document.cookie.split('; ').includes('sdw_statistics=off')||navigator.doNotTrack==='1'||navigator.globalPrivacyControl;
  modal('Privacy en bezoekersstatistieken',`<p class="settings-description">We tellen beperkte bezoekersstatistieken om te zien hoeveel bereik gedeelde links hebben. Een willekeurige cookie herkent dezelfde browser maximaal 90 dagen. We bewaren alleen een afgeschermde browsercode, dag en bezoektijd, deellink, mobiel of desktop en aantallen. Geen IP-adressen, namen, precieze locaties of volledige bezochte URL’s. De gegevens blijven bij deze website en worden niet aan advertentiebedrijven doorgegeven. Bezoekgegevens worden na maximaal 90 dagen verwijderd.</p><p class="settings-description">Je kunt statistieken hieronder uitzetten. De planning en je account blijven normaal werken. Browsers met Do Not Track of Global Privacy Control worden niet meegeteld.</p><p>${off?'Statistieken staan uit voor deze browser.':'Beperkte statistieken staan aan voor deze browser.'}</p><div class="modal-actions"><button class="button" data-action="statistics-off">Statistieken uitzetten</button><button class="button primary" data-action="statistics-on">Statistieken aanzetten</button></div>`);
}
function shiftDate(s) { return `<div class="date-box"><span>${esc(fmt(s.starts_at,{month:'short'}))}</span><strong>${esc(fmt(s.starts_at,{day:'numeric'}))}</strong></div>`; }
function shiftRow(s, detailed=false) {
  const demo=s.demo_assigned||0; const occupied=s.confirmed+s.waiting+demo;
  const status=s.state!=='open'?badge(s.state):demo>=s.capacity?badge('simulated','Demo: volledig ingedeeld'):s.confirmed>=s.capacity?badge('confirmed','Volledig bezet'):s.waiting?badge('pending',`${s.waiting} reactie${s.waiting>1?'s':''} afwachten`):badge('expired','Hulp nodig');
  const people=[...s.invitations.filter(i=>['confirmed','pending','queued'].includes(i.state)),...(s.demo_assignments||[])];
  return `<div class="shift-row">${shiftDate(s)}<div class="row-info"><strong>${time(s.starts_at)} – ${time(s.ends_at)} <span class="muted">· Kantinedienst</span></strong><small>Sportpark Spieringhorn${s.is_demo?' · Testdienst':''}</small><div class="mini-avatars">${people.slice(0,4).map(i=>`<span class="avatar" title="${esc(i.name)}">${esc(initials(i.name))}</span>`).join('')}${Array.from({length:Math.max(0,Math.min(3,s.capacity-occupied))},()=>'<span class="avatar empty">+</span>').join('')}<small>${demo?`${demo}/${s.capacity} fictief ingedeeld`:`${s.confirmed}/${s.capacity} bevestigd`}</small></div>${demo?`<small class="demo-names">${(s.demo_assignments||[]).map(a=>esc(a.name)).join(' · ')} · fictief</small>`:''}</div><div class="row-end">${status}<button class="text-button" data-action="shift-detail" data-id="${s.id}">${isAdmin()?'Dienst bekijken':'Bekijken & reageren'} ↗</button></div></div>`;
}
function coverage() {
  const groups=new Map(); activeShifts().forEach(s=>{const key=dateKey(s.starts_at);if(!groups.has(key))groups.set(key,{date:s.starts_at,capacity:0,confirmed:0});const g=groups.get(key);g.capacity+=s.capacity;g.confirmed+=s.confirmed+(s.demo_assigned||0);});
  return `<div class="panel"><div class="panel-head"><div><h2>Zo staan we ervoor</h2><p>Bezetting per thuiswedstrijddag</p></div><span class="subtle">KOMENDE WEKEN</span></div><div class="panel-body">${[...groups.values()].slice(0,5).map(g=>`<div class="coverage-row"><div class="coverage-title"><span>${esc(shortDay(g.date))}</span><small>${g.confirmed} / ${g.capacity} plekken</small></div><progress value="${g.confirmed}" max="${g.capacity}" aria-label="Bezetting ${esc(shortDay(g.date))}"></progress></div>`).join('')||'<p class="subtle">Nog geen diensten gepland.</p>'}<div class="legend"><span><i></i>Bezetting incl. demo</span><span><i class="pale"></i>Nog in te vullen</span></div></div></div>`;
}
function activity() {
  const actionText={'fixture.snapshot_imported':'Het echte clubprogramma is gecontroleerd en ingevoerd','demo.opening_0800.applied':'Demo: opening en diensten aangepast','demo.staffing_assigned':'Een fictieve ouder ingedeeld','invitation.proposed':'Een ouder is uitgenodigd','invitation.confirmed':'Een kantinedienst is bevestigd','invitation.declined':'Uitnodiging geweigerd; vervanging gezocht','invitation.expired':'Uitnodiging verlopen','invitation.cancelled':'Uitnodiging geannuleerd','demo.initialized':'Demonstratieomgeving ingericht','planning.run':'Planning en uitnodigingen bijgewerkt','parent.created':'Een ouderaccount is toegevoegd','policy.updated':'Planningsregels aangepast','fixture.created':'Wedstrijd toegevoegd','fixture.updated':'Wedstrijd gewijzigd','shift.updated':'Kantinedienst aangepast','shift.cancelled':'Kantinedienst geannuleerd','availability.updated':'Beschikbaarheid aangepast'};
  return `<div class="panel"><div class="panel-head"><h2>Laatste clubnieuws</h2><span class="subtle">PLANNINGSACTIVITEIT</span></div><div class="panel-body">${(state.activity||[]).slice(0,5).map(e=>`<div class="activity-row"><span class="dot"></span><div><strong>${esc(actionText[e.action]||e.action)}</strong><small>${esc(datetime(e.at))}</small></div></div>`).join('')||'<p class="subtle">Je bent helemaal bij.</p>'}</div></div>`;
}
function overview() {
  const shifts=activeShifts(); const waiting=shifts.reduce((n,s)=>n+s.waiting,0); const confirmed=shifts.reduce((n,s)=>n+s.confirmed+(s.demo_assigned||0),0);const total=shifts.reduce((n,s)=>n+s.capacity,0);const next=state.fixtures.find(f=>f.is_home&&f.status==='scheduled'&&new Date(f.kickoff)>new Date());
  const first=state.user.name.split(' ')[0];
  let html=heading(`Hoi ${first}, samen maken we SDW.`,isAdmin()?'Een helder overzicht van onze kantine, vrijwilligers en komende thuiswedstrijden.':'Bekijk je uitnodigingen en laat weten wanneer je kunt helpen.',isAdmin()?'<button class="button" data-page="schedule">Bekijk planning ↗</button><button class="button primary" data-action="plan">↻ Planning bijwerken</button>':'<button class="button primary" data-page="mine">Mijn diensten ↗</button>');
  html+=`<section class="hero"><div class="hero-copy"><span class="eyebrow">${next?'DE VOLGENDE THUISWEDSTRIJDDAG':'DE CLUB DRAAIT OP ONS ALLEMAAL'}</span><h2>${next?`${esc(day(next.kickoff))}.<br>De koffie staat bijna klaar.`:'Samen achter de bar,<br>samen voor de club.'}</h2><p>${next?'Een warm welkom voor spelers, ouders en supporters. Help jij mee om er een mooie clubdag van te maken?':'Zodra thuiswedstrijden zijn ingevoerd, maken we een eerlijke kantineplanning.'}</p><div class="hero-bottom"><span class="badge outline">⚑ Sportpark Spieringhorn</span><span>Amsterdam West</span></div></div><div class="hero-right">${next?`<span class="match-tag">${next.is_demo?'DEMONSTRATIEWEDSTRIJD':'EERSTE AFTRAP'}</span><span class="match-score">${time(next.kickoff)}</span>`:''}</div><div class="pitch" aria-hidden="true"><div class="pitch-half"></div><div class="pitch-circle"></div><div class="pitch-box"></div></div></section>`;
  html+=`<section class="stats"><div class="stat"><div class="stat-top">${isAdmin()?'Kantinediensten':'Jouw diensten'}<span class="stat-icon">▤</span></div><strong>${shifts.length}</strong><small>In de huidige planning</small></div><div class="stat"><div class="stat-top">Bezetting incl. demo<span class="stat-icon">✓</span></div><strong>${confirmed}<span class="muted"> / ${total}</span></strong><small>${total?Math.round(100*confirmed/total):0}% van de planning ingevuld</small></div><div class="stat"><div class="stat-top">Wacht op reactie<span class="stat-icon">◷</span></div><strong>${waiting}</strong><small>Maximaal ${state.policy.response_hours} uur om te reageren</small></div><div class="stat"><div class="stat-top">${isAdmin()?'Actieve vrijwilligers':'Jouw inzet'}<span class="stat-icon">♧</span></div><strong>${isAdmin()?state.parents.filter(p=>p.active&&p.volunteering).length:shifts.filter(s=>s.invitations.some(i=>i.state==='confirmed')).length}</strong><small>${isAdmin()?'Ouders die samen het verschil maken':'Bevestigde komende diensten'}</small></div></section>`;
  if(!isAdmin())return html+mine(false);
  const needs=shifts.filter(s=>s.confirmed+s.waiting+(s.demo_assigned||0)<s.capacity).length;
  const integr=state.integrations;
  const notice=needs?`<div class="notice"><span>◷</span><div><strong>${needs} dienst${needs===1?' heeft':'en hebben'} nog hulp nodig</strong><p>We houden rekening met minimaal ${state.policy.min_gap_days} dagen tussen voorstellen en slaan opeenvolgende thuiswedstrijddagen over. Zijn er geen geschikte ouders? Dan blijft de plek zichtbaar voor jou.</p></div></div>`:`<div class="notice green"><span>✓</span><div><strong>Iedere plek is ingedeeld of aangeboden</strong><p>We volgen de reacties en zoeken automatisch vervanging waar dat nodig is.</p></div></div>`;
  html+=`<div class="two-col"><div><section class="panel"><div class="panel-head"><div><h2>Komende kantinediensten</h2><p>Kleine inzet, groot clubgevoel.</p></div><button class="text-button" data-page="schedule">Hele planning ↗</button></div>${shifts.slice(0,4).map(s=>shiftRow(s)).join('')||empty('De planning is nog leeg','Voeg thuiswedstrijden toe om te beginnen.')}<div class="footer-note">Alleen thuiswedstrijden bij SDW leveren diensten op.</div></section>${notice}</div><div class="right-column">${coverage()}${activity()}</div></div>`;
  html+=fixtureSourceNotice();
  if(!integr.fixtures_ready&&!state.fixture_snapshot) html+=`<div class="notice"><span>⚑</span><div><strong>De officiële wedstrijdkoppeling wacht op activatie</strong><p>Vraag de clubbeheerder om het Sportlink Club.Dataservice Client ID en de clubcode. Tot die tijd kun je wedstrijden zelf invoeren. De getoonde testwedstrijden zijn fictief.</p></div></div>`;
  return html;
}
function fixtureSourceNotice() { const snap=state.fixture_snapshot; return snap?`<div class="notice"><span>⚑</span><div><strong>Echt clubprogramma · fictieve bezetting</strong><p><a href="${esc(snap.source_url)}" target="_blank" rel="noopener noreferrer">Officieel SDW-programma</a> · gecontroleerd ${esc(datetime(snap.verified_at))}. Dekking: ${snap.coverage_dates.map(d=>esc(shortDay(d+'T12:00:00Z'))).join(', ')}. Handmatige momentopname; geen automatische feed. Opening 08:00, volledige blokken van twee uur tot twee uur na de laatste aftrap, naar boven afgerond. Drie fictieve ouders per dienst; geen echte bevestigingen.</p></div></div>`:''; }
function schedule() {
  let rows=state.shifts.filter(s=>s.state!=='cancelled');
  return heading('Een plek voor iedereen.','Plan de kantine eerlijk, met voldoende tijd voor ouders om te reageren.','<button class="button" data-page="settings">Planningsregels ⚙</button><button class="button primary" data-action="plan">↻ Planning bijwerken</button>','KANTINEPLANNING')+fixtureSourceNotice()+
    (state.demo_mode&&!state.fixture_snapshot?'<div class="notice"><span>⚑</span><div><strong>Demo: open vanaf 08:00</strong><p>Volledige blokken van twee uur, met drie fictieve ouders per dienst. De eindtijd is voorlopig en volgt het fictieve programma; echte wedstrijden zijn nog niet geverifieerd. Fictieve indelingen zijn geen bevestigingen van echte ouders.</p></div></div>':'')+`<div class="notice green"><span>↔</span><div><strong>Eerlijk verdeeld, met ruimte ertussen</strong><p>Minimaal ${state.policy.min_gap_days} dagen tussen voorstellen · geen opeenvolgende thuiswedstrijddagen · ${state.policy.response_hours} uur reactietijd · automatisch uitnodigen ${state.policy.automation_enabled?'aan':'uit'}.</p></div></div><section class="panel"><div class="panel-head"><div><h2>De komende diensten</h2><p>Bekijk een dienst om tijden of bezetting aan te passen.</p></div><span class="badge outline">${rows.length} diensten</span></div>${rows.map((s,i)=>`${i===0||dateKey(rows[i-1].starts_at)!==dateKey(s.starts_at)?`<div class="day-label">${esc(day(s.starts_at))}</div>`:''}${shiftRow(s,true)}`).join('')||empty('Nog geen diensten','Voer eerst een thuiswedstrijd in en werk de planning bij.')}</section>`;
}
function fixtures() {
  const filtered=state.fixtures.filter(f=>(matchFilter==='all'||(matchFilter==='home'?f.is_home:!f.is_home))&&(!filter||`${f.home_team} ${f.away_team}`.toLowerCase().includes(filter)));
  return heading('Op eigen veld. Samen in de kantine.','Het programma voor SDW. Uitwedstrijden tellen niet mee voor kantinediensten.',isAdmin()?'<button class="button" data-action="sync">↻ Wedstrijden ophalen</button><button class="button primary" data-action="new-fixture">+ Wedstrijd toevoegen</button>':'','WEDSTRIJDPROGRAMMA')+
  fixtureSourceNotice()+(state.fixtures.some(f=>f.is_demo)?'<div class="notice"><span>⚑</span><div><strong>Dit zijn demonstratiewedstrijden</strong><p>Deze wedstrijden zijn verzonnen om de planning te testen. Raadpleeg de clubwebsite voor het echte programma.</p></div></div>':'')+
  `<section class="panel"><div class="filter-row"><input id="fixture-search" value="${esc(filter)}" placeholder="Zoek een team…" aria-label="Team zoeken"><select id="fixture-filter" aria-label="Thuis of uit"><option value="all" ${matchFilter==='all'?'selected':''}>Alle wedstrijden</option><option value="home" ${matchFilter==='home'?'selected':''}>Alleen thuis</option><option value="away" ${matchFilter==='away'?'selected':''}>Alleen uit</option></select></div><div class="table-wrap"><table><thead><tr><th>Datum & aftrap</th><th>Wedstrijd</th><th>Locatie</th><th>Thuis / uit</th><th>Status</th>${isAdmin()?'<th>Beheer</th>':''}</tr></thead><tbody>${filtered.map(f=>`<tr><td><strong>${esc(shortDay(f.kickoff))}</strong><small>${time(f.kickoff)}</small></td><td><strong>${esc(f.home_team)}</strong><small>tegen ${esc(f.away_team)}</small></td><td>${esc(f.venue||'Locatie onbekend')}<small>${esc(f.city)} · ${f.is_demo?'Testgegevens':f.source==='manual'?'Handmatig bevestigd':f.source==='club_snapshot'?'Clubmomentopname':'Sportlink'}</small></td><td>${badge(f.is_home?'confirmed':'cancelled',f.is_home?'Thuis':'Uit')}</td><td>${badge(f.status)}${f.source_url?`<small><a href="${esc(f.source_url)}" target="_blank" rel="noopener noreferrer">Officiële wedstrijddetails ↗</a></small>`:''}${f.is_home&&!f.home_venue_approved?'<small>Locatie controleren</small>':''}</td>${isAdmin()?`<td><button class="text-button" data-action="fixture-detail" data-id="${f.id}">Beheren ↗</button></td>`:''}</tr>`).join('')}</tbody></table>${!filtered.length?empty('Geen wedstrijden gevonden','Pas je filter aan of voeg een wedstrijd toe.'):''}</div></section>`;
}
function parents() {
  const data=state.parents.filter(p=>p.role==='parent'&&(!filter||`${p.name} ${p.email} ${p.username}`.toLowerCase().includes(filter)));
  return heading('Vele handen. Eén club.','Iedere ouder een eigen account. Samen verdelen we de inzet eerlijk.','<button class="button primary" data-action="new-parent">+ Ouder toevoegen</button>','OUDERS & VERZORGERS')+
  `<section class="panel"><div class="filter-row"><input id="parent-search" value="${esc(filter)}" placeholder="Zoek op naam of e-mailadres…" aria-label="Ouder zoeken"></div><div class="table-wrap"><table><thead><tr><th>Ouder / verzorger</th><th>Team</th><th>Voorstellen</th><th>Bevestigd / gedaan</th><th>Status</th><th></th></tr></thead><tbody>${data.map(p=>`<tr><td><div class="table-person"><span class="avatar">${esc(initials(p.name))}</span><div><strong>${esc(p.name)}</strong><small>${esc(p.email)}</small></div></div></td><td>${p.team_ids.map(id=>esc(state.teams.find(t=>t.id===id)?.name||'')).join('<br>')||'—'}</td><td>${p.proposals}</td><td>${p.confirmed} / ${p.completed}</td><td>${badge(p.active&&p.volunteering?'confirmed':'cancelled',!p.active?'Inactief':p.volunteering?'In de pool':'Gepauzeerd')}</td><td><button class="text-button" data-action="parent-detail" data-id="${p.id}">Beheren ↗</button></td></tr>`).join('')}</tbody></table>${!data.length?empty('Nog geen ouders','Voeg ouders toe om eerlijk te kunnen verdelen.'):''}</div><div class="footer-note">Afgeronde diensten worden na afloop door de coördinator vastgelegd. Er worden geen kindgegevens opgeslagen.</div></section>`;
}
function mail() {
  return heading('Een uitnodiging. Een helder antwoord.','Verzending, reacties en vervanging op één plek.','','UITNODIGINGEN & E-MAIL')+
  `<div class="notice ${state.integrations.smtp_ready&&!state.demo_mode?'green':''}"><span>✉</span><div><strong>${state.local_mail_capture?'E-mails alleen in de lokale testinbox':state.demo_mode?'E-mails worden gesimuleerd':state.integrations.smtp_ready?'SMTP is ingesteld':'E-mailverzending wacht op SMTP-instellingen'}</strong><p>Na een geslaagde verzending gaat de reactietijd van maximaal ${state.policy.response_hours} uur in. Bij weigeren of verlopen zoeken we een andere geschikte ouder. Verzendfouten worden opnieuw geprobeerd.</p></div></div><section class="panel"><div class="panel-head"><h2>Verzendoverzicht</h2><button class="text-button" data-action="plan">Bijwerken ↻</button></div><div class="table-wrap"><table><thead><tr><th>Ouder</th><th>Bericht</th><th>Status</th><th>Verzonden</th><th>Pogingen / melding</th></tr></thead><tbody>${state.emails.map(e=>`<tr><td>${esc(e.parent)}</td><td>${e.kind==='invitation'?'Uitnodiging kantinedienst':'Annulering'}</td><td>${badge(e.state)}</td><td>${e.sent_at?esc(datetime(e.sent_at)):'—'}</td><td class="text-wrap">${e.attempts}<small>${esc(translateMessage(e.error))}</small></td></tr>`).join('')}</tbody></table>${!state.emails.length?empty('Nog geen uitnodigingen','Zodra ouders worden voorgesteld, zie je hier de verzendstatus.'):''}</div></section>`;
}
function settingsPage() {
  const p=state.policy, i=state.integrations;const jobRecent=i.last_job&&new Date()-new Date(i.last_job.at)<30*60*1000;
  return heading('Een eerlijke basis. Jullie eigen regels.','Stel de planning af op wat werkt voor de club.','','INSTELLINGEN')+
  `<div class="two-col"><section class="panel"><div class="panel-head"><h2>Planningsregels</h2></div><div class="panel-body"><p class="settings-description">Dezelfde ouder krijgt nooit een voorstel op opeenvolgende thuiswedstrijddagen. Daarbovenop geldt de minimale tussenperiode. Bij te weinig geschikte ouders blijft de dienst open voor de coördinator.</p><form id="policy-form"><div class="form-grid"><label>Minimaal aantal dagen tussen voorstellen<input name="min_gap_days" type="number" min="1" max="90" value="${p.min_gap_days}" required></label><label>Vrijwilligers per dienst<input name="volunteers_per_shift" type="number" min="1" max="10" value="${p.volunteers_per_shift}" required></label><label>Duur van een dienst (minuten)<input name="shift_minutes" type="number" min="30" max="480" value="${p.shift_minutes}" required></label><label>Vooruit plannen (dagen)<input name="lookahead_days" type="number" min="7" max="42" value="${p.lookahead_days}" required></label><label>Maximale reactietijd (uren)<input name="response_hours" type="number" min="1" max="48" value="${p.response_hours}" required></label></div><label class="check-label"><input name="automation_enabled" type="checkbox" ${p.automation_enabled?'checked':''}>Automatisch uitnodigen en vervanging zoeken</label><p class="form-help">Duur en bezetting gelden voor nieuw aangemaakte diensten. Bestaande diensten pas je aan in de planning. Nieuwe voorstellen stoppen uiterlijk zes uur voor aanvang.</p><button class="button primary" type="submit">Instellingen opslaan</button></form></div></section><div><div class="integration-card"><div class="integration-top"><h3>Wedstrijdprogramma</h3>${badge(i.fixtures_ready?'confirmed':'review',i.fixtures_ready?'Ingesteld':'Nog te koppelen')}</div><p>Sportlink Club.Dataservice levert teams, aftraptijden, accommodaties en wedstrijdstatussen. Voor activatie zijn het Client ID en de SDW-clubcode nodig. Elk uur wordt het programma vernieuwd.</p>${i.last_sync?`<p>Laatste poging: ${esc(datetime(i.last_sync.at))} · ${esc(statusLabels[i.last_sync.state]||i.last_sync.state)} · ${i.last_sync.count} wedstrijden</p>`:''}<button class="button small" data-action="sync">Verbinding controleren ↻</button></div><div class="integration-card"><div class="integration-top"><h3>E-mail via Proton</h3>${badge(i.smtp_ready?'confirmed':'review',i.smtp_ready?'Ingesteld':'Nog te koppelen')}</div><p>Datariotfc@proton.me gebruikt het gratis abonnement en kan niet via Proton SMTP verzenden. Gebruik een betaald abonnement met eigen domein, of kies een andere SMTP-afzender. Er worden geen echte uitnodigingen verzonden voordat e-mail is ingesteld.</p><p><a href="https://proton.me/support/smtp-submission" target="_blank" rel="noreferrer">Proton SMTP-vereisten ↗</a></p></div><div class="integration-card"><div class="integration-top"><h3>Automatische controle</h3>${badge(jobRecent?'confirmed':'review',jobRecent?'Actief':'Controleren')}</div><p>De geplande taak controleert iedere tien minuten verlopen uitnodigingen en e-mailbezorging. Een verlopen uitnodiging kan na de deadline niet meer worden bevestigd.</p><p>${i.last_job?'Laatste uitvoering: '+esc(datetime(i.last_job.at)):'Er is nog geen uitvoering van de geplande taak geregistreerd.'}</p></div></div></div>`;
}
function mine(withHeading=true) {
  const mine=state.shifts.filter(s=>s.invitations.some(i=>i.user_id===state.user.id)||(s.demo_assignments||[]).length);
  const pending=mine.filter(s=>s.invitations.some(i=>i.user_id===state.user.id&&i.state==='pending'));
  const cards=pending.map(s=>`<div class="personal-invite"><span class="eyebrow">JE BENT UITGENODIGD</span><h3>${esc(day(s.starts_at))} · ${time(s.starts_at)}–${time(s.ends_at)}</h3><p>Kom je meehelpen in de kantine op Sportpark Spieringhorn? ${s.is_demo?'Dit is een testuitnodiging.':''}</p>${s.invitations.filter(i=>i.user_id===state.user.id&&i.state==='pending').map(i=>`${badge('pending','Reageer vóór '+datetime(i.expires_at))}<div class="actions"><button class="button primary" data-action="respond" data-id="${i.id}" data-decision="confirmed">✓ Ja, ik help mee</button><button class="button" data-action="respond" data-id="${i.id}" data-decision="declined">Ik kan niet</button></div>`).join('')}</div>`).join('');
  return (withHeading?heading('Jouw inzet maakt het verschil.','Bevestig je uitnodiging of geef aan dat je niet kunt. We zoeken dan een andere ouder.','<button class="button" data-page="account">Beschikbaarheid doorgeven ↗</button>','MIJN DIENSTEN'):'')+
  `<section class="panel"><div class="panel-head"><h2>${pending.length?'Jouw uitnodigingen':'Jouw kantinediensten'}</h2><span class="badge outline">${pending.length} wacht op jou</span></div>${cards}${mine.filter(s=>!pending.includes(s)).map(s=>shiftRow(s)).join('')||(!cards?empty('Je bent helemaal bij','Je hebt op dit moment geen uitnodigingen om te beantwoorden.'):'')}</section>`;
}
function account() {
  return heading('Ruimte voor jouw agenda.','Geef je afwezigheid door en beheer je eigen account.','','MIJN ACCOUNT')+
  `<section class="panel"><div class="panel-head"><h2>SDW Kantine op je telefoon</h2></div><div class="panel-body install-help"><p>iPhone: open deze website in Safari, tik op Deel en kies Zet op beginscherm. Android: open in Chrome, tik op het menu en kies App installeren of Toevoegen aan startscherm.</p><p>Je gebruikt dezelfde account en actuele planning op elk apparaat. Je hebt internet nodig om te reageren.</p><button type="button" class="button install-button hidden">App installeren ↗</button></div></section>`+
  `<div class="two-col"><div><section class="panel"><div class="panel-head"><h2>Wanneer kun je niet?</h2></div><div class="panel-body"><p class="settings-description">Voeg bijvoorbeeld een vakantie of een drukke dag toe. We stellen je in die periode niet voor. Voor een al bevestigde dienst neem je contact op met de coördinator.</p><form id="availability-form"><div class="form-grid"><label>Vanaf (Amsterdam)<input type="datetime-local" name="starts_at" required></label><label>Tot (Amsterdam)<input type="datetime-local" name="ends_at" required></label></div><button class="button primary" type="submit">Afwezigheid toevoegen</button></form><div>${state.my_unavailability.map(b=>`<div class="availability-row"><span>${esc(datetime(b.starts_at))} → ${esc(datetime(b.ends_at))}</span><button class="text-button" data-action="remove-block" data-id="${b.id}">Verwijderen</button></div>`).join('')}</div></div></section></div><div><section class="panel"><div class="panel-head"><h2>Wachtwoord wijzigen</h2></div><div class="panel-body"><form id="password-form"><label>Huidig wachtwoord<input type="password" name="current_password" autocomplete="current-password" required></label><label>Nieuw wachtwoord<input type="password" name="new_password" minlength="12" maxlength="256" autocomplete="new-password" required></label><p class="form-help">Gebruik minimaal 12 tekens. Na de wijziging log je opnieuw in.</p><button class="button" type="submit">Wachtwoord wijzigen</button></form></div></section><div class="integration-card"><h3>${esc(state.user.name)}</h3><p>${esc(state.user.username)}<br>${esc(state.user.email)}</p></div></div></div>`;
}
function modal(title, body) { $('#modal-title').textContent=title;$('#modal-body').innerHTML=body;$('#modal').showModal(); }
function closeModal() { $('#modal').close(); }
function localInput(date) { const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Amsterdam',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(date));const v=Object.fromEntries(parts.map(p=>[p.type,p.value]));return `${v.year}-${v.month}-${v.day}T${v.hour}:${v.minute}`; }
function amsterdamISO(value) {
  const parts=value.split(/[-T:]/).map(Number);let stamp=Date.UTC(parts[0],parts[1]-1,parts[2],parts[3],parts[4]);const target=stamp;
  for(let n=0;n<3;n++){const p=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Amsterdam',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(stamp));const v=Object.fromEntries(p.map(x=>[x.type,x.value]));const represented=Date.UTC(+v.year,+v.month-1,+v.day,+v.hour,+v.minute);stamp+=target-represented;}
  return new Date(stamp).toISOString();
}
function demoPeople(s) { return (s.demo_assignments||[]).length?`<h3>Fictieve demo-indeling</h3><p class="form-help">Geen echte bevestigingen of e-mails.</p>${s.demo_assignments.map(a=>`<div class="availability-row"><span>${esc(a.name)}</span>${badge('simulated','Fictief')}</div>`).join('')}`:''; }
function invitationModal(s) {
  const invites=s.invitations.filter(i=>i.user_id===state.user.id);
  modal('Jouw kantinedienst',`${demoPeople(s)}<h3>${esc(day(s.starts_at))}</h3><p class="settings-description">${time(s.starts_at)} – ${time(s.ends_at)} · Sportpark Spieringhorn</p>${invites.map(i=>`<p>${badge(i.state)}</p>${i.state==='pending'?`<p class="settings-description">Reageer vóór ${esc(datetime(i.expires_at))}.</p><div class="actions"><button class="button primary" data-action="respond" data-id="${i.id}" data-decision="confirmed">Ja, ik help mee</button><button class="button" data-action="respond" data-id="${i.id}" data-decision="declined">Ik kan niet</button></div>`:''}`).join('')}`);
}
function shiftModal(s) {
  if(!isAdmin())return invitationModal(s);
  modal('Kantinedienst beheren',`<form id="shift-form" data-id="${s.id}"><div class="form-grid"><label>Begintijd (Amsterdam)<input name="starts_at" type="datetime-local" value="${localInput(s.starts_at)}" required></label><label>Eindtijd (Amsterdam)<input name="ends_at" type="datetime-local" value="${localInput(s.ends_at)}" required></label><label>Aantal vrijwilligers<input name="capacity" type="number" min="1" max="10" value="${s.capacity}" required></label><label>Notitie<input name="note" maxlength="1000" value="${esc(s.note)}"></label></div><p class="form-help">Een wijziging annuleert bestaande uitnodigingen en bevestigingen voor deze dienst. Ouders worden geïnformeerd; werk de planning bij om nieuwe uitnodigingen te maken.</p>${demoPeople(s)}<h3>Uitnodigingen</h3>${s.invitations.map(i=>`<div class="availability-row"><span>${esc(i.name)}<br>${badge(i.state)}</span>${i.state==='confirmed'&&new Date(s.ends_at)<new Date()?`<div><button type="button" class="button small" data-action="attendance" data-id="${i.id}" data-state="completed">Aanwezig</button> <button type="button" class="button small" data-action="attendance" data-id="${i.id}" data-state="no_show">Afwezig</button></div>`:''}</div>`).join('')||'<p class="subtle">Nog niemand voorgesteld.</p>'}<div class="modal-actions">${s.state==='open'&&new Date(s.starts_at)>new Date()?`<button type="button" class="button danger" data-action="cancel-shift" data-id="${s.id}">Dienst annuleren</button><button type="submit" class="button primary">Wijziging opslaan</button>`:''}</div></form>`);
}
function languageField(selected='nl') { return `<label>Voorkeurstaal<select name="language"><option value="nl" ${selected==='nl'?'selected':''}>Nederlands</option><option value="en" ${selected==='en'?'selected':''}>English</option></select></label>`; }
function parentModal(parent=null) {
  modal(parent?'Ouder beheren':'Een ouder verwelkomen',`<form id="parent-form" ${parent?`data-id="${parent.id}"`:''}>${!parent?'<div class="form-grid"><label class="span-2">Naam<input name="name" required maxlength="160"></label><label>Gebruikersnaam<input name="username" pattern="[a-z0-9._-]{3,80}" required autocomplete="off"></label><label>E-mailadres<input name="email" type="email" required></label><label class="span-2">Tijdelijk wachtwoord<input name="password" type="password" minlength="12" maxlength="256" required autocomplete="new-password"></label></div><p class="form-help">Minimaal 12 tekens. Geef de inloggegevens persoonlijk door. De ouder kan het wachtwoord na inloggen wijzigen.</p>':`<h3>${esc(parent.name)}</h3><p class="settings-description">${esc(parent.email)} · ${esc(parent.username)}</p><label class="check-label"><input name="active" type="checkbox" ${parent.active?'checked':''}>Account actief</label><label class="check-label"><input name="volunteering" type="checkbox" ${parent.volunteering?'checked':''}>Meenemen in de vrijwilligerspool</label>`}${languageField(parent?.language||locale)}<strong class="subtle">TEAM(S)</strong><div class="checkbox-group">${state.teams.map(t=>`<label class="check-label"><input type="checkbox" name="team_ids" value="${t.id}" ${parent?.team_ids.includes(t.id)?'checked':''}>${esc(t.name)}</label>`).join('')}</div>${parent?'<p class="form-help">Pauzeren annuleert toekomstige uitnodigingen en diensten. Ouders ontvangen zo nodig een annuleringsbericht.</p>':''}<div class="modal-actions"><button type="button" class="button" data-action="close-modal">Sluiten</button><button class="button primary" type="submit">${parent?'Wijzigingen opslaan':'Account aanmaken'}</button></div></form>`);
}
function fixtureModal(f=null) {
  if(f) { modal('Wedstrijd beheren',`<h3>${esc(f.home_team)} – ${esc(f.away_team)}</h3><p class="settings-description">${esc(day(f.kickoff))} · ${time(f.kickoff)}<br>${esc(f.venue)} · ${esc(f.city)}</p><form id="fixture-edit-form" data-id="${f.id}"><label>Aftraptijd (Amsterdam)<input name="kickoff" type="datetime-local" value="${localInput(f.kickoff)}" required></label><label>Status<select name="status">${['scheduled','cancelled','postponed'].map(s=>`<option value="${s}" ${s===f.status?'selected':''}>${esc(statusLabels[s])}</option>`).join('')}</select></label><p class="form-help">Wijzigingen maken betrokken kantinediensten en uitnodigingen ongeldig. Bij officiële feedwedstrijden pas je de bron aan en synchroniseer je opnieuw.</p><div class="modal-actions"><button class="button primary" type="submit">Opslaan</button></div></form>`);return; }
  modal('Wedstrijd toevoegen',`<form id="fixture-form"><div class="form-grid"><label>Thuisteam<input name="home_team" required placeholder="SDW JO12-1" maxlength="160"></label><label>Uitteam<input name="away_team" required placeholder="Tegenstander" maxlength="160"></label><label>Aftrap (Amsterdam)<input name="kickoff" type="datetime-local" required></label><label>SDW speelt<select name="is_home"><option value="true">Thuis</option><option value="false">Uit</option></select></label><label>Sportpark<input name="venue" value="Sportpark Spieringhorn" required maxlength="250"></label><label>Plaats<input name="city" value="Amsterdam" required maxlength="80"></label></div><p class="form-help">Controleer datum en locatie bij de wedstrijdsecretaris. Alleen SDW-thuiswedstrijden op Spieringhorn leveren diensten op. ${state.demo_mode?'In demonstratiemodus wordt dit een testwedstrijd.':''}</p><div class="modal-actions"><button type="submit" class="button primary">Wedstrijd toevoegen</button></div></form>`);
}
document.addEventListener('click',async event=>{
  const target=event.target.closest('[data-page],[data-action]');if(!target)return;
  if(target.dataset.page){navigateTo(target.dataset.page);return;}
  const action=target.dataset.action,id=Number(target.dataset.id);
  try {
    if(action==='statistics-privacy')return statisticsPrivacy();
    if(action==='statistics-off'||action==='statistics-on'){await post('/api/statistics-choice',{enabled:action==='statistics-on'});closeModal();toast(action==='statistics-on'?'Bezoekersstatistieken staan aan.':'Bezoekersstatistieken staan uit.');if(action==='statistics-on')await recordVisit();return;}
    if(action==='new-share')return shareModal();
    if(action==='analytics-refresh')return await loadAnalytics();
    if(action==='copy-share'){
      const link=analyticsReport?.links.find(link=>link.id===id);if(!link)return;
      try{await navigator.clipboard.writeText(link.url);toast('Deellink gekopieerd.');}
      catch{modal('Deellink kopiëren',`<label>Deellink<input id="copy-link-value" readonly value="${esc(link.url)}"></label><p class="form-help">Selecteer de link en kopieer deze naar je bericht.</p>`);$('#copy-link-value').select();}return;
    }
    if(action==='open-menu')return setMobileMenu(true);
    if(action==='close-modal')return closeModal();
    if(action==='shift-detail')return shiftModal(state.shifts.find(s=>s.id===id));
    if(action==='new-parent')return parentModal();
    if(action==='parent-detail')return parentModal(state.parents.find(p=>p.id===id));
    if(action==='new-fixture')return fixtureModal();
    if(action==='fixture-detail')return fixtureModal(state.fixtures.find(f=>f.id===id));
    target.disabled=true;
    if(action==='plan'){const r=await post('/api/admin/plan');toast(`Planning bijgewerkt: ${r.proposed} nieuwe voorstellen, ${r.expired} verlopen uitnodigingen.`);}
    if(action==='sync'){const r=await post('/api/admin/sync');toast(r.state==='not_configured'?'Het Sportlink Client ID en de clubcode zijn nog niet ingesteld.':r.state==='success'?`${r.count} wedstrijden gesynchroniseerd.`:'De feed kon niet worden bijgewerkt. Bestaande gegevens zijn behouden.',r.state!=='success');}
    if(action==='respond'){await post(`/api/invitations/${id}/respond`,{decision:target.dataset.decision});closeModal();toast(target.dataset.decision==='confirmed'?'Bedankt! Je kantinedienst is bevestigd.':'Bedankt voor je reactie. We zoeken een andere ouder.');}
    if(action==='cancel-shift'){await post(`/api/admin/shifts/${id}/cancel`);closeModal();toast('Dienst geannuleerd. Betrokken ouders worden geïnformeerd.');}
    if(action==='attendance'){await post(`/api/admin/invitations/${id}/attendance`,{state:target.dataset.state});closeModal();toast('Aanwezigheid vastgelegd.');}
    if(action==='remove-block'){await api(`/api/unavailability/${id}`,{method:'DELETE'});toast('Afwezigheid verwijderd.');}
    await refresh();
  }catch(e){toast(e.message,true);}finally{target.disabled=false;}
});
document.addEventListener('submit',async event=>{
  const form=event.target;if(!form.id)return;event.preventDefault();const values=Object.fromEntries(new FormData(form));const button=form.querySelector('[type=submit]');if(button)button.disabled=true;
  try{
    if(form.id==='share-form'){await post('/api/admin/share-links',values);closeModal();await loadAnalytics();toast('Deellink gemaakt. Kopieer de link om te delen.');return;}
    if(form.id==='login-form') { $('#login-error').textContent='';const r=await post('/api/login',values);csrf=r.csrf;form.reset();await showApp();return; }
    if(form.id==='policy-form'){for(const k of ['min_gap_days','volunteers_per_shift','shift_minutes','lookahead_days','response_hours'])values[k]=Number(values[k]);values.automation_enabled=new FormData(form).has('automation_enabled');await api('/api/admin/policy',{method:'PUT',body:JSON.stringify(values)});toast('Planningsregels opgeslagen.');}
    if(form.id==='parent-form'){values.team_ids=new FormData(form).getAll('team_ids').map(Number);if(form.dataset.id){values.active=new FormData(form).has('active');values.volunteering=new FormData(form).has('volunteering');await api(`/api/admin/parents/${form.dataset.id}`,{method:'PATCH',body:JSON.stringify(values)});}else await post('/api/admin/parents',values);closeModal();toast('Ouderaccount opgeslagen.');}
    if(form.id==='fixture-form'){values.kickoff=amsterdamISO(values.kickoff);values.is_home=values.is_home==='true';await post('/api/admin/fixtures',values);closeModal();toast('Wedstrijd toegevoegd.');}
    if(form.id==='fixture-edit-form'){values.kickoff=amsterdamISO(values.kickoff);await api(`/api/admin/fixtures/${form.dataset.id}`,{method:'PATCH',body:JSON.stringify(values)});closeModal();toast('Wedstrijd bijgewerkt.');}
    if(form.id==='shift-form'){values.starts_at=amsterdamISO(values.starts_at);values.ends_at=amsterdamISO(values.ends_at);values.capacity=Number(values.capacity);await api(`/api/admin/shifts/${form.dataset.id}`,{method:'PATCH',body:JSON.stringify(values)});closeModal();toast('Dienst aangepast. Werk de planning bij voor nieuwe uitnodigingen.');}
    if(form.id==='availability-form'){values.starts_at=amsterdamISO(values.starts_at);values.ends_at=amsterdamISO(values.ends_at);await post('/api/unavailability',values);toast('Je afwezigheid is opgeslagen.');}
    if(form.id==='password-form'){await post('/api/password',values);showLogin();toast('Wachtwoord gewijzigd. Log opnieuw in.');return;}
    await refresh();
  }catch(e){if(form.id==='login-form')$('#login-error').textContent=e.message;else toast(e.message,true);}finally{if(button)button.disabled=false;}
});
document.addEventListener('input',event=>{
  if(['parent-search','fixture-search'].includes(event.target.id)){const start=event.target.selectionStart;filter=event.target.value.toLowerCase();const id=event.target.id;render();const input=$('#'+id);input.focus();input.setSelectionRange(start,start);}
});
document.addEventListener('change',async event=>{
  if(event.target.id==='analytics-period'){analyticsDays=Number(event.target.value);await loadAnalytics();}
  if(event.target.id==='analytics-device'){analyticsMobile=event.target.value==='mobile';await loadAnalytics();}
  if(event.target.id==='fixture-filter'){matchFilter=event.target.value;render();}
  if(event.target.matches('.language-select')){
    const language=event.target.value;
    if(!['nl','en'].includes(language))return;
    try { if(state)await post('/api/language',{language}); }catch(e){toast(e.message,true);event.target.value=locale;return;}
    document.cookie=`sdw_language=${language}; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol==='https:'?'; Secure':''}`;
    const nextURL=new URL(location.href);nextURL.searchParams.set('lang',language);location.assign(nextURL.href);
  }
});
document.querySelectorAll('.language-select').forEach(select=>select.value=locale);
$('#modal-close').addEventListener('click',closeModal);
$('#account-button').addEventListener('click',()=>navigateTo('account'));
$('#mobile-menu').addEventListener('click',()=>setMobileMenu(true));
$('#menu-close').addEventListener('click',()=>setMobileMenu(false,true));
$('#menu-backdrop').addEventListener('click',()=>setMobileMenu(false,true));
mobileWidth.addEventListener('change',()=>setMobileMenu(false));
document.addEventListener('keydown',event=>{
  if(!$('.sidebar').classList.contains('mobile-open'))return;
  if(event.key==='Escape'){event.preventDefault();setMobileMenu(false,true);}
  if(event.key==='Tab'){
    const controls=[...$('#sidebar').querySelectorAll('button,a[href]')].filter(el=>el.getClientRects().length);
    const first=controls[0],last=controls.at(-1);
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
  }
});
setMobileMenu(false);
const connectionStatus=()=>$('#connection-status').classList.toggle('hidden',navigator.onLine);
window.addEventListener('online',connectionStatus);window.addEventListener('offline',connectionStatus);connectionStatus();
let installPrompt=null;
function updateInstallButtons(){document.querySelectorAll('.install-button').forEach(button=>button.classList.toggle('hidden',!installPrompt));}
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;updateInstallButtons();});
window.addEventListener('appinstalled',()=>{installPrompt=null;updateInstallButtons();});
document.addEventListener('click',async event=>{
  const button=event.target.closest('.install-button');if(!button||!installPrompt)return;
  const prompt=installPrompt;installPrompt=null;updateInstallButtons();await prompt.prompt();await prompt.userChoice;
});
$('#logout').addEventListener('click',async()=>{try{await post('/api/logout');showLogin();}catch(e){toast(e.message,true);}});
(async()=>{try{const r=await api('/api/me');csrf=r.csrf;await showApp();}catch(e){showLogin();}finally{await recordVisit();}})();
setInterval(()=>{if(state&&isAdmin()&&page==='analytics'&&!document.hidden)void loadAnalytics();},30000);
