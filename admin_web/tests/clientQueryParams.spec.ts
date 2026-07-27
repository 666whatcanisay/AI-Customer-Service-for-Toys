import { describe, expect, it } from 'vitest'

import { omitBlankQueryParams } from '../src/api/client'

describe('omitBlankQueryParams', () => {
  it('does not send empty enum filters from an Admin all-filter selection', () => {
    expect(omitBlankQueryParams({
      store_code: '',
      product_id: '',
      review_status: '',
      page: 1,
      size: 20,
    })).toEqual({ page: 1, size: 20 })
  })

  it('preserves selected values and treats a completely blank filter as absent', () => {
    expect(omitBlankQueryParams({
      store_code: 'PDD-SM',
      evaluation_status: 'EVALUATED',
      page: 1,
    })).toEqual({ store_code: 'PDD-SM', evaluation_status: 'EVALUATED', page: 1 })
    expect(omitBlankQueryParams({ review_status: '', evaluation_status: undefined })).toBeUndefined()
  })
})
