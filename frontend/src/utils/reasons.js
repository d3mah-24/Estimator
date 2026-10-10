// Status reasons arrive as codes (reason_code + reason_args) and are translated here,
// mirroring equans_bid/reasons.py: a nested `detail` reason and a `family` code are
// translated before they are put into the template.

function parse(args) {
  if (!args) return {}
  if (typeof args === 'string') {
    try {
      return JSON.parse(args)
    } catch {
      return {}
    }
  }
  return args
}

export function reasonText(t, code, args, fallback = '') {
  if (!code) return fallback
  const values = { ...parse(args) }
  if (values.detail && typeof values.detail === 'object' && values.detail.code) {
    values.detail = reasonText(t, values.detail.code, values.detail.args)
  }
  if (values.family) values.family = t(`family.${values.family}`)
  return t(`reason.${code}`, values)
}

export function warningText(t, code, args) {
  return t(`warning.${code}`, parse(args))
}
