// Run upstream compilation phases serially with one shared heap policy.
// Do not call `pnpm build`: its 8192 MB flag overrides NODE_OPTIONS.
const {spawnSync} = require('node:child_process')
const {version} = require('../../package.json')
const phases = [
  ['exec', 'node', 'scripts/generateGraphQLArtifacts.js'],
  ['exec', 'webpack', '--config', './scripts/webpack/prod.webworkers.config.js'],
  ['exec', 'webpack', '--config', './scripts/webpack/prod.client.config.js', '--env=minimize=false'],
  ['exec', 'webpack', '--config', './scripts/webpack/prod.servers.config.js', '--env=noDeps=true'],
  ['exec', 'webpack', '--config', './packages/mattermost-plugin/prod.webpack.config.js', '--env=minimize=false']
]
function build(run = spawnSync) {
  for (const args of phases) {
    const result = run('pnpm', args, {
      stdio: 'inherit', env: {...process.env, npm_package_version: version}
    })
    if (result.error) throw result.error
    if (result.status !== 0) throw new Error(`Build phase failed: ${args.join(' ')} (${result.status}/${result.signal})`)
  }
}
if (require.main === module) build()
module.exports = {build, phases}
