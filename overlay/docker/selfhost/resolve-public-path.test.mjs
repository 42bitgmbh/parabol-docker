import assert from 'node:assert/strict'
import {test} from 'node:test'
import {resolvePublicPath} from '../../packages/server/resolvePublicPath.ts'

const defaults = {appOrigin: 'https://parabol.example.test', isProduction: true}

test('STATIC_ASSET_PATH selects same-origin assets without changing appOrigin', () => {
  assert.equal(resolvePublicPath({...defaults, staticAssetPath: '/static/'}), '/static/')
})

test('STATIC_ASSET_PATH rejects URLs and malformed paths', () => {
  for (const value of ['https://assets.example.test/static/', '//assets.example.test/', 'static/', '/static']) {
    assert.throws(() => resolvePublicPath({...defaults, staticAssetPath: value}), /STATIC_ASSET_PATH/)
  }
})

test('canonical origin and CDN behavior remain unchanged', () => {
  assert.equal(resolvePublicPath(defaults), 'https://parabol.example.test/static/')
  assert.equal(resolvePublicPath({...defaults, cdnBaseUrl: 'https://cdn.example.test'}), 'https://cdn.example.test/build/')
  assert.equal(resolvePublicPath({...defaults, cdnBaseUrl: 'https://cdn.example.test', proxyCdn: 'true'}), '/build/')
})
