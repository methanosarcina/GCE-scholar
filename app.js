const $ = id => document.getElementById(id);
const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeURL = value => { try { const u = new URL(value); return u.protocol === 'https:' ? u.href : '#'; } catch { return '#'; } };
let scholars = [], catalog, current, entry;
let sourceReport = null;
const figureLabel = p => p.figure?.provider === 'publisher' ? '摘要图 · 出版社' : (p.figure?.kind || '文献封面');
const publisherStatus = s => ({found:'已配上出版社摘要图',host_deferred:'站点访问受限，未逐篇读取',access_restricted:'访问受限',no_graphic_detected:'本次未检测到摘要图',doi_not_verified:'页面 DOI 未能核对',doi_mismatch:'页面 DOI 不符',image_unavailable:'图片地址暂不可用',request_failed:'网络请求失败',http_error:'页面请求失败'}[s] || s);
function publisherCoverage(r) {
  if (!r.publisher) return '';
  return `<section id="publisher-coverage"><h3>出版社摘要图</h3><p>${r.publisher.publisherGraphics} 篇已配图 · 最近检查 ${esc(r.publisher.updated.slice(0,10))}</p><p>访问受限不代表文章没有摘要图；未检测到也可能是页面结构暂不支持。</p><ul>${Object.entries(r.publisher.statuses).map(([s,n])=>`<li>${esc(publisherStatus(s))}：${n}</li>`).join('')}</ul><details><summary>逐篇查看出版社检查结果</summary><ul>${(r.publisherAttempts||[]).map(p=>`<li><a href="${esc(safeURL(p.source))}" target="_blank" rel="noopener">${esc(p.doi)}</a> · ${esc(publisherStatus(p.status))}</li>`).join('')}</ul></details></section>`;
}
const matchesOrcid = (paper, orcid) => (paper.authorDetails || []).some(a => a.authorId?.type === "ORCID" && a.authorId.value === orcid);
function cover(p) {
  return `<div class="paper-cover"><div class="cover-journal">${esc(p.journal || 'RESEARCH PAPER')}</div><div class="cover-year">${esc(p.year)}</div><div class="cover-title">${esc(p.title)}</div><div class="cover-note">文献封面 · 非原文图片</div></div>`;
}
function visual(p) {
  return `<div class="visual ${p.figure ? '' : 'no-image'}">${p.figure ? `<img loading="lazy" src="${esc(safeURL(p.figure.url))}" alt="${esc(figureLabel(p))}"><div class="image-fallback" hidden>${cover(p)}</div>` : cover(p)}<span class="tag">${esc(figureLabel(p))}</span></div>`;
}
function nav() {
  const term = $('scholar-search').value.toLowerCase();
  $('scholars').innerHTML = scholars.filter(s => s.name.toLowerCase().includes(term)).map(s => `<button class="${s.id === current?.id ? 'active' : ''}" data-id="${esc(s.id)}"><span class="avatar">${s.name.split(' ').map(w=>w[0]).join('')}</span>${esc(s.name)}</button>`).join('');
  $('scholars').querySelectorAll('button').forEach(b => b.onclick = () => select(b.dataset.id));
}
function select(id) {
  current = scholars.find(s => s.id === id) || scholars[0];
  history.replaceState(null, '', '#' + current.id);
  entry = structuredClone(catalog.scholars[current.id] || {papers:[], total:0, cursor:'*'});
  entry.papers = (entry.papers || []).filter(p => matchesOrcid(p, current.orcid));
  $('name').textContent = current.name; $('breadcrumb').textContent = current.name;
  $('description').textContent = [current.institution, 'ORCID '+current.orcid].filter(Boolean).join(' · ');
  $('lab-link').innerHTML = entry.labSource ? `<a href="${esc(safeURL(entry.labSource.url))}" target="_blank" rel="noopener">${esc(entry.labSource.label)} ↗</a><span>${entry.labSource.status === 'ok' ? (entry.labSource.doiCount ? '已按 DOI 对照官方来源' : '已读取官网 · 未解析到 DOI') : '官方来源本次未能读取'}</span>` : '';
  $('paper-search').value = ''; $('year').value = ''; $('only-images').checked = false;
  $('only-abstracts').checked = false;
  $('status').textContent = entry.complete ? '已载入快照中全部 ORCID 匹配记录。' : '当前显示已核实 ORCID 的部分记录，后续数据同步将补充。';
  nav(); years(); render();
}
function years() {
  const selected = $('year').value;
  $('year').innerHTML = '<option value="">全部年份</option>' + [...new Set(entry.papers.map(p => p.year))].filter(Boolean).sort().reverse().map(y => `<option>${esc(y)}</option>`).join('');
  $('year').value = selected;
}
function filtered() {
  const term = $('paper-search').value.toLowerCase();
  return entry.papers.filter(p => (!term || `${p.title} ${p.abstract} ${p.journal}`.toLowerCase().includes(term)) && (!$('year').value || p.year === $('year').value) && (!$('only-images').checked || p.figure) && (!$('only-abstracts').checked || p.figure?.kind === '摘要图'))
    .sort((a,b) => $('sort').value === 'cited' ? b.citations-a.citations : ($('sort').value === 'old' ? a.year-b.year : b.year-a.year));
}
function render() {
  const papers = filtered();
  $('loaded').textContent = entry.papers.length;
  $('total').textContent = entry.total ?? '—';
  $('figures').textContent = entry.papers.filter(p=>p.figure).length;
  $('result-count').textContent = `${papers.length} 篇当前可见 · 筛选仅作用于已载入论文`;
  $('updated').textContent = entry.updated ? '数据快照 ' + entry.updated.slice(0,10) : '实时检索';
  $('papers').innerHTML = papers.map(p => `<button class="card" data-id="${esc(p.id)}">${visual(p)}<div class="body"><div class="meta">${esc(p.year)} · ${esc(p.journal || '期刊未提供')}</div><h3>${esc(p.title)}</h3><div class="authors">${esc(p.authors)}</div><div class="card-bottom"><span>${p.citations} 次引用 ${p.oa ? '· 开放获取' : ''}</span><span>阅读论文 ↗</span></div></div></button>`).join('') || '<div class="empty">没有符合条件的论文。可以调整筛选条件，或等待数据更新。</div>';
  $('papers').querySelectorAll('.card').forEach(b => b.onclick = () => detail(entry.papers.find(p=>p.id===b.dataset.id)));
  $('papers').querySelectorAll('img').forEach(img => img.onerror = () => { img.hidden = true; img.parentElement.querySelector('.image-fallback').hidden = false; img.parentElement.classList.add('no-image'); img.parentElement.querySelector('.tag').textContent = '原图暂不可用 · 文献封面'; });
}
function detail(p) {
  $('detail-content').innerHTML = `<p class="eyebrow">${esc(p.year)} · ${esc(p.journal)}</p><h2>${esc(p.title)}</h2><p class="caption">${esc(p.authors)}</p>${p.figure ? `<img src="${esc(safeURL(p.figure.url))}" alt="${esc(p.figure.kind)}"><p class="caption">${esc(p.figure.kind)} · ${esc(p.figure.caption)}<br><a target="_blank" rel="noopener" href="${esc(safeURL(p.figure.source))}">图片来源 ↗</a>${esc(p.license)}</p>` : ''}<h3>摘要</h3><p>${esc(p.abstract || '数据源未提供摘要，请访问原文。')}</p><a target="_blank" rel="noopener" href="${esc(safeURL(p.url))}">Europe PMC ↗</a>${p.doi ? `<a target="_blank" rel="noopener" href="https://doi.org/${encodeURIComponent(p.doi)}">出版社原文 ↗</a>` : ''}<details><summary>作者机构与 ORCID（用于身份核对）</summary><ul>${(p.authorDetails||[]).map(a=>`<li><b>${esc(a.firstName || '')} ${esc(a.lastName || a.fullName)}</b> ${esc(a.authorId?.value || '')}<br>${esc((a.authorAffiliationDetailsList?.authorAffiliation || []).map(x=>x.affiliation).join(' / '))}</li>`).join('')}</ul></details>`;
  $('detail').showModal();
  const detailImage = $('detail-content').querySelector('img');
  if (detailImage) detailImage.onerror = () => { detailImage.hidden = true; detailImage.insertAdjacentHTML('afterend', cover(p)); };
  else $('detail-content').querySelector('.caption').insertAdjacentHTML('afterend', cover(p));
  if (p.labSources?.length) $('detail-content').insertAdjacentHTML('beforeend', '<h3>官方来源核对</h3>'+p.labSources.map(url=>`<p><a href="${esc(safeURL(url))}" target="_blank" rel="noopener">课题组发表清单 · DOI 匹配 ↗</a></p>`).join(''));
}
$('sources').onclick = async () => {
  try {
    if (!sourceReport) { const r=await fetch('data/source-report.json'); if(!r.ok)throw Error(); sourceReport=await r.json(); }
    $('detail-content').innerHTML='<h2>官方来源与图片覆盖</h2><p>沿用固定 ORCID 收录规则。官网按 DOI 核对已有论文；未匹配条目只列为待核实，不自动添加。课题组配图和正文插图不等同于摘要图。</p><div class="source-table">'+sourceReport.sources.map(s=>`<div><a href="${esc(safeURL(s.url))}" target="_blank" rel="noopener">${esc(s.label)} ↗</a><span>${s.status==='ok' ? `${s.matched} 个 DOI 已在目录 · ${s.images} 张官网配图` : '本次未能读取'}</span></div>`).join('')+'</div><p>部分官网只列代表性论文，或使用动态列表；未解析到 DOI 不代表没有论文。</p><details><summary>官网中未在当前目录匹配的 DOI（'+sourceReport.unmatched.length+'）</summary><ul>'+sourceReport.unmatched.map(p=>`<li>${esc(scholars.find(s=>s.id===p.scholar)?.name || p.scholar)} · <a target="_blank" rel="noopener" href="https://doi.org/${encodeURIComponent(p.doi)}">${esc(p.doi)}</a> <a target="_blank" rel="noopener" href="${esc(safeURL(p.source))}">官网来源</a></li>`).join('')+'</ul></details>';
    $('detail-content').querySelector('p').insertAdjacentHTML('afterend', publisherCoverage(sourceReport));
    $('detail').showModal();
  } catch { $('status').textContent='来源核对报告尚未生成，请运行 enrich.py 后刷新。'; }
};
$('scholar-search').oninput = nav;
['paper-search','year','sort','only-images','only-abstracts'].forEach(id => $(id).addEventListener('input',render));
$('close').onclick = () => $('detail').close();
$('detail').onclick = e => { if(e.target === $('detail')) $('detail').close(); };
$('export').onclick = () => {
  const blob = new Blob([JSON.stringify({scholar:current,query:entry.query,exported:new Date().toISOString(),papers:filtered()},null,2)],{type:'application/json'});
  const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = current.id+'.json'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
};
Promise.all([fetch('scholars.json').then(r=>r.json()),fetch('data/catalog.json').then(r=>r.json())]).then(([s,c])=>{scholars=s;catalog=c;$('scholar-count').textContent=s.length;select(location.hash.slice(1));}).catch(e=>{$('status').textContent='无法读取数据。请用 python server.py 启动项目，或通过 GitHub Pages 打开。';});
