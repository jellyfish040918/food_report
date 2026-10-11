// Preserve a public-site feature selection through sign-in without accepting redirect URLs.
const FEATURES = new Set(['ask', 'new-report', 'workspace', 'login', 'register']);
export function startupEntry(search) {
  const params = new URLSearchParams(search);
  return {view: FEATURES.has(params.get('start')) ? params.get('start') : '', language: ['ko','en'].includes(params.get('lang')) ? params.get('lang') : ''};
}
export function entryHash(view) {
  return view === 'new-report' ? '#reports' : ['ask','workspace'].includes(view) ? `#${view}` : '#dashboard';
}
