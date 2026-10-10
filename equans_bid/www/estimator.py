import frappe

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/estimator"
		raise frappe.Redirect
	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()  # persist the new CSRF token for this session
	context.boot = {"csrf_token": csrf_token, "site_name": frappe.local.site, "user": frappe.session.user}
	return context
