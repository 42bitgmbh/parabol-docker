const {test} = require('node:test')
const assert = require('node:assert/strict')
const {build, phases} = require('./build.cjs')
const {version} = require('../../package.json')

test('all upstream phases run sequentially with the pinned package version', () => {
  const calls = []
  build((cmd, args, opts) => {
    calls.push(args)
    assert.equal(cmd, 'pnpm')
    assert.equal(opts.env.npm_package_version, version)
    return {status: 0}
  })
  assert.deepEqual(calls, phases)
  assert.equal(phases.length, 5)
  assert.ok(phases[3].includes('--env=noDeps=true'))
})

test('a failed compile stops later phases', () => {
  let calls = 0
  assert.throws(() => build(() => { calls++; return {status: 1} }), /Build phase failed/)
  assert.equal(calls, 1)
})

test('a spawn failure is not silently ignored', () => {
  assert.throws(() => build(() => ({error: Error('cannot spawn')})), /cannot spawn/)
})
