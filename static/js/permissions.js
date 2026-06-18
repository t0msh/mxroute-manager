/** Permission helpers for delegated access (pure, no DOM). */

export const DELEGATION_PERMISSION_CATALOG = [
    "dashboard",
    "emails",
    "forwarders",
    "spam",
    "dns",
];

export const TAB_REQUIRED_PERMISSION = {
    dashboard: "dashboard",
    domains: "dns",
    emails: "emails",
    forwarders: "forwarders",
    spam: "spam",
};

export function userHasPermission(currentUser, permission, domain) {
    if (!currentUser) return false;
    if (currentUser.is_admin) return true;
    const grants = currentUser.domain_grants || {};
    const domainKey = (domain || "").toLowerCase();
    return (grants[domainKey] || []).includes(permission);
}

export function userHasAnyPermission(currentUser, permissions, domain) {
    return permissions.some((permission) => userHasPermission(currentUser, permission, domain));
}

export function getUserPermissionUnion(currentUser, catalog = DELEGATION_PERMISSION_CATALOG) {
    if (!currentUser || currentUser.is_admin) {
        return new Set(catalog);
    }
    const union = new Set();
    Object.values(currentUser.domain_grants || {}).forEach((perms) => {
        perms.forEach((permission) => union.add(permission));
    });
    return union;
}

export function tabVisibleForUser(currentUser, tab, catalog = DELEGATION_PERMISSION_CATALOG) {
    if (!currentUser || currentUser.is_admin) return true;
    if (tab === "dashboard") {
        const union = getUserPermissionUnion(currentUser, catalog);
        return union.has("dashboard") || union.has("dns");
    }
    const required = TAB_REQUIRED_PERMISSION[tab];
    if (!required) return true;
    return getUserPermissionUnion(currentUser, catalog).has(required);
}
