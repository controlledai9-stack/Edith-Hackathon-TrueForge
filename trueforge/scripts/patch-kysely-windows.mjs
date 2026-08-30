import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const target = path.resolve(here, '..', 'node_modules', 'kysely', 'dist', 'migration', 'file-migration-provider.js');
let source = await readFile(target, 'utf8');

if (!source.includes("from 'node:url'")) {
  source = source.replace(
    "import { isFunction, isObject } from '../util/object-utils.js';",
    "import { isFunction, isObject } from '../util/object-utils.js';\nimport { pathToFileURL } from 'node:url';",
  );
}
source = source.replace(
  'await import(/* webpackIgnore: true */ filePath);',
  'await import(/* webpackIgnore: true */ pathToFileURL(filePath).href);',
);
await writeFile(target, source, 'utf8');
console.log('Applied TrueForge Windows migration-loader compatibility patch.');

for (const extension of ['js', 'mjs']) {
  const coreTarget = path.resolve(here, '..', 'node_modules', '@truefoundry', 'trueforge-core', 'dist', 'core', 'llm', `VercelAILLM.${extension}`);
  let coreSource = await readFile(coreTarget, 'utf8');
  coreSource = coreSource.replace(
    'if (Array.isArray(rawThinking) && provider !== "alibaba") {',
    'if (Array.isArray(rawThinking) && provider !== "alibaba" && providerName !== "groq") {',
  );
  coreSource = coreSource.replace('maxRetries: 0', 'maxRetries: 3');
  await writeFile(coreTarget, coreSource, 'utf8');
}
console.log('Applied Groq reasoning-history and rate-limit retry compatibility patches.');
