'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = value => value == null ? '—' : new Intl.NumberFormat('en-US',{maximumFractionDigits:0}).format(value);
const compact = value => value == null ? '—' : new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:2}).format(value);
const pct = (value,digits=2) => value == null ? '—' : (value*100).toFixed(digits)+'%';
const money = value => value == null ? '—' : `$${new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:2}).format(value)}`;
const titles = {overview:'Executive overview',global:'Worldwide statistics',predict:'Individual prediction',batch:'Batch CSV check',eda:'Explore the data',assistant:'AI assistant',models:'Deploy model'};
const COUNTRY_COORDS={BGD:[23.685,90.3563],IND:[20.5937,78.9629],PAK:[30.3753,69.3451],CHN:[35.8617,104.1954],JPN:[36.2048,138.2529],USA:[37.0902,-95.7129],GBR:[55.3781,-3.436],DEU:[51.1657,10.4515],FRA:[46.2276,2.2137],CAN:[56.1304,-106.3468],AUS:[-25.2744,133.7751],BRA:[-14.235,-51.9253],ZAF:[-30.5595,22.9375],SAU:[23.8859,45.0792],ARE:[23.4241,53.8478],SGP:[1.3521,103.8198]};
const ROBINSON_X=[1,.9986,.9954,.99,.9822,.973,.96,.9427,.9216,.8962,.8679,.835,.7986,.7597,.7186,.6732,.6213,.5722,.5322];
const ROBINSON_Y=[0,.062,.124,.186,.248,.31,.372,.434,.4958,.5571,.6176,.6769,.7346,.7903,.8435,.8936,.9394,.9761,1];
function robinsonPoint(code){const [lat,lon]=COUNTRY_COORDS[code];const absolute=Math.abs(lat),index=Math.min(17,Math.floor(absolute/5)),fraction=(absolute-index*5)/5;const xFactor=ROBINSON_X[index]+(ROBINSON_X[index+1]-ROBINSON_X[index])*fraction;const yFactor=ROBINSON_Y[index]+(ROBINSON_Y[index+1]-ROBINSON_Y[index])*fraction;const centeredLongitude=((lon-11+540)%360)-180;return {x:(centeredLongitude*xFactor+180)/3.6,y:50-Math.sign(lat)*yFactor*50};}
const state = {config:null,models:[],filters:{},dashboard:null,eda:null,edaTab:'all',edaModelGroup:'all',search:'',applicant:null,result:null,batch:null,selectedCase:null,selectedLabel:'',assistant:'ollama',messages:{ollama:[],gemini:[]},busyChat:false,adminToken:'',routeVersion:0,dashboardVersion:0,caseVersion:0,globalCountry:'BGD',lgd:.4};
let toastTimer;
function toast(message){$('#toast').textContent=message;$('#toast').style.display='block';clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').style.display='none',4500);}
async function api(path, options={}){
  const response=await fetch('/api'+path,{...options,headers:{...(options.body && !(options.body instanceof FormData)?{'Content-Type':'application/json'}:{}),...(state.adminToken?{'X-Admin-Token':state.adminToken}:{}),...options.headers}});
  const data=await response.json();
  if(!response.ok){let error=data.detail;if(Array.isArray(error))error=error.map(e=>`${e.loc.slice(1).join(' · ')}: ${e.msg}`).join('\n');throw new Error(typeof error==='string'?error:'The request could not be completed.');}
  return data;
}
function download(name,content,type='application/json'){
  const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function heading(eyebrow,title,description,action=''){return `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${description}</p></div><div class="actions">${action}</div></div>`;}
const METRIC_INFO={
  applicants:{title:'Total applicants',body:'The number of applications in the current dashboard selection.',use:'Use this as the denominator when reading the selected segment’s rates.'},
  default_rate:{title:'Recorded repayment difficulty rate',body:'The share of selected historical applications where TARGET equals 1.',use:'This is an observed dataset outcome. It is not a forecast for a new applicant.'},
  average_income:{title:'Average annual income',body:'Mean AMT_INCOME_TOTAL for applicants in the current selection.',use:'Amounts remain in the source dataset’s currency units.'},
  average_credit:{title:'Average requested credit',body:'Mean AMT_CREDIT for applicants in the current selection.',use:'This describes requested credit size and is also used as the simplified exposure amount.'},
  average_age:{title:'Average applicant age',body:'Mean applicant age in years for the current selection, derived from DAYS_BIRTH.',use:'It changes immediately when dashboard filters are applied.'},
  npl:{title:'Bank non-performing loans',body:'Non-performing loans as a percentage of total gross loans in the selected country’s banking system.',use:'A country-level World Bank indicator sourced from IMF Financial Soundness Indicators. It is not the CreditScope dataset default rate.',source:'https://data.worldbank.org/indicator/FB.AST.NPER.ZS'},
  npl_change:{title:'Annual NPL movement',body:'The percentage-point change between the selected market’s latest NPL ratio and its previous reported value.',use:'A positive number means the reported share of problem loans increased.'},
  gdp_growth:{title:'GDP growth',body:'Annual percentage growth rate of gross domestic product at market prices.',use:'Provides economic context; it does not determine an individual prediction.'},
  inflation:{title:'Inflation',body:'Annual percentage change in the consumer price index.',use:'Higher inflation can affect borrower expenses and real repayment capacity.'},
  unemployment:{title:'Unemployment',body:'Share of the labor force without work but available for and seeking employment.',use:'This is a national indicator and may differ from the applicant population.'},
  lending_rate:{title:'Lending interest rate',body:'Bank rate that usually meets short- and medium-term private-sector financing needs.',use:'Reporting years differ by country; missing values are not estimated.'},
  bank_capital:{title:'Bank capital to assets',body:'Bank capital and reserves as a percentage of total assets.',use:'A larger capital buffer can provide more capacity to absorb unexpected losses.',source:'https://data.worldbank.org/indicator/FB.BNK.CAPA.ZS'},
  private_credit:{title:'Private-sector credit',body:'Financial resources supplied to the private sector as a percentage of GDP.',use:'This indicates the depth of credit activity in the economy, not the quality of those loans.',source:'https://data.worldbank.org/indicator/FS.AST.PRVT.GD.ZS'},
  lgd:{title:'Loss given default (LGD)',body:'The assumed percentage of exposure that would be lost if default occurs, after recoveries.',use:'Change the slider to test scenarios. CreditScope does not estimate LGD from this dataset.'},
  ead:{title:'Exposure at default (EAD)',body:'The credit amount assumed to be outstanding when default occurs.',use:'CreditScope uses requested credit or summed portfolio credit as a simplified proxy for EAD.'},
  expected_loss:{title:'Estimated expected loss',body:'A simplified planning estimate calculated as probability or risk rate × LGD × EAD.',use:'This is not a complete IFRS 9 expected-credit-loss calculation.'},
  difficulty_exposure:{title:'Recorded difficulty exposure',body:'Total historical requested credit for records where TARGET equals 1.',use:'This is a descriptive dataset total, not an accounting loss or model prediction.'},
  high_risk_exposure:{title:'High-risk exposure',body:'Total requested credit attached to applicants flagged by the selected model.',use:'It depends on the model threshold and should be interpreted with the model caveats.'},
  global_credit_exposure:{title:'Worldwide bank credit exposure',body:'Loans and deposits reported by internationally active banks across BIS reporting countries.',use:'This measures the scale of bank credit exposure. It is not an estimate of losses from default.',source:'https://data.bis.org/topics/CBS/tables-and-dashboards/BIS,CBS_B1,1.0'},
  global_default_loss_estimate:{title:'Illustrative worldwide default-loss scenario',body:'CreditScope applies a 40% loss-given-default assumption to the $80.4 trillion worldwide banking exposure and the median NPL ratio across the countries included on this page.',use:'This is a transparent scenario estimate, not a reported worldwide accounting loss. Different exposure coverage, NPL rates, recoveries, and timing would change the result.',source:'https://www.bis.org/publications/working-paper-1101-insights-credit-loss-rates-global-database'},
  global_loss_gap:{title:'Why no worldwide default-loss total?',body:'There is no single reliable and consistently reported worldwide total for money lost because of loan defaults.',use:'BIS research provides country-level credit-loss measures and identifies limited comparable data as a continuing gap.',source:'https://www.bis.org/publications/working-paper-1101-insights-credit-loss-rates-global-database'}
};
function infoButton(key){return `<button class="info-button" type="button" data-info="${esc(key)}" aria-label="Explain this metric">i</button>`;}
function bindInfoButtons(root=document){$$('[data-info]',root).forEach(button=>button.onclick=()=>{const info=METRIC_INFO[button.dataset.info];if(!info)return;$('#metric-dialog-title').textContent=info.title;$('#metric-dialog-body').textContent=info.body;$('#metric-dialog-use').textContent=info.use;const source=$('#metric-dialog-source');source.hidden=!info.source;if(info.source)source.href=info.source;$('#metric-dialog').showModal();});}
function stat(label,value,note,symbol='◈',accent=false,infoKey=''){return `<div class="stat ${accent?'accent':''}"><div class="stat-label">${label}<span class="stat-symbol"><span aria-hidden="true">${symbol}</span>${infoKey?infoButton(infoKey):''}</span></div><div class="stat-value">${value}</div><div class="stat-note">${note}</div></div>`;}
function panel(title,subtitle,content,tag=''){return `<section class="panel"><div class="panel-head"><div><h2>${title}</h2><p>${subtitle}</p></div>${tag?`<span class="panel-kicker">${tag}</span>`:''}</div>${content}</section>`;}
function shortAge(label){return label.replace(/[()[\]]/g,'').replace(', ','–');}
function bars(rows,vertical=false){
  if(!rows.length)return '<div class="empty"><p>No applicants in this selection.</p></div>';
  const max=Math.max(...rows.map(r=>r.rate),.01)*1.15;
  if(vertical)return `<div class="vertical-chart">${rows.map(r=>`<div class="vbar"><strong>${pct(r.rate,1)}</strong><button style="height:${r.rate/max*100}%" title="${esc(r.group)}: ${pct(r.rate)} · ${number(r.applicants)} applicants" aria-label="${esc(r.group)}: ${pct(r.rate)} default rate among ${number(r.applicants)} applicants" data-age="${esc(r.group)}"></button><small>${esc(shortAge(r.group))}</small></div>`).join('')}</div>`;
  return rows.map(r=>`<div class="hbar" title="${number(r.applicants)} applicants · ${number(r.defaults)} repayment difficulty cases"><span class="hbar-label">${esc(r.group)}</span><div class="bar-track"><div class="bar-fill" style="width:${r.rate/max*100}%"></div></div><b>${pct(r.rate,1)}</b></div>`).join('');
}
function matrix(data){
  const ages=[...new Set(data.map(r=>r.age))].sort();const incomes=[...new Set(data.map(r=>r.income))].sort();
  if(!ages.length)return '<div class="empty"><p>No data in this selection.</p></div>';
  return `<div class="matrix-wrap"><table class="matrix"><caption class="muted">Default rate by age and income quintile</caption><thead><tr><th>AGE / INCOME</th>${incomes.map(i=>`<th>${esc(i.replace(' Lowest','').replace(' Highest',''))}</th>`).join('')}</tr></thead><tbody>${ages.map(age=>`<tr><th>${esc(shortAge(age))}</th>${incomes.map(income=>{const r=data.find(r=>r.age===age&&r.income===income);return r?`<td style="background:rgba(76,148,101,${Math.min(.65,.05+r.rate*2.8)})" title="${number(r.applicants)} applicants · ${number(r.defaults)} cases"><button data-age="${esc(age)}" aria-label="Filter age ${esc(age)}; ${esc(income)} rate ${pct(r.rate)}">${pct(r.rate,1)}</button></td>`:'<td>—</td>';}).join('')}</tr>`).join('')}</tbody></table></div><div class="matrix-key">Lower risk <span class="gradient-key"></span> Higher risk</div>`;
}
function indicatorCard(label,item,note='',infoKey=''){
  const shown=item?.value==null?'Not reported':`${Number(item.value).toFixed(1)}%`;
  return `<div class="macro-metric"><small>${esc(label)} ${infoKey?infoButton(infoKey):''}</small><strong>${shown}</strong><span>${item?.year?`World Bank · ${item.year}`:'No aggregate in this series'}</span>${note?`<em>${esc(note)}</em>`:''}</div>`;
}
function globalRiskMarkup(){
  const snapshot=state.config.global_risk,c=snapshot.countries[state.globalCountry]||snapshot.countries.BGD;
  const change=c.npl.value!=null&&c.npl.previous!=null?c.npl.value-c.npl.previous:null;
  const changeNote=change==null?'':`${change>=0?'Up':'Down'} ${Math.abs(change).toFixed(1)} pp from ${c.npl.previous_year}`;
  const countryOptions=Object.entries(snapshot.countries).map(([code,item])=>`<option value="${code}" ${code===state.globalCountry?'selected':''}>${esc(item.short_name)}</option>`).join('');
  const dots=Object.entries(snapshot.countries).filter(([code])=>COUNTRY_COORDS[code]).map(([code,item])=>{const point=robinsonPoint(code);return `<button class="map-dot ${code===state.globalCountry?'active':''}" style="left:${point.x.toFixed(2)}%;top:${point.y.toFixed(2)}%" data-country="${code}" title="${esc(item.name)}" aria-label="Show ${esc(item.name)} statistics"><span></span><em>${esc(item.short_name)}</em></button>`;}).join('');
  return `<section class="panel global-health"><div class="panel-head"><div><div class="eyebrow">WORLDWIDE FINANCIAL ENVIRONMENT</div><h2>Global Loan Health</h2><p>Select a country on the map or use the list to compare banking and economic conditions.</p></div><div class="country-control"><label for="global-country">Country</label><select id="global-country">${countryOptions}</select></div></div><div class="world-map real-map"><img src="/static/world-map.svg" alt="Political world map in Robinson projection"><div class="map-overlay">${dots}</div><div class="map-key"><span></span>Countries available in CreditScope</div></div><div class="macro-metrics">${indicatorCard('Bank non-performing loans',c.npl,changeNote,'npl')}${indicatorCard('GDP growth',c.gdp_growth,'','gdp_growth')}${indicatorCard('Inflation',c.inflation,'','inflation')}${indicatorCard('Unemployment',c.unemployment,'','unemployment')}${indicatorCard('Lending interest rate',c.lending_rate,'','lending_rate')}${indicatorCard('Bank capital to assets',c.bank_capital,'','bank_capital')}${indicatorCard('Private-sector credit / GDP',c.private_credit,'','private_credit')}</div><div class="chart-foot">${esc(snapshot.method_note)} <a href="${esc(snapshot.indicators.npl.url)}" target="_blank" rel="noopener">World Bank indicators ↗</a> · <a href="https://commons.wikimedia.org/wiki/File:Blank_world_map_Robinson_projection.svg" target="_blank" rel="noopener">Natural Earth map · CC0 ↗</a></div></section>`;
}
function defaultRiskPulseMarkup(d){
  const globalExposure=state.config.global_risk.credit_context.global_bank_loans_deposits;
  const rates=Object.values(state.config.global_risk.countries).map(country=>country.npl?.value).filter(value=>value!=null).sort((a,b)=>a-b);const middle=Math.floor(rates.length/2);const medianNpl=rates.length%2?rates[middle]:(rates[middle-1]+rates[middle])/2;const estimatedLossBillions=globalExposure.value*1000*(medianNpl/100)*.4;
  return `<aside class="panel risk-pulse compact-pulse"><div class="eyebrow">GLOBAL BANKING SCALE</div><h2>Worldwide banking</h2><div><small>WORLDWIDE BANKING · ${esc(globalExposure.period)}</small><span>${esc(globalExposure.label)} ${infoButton('global_credit_exposure')}</span><b>$${globalExposure.value.toFixed(1)}T</b><a class="risk-source" href="${esc(globalExposure.url)}" target="_blank" rel="noopener">BIS source ↗</a></div><div class="loss-estimate"><small>ILLUSTRATIVE DEFAULT-LOSS SCENARIO</small><span>Exposure × ${medianNpl.toFixed(1)}% median NPL × 40% LGD ${infoButton('global_default_loss_estimate')}</span><b>≈ $${estimatedLossBillions.toFixed(0)}B</b><a class="risk-source" href="https://www.bis.org/publications/working-paper-1101-insights-credit-loss-rates-global-database" target="_blank" rel="noopener">Method context ↗</a></div></aside>`;
}
function lossPanelMarkup(prefix,pd,exposure,highRiskExposure=null,title='Financial impact / expected loss',highRiskLabel='HIGH-RISK EXPOSURE',highRiskNote='Credit attached to flagged cases'){
  const expected=(pd||0)*state.lgd*(exposure||0);
  const thirdInfo=highRiskLabel.startsWith('RECORDED')?'difficulty_exposure':'high_risk_exposure';
  return `<section class="panel loss-panel"><div class="panel-head"><div><div class="eyebrow">PD × LGD × EAD</div><h2>${title}</h2><p>A simplified scenario translating risk into potential financial impact.</p></div><span class="pill amber">SCENARIO</span></div><div class="loss-controls single"><div><label for="${prefix}-lgd">Assumed loss given default ${infoButton('lgd')} <b id="${prefix}-lgd-label">${pct(state.lgd,0)}</b></label><input id="${prefix}-lgd" type="range" min="10" max="100" step="5" value="${state.lgd*100}"></div><div class="fixed-currency"><small>DISPLAY</small><strong>USD · $</strong></div></div><div class="loss-metrics ${highRiskExposure==null?'two':''}"><div><small>EXPOSURE AT DEFAULT ${infoButton('ead')}</small><strong id="${prefix}-exposure">${money(exposure)}</strong><span>EAD · requested or portfolio credit</span></div><div class="accent"><small>ESTIMATED EXPECTED LOSS ${infoButton('expected_loss')}</small><strong id="${prefix}-expected">${money(expected)}</strong><span id="${prefix}-formula">Risk rate ${pct(pd,1)} × LGD ${pct(state.lgd,0)} × EAD</span></div>${highRiskExposure==null?'':`<div><small>${esc(highRiskLabel)} ${infoButton(thirdInfo)}</small><strong id="${prefix}-high-risk">${money(highRiskExposure)}</strong><span>${esc(highRiskNote)}</span></div>`}</div><div class="chart-foot">Simplified planning estimate only. Model scores may be uncalibrated. This is not an IFRS 9 expected-credit-loss calculation. Values use a fixed dollar display; the source amounts have not been converted using exchange rates.</div></section>`;
}
function bindLossPanel(prefix,pd,exposure,highRiskExposure=null){
  const update=()=>{const lgd=Number($(`#${prefix}-lgd`)?.value||40)/100;state.lgd=lgd;$(`#${prefix}-lgd-label`).textContent=pct(lgd,0);$(`#${prefix}-exposure`).textContent=money(exposure);$(`#${prefix}-expected`).textContent=money((pd||0)*lgd*(exposure||0));$(`#${prefix}-formula`).textContent=`Risk rate ${pct(pd,1)} × LGD ${pct(lgd,0)} × EAD`;if($(`#${prefix}-high-risk`))$(`#${prefix}-high-risk`).textContent=money(highRiskExposure);};
  $(`#${prefix}-lgd`)?.addEventListener('input',update);
}
function portfolioLossMarkup(d){return lossPanelMarkup('portfolio',d.default_rate,d.total_exposure,d.difficulty_exposure,'Portfolio expected-loss scenario','RECORDED DIFFICULTY EXPOSURE','Historical credit where TARGET = 1');}
function bindGlobalRisk(d){
  const choose=code=>{state.globalCountry=code;$('#global-risk').innerHTML=globalRiskMarkup();$('#global-pulse').innerHTML=defaultRiskPulseMarkup(d);bindGlobalRisk(d);bindInfoButtons();};
  $('#global-country')?.addEventListener('change',e=>choose(e.target.value));$$('[data-country]').forEach(button=>button.onclick=()=>choose(button.dataset.country));
}
async function renderGlobal(){
  let d=state.dashboard;
  if(!d){d=await api('/dashboard');state.dashboard=d;}
  $('#main').innerHTML=heading('MACRO & BANKING CONTEXT','Worldwide statistics','Country-level credit quality and economic indicators from a saved World Bank snapshot.')+`<div class="macro-grid"><div id="global-risk">${globalRiskMarkup()}</div><div id="global-pulse">${defaultRiskPulseMarkup(d)}</div></div>`;
  bindGlobalRisk(d);bindInfoButtons();
}
async function renderOverview(){
  $('#main').innerHTML=heading('PORTFOLIO INTELLIGENCE','Executive overview','A complete view of your applicants, exposure, and repayment risk.','<button class="secondary" id="print-dashboard">▣ Print report</button><button class="secondary" id="export-dashboard">↓ Export data</button>')+
    `<section class="portfolio-control"><div class="filter-panel"><div class="filter-top"><b>⌕ &nbsp; Explore a segment</b><button class="link-button" id="reset-filters">Reset filters</button></div><div class="filter-row">${state.config.filters.map(f=>`<div><label for="filter-${f.key}">${esc(f.label)}</label><select id="filter-${f.key}" data-filter="${f.key}"><option value="">All ${esc(f.label.toLowerCase())}</option>${f.options.map(o=>`<option value="${esc(o)}" ${state.filters[f.key]===o?'selected':''}>${esc(o)}</option>`).join('')}</select></div>`).join('')}</div></div><div id="portfolio-kpis"><div class="loading">Calculating your portfolio…</div></div></section><div id="dashboard-content"></div>`;
  $$('[data-filter]').forEach(el=>el.addEventListener('change',()=>{state.filters[el.dataset.filter]=el.value;refreshDashboard();}));
  $('#reset-filters').onclick=()=>{state.filters={};$$('[data-filter]').forEach(e=>e.value='');refreshDashboard();};
  $('#export-dashboard').onclick=()=>{if(!state.dashboard)return;download('creditscope-portfolio.json',JSON.stringify({filters:state.filters,...state.dashboard},null,2));toast('Portfolio summary downloaded.');};
  $('#print-dashboard').onclick=()=>{const query=new URLSearchParams(Object.entries(state.filters).filter(([,value])=>value));window.location.href='/api/dashboard/report?'+query;toast('Preparing the filtered PDF report…');};
  await refreshDashboard();
}
async function refreshDashboard(){
  const version=++state.dashboardVersion;
  $('#portfolio-kpis')?.setAttribute('aria-busy','true');
  $('#dashboard-content')?.setAttribute('aria-busy','true');
  try{
    const d=await api('/dashboard?'+new URLSearchParams(Object.entries(state.filters).filter(([,v])=>v)));
    if(version!==state.dashboardVersion || !$('#dashboard-content'))return;
    state.dashboard=d;
    const nondefaults=d.applicants-d.defaults;
    const cohort=d.filtered?'Selected segment':'All applicants';
    $('#portfolio-kpis').innerHTML=`<div class="stats">${stat('Total applicants',number(d.applicants),`${cohort} · full dataset`,'♧',false,'applicants')}${stat('Default rate',pct(d.default_rate),`${number(d.defaults)} repayment difficulty cases`,'↗',true,'default_rate')}${stat('Average income',compact(d.average_income),'Annual · source currency units','◫',false,'average_income')}${stat('Average credit',compact(d.average_credit),'Requested credit amount','▱',false,'average_credit')}${stat('Average age',d.average_age?.toFixed(1)??'—','Years · selected applicants','◷',false,'average_age')}</div>`;
    $('#portfolio-kpis').removeAttribute('aria-busy');
    $('#dashboard-content').innerHTML=`<div id="portfolio-impact">${portfolioLossMarkup(d)}</div>`+
      `<div class="grid-two">${panel('Repayment profile','The balance of observed repayment outcomes',`<div class="chart-layout"><div class="donut" style="--angle:${(d.default_rate||0)*360}deg"><div class="donut-text"><strong>${compact(d.applicants)}</strong><small>APPLICANTS</small></div></div><div class="legend"><div class="legend-row"><div class="legend-label"><i class="dot"></i>No repayment difficulty</div><div class="legend-numbers"><b>${number(nondefaults)}</b><span>${d.applicants?pct(1-d.default_rate):'—'}</span></div></div><div class="legend-row"><div class="legend-label"><i class="dot rose"></i>Repayment difficulty</div><div class="legend-numbers"><b>${number(d.defaults)}</b><span>${pct(d.default_rate)}</span></div></div></div></div><div class="chart-foot">Observed TARGET labels · not model predictions</div>`,'TARGET DISTRIBUTION')}${panel('Risk across age groups','Default rate within each age band',bars(d.age,true)+'<div class="chart-foot">Click a bar to focus the dashboard on that age group.</div>','DEFAULT RATE')}</div>`+
      `<div class="grid-two">${panel('Where risk concentrates','Explore the intersection of age and income',matrix(d.matrix)+'<div class="chart-foot">Hover for cohort size. Click a cell to select its age group.</div>','SEGMENT MATRIX')}${panel('Debt burden & repayment','Bureau debt relative to annual income',bars(d.debt)+`<div class="insight">Average credit-to-income ratio <strong>${d.average_ratio?.toFixed(2)??'—'}×</strong> for this selection.</div>`,'DEFAULT RATE')}</div>`+
      `<div class="grid-even">${panel('Income profile','Observed repayment difficulty by income type',bars(d.income))}${panel('Education profile','Associations in the historical dataset',bars(d.education))}</div><div class="live-label">${d.filtered?'Filtered':'Full'} portfolio · ${number(d.applicants)} of ${number(d.population)} applicants · ${esc(d.source)}</div>`;
    $('#dashboard-content').removeAttribute('aria-busy');
    bindLossPanel('portfolio',d.default_rate,d.total_exposure,d.difficulty_exposure);bindInfoButtons();
    $$('[data-age]').forEach(el=>el.onclick=()=>{state.filters.age_group=el.dataset.age;$('#filter-age_group').value=el.dataset.age;refreshDashboard();});
  }catch(e){if($('#portfolio-kpis'))$('#portfolio-kpis').innerHTML=`<div class="error-box" role="alert">${esc(e.message)}</div>`;if($('#dashboard-content'))$('#dashboard-content').innerHTML='';}
}
function field(label,name,value,type='number',options={}){
  const {hint='',min,max,step='any',items,optional=false}=options;
  return `<div class="field"><label for="case-${name}">${label}${optional?' <span class="muted">· optional</span>':''}</label>${items?`<select id="case-${name}" name="${name}">${items.map(item=>`<option value="${esc(item.value??item)}" ${String(value)===String(item.value??item)?'selected':''}>${esc(item.label??item)}</option>`).join('')}</select>`:`<input id="case-${name}" name="${name}" type="${type}" value="${esc(value)}" ${min!=null?`min="${min}"`:''} ${max!=null?`max="${max}"`:''} step="${step}" ${optional?'placeholder="Use training median"':'required'}>`}${hint?`<small>${hint}</small>`:''}</div>`;
}
function readCase(){
  const raw=Object.fromEntries(new FormData($('#case-form')));const a={};
  for(const [k,v] of Object.entries(raw)){if(k==='model_id')continue;if(['education','income_type','contract_type'].includes(k))a[k]=v;else if(k==='own_car')a[k]=v==='true';else a[k]=v===''?null:Number(v);}
  return a;
}
async function renderPredict(){
  if(state.result)selectChatCase({model_id:state.result.model_id,applicant:state.result.inputs},state.result.case_id);
  const a=state.applicant||{...state.config.reference_case,age:Number(state.config.reference_case.age.toFixed(1)),employment_years:Number(state.config.reference_case.employment_years.toFixed(1)),external_score_2:null,external_score_3:null,late_payment_rate:null};
  $('#main').innerHTML=heading('INDIVIDUAL RISK ANALYSIS','Every application has a story.','Enter 12 key details. Explore the score and the assumptions behind it.','<button class="secondary" id="reset-case">Reset case</button>')+
    (!state.models.length?'<div class="notice warning">No models deployed yet. <a href="#models"><b>Add your first model</b></a> to run a prediction. You can prepare the case below.</div>':'')+
    `<div class="predict-layout"><section class="panel"><div class="panel-head"><div><h2>Applicant details</h2><p>Amounts use the same currency units as your training data.</p></div><span class="pill">12 INPUTS</span></div><form id="case-form"><div class="model-control"><label for="case-model">Prediction model</label><select name="model_id" id="case-model" ${state.models.length?'':'disabled'}>${state.models.length?state.models.map(m=>`<option value="${m.id}" ${state.result?.model_id===m.id?'selected':''}>${esc(m.name)} · ${m.feature_columns.length} features</option>`).join(''):'<option>No model deployed</option>'}</select></div><h3>Application & finances</h3><div class="form-grid">`+
    field('Annual income','income',a.income,'number',{min:1000,max:100000000,hint:'Total annual income before deductions'})+
    field('Credit amount','credit',a.credit,'number',{min:1000,max:100000000})+
    field('Loan annuity','annuity',a.annuity,'number',{min:1,max:10000000,hint:'AMT_ANNUITY in your source dataset'})+
    field('Contract type','contract_type',a.contract_type,'select',{items:['Cash loans','Revolving loans']})+
    `</div><div class="form-section"><h3>Applicant profile</h3><div class="form-grid">`+
    field('Age in years','age',a.age,'number',{min:19,max:100})+
    field('Years employed','employment_years',a.employment_years,'number',{min:0,max:85})+
    field('Education','education',a.education,'select',{items:['Lower secondary','Secondary / secondary special','Incomplete higher','Higher education','Academic degree']})+
    field('Income type','income_type',a.income_type,'select',{items:['Working','Commercial associate','Pensioner','State servant','Other']})+
    field('Owns a car','own_car',a.own_car,'select',{items:[{value:false,label:'No'},{value:true,label:'Yes'}]})+
    `</div></div><div class="form-section"><h3>Credit history signals</h3><div class="form-grid">`+
    field('External score 2','external_score_2',a.external_score_2,'number',{min:0,max:1,optional:true,hint:'EXT_SOURCE_2 · normalized score, 0–1'})+
    field('External score 3','external_score_3',a.external_score_3,'number',{min:0,max:1,optional:true,hint:'EXT_SOURCE_3 · normalized score, 0–1'})+
    field('Late payment rate','late_payment_rate',a.late_payment_rate,'number',{min:0,max:1,optional:true,hint:'Proportion, 0–1. Leave blank if unknown.'})+
    `</div></div><div id="prediction-error"></div><div class="form-footer"><small>Unentered features use training medians or modes.</small><button class="primary" id="predict-submit" ${state.models.length?'':'disabled'}>◎ &nbsp; Calculate risk</button></div></form></section><div id="prediction-result">${state.result?resultMarkup(state.result):panel('Prediction insight','Understand the score, not just the number.','<div class="result-placeholder"><div class="target-icon">◎</div><h2>Your analysis starts here</h2><p>Choose a deployed model and complete the case to see its risk score, key influences, and filled-in values.</p></div><div class="notice">Your form has 12 inputs. Derived fields and training defaults complete the model’s feature vector.</div>')}</div></div>`;
  $('#reset-case').onclick=()=>{state.applicant=null;state.result=null;state.selectedCase=null;state.messages={ollama:[],gemini:[]};renderPredict();};
  $('#case-form').oninput=()=>{++state.caseVersion;state.applicant=readCase();if(state.result){state.result=null;state.selectedCase=null;state.messages={ollama:[],gemini:[]};$('#prediction-result').innerHTML=panel('Case updated','Run the model again to refresh the result.','<div class="empty"><p>The inputs changed. Your previous prediction is no longer current.</p></div>');}};
  $('#case-form').onsubmit=async event=>{
    event.preventDefault();const button=$('#predict-submit');button.disabled=true;button.textContent='Calculating…';$('#prediction-error').innerHTML='';
    const applicant=readCase();state.applicant=applicant;const modelId=$('#case-model').value;const version=state.routeVersion;const caseVersion=state.caseVersion;
    try{const result=await api('/predict',{method:'POST',body:JSON.stringify({model_id:modelId,applicant})});if(version!==state.routeVersion)return;if(caseVersion!==state.caseVersion){toast('Inputs changed during calculation. Please calculate again.');return;}state.result=result;selectChatCase({model_id:modelId,applicant},result.case_id);$('#prediction-result').innerHTML=resultMarkup(result);bindResult();toast('Prediction and applicant chat ready.');}
    catch(e){if($('#prediction-error'))$('#prediction-error').innerHTML=`<div class="error-box" role="alert">${esc(e.message)}</div>`;}
    finally{if($('#predict-submit')){$('#predict-submit').disabled=false;$('#predict-submit').innerHTML='◎ &nbsp; Calculate risk';}}
  };
  bindResult();
}

function selectChatCase(caseData,label='Selected case'){
  state.selectedCase=caseData;
  state.selectedLabel=label;
  state.messages={ollama:[],gemini:[]};
}
function renderBatch(){
  $('#main').innerHTML=heading('MULTIPLE APPLICANT CHECK','Score a CSV of applicants.','Upload a test CSV, review the ranked scores, and open a row for its feature evidence.')+
    (!state.models.length?'<div class="notice warning">No model is deployed. <a href="#models"><b>Deploy a model</b></a> first, then return here to score a CSV.</div>':'')+
    `<section class="panel"><div class="panel-head"><div><h2>Upload applicant CSV</h2><p>Upload one applicant per row. CreditScope matches the available columns and prepares every applicant for the selected model.</p></div><span class="pill">UP TO 50,000 ROWS</span></div><form id="batch-form" class="batch-form"><div class="field"><label for="batch-model">Prediction model</label><select id="batch-model" name="model_id" required>${state.models.map(m=>`<option value="${esc(m.id)}">${esc(m.name)}</option>`).join('')}</select></div><div class="field"><label for="batch-file">CSV file</label><input id="batch-file" type="file" name="file" accept=".csv,text/csv" required></div><button class="primary" ${state.models.length?'':'disabled'}>Score applicants</button></form><p class="chart-foot">Columns unavailable in the uploaded file use the model's saved training defaults. The file is processed locally by CreditScope, and batch details expire after one hour or an app restart.</p><div id="batch-progress" class="live-label" role="status" aria-live="polite"></div><div id="batch-error"></div></section><div id="batch-results" class="section-space"></div>`;
  $('#batch-form').onsubmit=async event=>{
    event.preventDefault();const button=$('#batch-form button');button.disabled=true;button.textContent='Scoring applicants…';$('#batch-error').innerHTML='';
    const started=Date.now();const progress=$('#batch-progress');const update=()=>{if(progress)progress.textContent=`Scoring locally… ${Math.floor((Date.now()-started)/1000)} seconds elapsed. Large files may take a few minutes; keep this page open.`;};update();const timer=setInterval(update,1000);
    try{const report=await api('/batch/predict',{method:'POST',body:new FormData(event.target)});state.batch=report;state.batchPage=0;renderBatchResults();toast(`${report.results.length} applicants scored.`);}
    catch(error){$('#batch-error').innerHTML=`<div class="error-box" role="alert">${esc(error.message)}</div>`;}
    finally{clearInterval(timer);if(progress)progress.textContent='';button.disabled=false;button.textContent='Score applicants';}
  };
  if(state.batch)renderBatchResults();
}
function renderBatchResults(){
  const report=state.batch;if(!report||!$('#batch-results'))return;
  const rows=[...report.results].sort((a,b)=>b.probability-a.probability);
  const totalExposure=report.results.reduce((sum,row)=>sum+(row.exposure||0),0);
  const weightedPd=totalExposure?report.results.reduce((sum,row)=>sum+row.probability*(row.exposure||0),0)/totalExposure:0;
  const highRiskExposure=report.results.filter(row=>row.prediction).reduce((sum,row)=>sum+(row.exposure||0),0);
  const page=state.batchPage||0;const shown=rows.slice(page*100,(page+1)*100);
  $('#batch-results').innerHTML=panel('Batch results',`${report.model_name} · ${report.results.length} scored · ${report.errors.length} rows need correction`,
    `<div class="batch-summary"><b>${report.results.filter(r=>r.prediction).length}</b> flagged at ${pct(report.threshold,1)} threshold <button class="secondary" id="batch-export">↓ Export results CSV</button></div><div class="live-label">Read ${report.input_columns??'—'} uploaded columns · ${report.matched_model_columns??'—'} directly matched this model · ${report.unique_scores??'—'} distinct scores</div>${report.results.length>1&&report.unique_scores===1?'<div class="notice warning section-space"><b>All applicants received the same score.</b> Check that the file contains varying values under the model’s expected headers. A file with identical applicants can also produce this result.</div>':''}`)+lossPanelMarkup('batch',weightedPd,totalExposure,highRiskExposure,'Batch financial impact')+`<div class="research-metrics section-space"><table class="detail-table batch-table"><thead><tr><th>Row</th><th>Applicant ID</th><th>Exposure</th><th>Model score</th><th>Result</th><th>Defaults used</th><th></th></tr></thead><tbody>${shown.map(r=>`<tr><td>${r.row}</td><td>${esc(r.applicant_id)}</td><td>${money(r.exposure)}</td><td><b>${pct(r.probability)}</b></td><td><span class="pill ${r.prediction?'red':'green'}">${r.prediction?'FLAGGED':'NOT FLAGGED'}</span></td><td>${r.assumed_features}</td><td><button class="link-button" data-batch-row="${r.row}">Inspect row →</button></td></tr>`).join('')}</tbody></table></div><div class="batch-pages"><button class="secondary" id="batch-prev" ${page?'':'disabled'}>Previous</button><span>Page ${page+1} of ${Math.ceil(rows.length/100)}</span><button class="secondary" id="batch-next" ${(page+1)*100<rows.length?'':'disabled'}>Next</button></div>${report.errors.length?`<details><summary>${report.errors.length} rows could not be scored</summary><div class="scroll-table"><table class="detail-table"><tbody>${report.errors.map(e=>`<tr><td>Row ${e.row}</td><td>${esc(e.error)}</td></tr>`).join('')}</tbody></table></div></details>`:''}`+`<div id="batch-detail" class="section-space"></div>`;
  bindLossPanel('batch',weightedPd,totalExposure,highRiskExposure);
  bindInfoButtons($('#batch-results'));
  $('#batch-prev').onclick=()=>{state.batchPage--;renderBatchResults();};$('#batch-next').onclick=()=>{state.batchPage++;renderBatchResults();};
  $('#batch-export').onclick=()=>{const safeId=value=>{let text=String(value);if(/^[=+\-@]/.test(text))text="'"+text;return text.replaceAll('"','""');};const lines=['row,applicant_id,exposure,model_score,flagged,expected_loss,assumed_features',...report.results.map(r=>`${r.row},"${safeId(r.applicant_id)}",${r.exposure},${r.probability},${r.prediction},${r.probability*state.lgd*r.exposure},${r.assumed_features}`)];download('creditscope-batch-results.csv',lines.join('\n'),'text/csv');};
  $$('[data-batch-row]').forEach(button=>button.onclick=async()=>{
    const record=report.results.find(r=>r.row===Number(button.dataset.batchRow));button.disabled=true;button.textContent='Inspecting…';
    try{const result=await api('/batch/detail',{method:'POST',body:JSON.stringify({batch_id:report.batch_id,row:record.row})});selectChatCase(result.selected_case,record.applicant_id);$('#batch-detail').innerHTML=`<div class="batch-detail-head"><h2>Applicant ${esc(record.applicant_id)} · CSV row ${record.row}</h2><button class="link-button" id="batch-close">Close details</button></div>`+resultMarkup(result);$('#batch-close').onclick=()=>$('#batch-detail').innerHTML='';bindResult(result);$('#batch-detail').scrollIntoView({behavior:'smooth',block:'start'});}
    catch(error){toast(error.message);}finally{button.disabled=false;button.textContent='Inspect row →';}
  });
}
function resultMarkup(r){
  const maximum=Math.max(...r.contributions.map(c=>Math.abs(c.change)),.001);
  const assumptions=r.assumptions.map(a=>`<tr><td>${esc(a.feature)}</td><td>${esc(typeof a.value==='number'?a.value.toLocaleString('en-US',{maximumFractionDigits:5}):a.value)}</td><td>${esc(a.source)}</td></tr>`).join('');
  return `<section class="panel"><div class="score-head"><div><div class="eyebrow">${esc(r.model_name)} · MODEL OUTPUT</div><h2>Risk assessment</h2></div><span class="pill ${r.prediction?'red':'green'}">${r.prediction?'FLAGGED':'NOT FLAGGED'}</span></div><div class="score-value ${r.prediction?'risk':''}">${(r.probability*100).toFixed(1)}<span>%</span></div><div class="score-caption">Model default score · not calibrated</div><div class="score-track"><span class="score-marker" style="left:${r.probability*100}%" title="Model score"></span><span class="score-marker" style="left:${r.threshold*100}%;background:#996654" title="Classification threshold"></span></div><div class="score-axis"><span>0%</span><span>Threshold ${pct(r.threshold,1)}</span><span>100%</span></div><div class="insight">${r.prediction?'The score is at or above':'The score is below'} this model’s <strong>${pct(r.threshold,1)} threshold</strong>. ${r.assumed_features} of ${r.feature_count} features use training defaults.</div><div class="result-section"><h3>What influenced this score?</h3><p>Change in score when one entered value is replaced with its reference value.</p>${r.contributions.filter(c=>Math.abs(c.change)>.00001).slice(0,8).map(c=>`<div class="driver" title="Entered: ${esc(c.value)} · Reference: ${esc(c.reference)}"><span>${esc(c.label)}<small class="driver-values">${esc(typeof c.value==='number'?Number(c.value.toFixed(3)):c.value)} · ref ${esc(typeof c.reference==='number'?Number(c.reference.toFixed(3)):c.reference)}</small></span><div class="driver-track"><div class="driver-fill ${c.change<0?'down':''}" style="width:${Math.abs(c.change)/maximum*100}%"></div></div><b class="${c.change<0?'down':''}">${c.change>=0?'+':''}${(c.change*100).toFixed(2)} pp</b></div>`).join('')||'<p>This case is close to the reference values; no material input effect was measured.</p>'}<p class="section-space">Positive values raise the score relative to that reference; negative values lower it. These effects are not additive or causal.</p></div><div class="result-section"><details><summary>Inspect all ${r.feature_count} model inputs</summary><div class="scroll-table"><table class="detail-table"><thead><tr><th>Feature</th><th>Value</th><th>Origin</th></tr></thead><tbody>${assumptions}</tbody></table></div></details></div><div class="notice warning section-space">${esc(r.caveat)}</div><div class="actions report-actions"><button class="secondary" id="download-report">↓ Download report</button><button class="secondary" id="compare-models" ${state.models.length<2?'disabled':''}>Compare models</button></div><div id="comparison" class="comparison"></div><div class="chart-foot">Case ${esc(r.case_id)} · ${esc(new Date(r.created_at).toLocaleString())}</div></section>${lossPanelMarkup('case',r.probability,r.inputs?.credit||0,null,'Applicant financial impact')}<div id="case-chat" class="section-space"></div>`;
}
function bindResult(result=state.result){
  if(!$('#download-report'))return;
  bindLossPanel('case',result.probability,result.inputs?.credit||0);
  bindInfoButtons($('#prediction-result'));
  if(state.selectedCase)renderCaseChat();
  $('#download-report').onclick=()=>download(`creditscope-case-${result.case_id}.json`,JSON.stringify(result,null,2));
  $('#compare-models').onclick=async()=>{const button=$('#compare-models');button.disabled=true;try{const rows=await api('/compare',{method:'POST',body:JSON.stringify(result.inputs)});if(!$('#comparison'))return;$('#comparison').innerHTML='<h3>Same case, different models</h3><table class="detail-table"><thead><tr><th>Model</th><th>Score</th><th>Threshold</th></tr></thead><tbody>'+rows.map(r=>`<tr><td>${esc(r.model_name)}</td><td>${r.error?esc(r.error):pct(r.probability)}</td><td>${pct(r.threshold)}</td></tr>`).join('')+'</tbody></table>';}catch(e){toast(e.message);}finally{if($('#compare-models'))$('#compare-models').disabled=false;}};
}
async function renderEDA(){
  const version=state.routeVersion;if(!state.eda)state.eda=await api('/eda');if(version!==state.routeVersion)return;
  $('#main').innerHTML=heading('THE RESEARCH LIBRARY','Explore the evidence.','Original notebook plots, feature engineering, and reported model results.')+
    `<div class="metric-stack">${stat('Original notebook plots',state.eda.plots.length,'Preserved from saved cell outputs')}${stat('Engineered features','40','Application, bureau, and payment history')}${stat('Final numeric features','107','After redundancy reduction')}</div><div class="tabs" role="tablist"><button role="tab" data-eda-tab="all">All plots</button><button role="tab" data-eda-tab="Exploratory analysis">Exploratory analysis</button><button role="tab" data-eda-tab="Model evaluation">Model evaluation</button><button role="tab" data-eda-tab="pipeline">Data pipeline</button></div><div id="eda-content"></div>`;
  $$('[data-eda-tab]').forEach(b=>b.onclick=()=>{state.edaTab=b.dataset.edaTab;renderEDABody();});renderEDABody();
}
function renderEDABody(){
  $$('[data-eda-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.edaTab===state.edaTab);b.setAttribute('aria-selected',b.dataset.edaTab===state.edaTab);});
  if(state.edaTab==='pipeline'){
    const rows=state.eda.stages;
    $('#eda-content').innerHTML=panel('From raw data to model-ready inputs','Recorded processing stages from your Power BI export',`<div class="research-metrics"><table class="detail-table"><thead><tr>${Object.keys(rows[0]||{}).map(k=>`<th>${esc(k)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${Object.values(r).map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`);return;
  }
  const modelFilters=state.edaTab==='Model evaluation'?`<div class="model-plot-filters" aria-label="Model plot type"><button data-model-group="all">All model plots</button>${['Comparisons','Curves','Confusion matrices','Feature importance'].map(group=>`<button data-model-group="${group}">${group}</button>`).join('')}</div>`:'';
  $('#eda-content').innerHTML=(state.edaTab==='Model evaluation'?researchMetrics():'')+modelFilters+`<div class="search-row"><input type="search" id="plot-search" aria-label="Search notebook plots" placeholder="Search plots or notebook sections…" value="${esc(state.search)}"><span id="plot-count"></span></div><div id="gallery" class="gallery"></div>`;
  $$('[data-model-group]').forEach(button=>{button.classList.toggle('active',button.dataset.modelGroup===state.edaModelGroup);button.onclick=()=>{state.edaModelGroup=button.dataset.modelGroup;$$('[data-model-group]').forEach(item=>item.classList.toggle('active',item===button));renderGallery();};});
  $('#plot-search').oninput=e=>{state.search=e.target.value;renderGallery();};renderGallery();
}
function researchMetrics(){
  const rows=state.eda.metrics||[];
  if(!rows.length)return '';
  const bestAuc=rows.reduce((best,row)=>row.ROC_AUC>best.ROC_AUC?row:best,rows[0]);
  const bestRecall=rows.reduce((best,row)=>row.Recall>best.Recall?row:best,rows[0]);
  return panel('Complete model leaderboard','Validation results saved by the final notebook comparison cell.',`<div class="model-summary-strip"><div><small>MODELS COMPARED</small><strong>${rows.length}</strong></div><div><small>BEST ROC-AUC</small><strong>${bestAuc.ROC_AUC.toFixed(4)}</strong><span>${esc(bestAuc.Model)}</span></div><div><small>BEST RECALL</small><strong>${pct(bestRecall.Recall)}</strong><span>${esc(bestRecall.Model)}</span></div></div><div class="research-metrics"><table class="detail-table"><thead><tr><th>Model</th><th>Family</th><th>Accuracy</th><th>Precision</th><th>Recall</th><th>F1</th><th>ROC-AUC</th><th>PR-AUC</th></tr></thead><tbody>${rows.map(r=>`<tr><td><b>${esc(r.Model)}</b></td><td>${esc(r.Group||r.ModelType||'—')}</td><td>${pct(r.Accuracy)}</td><td>${pct(r.Precision)}</td><td>${pct(r.Recall)}</td><td>${Number(r.F1).toFixed(4)}</td><td><b>${Number(r.ROC_AUC).toFixed(4)}</b></td><td>${Number(r.PR_AUC).toFixed(4)}</td></tr>`).join('')}</tbody></table></div><div class="chart-foot">ROC-AUC and PR-AUC compare ranking quality without choosing a classification threshold. Accuracy, precision, recall, and F1 use the prediction rule saved in the notebook for each model.</div>`,'VALIDATION SET');
}
function renderGallery(){
  const plots=state.eda.plots.filter(p=>(state.edaTab==='all'||p.category===state.edaTab)&&(state.edaTab!=='Model evaluation'||state.edaModelGroup==='all'||p.group===state.edaModelGroup)&&`${p.title} ${p.section}`.toLowerCase().includes(state.search.toLowerCase()));
  $('#plot-count').textContent=`${plots.length} plots · click to inspect`;
  $('#gallery').innerHTML=plots.length?plots.map(p=>`<article class="plot-card"><button class="plot-open" data-plot="${esc(p.id)}" aria-label="Enlarge ${esc(p.title)}"><img class="plot-image" src="${esc(p.url)}" alt="${esc(p.title)}" loading="lazy"></button><div class="plot-body"><div class="plot-meta"><span>${esc(p.category.toUpperCase())}</span><span>CELL ${p.cell}</span></div><h3>${esc(p.title)}</h3><p>${esc(p.section)}</p></div></article>`).join(''):'<div class="empty"><h2>No matching plots</h2><p>Try a different search or category.</p></div>';
  $$('[data-plot]').forEach(b=>b.onclick=()=>{const p=state.eda.plots.find(p=>p.id===b.dataset.plot);const d=$('#plot-dialog');$('h2',d).textContent=p.title;$('img',d).src=p.url;$('img',d).alt=p.title;$('p',d).textContent=`Original notebook output · Cell ${p.cell} · ${p.section}`;d.showModal();});
}
function currentAssistant(){return state.config.health.assistants.find(a=>a.id===state.assistant);}
function formattedAnswer(value){
  const inline=s=>esc(s).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>');
  const lines=String(value||'').split(/\r?\n/);let html='',list='';
  const close=()=>{if(list){html+=`</${list}>`;list='';}};
  for(const raw of lines){const line=raw.trim();if(!line){close();continue;}
    const bullet=line.match(/^[-*]\s+(.+)$/),numbered=line.match(/^\d+[.)]\s+(.+)$/);
    if(bullet||numbered){const kind=bullet?'ul':'ol';if(list!==kind){close();html+=`<${kind}>`;list=kind;}html+=`<li>${inline((bullet||numbered)[1])}</li>`;continue;}
    close();const heading=line.match(/^#{1,3}\s+(.+)$/);html+=heading?`<h3>${inline(heading[1])}</h3>`:`<p>${inline(line)}</p>`;
  }
  close();return html;
}
function renderCaseChat(){
  const mount=$('#case-chat');if(!mount||!state.selectedCase)return;
  const assistant=currentAssistant(),configured=assistant.configured;
  mount.innerHTML=`<section class="panel chat-panel"><div class="chat-header"><div class="ai-icon">${assistant.local?'◌':'✦'}</div><div><h2>Chat about this applicant</h2><p>Ask about the score, feature evidence, and similar historical cases.</p></div><span class="pill ${configured?'green':'amber'}">${configured?(assistant.local?'LOCAL':'CLOUD'):'SETUP NEEDED'}</span></div><div class="assistant-switch" role="tablist" aria-label="Choose applicant assistant">${state.config.health.assistants.map(a=>`<button role="tab" class="${a.id===assistant.id?'active':''}" data-case-assistant="${a.id}" aria-selected="${a.id===assistant.id}"><span class="assistant-switch-icon">${a.local?'◌':'✦'}</span><span><b>${esc(a.name)}</b><small>${esc(a.provider)} · ${esc(a.model)}</small></span></button>`).join('')}</div>${configured?'':`<div class="notice warning">${assistant.local?'Start Ollama to use local chat.':'Add GEMINI_API_KEY to .env and restart CreditScope to use Gemini.'}</div>`}<div class="chat-messages" id="chat-messages" aria-live="polite"></div><form class="chat-compose" id="chat-form"><textarea id="chat-input" aria-label="Question about this applicant" placeholder="Why is this applicant riskier than average?" maxlength="5000" rows="2" required ${configured?'':'disabled'}></textarea><button class="primary" id="chat-send" ${configured?'':'disabled'}>Send</button></form><div class="chat-note">${assistant.local?'Applicant details stay on this computer.':'Applicant details are sent to Gemini for this conversation.'} The model score is an estimate, not a calibrated default rate.</div></section>`;
  $$('[data-case-assistant]',mount).forEach(button=>button.onclick=()=>{if(state.busyChat)return;state.assistant=button.dataset.caseAssistant;renderCaseChat();});
  renderMessages();
  $('#chat-form').onsubmit=async e=>{e.preventDefault();await sendChat();};
  $('#chat-input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();if(!state.busyChat&&configured)sendChat();}};
}
function renderAssistant(){
  const assistant=currentAssistant();
  const configured=assistant.configured;
  $('#main').innerHTML=heading('YOUR RESEARCH COMPANION',state.selectedCase?'Ask this applicant.':'A conversation with your project.','Switch between a local assistant and Gemini for project or selected-case questions.')+
    `<div class="assistant-switch" role="tablist" aria-label="Choose an assistant">${state.config.health.assistants.map(a=>`<button role="tab" class="${a.id===assistant.id?'active':''}" data-assistant="${a.id}" aria-selected="${a.id===assistant.id}"><span class="assistant-switch-icon">${a.local?'◌':'✦'}</span><span><b>${esc(a.name)}</b><small>${esc(a.provider)} · ${esc(a.model)}</small></span>${a.configured?'<i class="switch-status">Ready</i>':'<i class="switch-status waiting">Key needed</i>'}</button>`).join('')}</div>`+
    (!configured?'<div class="notice warning"><b>Connect Gemini to use this assistant.</b> Add GEMINI_API_KEY to the local .env file, then stop and restart CreditScope.</div>':'')+
    `<div class="chat-layout"><section class="panel chat-panel"><div class="chat-header"><div class="ai-icon">${assistant.local?'◌':'✦'}</div><div><h2>${esc(assistant.name)}</h2><p>${assistant.local?'Runs on this computer':'Cloud chat through Google Gemini'}</p></div><span class="pill ${configured?'green':'amber'}">${configured?(assistant.local?'LOCAL':'CLOUD'):'SETUP NEEDED'}</span></div><div class="chat-messages" id="chat-messages" aria-live="polite"></div><form class="chat-compose" id="chat-form"><textarea id="chat-input" aria-label="Your message" placeholder="Ask about CreditScope…" maxlength="5000" rows="2" required ${configured?'':'disabled'}></textarea><button class="primary" id="chat-send" ${configured?'':'disabled'}>Send</button></form><div class="chat-note">${assistant.local?'Runs through Ollama on this computer.':'Sends aggregate project context and this conversation to Gemini.'} ${state.selectedCase?(assistant.local?'Selected applicant details stay on this computer.':'Selected applicant details are sent to Gemini for this conversation.'):'No applicant-level rows are sent.'}</div></section><aside class="panel chat-context"><div class="eyebrow">PROJECT BRIEFING</div><h2>Built on your evidence</h2><div class="source-item"><b>${number(state.config.provenance.applicants)} applicants</b><p>Full Home Credit applicant export. Observed repayment difficulty: 8.07%.</p></div><div class="source-item"><b>107 numeric features</b><p>Includes 40 engineered features from historical applications, bureau records, and payments.</p></div><div class="source-item"><b>${state.models.length} deployed models</b><p>Live registry details are included with each message.</p></div><div class="source-item"><b>Notebook & benchmark results</b><p>EDA notes, validation metrics, class imbalance, and preprocessing decisions.</p></div><div class="source-item"><b>Clear limits</b><p>The assistant explains supplied evidence. It does not train models or run borrower predictions.</p></div>${adminInput()}</aside></div>`;
  if(state.selectedCase){
    $('.assistant-switch').insertAdjacentHTML('afterend',`<div class="selected-case-banner"><span><b>Applicant ${esc(state.selectedLabel)}</b> · ${esc(state.models.find(m=>m.id===state.selectedCase.model_id)?.name||'Selected model')} · case context active</span><button class="link-button" id="clear-applicant-context">Clear case</button></div>`);
    $('#clear-applicant-context').onclick=()=>{state.selectedCase=null;state.selectedLabel='';state.messages={ollama:[],gemini:[]};renderAssistant();};
  }
  $$('[data-assistant]').forEach(button=>button.onclick=()=>{if(state.busyChat)return;state.assistant=button.dataset.assistant;renderAssistant();});
  bindAdmin();renderMessages();
  $('#chat-form').onsubmit=async e=>{e.preventDefault();await sendChat();};
  $('#chat-input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();if(!state.busyChat&&configured)sendChat();}};
}
function renderMessages(){
  if(!$('#chat-messages'))return;
  const messages=state.messages[state.assistant];
  const prompts=state.selectedCase?['Why is this applicant riskier than average?','Show evidence for the late-payment concern.','Compare this applicant with similar cases.','What changes most affect this prediction?','Summarize this case in three sentences for a senior reviewer.']:['What are the strongest findings in our EDA?','How should I interpret a model’s default score?','Compare the reported model performance.'];
  $('#chat-messages').innerHTML=messages.length?messages.map(m=>`<div class="message ${m.role}"><div class="message-label">${m.role==='user'?'You':currentAssistant().name}</div><div class="message-content">${m.role==='assistant'?formattedAnswer(m.content):esc(m.content)}</div></div>`).join(''):`<div class="chat-welcome"><div class="ai-icon" style="margin:auto">${currentAssistant().local?'◌':'✦'}</div><h2>${state.selectedCase?'Ask about this applicant.':'Let’s make sense of the data.'}</h2><p>${state.selectedCase?'The selected score, input values, and similar historical cases are available to this assistant.':'Start with a question about your project’s data, features, or models.'}</p><div class="suggestions">${prompts.map(t=>`<button data-prompt="${esc(t)}">${esc(t)}</button>`).join('')}</div></div>`;
  if(state.busyChat)$('#chat-messages').innerHTML+='<div class="message"><div class="message-label">CreditScope</div><p>Reviewing the project context…</p></div>';
  $$('[data-prompt]').forEach(b=>b.onclick=()=>{if(!currentAssistant().configured){toast('Add the Gemini API key in .env first.');return;}$('#chat-input').value=b.dataset.prompt;sendChat();});
  $('#chat-messages').scrollTop=$('#chat-messages').scrollHeight;
}
async function sendChat(){
  const input=$('#chat-input');const text=input?.value.trim();const assistant=state.assistant;if(!text||state.busyChat)return;
  const messages=state.messages[assistant];messages.push({role:'user',content:text});input.value='';state.busyChat=true;$('#chat-send').disabled=true;renderMessages();
  try{const result=await api('/chat',{method:'POST',body:JSON.stringify({assistant,messages:messages.slice(-11),applicant_context:state.selectedCase})});messages.push({role:'assistant',content:result.answer});}
  catch(e){messages.pop();if($('#chat-input'))$('#chat-input').value=text;toast(e.message);}
  finally{state.busyChat=false;renderMessages();if($('#chat-send'))$('#chat-send').disabled=false;}
}
function adminInput(){return state.config.health.admin_required?'<div class="field admin-field"><label for="admin-token">Administrator token</label><input id="admin-token" type="password" autocomplete="off" placeholder="Required for model management and AI chat"><small>Held in this page’s memory only.</small></div>':'';}
function bindAdmin(){if($('#admin-token')){$('#admin-token').value=state.adminToken;$('#admin-token').oninput=e=>state.adminToken=e.target.value;}}
function renderModels(){
  $('#main').innerHTML=heading('MODEL OPERATIONS','Your models. One workspace.','Deploy a trained model, validate its inputs, and make it available for prediction.','<button class="secondary" id="download-template">↓ Metadata template</button>')+
    `<div id="model-cards">${state.models.length?`<div class="model-grid">${state.models.map(m=>`<article class="panel model-card"><div class="model-title"><div><div class="eyebrow">${esc(m.kind==='pytorch_dcn'?'PYTORCH':m.kind.toUpperCase())}</div><h2>${esc(m.name)}</h2></div><span class="pill green">DEPLOYED</span></div><p>${esc(m.description)}</p><div class="model-info"><div><small>FEATURES</small><b>${m.feature_columns.length}</b></div><div><small>THRESHOLD</small><b>${pct(m.threshold,1)}</b></div><div><small>REPORTED ROC-AUC</small><b>${typeof m.validation_metrics?.roc_auc==='number'?m.validation_metrics.roc_auc.toFixed(3):'—'}</b></div></div><div class="model-card-bottom"><a href="#predict" class="link-button">Use for prediction</a><button class="link-button" style="color:#b07670" data-delete="${m.id}">Remove</button></div></article>`).join('')}</div>`:`<section class="panel empty"><div class="empty-icon">⬡</div><h2>A clean slate for your models</h2><p>No model is preloaded. Add your MLP, DCN, or SMOTE-trained model below. Successfully validated models become available immediately.</p><span class="pill">READY WHEN YOU ARE</span></section>`}</div><section class="panel section-space"><div class="panel-head"><div><h2>Deploy a trained model</h2><p>Upload the model and the files that define how its inputs are prepared.</p></div><span class="pill">LOCAL STORAGE</span></div><div class="model-upload"><form id="upload-form"><div class="form-grid"><div class="field"><label for="model-name">Model name</label><input id="model-name" name="name" required maxlength="80" placeholder="e.g. DCN + SMOTE"></div><div class="field"><label for="model-kind">Model format</label><select id="model-kind" name="kind"><option value="sklearn">Scikit-learn · joblib / pkl</option><option value="pytorch_dcn">PyTorch DCN checkpoint · pth / pt</option><option value="torchscript">PyTorch TorchScript · pt</option><option value="lightgbm">LightGBM · txt</option><option value="catboost">CatBoost · cbm</option><option value="keras">Keras · h5 / keras</option></select></div><div class="field"><label for="model-file">Trained model file</label><input id="model-file" class="file-input" name="artifact" type="file" accept=".joblib,.pkl" required><small>Maximum 100 MB · use trusted files only</small></div><div class="field"><label for="metadata-file">Metadata JSON</label><input id="metadata-file" class="file-input" name="metadata" type="file" accept=".json"><small>Feature order and classification threshold</small></div><div class="field"><label for="preprocessor-file">Preprocessor · if separate</label><input id="preprocessor-file" class="file-input" name="preprocessor" type="file" accept=".joblib,.pkl"><small>Required for the saved PyTorch DCN</small></div><div class="field"><label for="features-file">Feature columns · if separate</label><input id="features-file" class="file-input" name="feature_columns" type="file" accept=".json"><small>Ordered JSON feature names</small></div><div class="field"><label for="categories-file">CatBoost categorical columns</label><input id="categories-file" class="file-input" name="categorical_features" type="file" accept=".json"><small>Upload categorical_features.json for CatBoost.</small></div></div><label class="check-label"><input type="checkbox" name="trusted" value="true" required><span>I created or trust these files. Serialized model and preprocessor files can execute code when loaded.</span></label>${adminInput()}<div id="upload-error"></div><button class="primary section-space" id="deploy-submit">Validate & deploy</button></form><div class="upload-guide"><h3>What makes a deployable model?</h3><ol><li>A trained model that returns a probability for class 1.</li><li>The exact feature order used in training.</li><li>The original fitted scaler and imputer, inside the pipeline or uploaded separately.</li><li>A classification threshold from validation.</li></ol><div class="notice">SMOTE is a training step. Upload the model trained with SMOTE and its preprocessing; resampling is not applied to a new applicant.</div><h3>Compatible with your notebook</h3><p><b>MLP:</b> upload mlp_pipeline.joblib and metadata.json.</p><p><b>DCN:</b> upload credit_dcn.pth and preprocessor.joblib. The checkpoint contains feature order and threshold.</p><p><b>MLP / DCN + SMOTE:</b> upload the saved model, its scaler, and metadata with the exact selected features.</p><p><b>Keras:</b> full saved models only. Requires the optional TensorFlow runtime. Weight-only H5 files need their architecture packaged first.</p><p>For Main project/model: choose TorchScript for dcn/model.pt, LightGBM for model.txt, and CatBoost for model.cbm. Upload metadata.json and feature_columns.json; add preprocessor.pkl or categorical_features.json when present. Invalid outputs are rejected.</p></div></div></section>`;
  bindAdmin();$('#download-template').onclick=async()=>{try{download('creditscope-metadata-template.json',JSON.stringify(await api('/models/template'),null,2));}catch(e){toast(e.message);}};
  $('#model-kind').onchange=e=>{$('#model-file').accept=({sklearn:'.joblib,.pkl',pytorch_dcn:'.pth,.pt',torchscript:'.pt',lightgbm:'.txt',catboost:'.cbm',keras:'.h5,.keras'})[e.target.value];};
  $('#upload-form').onsubmit=async e=>{
    e.preventDefault();const button=$('#deploy-submit');button.disabled=true;button.textContent='Validating model…';$('#upload-error').innerHTML='';
    const data=new FormData(e.target);for(const key of ['metadata','preprocessor','feature_columns','categorical_features'])if(!data.get(key)?.size)data.delete(key);
    try{const result=await api('/models',{method:'POST',body:data});await refreshModels();if(currentPage()==='models')renderModels();toast(`${result.name} is deployed and ready for prediction.`);}
    catch(e){if($('#upload-error'))$('#upload-error').innerHTML=`<div class="error-box" role="alert">${esc(e.message)}</div>`;}
    finally{if($('#deploy-submit')){$('#deploy-submit').disabled=false;$('#deploy-submit').textContent='Validate & deploy';}}
  };
  $$('[data-delete]').forEach(button=>button.onclick=()=>{
    const id=button.dataset.delete;const dialog=$('#delete-dialog');dialog.showModal();$('#confirm-delete').onclick=async()=>{const confirm=$('#confirm-delete');confirm.disabled=true;try{await api('/models/'+id,{method:'DELETE'});dialog.close();await refreshModels();if(currentPage()==='models')renderModels();if(state.result?.model_id===id)state.result=null;toast('Model removed. A local archived copy is preserved.');}catch(e){toast(e.message);}finally{confirm.disabled=false;}};
  });
}
async function refreshModels(){state.models=await api('/models');$('#model-count').textContent=state.models.length;}
function currentPage(){return location.hash.slice(1)||'overview';}
async function navigate(){
  const page=titles[currentPage()]?currentPage():'overview';++state.routeVersion;++state.dashboardVersion;
  $$('[data-page]').forEach(a=>{a.classList.toggle('active',a.dataset.page===page);if(a.dataset.page===page)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  $('#breadcrumb').textContent=titles[page];document.title=`${titles[page]} · CreditScope`;
  $('#main').innerHTML='<div class="loading">Opening workspace…</div>';
  try{await ({overview:renderOverview,global:renderGlobal,predict:renderPredict,batch:renderBatch,eda:renderEDA,assistant:renderAssistant,models:renderModels})[page]();bindInfoButtons($('#main'));}
  catch(e){$('#main').innerHTML=`<div class="error-box" role="alert">${esc(e.message)}</div><button class="secondary" id="retry-page">Try again</button>`;$('#retry-page').onclick=navigate;}
  window.scrollTo({top:0});
}
$('.dialog-close').onclick=()=>$('#plot-dialog').close();$('[data-close]').onclick=()=>$('#delete-dialog').close();$('.metric-dialog-close').onclick=()=>$('#metric-dialog').close();
async function start(){
  try{state.config=await api('/config');await refreshModels();await navigate();window.addEventListener('hashchange',navigate);}
  catch(e){$('#main').innerHTML=`<div class="error-box">Unable to open CreditScope: ${esc(e.message)}. Ensure the project import has completed.</div><button class="secondary" id="reload-app">Retry</button>`;$('#reload-app').onclick=()=>location.reload();}
}
start();
