import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { trendStats, evidenceFor, createReport, ollamaContext, reportMarkdown, esc } from '../src/engine.mjs';

const data = JSON.parse(readFileSync(new URL('../src/generated/data.json', import.meta.url), 'utf8'));
const profile = { company: '테스트식품', product: 'kimchi', market: '일본', format: '냉장 완제품', channel: '현지 아시안 마켓', goal: '저당 제품의 소량 수출 검증' };

test('recent means use 12 complete months and exclude October 2026', () => {
  const p = data.products.find(x => x.id === 'kimchi');
  const s = trendStats(p);
  assert.equal(s.rows.length, 60);
  assert.equal(s.start, '2025-10-01');
  assert.equal(s.end, '2026-09-01');
  assert.equal(s.current, 74.75); // independent sum of the 12 source CSV values: 897 / 12
  assert.ok(s.growth > 9 && s.growth < 9.2);
  const changed = structuredClone(p);
  changed.channels.web.series.at(-1).value = 999999;
  assert.equal(trendStats(changed).growth, s.growth);
});

test('typo, sparse data and zero baseline cannot become growth claims', () => {
  const typo = data.products.find(x => x.id === 'tteokbokki');
  assert.equal(trendStats(typo).growth, null);
  const zeros = { eligible: true, channels: { web: { series: Array.from({length:24}, (_,i) => ({date:`${2024+Math.floor(i/12)}-${String(i%12+1).padStart(2,'0')}-01`, value:0})) } } };
  assert.equal(trendStats(zeros).growth, null);
  assert.equal(trendStats(zeros, 'news').current, null);
});

test('market-specific evidence does not equate absent data with no demand', () => {
  const jp = evidenceFor(data, profile);
  assert.equal(jp.cuisine.count, 1423);
  assert.equal(jp.region.value, 1);
  const sg = evidenceFor(data, {...profile, market:'싱가포르'});
  assert.equal(sg.cuisine, null);
  assert.match(sg.facts[2].text, /표본은 없습니다/);
  const missing = evidenceFor(data, {...profile, market:'존재하지않는시장'});
  assert.equal(missing.region, undefined);
  assert.match(missing.facts[1].text, /수요가 없다는 의미는 아닙니다/);
});

test('report profile, actual sources and mode survive Markdown export', () => {
  const r = createReport(data, profile);
  assert.equal(r.mode, 'evidence');
  assert.equal(r.evidence.length, 8);
  assert.equal(r.localization.length, 3);
  assert.equal(r.plan.length, 3);
  const md = reportMarkdown(r);
  assert.match(md, /테스트식품/);
  assert.match(md, /AI 미사용/);
  assert.match(md, /data\/google_trend/);
  assert.match(md, /102,582/);
  assert.ok(r.localization.some(x => x.hypothesis.includes('냉장 완제품')));
});

test('AI context contains ground facts, quality caveats and no raw reviews', () => {
  const c = ollamaContext(data, profile);
  assert.equal(c.profile.product, '김치');
  assert.equal(c.profile.goal, profile.goal);
  assert.deepEqual(c.evidence.map(e => e.id), ['E1','E2','E3','E4','E5','E6','E7','E8']);
  assert.ok(c.relatedSearches.every(x => !x.noise));
  assert.ok(JSON.stringify(c).length < 20000);
  assert.equal(c.reviews, undefined);
});

test('untrusted company names and generated HTML are escaped', () => {
  assert.equal(esc('<script>"x"</script>'), '&lt;script&gt;&quot;x&quot;&lt;/script&gt;');
  assert.equal(esc("a&b'"), 'a&amp;b&#39;');
});

test('snapshot totals are derived from unique canonical datasets', () => {
  assert.equal(data.recipes.count, 522517);
  assert.equal(data.ingredients.count, 39774);
  assert.equal(data.reviews.count, 102582);
  assert.equal(data.flavors.count, 10000);
  assert.equal(data.products.length, 9);
  assert.equal(data.trendFileCount, 148);
  for (const p of data.products) for (const c of Object.values(p.channels)) {
    for (const row of c.series) assert.ok(row.value >= 0 && row.value <= 100);
    for (const path of Object.values(c.sources)) assert.ok(path.startsWith('data/google_trend/'));
  }
});


test('Food.com product evidence uses joined reviews, not all platform reviews', () => {
  const e = evidenceFor(data, profile);
  assert.equal(e.food.reviewCount, 195);
  assert.equal(e.food.ratedCount, 184);
  assert.equal(e.food.meanRating, 4.65);
  assert.match(e.facts[5].text, /195건/);
  assert.match(e.facts[6].text, /29.2%/); // 57 easy/simple/quick mentions / 195 reviews
  const absent = evidenceFor(data, {...profile, product:'tteokbokki'});
  assert.equal(absent.food.reviewCount, 0);
  assert.equal(absent.food.meanRating, null);
  assert.match(absent.facts[5].text, /유효 평점이 없습니다/);
  assert.doesNotMatch(absent.facts[6].text, /NaN|Infinity/);
  const report = createReport(data, profile);
  assert.equal(report.analysis.food.reviewCount, 195);
  assert.equal(data.foodcom.count, 1401982);
  assert.equal(data.foodcom.quality.linkedReviewCount, 1401963);
  assert.equal(data.foodcom.quality.unmatchedReviewCount, 19);
});

test('AI export uses app branding, not engine name or model identifier', () => {
  const base = createReport(data, profile);
  const r = createReport(data, profile, base, 'private-model:4b');
  const markdown = reportMarkdown(r);
  assert.match(markdown, /FLAVO AI/);
  assert.doesNotMatch(markdown, /Ollama|private-model/i);
});
