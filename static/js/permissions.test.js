import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
    DELEGATION_PERMISSION_CATALOG,
    getUserPermissionUnion,
    tabVisibleForUser,
    userHasAnyPermission,
    userHasPermission,
} from "./permissions.js";

const catalog = DELEGATION_PERMISSION_CATALOG;

describe("userHasPermission", () => {
    it("denies when no user", () => {
        assert.equal(userHasPermission(null, "emails", "example.com"), false);
    });

    it("allows admin for any permission", () => {
        const admin = { is_admin: true, domain_grants: {} };
        assert.equal(userHasPermission(admin, "spam", "example.com"), true);
    });

    it("checks domain grants case-insensitively", () => {
        const user = {
            is_admin: false,
            domain_grants: { "example.com": ["emails"] },
        };
        assert.equal(userHasPermission(user, "emails", "Example.COM"), true);
        assert.equal(userHasPermission(user, "spam", "example.com"), false);
    });
});

describe("userHasAnyPermission", () => {
    it("returns true when one permission matches", () => {
        const user = {
            is_admin: false,
            domain_grants: { "a.test": ["dns"] },
        };
        assert.equal(userHasAnyPermission(user, ["dashboard", "dns"], "a.test"), true);
    });
});

describe("getUserPermissionUnion", () => {
    it("returns full catalog for admin", () => {
        const union = getUserPermissionUnion({ is_admin: true }, catalog);
        assert.deepEqual([...union].sort(), [...catalog].sort());
    });

    it("unions grants across domains", () => {
        const user = {
            is_admin: false,
            domain_grants: {
                "a.test": ["emails"],
                "b.test": ["spam", "emails"],
            },
        };
        const union = getUserPermissionUnion(user, catalog);
        assert.deepEqual([...union].sort(), ["emails", "spam"]);
    });
});

describe("tabVisibleForUser", () => {
    it("shows dashboard when user has dns-only access", () => {
        const user = {
            is_admin: false,
            domain_grants: { "x.test": ["dns"] },
        };
        assert.equal(tabVisibleForUser(user, "dashboard", catalog), true);
        assert.equal(tabVisibleForUser(user, "emails", catalog), false);
    });

    it("shows all tabs for admin", () => {
        const admin = { is_admin: true };
        assert.equal(tabVisibleForUser(admin, "spam", catalog), true);
    });

    it("allows settings tab without explicit grant", () => {
        const user = {
            is_admin: false,
            domain_grants: { "x.test": ["emails"] },
        };
        assert.equal(tabVisibleForUser(user, "settings", catalog), true);
    });
});
