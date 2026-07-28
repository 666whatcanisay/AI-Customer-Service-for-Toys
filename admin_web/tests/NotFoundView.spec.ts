import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import NotFoundView from '../src/views/NotFoundView.vue'
import { router } from '../src/router'

describe('NotFoundView', () => {
  it('shows a clear Chinese fallback instead of an empty unknown route', () => {
    const wrapper = mount(NotFoundView, {
      global: { stubs: { RouterLink: { props: ['to'], template: '<a><slot /></a>' } } },
    })

    expect(wrapper.text()).toContain('没有找到这个页面')
    expect(wrapper.text()).toContain('返回运营概览')
    expect(router.resolve('/not-a-route').name).toBe('not-found')
  })
})
