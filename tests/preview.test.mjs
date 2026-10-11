import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createReport} from '../src/engine.mjs';
import {createViews} from '../src/views.mjs';
import {setLanguage,registerCountries} from '../src/i18n.mjs';
const data=JSON.parse(readFileSync(new URL('../src/generated/data.json',import.meta.url)));
const geography=JSON.parse(readFileSync(new URL('../src/geo/world.json',import.meta.url)));
registerCountries(geography.countries);
function render(publicPreview,language){
  setLanguage(language);
  const report=createReport(data,{company:'Public sample',product:'kimchi',market:'일본',format:'냉장 완제품',channel:'현지 아시안 마켓',language});
  const main={innerHTML:''},previous=globalThis.document;
  globalThis.document={querySelector:selector=>{assert.equal(selector,'#main');return main;}};
  try{createViews({data,geography,state:{report},publicPreview}).render('reports');return main.innerHTML;}
  finally{globalThis.document=previous;setLanguage('ko');}
}
test('public report is labelled, keeps sources, and cannot imply server review or AI availability',()=>{
  for(const language of ['ko','en']){
    const html=render(true,language);
    assert.match(html,/preview-report-note/);
    assert.match(html,/evidence-E6/);
    assert.match(html,/195/);
    assert.match(html,/data-action="download-report"/);
    assert.doesNotMatch(html,/data-review-report|href="#ask"|evidence-receipt|FLAVO AI/);
  }
});
test('authenticated server report retains review and Q&A controls',()=>{
  const html=render(false,'en');
  assert.match(html,/data-review-report/);
  assert.match(html,/href="#ask"/);
  assert.match(html,/evidence-receipt/);
  assert.doesNotMatch(html,/preview-report-note/);
});
