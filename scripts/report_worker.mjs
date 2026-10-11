// Canonical report calculations shared by server and UI; input is data, never code.
import {readFileSync} from 'node:fs';
import {createReport,ollamaContext} from '../src/engine.mjs';
import {registerCountries} from '../src/i18n.mjs';
const data=JSON.parse(readFileSync(new URL('../src/generated/data.json',import.meta.url)));
registerCountries(JSON.parse(readFileSync(new URL('../src/geo/world.json',import.meta.url))).countries);
let input='';for await(const chunk of process.stdin){input+=chunk;if(input.length>60000)throw new Error('Input too large');}
const request=JSON.parse(input);
const result=request.action==='context'?ollamaContext(data,request.profile):createReport(data,request.profile,request.ai||null,request.ai?'server-managed':null);
process.stdout.write(JSON.stringify(result));
