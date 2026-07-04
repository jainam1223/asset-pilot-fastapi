# M6 — User Management

**Status:** Done
**Depends on:** M1, M2
**Complexity:** M

> Read `specs/00_CONTEXT.md` and `CLAUDE.md` first for shared stack/conventions/enums. This file is the complete spec for M6 only.

## Goal

IT-Admin user administration: list, create, change role, activate/deactivate (with the hard-block rule).

## Context recap (API §13)

- `GET /admin/users` — filters `role, is_active, search`(name/email) + manager name; paginated.
- `POST /admin/users` — body `{name, email, role}`; is_active=true; `manager_id` NOT set (self-service). NOTE: needs a `password_hash` — set the shared dev password so the created user can log in.
- `PATCH /admin/users/{id}/role` — body `{role}`.
- `PATCH /admin/users/{id}/deactivate` / `PATCH /admin/users/{id}/activate` — toggle is_active. **F4 (see `00_CONTEXT.md`): deactivate is hard-blocked (409) if the user owns any item (`current_owner_id`) or has any non-terminal request.**

## Preconditions

M1 (User model + password_hash), M2 (`require_it_admin`, `UserRepository`, `hash_password`).

## Scope checklist

- [x] Extend `UserRepository`: list with filters + manager-name join; `has_active_devices_or_requests(user_id)`.
- [x] `UserService`: list, create (hash a default password), change_role, activate, deactivate (raise `ConflictException` per F4).
- [x] Schemas: `UserListItem`, `CreateUserRequest`, `ChangeRoleRequest`.
- [x] Router `users.py` (prefix `/admin/users`) + register.
- [x] Email uniqueness →409. Tests incl. deactivate-blocked path.

## Out of scope

Login/refresh (M2); manager assignment (self-service, not an admin endpoint); password reset.

## Acceptance criteria

`POST /admin/users` creates a user that can log in via M2; `PATCH .../deactivate` on a user with an assigned device → 409 `CONFLICT`; on a user with none → 200 and `is_active=false`; `GET /admin/users?role=manager` filters correctly with manager names populated.

## Suggested session prompt

"Read `specs/M06_user_management.md` and `specs/00_CONTEXT.md` plus `CLAUDE.md`. Build IT-Admin user management (API §13): list/create/change-role/activate/deactivate, with the F4 hard-block on deactivation. New users get the shared dev password so they can log in. Verify acceptance criteria. Mark M6 Done in this spec file and in `_docs/IMPLEMENTATION_PLAN.md`."
