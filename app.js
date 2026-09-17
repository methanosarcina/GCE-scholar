const $ = id => document.getElementById(id);
const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const plain = text => { const doc = new DOMParser().parseFromString(text || '', 'text/html'); return doc.body.textContent || ''; };
const safeURL = value => { try { const u = new URL(value); return u.protocol === 'https:' ? u.href : '#'; } catch { return '#'; } };
let scholars = [], catalog, current, entry, generation = 0, busy = false;
let overrides = {}; try { overrides = JSON.parse(localStorage.getItem('scholar-queries') || '{}'); } catch {}
const save = () => { try { localStorage.setItem('scholar-queries', JSON.stringify(overrides)); } catch {} };
function nav() {
  const term = $('scholar-search').value.toLowerCase();
  $('scholars').innerHTML = scholars.filter(s => s.name.toLowerCase().includes(term)).map(s => `<button class="${s.id === current?.id ? 'active' : ''}" data-id="${esc(s.id)}"><span class="avatar">${s.name.split(' ').map(w=>w[0]).join('')}</span>${esc(s.name)}</button>`).join('');
  $('scholars').querySelectorAll('button').forEach(b => b.onclick = () => select(b.dataset.id));
}
function select(id) {
  generation++; busy = false;
  current = scholars.find(s => s.id === id) || scholars[0];
  history.replaceState(null, '', '#' + current.id);
  entry = structuredClone(catalog.scholars[current.id] || {papers:[], total:0, cursor:'*'});
  entry.papers ||= [];
  $('name').textContent = current.name; $('breadcrumb').textContent = current.name;
  $('description').textContent = current.orcid ? [current.institution, 'ORCID '+current.orcid, current.identityStatus || '按公开作者资料匹配'].filter(Boolean).join(' · ') : '论文、图像与灵感，汇集于此。 · 姓名匹配待核对';
  $('paper-search').value = ''; $('year').value = ''; $('only-images').checked = false;
  $('query').value = overrides[current.id] || current.query;
  $('orcid').value = current.orcid || '';
  $('status').textContent = entry.error ? '上次同步失败；可点击加载按钮重试。' : (entry.complete ? '该查询的数据库结果已全部载入。未关联 ORCID 或未收录的论文仍需补充。' : '');
  nav(); years(); render();
  if (overrides[current.id]) load(true);
}
function years() {
  const selected = $('year').value;
  $('year').innerHTML = '<option value="">全部年份</option>' + [...new Set(entry.papers.map(p => p.year))].filter(Boolean).sort().reverse().map(y => `<option>${esc(y)}</option>`).join('');
  $('year').value = selected;
}
function filtered() {
  const term = $('paper-search').value.toLowerCase();
  return entry.papers.filter(p => (!term || `${p.title} ${p.abstract} ${p.journal}`.toLowerCase().includes(term)) && (!$('year').value || p.year === $('year').value) && (!$('only-images').checked || p.figure))
    .sort((a,b) => $('sort').value === 'cited' ? b.citations-a.citations : ($('sort').value === 'old' ? a.year-b.year : b.year-a.year));
}
function render() {
  const papers = filtered();
  $('loaded').textContent = entry.papers.length;
  $('total').textContent = entry.total ?? '—';
  $('figures').textContent = entry.papers.filter(p=>p.figure).length;
  $('result-count').textContent = `${papers.length} 篇当前可见 · 筛选仅作用于已载入论文`;
  $('updated').textContent = entry.updated ? '数据快照 ' + entry.updated.slice(0,10) : '实时检索';
  $('query-info').textContent = '当前查询：' + (entry.query || $('query').value);
  $('more').disabled = busy;
  $('more').hidden = !entry.cursor && !entry.error;
  $('more').textContent = busy ? '正在获取论文…' : (['localhost','127.0.0.1'].includes(location.hostname) ? '加载更多历史论文' : '在数据源查看完整检索结果 ↗');
  $('papers').innerHTML = papers.map(p => `<button class="card" data-id="${esc(p.id)}"><div class="visual">${p.figure ? `<img loading="lazy" src="${esc(safeURL(p.figure.url))}" alt="${esc(p.figure.kind)}">` : `<div class="abstract-preview">${esc(p.abstract || '此记录暂无摘要。打开论文查看出版社原文。')}</div>`}<span class="tag">${esc(p.figure?.kind || '摘要文字')}</span></div><div class="body"><div class="meta">${esc(p.year)} · ${esc(p.journal || '期刊未提供')}</div><h3>${esc(p.title)}</h3><div class="authors">${esc(p.authors)}</div><div class="card-bottom"><span>${p.citations} 次引用 ${p.oa ? '· 开放获取' : ''}</span><span>阅读论文 ↗</span></div></div></button>`).join('') || '<div class="empty">没有符合条件的论文。可以调整筛选条件，或加载更多历史记录。</div>';
  $('papers').querySelectorAll('.card').forEach(b => b.onclick = () => detail(entry.papers.find(p=>p.id===b.dataset.id)));
  $('papers').querySelectorAll('img').forEach(img => img.onerror = () => { img.hidden = true; img.parentElement.querySelector('.tag').textContent = '图片不可用 · 点击阅读摘要'; });
}
function detail(p) {
  $('detail-content').innerHTML = `<p class="eyebrow">${esc(p.year)} · ${esc(p.journal)}</p><h2>${esc(p.title)}</h2><p class="caption">${esc(p.authors)}</p>${p.figure ? `<img src="${esc(safeURL(p.figure.url))}" alt="${esc(p.figure.kind)}"><p class="caption">${esc(p.figure.kind)} · ${esc(p.figure.caption)}<br><a target="_blank" rel="noopener" href="${esc(safeURL(p.figure.source))}">图片原文与授权说明 ↗</a>${esc(p.license)}</p>` : ''}<h3>摘要</h3><p>${esc(p.abstract || '数据源未提供摘要，请访问原文。')}</p><a target="_blank" rel="noopener" href="${esc(safeURL(p.url))}">Europe PMC ↗</a>${p.doi ? `<a target="_blank" rel="noopener" href="https://doi.org/${encodeURIComponent(p.doi)}">出版社原文 ↗</a>` : ''}<details><summary>作者机构与 ORCID（用于身份核对）</summary><ul>${(p.authorDetails||[]).map(a=>`<li><b>${esc(a.firstName || '')} ${esc(a.lastName || a.fullName)}</b> ${esc(a.authorId?.value || '')}<br>${esc((a.authorAffiliationDetailsList?.authorAffiliation || []).map(x=>x.affiliation).join(' / '))}</li>`).join('')}</ul></details>`;
  $('detail').showModal();
}
function normalize(p) {
  return {id:p.source+':'+p.id,title:plain(p.title),year:p.pubYear||'',journal:p.journalInfo?.journal?.title||'',abstract:plain(p.abstractText),authors:p.authorString||'',doi:p.doi||'',pmcid:p.pmcid||'',oa:p.isOpenAccess==='Y',citations:p.citedByCount||0,license:p.license||'',url:`https://europepmc.org/article/${p.source}/${p.id}`,authorDetails:p.authorList?.author||[]};
}
async function request(query, cursor) {
    const response = await fetch('/api/search?'+new URLSearchParams({query,cursor}), {signal:AbortSignal.timeout(45000)});
    if (!response.ok) throw new Error('数据源暂时不可用（'+response.status+'）');
    return response.json();
}
async function load(reset=false) {
  if (busy) return;
  const token = generation, query = reset ? $('query').value.trim() : (entry.query || current.query);
  if (!query) return;
  if (!['localhost','127.0.0.1'].includes(location.hostname)) {
    $('status').innerHTML = '静态网站展示已同步的记录。<a target="_blank" rel="noopener" href="https://europepmc.org/search?query='+encodeURIComponent(query)+'">在 Europe PMC 打开此查询 ↗</a>；在本地版可直接加载，或运行采集器更新网站。';
    return;
  }
  busy = true; render(); $('status').textContent = '正在读取公开论文数据…';
  try {
    const data = await request(query, reset ? '*' : (entry.cursor || '*'));
    if (token !== generation) return;
    const previous = reset ? [] : entry.papers;
    const seen = new Set(previous.map(p=>p.id));
    entry = {...data, query, papers:[...previous,...data.papers.filter(p=>!seen.has(p.id))]};
    $('status').textContent = entry.cursor ? '已载入一页；可继续加载更早论文。' : '该查询的数据库结果已全部载入；仍可能存在数据库未收录的论文。';
    years();
  } catch (e) {
    if (token === generation) $('status').textContent = '加载失败，已保留现有数据。'+e.message+'，请稍后重试。';
  } finally { if (token === generation) {busy = false; render();} }
}
$('scholar-search').oninput = nav;
['paper-search','year','sort','only-images'].forEach(id => $(id).addEventListener('input',render));
$('more').onclick = () => load();
$('close').onclick = () => $('detail').close();
$('detail').onclick = e => { if(e.target === $('detail')) $('detail').close(); };
$('apply-query').onclick = () => { if(busy) return; overrides[current.id] = $('query').value.trim(); save(); load(true); };
$('apply-orcid').onclick = () => {
  if(busy) return;
  const id = $('orcid').value.trim().replace('https://orcid.org/','');
  if(!/^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/.test(id)) { $('status').textContent = '请输入有效格式的 ORCID。'; return; }
  $('query').value = 'AUTHORID:"'+id+'"'; $('apply-query').click();
};
$('reset-query').onclick = () => { delete overrides[current.id]; save(); select(current.id); };
$('export').onclick = () => {
  const blob = new Blob([JSON.stringify({scholar:current,query:entry.query,exported:new Date().toISOString(),papers:filtered()},null,2)],{type:'application/json'});
  const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = current.id+'.json'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
};
Promise.all([fetch('scholars.json').then(r=>r.json()),fetch('data/catalog.json').then(r=>r.json())]).then(([s,c])=>{scholars=s;catalog=c;$('scholar-count').textContent=s.length;select(location.hash.slice(1));}).catch(e=>{$('status').textContent='无法读取数据。请用 python server.py 启动项目，或通过 GitHub Pages 打开。';});
