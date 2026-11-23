// Match API province names to the names in the loaded GeoJSON, including fallback maps.
export function provinceKey(name) {
  return String(name ?? '').trim().replace(/(?:壮族自治区|回族自治区|维吾尔自治区|自治区|特别行政区|省|市)$/u, '')
}

export function buildProvinceLookup(geoJson) {
  const lookup = Object.create(null)
  for (const feature of geoJson?.features || []) {
    const { name, fullname } = feature.properties || {}
    if (!name) continue
    for (const alias of [name, fullname]) {
      if (alias) lookup[provinceKey(alias)] = name
    }
  }
  return lookup
}

export function normalizeEmploymentRegions(rows, lookup) {
  const counts = new Map()
  for (const row of rows || []) {
    const name = lookup[provinceKey(row?.name)]
    if (!name || row?.value == null || row.value === '') continue
    const value = Number(row.value)
    if (!Number.isFinite(value) || value < 0) continue
    counts.set(name, (counts.get(name) || 0) + value)
  }
  return [...counts].map(([name, value]) => ({ name, value }))
}

export function employmentRegionTooltip(params) {
  const name = String(params?.name ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))
  const value = params?.data?.value
  return name + '<br/>' + (typeof value === 'number' && Number.isFinite(value)
    ? '就业人数：' + value + '人' : '暂无就业地区记录')
}
